import os
import asyncio
import aiohttp
import math
import json
import time
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Tunables
WINDOW_BLOCKS = int(os.getenv("WINDOW_BLOCKS", "20"))
BASELINE_EMA_ALPHA = float(os.getenv("BASELINE_EMA_ALPHA", "0.1"))
ZSCORE_THRESHOLD = float(os.getenv("ZSCORE_THRESHOLD", "3.0"))
RATIO_THRESHOLD = float(os.getenv("RATIO_THRESHOLD", "2.0"))
MIN_COUNT = int(os.getenv("MIN_COUNT", "20"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))
VALUE_ETH_THRESHOLD = float(os.getenv("VALUE_ETH_THRESHOLD", "10.0"))

STATE_PATH = Path("state.json")

getcontext().prec = 36  # high precision for ETH value computations

if not ETHERSCAN_API_KEY:
    raise SystemExit("Missing ETHERSCAN_API_KEY in environment")
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment")

ETHERSCAN_BASE = "https://api.etherscan.io/api"
TELEGRAM_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def eth_from_wei(hex_value: str) -> Decimal:
    # hex string like '0x1234...'
    wei = int(hex_value, 16)
    return Decimal(wei) / Decimal(10**18)

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Initialize EMA mean/var for baseline; unbiased defaults
    return {
        "ema_mean": None,
        "ema_var": None,
        "last_alert_block": None
    }

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def ema_update(prev, x, alpha):
    return (alpha * x) + ((1 - alpha) * prev) if prev is not None else x

async def telegram_send(session: aiohttp.ClientSession, text: str):
    url = f"{TELEGRAM_BASE}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status != 200:
            body = await r.text()
            print(f"[telegram] send error {r.status}: {body}")

async def etherscan_get_block_number(session: aiohttp.ClientSession) -> int:
    params = {"module": "proxy", "action": "eth_blockNumber", "apikey": ETHERSCAN_API_KEY}
    async with session.get(ETHERSCAN_BASE, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
        data = await r.json()
        return int(data["result"], 16)

async def etherscan_get_block_by_number(session: aiohttp.ClientSession, num: int) -> dict:
    # boolean=true to include full tx objects
    params = {
        "module": "proxy",
        "action": "eth_getBlockByNumber",
        "tag": hex(num),
        "boolean": "true",
        "apikey": ETHERSCAN_API_KEY,
    }
    async with session.get(ETHERSCAN_BASE, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
        data = await r.json()
        return data["result"]

async def count_high_value_in_blocks(session: aiohttp.ClientSession, start_block: int, end_block: int) -> int:
    # inclusive range [start_block, end_block]
    threshold = Decimal(str(VALUE_ETH_THRESHOLD))
    total = 0
    for b in range(start_block, end_block + 1):
        block = await etherscan_get_block_by_number(session, b)
        txs = block.get("transactions", [])
        hi = 0
        for tx in txs:
            v = eth_from_wei(tx["value"])
            if v >= threshold:
                hi += 1
        total += hi
    return total

def format_alert(current, mean, std, start_block, end_block, ratio, z):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    return (
        f"🚨 <b>Всплеск дорогих транзакций в Ethereum</b>\n"
        f"Время: {ts}\n"
        f"Окно: блоки [{start_block}…{end_block}] (n={end_block - start_block + 1})\n"
        f"Порог транзакции: ≥ {VALUE_ETH_THRESHOLD:g} ETH\n"
        f"Текущее значение: <b>{current}</b>\n"
        f"База (EMA среднее): {mean:.2f} | std≈ {std:.2f}\n"
        f"Отношение к базе: {ratio:.2f}× | z≈ {z:.2f}\n"
        f"#ETH #onchain #alerts"
    )

async def monitor():
    state = load_state()
    last_checked_block = None

    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                tip = await etherscan_get_block_number(session)
                if last_checked_block is None:
                    last_checked_block = tip - 1  # start just before tip to fill window quickly

                # Advance window to the latest known block
                # We compute counts over last WINDOW_BLOCKS blocks ending at tip
                start_block = max(0, tip - WINDOW_BLOCKS + 1)
                end_block = tip

                current_hi = await count_high_value_in_blocks(session, start_block, end_block)

                # Update baseline EMA mean/variance (Welford-like via EMA)
                ema_mean = state.get("ema_mean")
                ema_var = state.get("ema_var")  # EMA of squared deviation (approx variance)
                alpha = BASELINE_EMA_ALPHA

                if ema_mean is None:
                    ema_mean = float(current_hi)
                    ema_var = 0.0  # start with zero variance
                else:
                    # Update EMA mean and EMA of squared deviation
                    prev_mean = ema_mean
                    ema_mean = ema_update(prev_mean, float(current_hi), alpha)
                    # EMA variance approx: ema_var = (1-alpha)*(ema_var) + alpha*(x - ema_mean)^2
                    ema_var = (1 - alpha) * (ema_var if ema_var is not None else 0.0) + alpha * ((float(current_hi) - ema_mean) ** 2)

                std = math.sqrt(max(ema_var, 0.0))
                ratio = (float(current_hi) / ema_mean) if ema_mean > 0 else float('inf')
                z = ((float(current_hi) - ema_mean) / std) if std > 1e-9 else float('inf')

                state["ema_mean"] = ema_mean
                state["ema_var"] = ema_var
                save_state(state)

                # Decide alert
                should_alert = (
                    (float(current_hi) >= ema_mean + ZSCORE_THRESHOLD * std) or
                    (float(current_hi) >= ema_mean * RATIO_THRESHOLD)
                ) and (int(current_hi) >= MIN_COUNT)

                # Avoid spamming the same tip repeatedly
                if should_alert:
                    last_alert_block = state.get("last_alert_block")
                    if last_alert_block != end_block:
                        msg = format_alert(current_hi, ema_mean, std, start_block, end_block, ratio, z)
                        await telegram_send(session, msg)
                        state["last_alert_block"] = end_block
                        save_state(state)

                # Logs to stdout
                print(f"[{time.strftime('%H:%M:%S')}] window=[{start_block}..{end_block}] current_hi={current_hi} mean={ema_mean:.2f} std={std:.2f} ratio={ratio:.2f} z={z:.2f} alert={should_alert}")

                last_checked_block = end_block
            except Exception as e:
                print(f"Error: {e}")

            await asyncio.sleep(POLL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        print("Stopped by user.")
