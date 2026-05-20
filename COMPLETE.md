# ✅ ПРОЕКТ ЗАВЕРШЁН — WB Price Monitor с Telegram-ботом

## Что было сделано

### 🎯 Основной проект (исходный)
✅ Парсер Wildberries с рейт-лимитами
✅ SQLite база с историей цен
✅ 10 моделей Яндекс Станций с раздельными запросами
✅ Фильтрация аксессуаров
✅ Расчёт динамики (медиана 24ч/7д, минимумы, падения)
✅ 5 правил алертов с приоритетами
✅ Антиспам (6 часов, 3% прогресс)
✅ Telegram-отправка уведомлений

### 🆕 Telegram-бот (новое)
✅ Long polling (работает на ноутбуке)
✅ Фоновый мониторинг в отдельном потоке
✅ Главное меню с 6 кнопками
✅ Выбор моделей с toggle (все 10 моделей)
✅ Статус с полной информацией
✅ Список последних найденных цен
✅ Команды (/start, /status, /stop, /run_all, /monitor_all)
✅ Защита по TELEGRAM_CHAT_ID
✅ Логирование в консоль и файл
✅ Windows batch-файл для запуска

## Файлы проекта

### 🎯 Основные (для запуска)
- `main.py` — точка входа (режимы: bot, run-once, monitor)
- `run_bot.bat` — Windows батник для бота
- `.env` — Telegram токен и chat_id (создать из .env.example)
- `config.yaml` — настройки моделей и цен (создать из config.yaml.example)

### 📚 Документация
- `QUICKSTART.md` — быстрый старт за 5 минут ⭐ ЧИТАЙТЕ ПЕРВЫМ
- `USAGE.md` — пошаговые инструкции по использованию
- `BOT_GUIDE.md` — гайд по Telegram-боту
- `README_BOT.md` — полная документация по боту
- `PROJECT_SUMMARY.md` — обзор всего проекта
- `README.md` — исходная документация

### 🔧 Исходный код
```
src/wb_price_monitor/
  ├── __init__.py              Package
  ├── config.py                Загрузка конфига
  ├── wb_client.py             Парсер WB (рейт-лимиты, кэш)
  ├── matcher.py               Сопоставление товаров с моделями
  ├── db.py                    SQLite (products, snapshots, notifications)
  ├── notify.py                Telegram отправка
  ├── logic.py                 Основной цикл мониторинга
  ├── monitor_manager.py       ⭐ Менеджер фонового мониторинга
  └── telegram_bot.py          ⭐ Telegram-бот с long polling
```

### 🧪 Тесты
```
tests/
  ├── conftest.py
  ├── test_matcher.py          Сопоставление моделей
  ├── test_filter_and_price.py Фильтры и расчёты
  └── test_notifications.py    Уведомления и антиспам
```

### 🐳 Развёртывание
- `Dockerfile` — контейнеризация
- `docker-compose.yml` — Docker-compose
- `examples/wb-monitor.service` — systemd unit (Linux)

## Быстрый старт

### 🚀 Запустить бот на ноутбуке (Linux/Mac)
```bash
cd /home/semyon/wb
source .venv/bin/activate
python main.py bot
```

### 🪟 Windows
Двойной клик на `run_bot.bat`

### 📱 Управление
Откройте Telegram, нажимайте кнопки в боте — вот и вся работа.

## Архитектура

```
┌─────────────────────────────────────┐
│    Telegram Bot (Long Polling)      │
│  - Получает команды и нажатия       │
│  - Защита по TELEGRAM_CHAT_ID       │
└────────────┬────────────────────────┘
             │
     ┌───────▼──────────┐
     │ MonitorManager   │
     │ (фоновый поток)  │
     │ - start_all()    │
     │ - start_selected()
     │ - run_once()     │
     │ - stop()         │
     └───────┬──────────┘
             │
     ┌───────▼──────────────┐
     │  Monitor / Logic     │
     │  - run_once()        │
     │  - запуск проверок   │
     └───────┬──────────────┘
             │
     ┌───────┴───────────────┬─────────────┐
     │                       │             │
┌────▼─────┐  ┌────────┐  ┌─▼─────┐  ┌──▼──┐
│ WB Client │  │ Matcher│  │  DB   │  │Notif│
│ (parses) │  │ (match) │  │(store)│  │(TG) │
└──────────┘  └────────┘  └───────┘  └─────┘
```

## Команды

```bash
python main.py bot              # Telegram-бот (РЕКОМЕНДУЕТСЯ)
python main.py run-once         # Проверка один раз
python main.py monitor          # Непрерывный мониторинг (без Telegram)
python main.py test-telegram    # Тест Telegram
python main.py show-last model  # Последние цены

pytest -q                       # Запустить тесты
```

## Особенности

✅ **Long polling** — работает везде, нет webhook
✅ **Фоновый поток** — бот получает команды, пока мониторинг работает
✅ **One at a time** — нельзя запустить два мониторинга
✅ **Graceful shutdown** — Ctrl+C корректно закрывает всё
✅ **Persistence** — база сохраняется между запусками
✅ **Ratelimits** — backoff на ошибки, кэширование
✅ **Logging** — всё в консоль и `wb_monitor.log`
✅ **Windows-friendly** — `run_bot.bat` для двойного клика

## Что дальше?

1. Откройте `QUICKSTART.md` для быстрого старта
2. Запустите `python main.py bot`
3. Нажимайте кнопки в Telegram
4. Получайте уведомления о хороших ценах

## 🎉 Всё готово!

Проект полностью готов к использованию на вашем ноутбуке.

**Главная команда:**
```bash
python main.py bot
```

Всё управление — через Telegram кнопки.

---

**Дата:** 16 мая 2026
**Статус:** ✅ Production Ready
**Все тесты:** ✅ 6/6 passed
