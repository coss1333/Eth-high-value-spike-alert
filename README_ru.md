# ETH High-Value Spike Alert (Ethereum, >10 ETH)

Скрипт мониторит сеть Ethereum через публичный Proxy API Etherscan и отправляет сигнал в телеграм‑чат,
когда **интенсивность дорогих транзакций** (каждая > заданного порога ETH, по умолчанию 10 ETH)
**резко возрастает** относительно базового среднего уровня сети.

## Что считается «всплеском»
В текущем окне последних `WINDOW_BLOCKS` блоков мы считаем:
- `current_rate`: количество транзакций с `value >= VALUE_ETH_THRESHOLD` (по умолчанию 10 ETH)
- фоновую «базу» — экспоненциальное скользящее среднее (`EMA`) и скользящее стандартное отклонение.
- Срабатывание сигнала происходит, если одновременно выполняется хотя бы одно из условий:
  - `current_rate >= mean + ZSCORE_THRESHOLD * std` (z‑score), **или**
  - `current_rate >= mean * RATIO_THRESHOLD` (мультипликатор),
  - **и** `current_rate >= MIN_COUNT` (чтобы избежать «шумовых» срабатываний).

Параметры настраиваются через `.env`.

## Что нужно подготовить
1) **Etherscan API Key** — бесплатно: https://etherscan.io/myapikey
2) **Телеграм‑бот** — у BotFather создать токен, получить `TELEGRAM_BOT_TOKEN`.
3) Узнать/получить `TELEGRAM_CHAT_ID` (например, написав боту и вызвав `https://api.telegram.org/bot<TOKEN>/getUpdates`).

## Установка
```bash
# 1) Распакуйте проект и перейдите в папку
cd eth_high_value_spike_alert

# 2) Создайте файл .env из шаблона
cp .env.example .env
# откройте .env и заполните ETHERSCAN_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# при желании подредактируйте параметры (порог ETH, окно, пороги сигналов, период опроса)

# 3) Установите зависимости (желательно в виртуальном окружении)
python -m venv .venv && . .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
```

## Запуск
```bash
python eth_high_value_spike_bot.py
```

Скрипт напечатает базовые логи и отправит сообщение в телеграм‑чат при обнаружении всплеска.

## Как это работает (коротко)
- Раз в `POLL_SECONDS` секунд скрипт через Etherscan Proxy API запрашивает:
  - `eth_blockNumber` — номер последнего блока,
  - `eth_getBlockByNumber` (с `boolean=true`) — полные транзакции блока.
- Вычисляет количество «дорогих» транзакций (>= `VALUE_ETH_THRESHOLD` ETH) в последних `WINDOW_BLOCKS` блоках.
- Поддерживает базовую статистику (EMA среднего и EMA дисперсии) в локальном файле `state.json`
  для устойчивости между перезапусками.
- При превышении порогов — шлёт телеграм‑алерт.

## Тюнинг параметров
В `.env` можно подбирать:
- `VALUE_ETH_THRESHOLD` — порог «дорогой» транзакции, по умолчанию 10 ETH.
- `WINDOW_BLOCKS` — ширина «текущего окна» (20 блоков ~ 4‑5 минут).
- `BASELINE_EMA_ALPHA` — «инертность» базы: 0.05–0.2 обычно адекватно.
- `ZSCORE_THRESHOLD`, `RATIO_THRESHOLD` — чувствительность к всплескам.
- `MIN_COUNT` — минимальный объём, исключает мелкие колебания.
- `POLL_SECONDS` — частота опроса (баланс между задержкой и лимитами API).

## Замечания и лимиты
- Нужен ключ Etherscan; на бесплатном тарифе есть ограничения по RPS.
- Проект ориентирован на оперативность в пределах минут. Для «почти real‑time»
  используйте WebSocket‑узел (Infura/Alchemy) — это можно добавить, но здесь
  используется бесплатный Proxy API Etherscan для простоты.
- Если телеграм‑сообщения не приходят — проверьте `TELEGRAM_CHAT_ID`, права бота в чате,
  и логи скрипта.

## Запуск как сервис (опционально, Linux)
Создайте `eth-high-spike.service` в `/etc/systemd/system/`:
```ini
[Unit]
Description=ETH High-Value Spike Alert
After=network.target

[Service]
WorkingDirectory=/PATH/TO/eth_high_value_spike_alert
ExecStart=/PATH/TO/eth_high_value_spike_alert/.venv/bin/python eth_high_value_spike_bot.py
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
Затем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eth-high-spike.service
journalctl -u eth-high-spike.service -f
```
