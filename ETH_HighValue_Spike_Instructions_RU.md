# Пошаговая инструкция: ETH High‑Value Spike Alert (всплески транзакций ≥ 10 ETH)

Эта инструкция поможет быстро запустить бота, который отправляет сигнал в Telegram,
когда интенсивность «дорогих» транзакций (каждая ≥ заданного порога ETH) резко растёт
по сравнению с базовым уровнем сети.

---

## 1) Что понадобится
1. **Ключ Etherscan API** — получите бесплатно: https://etherscan.io/myapikey
2. **Телеграм‑бот** — создайте у BotFather и получите `TELEGRAM_BOT_TOKEN`.
3. **Идентификатор чата** (`TELEGRAM_CHAT_ID`) — добавьте бота в нужный чат/группу и узнайте chat_id,
   отправив боту сообщение и вызвав в браузере:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` (замените `<TOKEN>` на ваш токен).

---

## 2) Скачайте проект
Скачайте ZIP‑архив проекта по ссылке из чата и распакуйте, например, в папку `eth_high_value_spike_alert`.

---

## 3) Установите зависимости
Рекомендуется использовать виртуальное окружение Python 3.10+.

**Linux/macOS:**
```bash
cd eth_high_value_spike_alert
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
cd eth_high_value_spike_alert
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 4) Настройте переменные окружения
Создайте файл `.env` из шаблона и заполните ключи/параметры.

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

Отредактируйте `.env` и укажите:
- `ETHERSCAN_API_KEY` — ваш ключ Etherscan
- `TELEGRAM_BOT_TOKEN` — токен бота от BotFather
- `TELEGRAM_CHAT_ID` — ID чата/группы, куда слать сигналы

При необходимости настройте параметры чувствительности:
- `VALUE_ETH_THRESHOLD` — порог «дорогой» транзакции (ETH), по умолчанию **10.0**
- `WINDOW_BLOCKS` — окно последних блоков для текущей интенсивности, по умолчанию **20**
- `BASELINE_EMA_ALPHA` — сглаживание базовой EMA, по умолчанию **0.1**
- `ZSCORE_THRESHOLD` — z‑порог для всплеска, по умолчанию **3.0**
- `RATIO_THRESHOLD` — мультипликатор к базе, по умолчанию **2.0**
- `MIN_COUNT` — минимальное число «дорогих» транзакций в окне, по умолчанию **20**
- `POLL_SECONDS` — период опроса в секундах, по умолчанию **15**

---

## 5) Запуск
```bash
python eth_high_value_spike_bot.py
```
Скрипт будет регулярно:
- узнавать номер последнего блока через Etherscan Proxy API,
- вытягивать полный список транзакций по последним блокам,
- считать количество транзакций ≥ `VALUE_ETH_THRESHOLD` ETH в текущем окне,
- поддерживать **базовую EMA** среднего и дисперсии,
- отправлять сигнал в Telegram при всплеске (по z‑score и/или по кратности), если объём ≥ `MIN_COUNT`.

---

## 6) Проверка работы
- В консоли должны появляться логи с окном блоков, текущим значением, базой и флагом `alert=True/False`.
- В Telegram‑чате появится сообщение при срабатывании условий.
- Если сообщений нет, проверьте `TELEGRAM_CHAT_ID`, что бот добавлен в чат и не ограничен правами.

---

## 7) Тюнинг/рекомендации
- Уменьшайте `BASELINE_EMA_ALPHA`, если хотите более «инертную» базу (меньше ложных всплесков).
- Увеличивайте `MIN_COUNT` при частых флуктуациях.
- Балансируйте `ZSCORE_THRESHOLD` и `RATIO_THRESHOLD` (например, 2.5 и 1.8) — зависит от рынка/времени.

---

## 8) Автозапуск как сервис (Linux, опционально)
Создайте `/etc/systemd/system/eth-high-spike.service`:
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

Команды:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eth-high-spike.service
journalctl -u eth-high-spike.service -f
```

---

## 9) Частые проблемы
- **429 / лимиты API**: увеличьте `POLL_SECONDS` или уменьшите `WINDOW_BLOCKS`.
- **Нет сообщений в чат**: проверьте, что бот состоит в чате и `TELEGRAM_CHAT_ID` верный.
- **Ошибки сети**: скрипт перехватывает исключения и продолжает попытки опроса.
- **Зависимости**: убедитесь, что установлены из `requirements.txt` в активном виртуальном окружении.

Готово! Если нужен вариант с WebSocket‑нодой (Infura/Alchemy) для почти real‑time — могу добавить.
