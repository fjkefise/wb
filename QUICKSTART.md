# ⚡ QUICK START — Быстрый старт за 5 минут

## 1️⃣ Установка (один раз)

```bash
# Откройте терминал в папке проекта
cd /home/semyon/wb

# Создайте виртуальное окружение
python -m venv .venv

# Активируйте (Linux/Mac):
source .venv/bin/activate
# или на Windows:
# .venv\Scripts\activate

# Установите зависимости
pip install -r requirements.txt
```

## 2️⃣ Настройка (один раз)

```bash
# Создайте .env файл
cp .env.example .env

# Добавьте ваш токен и chat_id:
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# TELEGRAM_CHAT_ID=123456789
```

```bash
# Создайте config.yaml
cp config.yaml.example config.yaml
# Отредактируйте по вкусу (цены, интервалы)
```

## 3️⃣ Запуск

**Linux/Mac:**
```bash
python main.py bot
```

**Windows:** двойной клик на `run_bot.bat`

## 4️⃣ Управление в Telegram

Откройте чат с вашим ботом и нажимайте кнопки:
- 🔍 **Проверить все** — проверка сейчас
- ♾ **Мониторинг всех** — вкл постоянный мониторинг
- 🎛 **Выбрать модели** — выбрать конкретные модели
- 📊 **Статус** — смотреть, что происходит
- 🧾 **Последние цены** — последние находки
- ⛔ **Остановить** — выключить мониторинг

---

## 🆘 Если не работает

**Telegram не отправляет уведомления:**
```bash
python main.py test-telegram
```

**Нужен chat_id:**
```bash
python - <<'PY'
import requests
token = '123456:ABC-DEF...'  # ваш токен из .env
r = requests.get(f'https://api.telegram.org/bot{token}/getUpdates').json()
for u in r.get('result', []):
    msg = u.get('message', {})
    print(f"chat_id: {msg.get('chat', {}).get('id')}")
PY
```

**Тесты:**
```bash
pytest -q
```

---

## 📋 Команды

```bash
python main.py bot              # Запустить Telegram-бот
python main.py run-once         # Проверить один раз
python main.py monitor          # Мониторинг без бота (фоновый)
python main.py test-telegram    # Тест отправки Telegram
python main.py show-last station_midi  # Показать последние цены для модели
```

---

## 📚 Документация

- **USAGE.md** — пошаговые инструкции
- **BOT_GUIDE.md** — гайд по Telegram-боту
- **README_BOT.md** — полная документация
- **PROJECT_SUMMARY.md** — обзор всего проекта

---

## 🎯 Что дальше?

1. Включите бота на своём компьютере
2. Нажмите ♾ **Мониторинг всех** или выберите модели
3. Получайте Telegram-уведомления о хороших ценах
4. Управляйте через кнопки в Telegram

**Вот и всё!** 🚀
