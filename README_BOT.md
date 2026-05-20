# Wildberries Yandex Station Price Monitor

Lightweight Python project to monitor prices of Yandex Stations on Wildberries, store price history and send Telegram alerts on interesting price drops.

**New!** Manage monitoring from your laptop via Telegram bot with long polling — no cloud required.

## Quick Start

### 1. Clone & Setup Environment

```bash
cd /home/semyon/wb
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Telegram

1. Open Telegram and write to `@BotFather`
2. Run `/newbot`, choose a name and username
3. Copy the token (e.g., `123456:ABC-DEF...`)
4. Open your new bot link and send it any message
5. Get your `chat_id`:

```bash
python - <<'PY'
import requests
token = '123456:ABC-DEF...'  # Replace with your token
r = requests.get(f'https://api.telegram.org/bot{token}/getUpdates', timeout=10).json()
for u in r.get('result', []):
    msg = u.get('message', {})
    print(f"chat_id: {msg.get('chat', {}).get('id')}")
PY
```

6. Create `.env` in project root:

```bash
cp .env.example .env
# Edit .env with your token and chat_id:
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# TELEGRAM_CHAT_ID=123456789
```

### 3. Configure Models & Price Thresholds

```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your price thresholds, search queries, etc.
```

### 4. Run

**On Linux/Mac (recommended):**
```bash
python main.py bot
```
Bot runs with long polling — you control monitoring via Telegram buttons.

**Single check:**
```bash
python main.py run-once
```

**Continuous monitoring (headless mode):**
```bash
python main.py monitor
```

**Test Telegram:**
```bash
python main.py test-telegram
```

**Show last prices for a model:**
```bash
python main.py show-last station_midi
```

---

## Telegram Bot Control (Recommended for Laptop Use)

Start bot in terminal:
```bash
python main.py bot
```

Then control from Telegram with buttons:

### Main Menu
- **🔍 Проверить все** — Run single check for all models
- **♾ Мониторинг всех** — Start continuous monitoring of all models
- **🎛 Выбрать модели** — Select specific models to monitor
- **📊 Статус** — Show monitoring status and last cycle results
- **🧾 Последние цены** — Show last found products
- **⛔ Остановить** — Stop monitoring (bot keeps running)

### Model Selection
- Toggle each model on/off with checkboxes
- **🔍 Проверить выбранные** — Run check for selected models only
- **♾ Мониторить выбранные** — Monitor only selected models
- **⬅️ Назад** — Return to main menu

### Key Features
- Long polling (no webhook, works on laptop with dynamic IP)
- One monitor per bot (no conflicting runs)
- Auto-stop on Ctrl+C or terminal close
- Telegram notifies you of good prices while bot runs
- Only your chat_id can control the bot

### How to Keep Bot Running
**On Linux/Mac:**
- Use `screen` or `tmux`:
  ```bash
  screen -S wb_monitor
  # or
  tmux new-session -s wb_monitor
  # Inside screen/tmux:
  python main.py bot
  # Detach with Ctrl+A D (screen) or Ctrl+B D (tmux)
  # Reattach: screen -r wb_monitor  or  tmux attach-session -t wb_monitor
  ```

- Use `systemd` (see systemd section below)

**On Windows:**
- Double-click `run_bot.bat` in the project folder
- Or use Windows Task Scheduler to auto-start

### What Happens If...

**Bot window closes / laptop shuts down:**
- Monitoring stops immediately
- No further checks or Telegram messages
- When you restart: old data is saved in `db.sqlite3`, bot starts fresh

**Laptop goes to sleep:**
- Monitoring pauses during sleep
- Resumes when laptop wakes (no interruption to bot)

**Network disconnects:**
- Bot will keep trying to reconnect with backoff
- Telegram updates will queue and arrive when network returns

---

## Installation & Running on Servers

### Server mode

For a long-running server process:

```bash
python main.py monitor
```

The default server-friendly settings are in `config.yaml`:
- `interval_seconds: 900` — check about once every 15 minutes
- `cycle_jitter_seconds: 300` — add up to 5 minutes of random delay between cycles
- `request_delay_seconds` and `request_jitter_seconds` — slow down requests inside a cycle
- `search_pages` and `search_sorts` — broaden coverage without hammering WB
- `max_requests_per_cycle` and `max_requests_per_hour` — hard request caps

### On Linux (with systemd)

1. Copy project to `/opt/wb-price-monitor`
2. Create user: `sudo useradd -r wb-monitor`
3. Set permissions: `sudo chown -R wb-monitor /opt/wb-price-monitor`
4. Copy service file:

```bash
sudo cp examples/wb-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wb-monitor
sudo systemctl start wb-monitor
```

Check logs:
```bash
sudo journalctl -u wb-monitor -f
```

### With Docker

```bash
docker-compose up -d
docker-compose logs -f
```

Or manually:
```bash
docker build -t wb-monitor .
docker run -d \
  --name wb-monitor \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e TELEGRAM_CHAT_ID="your_chat_id" \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/db.sqlite3:/app/db.sqlite3 \
  wb-monitor
```

---

## Configuration

`config.yaml` defines:
- **Models**: name, search queries per model
- **Prices**: `interesting_price`, `max_reasonable_price`
- **Thresholds**: drop % from previous, 24h median, 7d median
- **Interval**: check frequency (seconds)
- **Rate limits**: max requests per cycle/hour

Example model config:
```yaml
models:
  station_midi:
    name: "Яндекс Станция Миди"
    queries:
      - "Яндекс Станция Миди"
      - "Яндекс Станция Midi"
    interesting_price: 9850        # Alert if price is lower than this
    max_reasonable_price: 9850     # Only alert drops if price is lower than this
    sharp_drop_from_previous_pct: 15
    drop_from_24h_median_pct: 20
    drop_from_7d_median_pct: 25
```

## Data Storage

SQLite database (`db.sqlite3`) stores:
- **products**: product id, name, brand, seller
- **price_snapshots**: price history with timestamps
- **notifications**: sent alerts with timestamps

## Notification Rules

Alert is sent if:
1. **NEW_CHEAP_PRODUCT**: First found product with price < interesting_price
2. **CHEAP_PRICE**: Current price < interesting_price
3. **SHARP_DROP_FROM_PREVIOUS**: Drop ≥ threshold % AND price < max_reasonable_price
4. **DROP_FROM_24H_MEDIAN**: Drop from 24h median AND price < max_reasonable_price
5. **DROP_FROM_7D_MEDIAN**: Drop from 7d median AND price < max_reasonable_price

Anti-spam:
- Max 1 alert per product per cycle
- Same alert type not repeated within 6 hours (unless price drops 3%+)
- Different alert types can fire independently

## Testing

```bash
pytest -q
```

Tests cover:
- Product-to-model matching (Лайт vs Лайт 2, Мини vs Мини с часами, etc.)
- Accessory filtering
- Price drop calculation
- Anti-spam logic

## Troubleshooting

### Telegram not sending

Check:
1. `.env` has valid token and chat_id
2. Privacy Mode is disabled on the bot (via @BotFather)
3. Test with `python main.py test-telegram`
4. Check error logs for 401 (invalid token), 403 (chat blocked), 429 (rate limited)

### Bot doesn't respond to button clicks

1. Make sure chat_id in `.env` matches your Telegram user chat_id
2. Check console for "Message from unauthorized user"
3. Restart bot: Ctrl+C and `python main.py bot` again

### WB API changes

If prices don't parse:
1. Check [src/wb_price_monitor/wb_client.py](src/wb_price_monitor/wb_client.py) — parsing logic is isolated there
2. Run `python main.py run-once` and check console for parsing errors
3. Update selectors in `wb_client.py` if WB changed HTML structure

### Products not matching models

Check matching logic in [src/wb_price_monitor/matcher.py](src/wb_price_monitor/matcher.py):
- Run tests: `pytest -q`
- Add test cases for edge cases

## Project Structure

```
.
├── main.py                         # CLI entry point (new)
├── run_bot.bat                     # Windows bot launcher (new)
├── config.yaml.example             # Config template
├── .env.example                    # Env vars template
├── requirements.txt                # Dependencies
├── Dockerfile                      # Docker build
├── docker-compose.yml              # Docker compose
├── db.sqlite3                      # SQLite database (auto-created)
├── wb_monitor.log                  # Bot log file
├── src/
│   └── wb_price_monitor/
│       ├── config.py               # Config loader
│       ├── wb_client.py            # Wildberries API client (isolated)
│       ├── matcher.py              # Product-to-model matching
│       ├── db.py                   # SQLite layer
│       ├── notify.py               # Telegram sender
│       ├── logic.py                # Monitoring cycle
│       ├── monitor_manager.py      # Background monitor control (new)
│       └── telegram_bot.py         # Telegram bot with long polling (new)
├── tests/
│   ├── conftest.py                 # pytest config
│   ├── test_matcher.py             # Matching tests
│   ├── test_filter_and_price.py    # Filter & price tests
│   └── test_notifications.py       # Notification tests
└── examples/
    └── wb-monitor.service          # systemd unit file
```

## Notes

- WB client uses respectful rate limiting: configurable delay/jitter between requests, per-cycle/hour caps, caching, and backoff on 429/5xx
- Be careful with `interval_seconds` — too low will get you blocked
- Prices use **median**, not average, to handle outliers better
- All WB parsing is in one module — update it there if WB changes format
- Telegram bot uses long polling (no webhook) — perfect for laptop use

## License

MIT
