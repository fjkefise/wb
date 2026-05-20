# WB Price Monitor — Полный обзор

## Что было реализовано

### ✅ Ядро проекта (в наличии):
- **Парсер Wildberries** — получает товары по поисковым запросам
- **Фильтрация товаров** — исключает аксессуары и дубли
- **Сопоставление с моделями** — правильно различает Лайт/Лайт 2/Лайт 2 с часами и т.д.
- **История цен** — SQLite база с полной историей проверок
- **Расчёт динамики** — медиана 24ч, 7д, минимумы, падения цен
- **Правила алертов** — 5 типов уведомлений с приоритетами
- **Антиспам** — не спамит одинаковыми уведомлениями
- **Telegram-отправка** — красивые сообщения с деталями товара
- **Рейт-лимиты** — respectful delays, exponential backoff, кэширование

### 🆕 Telegram-бот (новое):
- **Long polling** — работает на ноутбуке без webhook
- **Фоновый мониторинг** — в отдельном потоке
- **Управление кнопками** — главное меню с 6 кнопками
- **Выбор моделей** — toggle для каждой из 10 моделей
- **Статус** — полная информация о работе
- **Последние цены** — краткий список дешёвых товаров
- **Команды** — /start, /status, /stop, /run_all, /monitor_all
- **Защита** — только ваш chat_id может управлять
- **Логирование** — в консоль и файл `wb_monitor.log`

## Структура файлов

```
.
├── main.py                                  ⭐ Основной файл запуска
├── run_bot.bat                              ⭐ Windows батник для бота
├── BOT_GUIDE.md                             ⭐ Краткий гайд по боту
├── USAGE.md                                 ⭐ Пошаговые инструкции
├── README_BOT.md                            ⭐ Полная документация по боту
├── run.py                                   (deprecated, используйте main.py)
├── config.yaml.example                      Шаблон конфига со всеми 10 моделями
├── .env.example                             Шаблон переменных окружения
├── requirements.txt                         Зависимости
├── Dockerfile                               Docker image
├── docker-compose.yml                       Docker-compose
├── pytest.ini (или тесты в tests/)          Тесты
├── db.sqlite3                               База данных (auto-created)
├── wb_monitor.log                           Логи бота
├── src/wb_price_monitor/
│   ├── __init__.py                          Package marker
│   ├── config.py                            Загрузка конфига
│   ├── wb_client.py                         Парсер Wildberries
│   ├── matcher.py                           Сопоставление с моделями
│   ├── db.py                                SQLite слой
│   ├── notify.py                            Telegram отправка
│   ├── logic.py                             Основной цикл мониторинга
│   ├── monitor_manager.py                   ⭐ Менеджер фонового мониторинга
│   └── telegram_bot.py                      ⭐ Telegram-бот с long polling
├── tests/
│   ├── conftest.py                          Pytest конфиг
│   ├── test_matcher.py                      Тесты матчинга моделей
│   ├── test_filter_and_price.py             Тесты фильтров и расчёта цен
│   └── test_notifications.py                Тесты уведомлений
└── examples/
    └── wb-monitor.service                   systemd unit для Linux

⭐ = новые файлы для Telegram-бота
```

## Команды запуска

### Telegram-бот (РЕКОМЕНДУЕТСЯ):
```bash
python main.py bot
```
Управление через кнопки в Telegram, фоновый мониторинг в отдельном потоке.

### Windows (двойной клик):
```
run_bot.bat
```

### Разовая проверка:
```bash
python main.py run-once
```

### Непрерывный мониторинг (без Telegram):
```bash
python main.py monitor
```

### Тест Telegram:
```bash
python main.py test-telegram
```

## Ключевые компоненты

### MonitorManager (`monitor_manager.py`)
Управляет фоновым мониторингом в отдельном потоке:
```python
manager = MonitorManager()
manager.start_all()                    # Запустить мониторинг всех
manager.start_selected(['station_light_2', 'station_midi'])  # Выбранных
manager.stop()                         # Остановить
manager.is_running()                   # Статус
manager.run_once_all()                 # Разовая проверка всех
manager.run_once_selected(models)      # Разовая проверка выбранных
manager.get_status()                   # Полный статус
manager.get_last_results()             # Последние товары
```

### TelegramBotController (`telegram_bot.py`)
Telegram-бот с long polling, обработкой команд и inline кнопок:
```python
bot = TelegramBotController()
bot.run()                              # Запустить loop
```

Автоматически:
- Получает команды и нажатия кнопок
- Вызывает методы `MonitorManager`
- Отправляет статусы и результаты
- Защищает по `TELEGRAM_CHAT_ID`

## Настройка на ноутбуке (пошагово)

1. **Скачайте проект и установите зависимости:**
   ```bash
   git clone <repo>
   cd wb
   python -m venv .venv
   source .venv/bin/activate  # или .venv\Scripts\activate на Windows
   pip install -r requirements.txt
   ```

2. **Создайте Telegram-бота через @BotFather**
   - /newbot → выберите имя → получите токен
   - Отправьте боту сообщение
   - Получите chat_id через getUpdates

3. **Создайте `.env`:**
   ```bash
   cp .env.example .env
   # Отредактируйте:
   # TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   # TELEGRAM_CHAT_ID=123456789
   ```

4. **Настройте цены в `config.yaml`:**
   ```bash
   cp config.yaml.example config.yaml
   # Отредактируйте интересующие вас модели и пороги
   ```

5. **Запустите бот:**
   ```bash
   python main.py bot
   ```

6. **Управляйте через Telegram:**
   - /start → видите меню с кнопками
   - Нажимаете ♾ Мониторинг всех или 🎛 Выбрать модели
   - Бот проверяет выбранные модели каждые N минут
   - При хорошей цене → Telegram-уведомление

## Особенности для ноутбука

✅ **Long polling** — работает везде (нет need для public webhook)
✅ **Фоновый поток** — мониторинг не блокирует получение команд
✅ **One at a time** — нельзя запустить два мониторинга одновременно
✅ **Graceful shutdown** — Ctrl+C корректно останавливает всё
✅ **Persistence** — база данных сохраняется между запусками
✅ **Logging** — всё логируется в консоль и `wb_monitor.log`

## Тестирование

```bash
pytest -q
```

Тесты покрывают:
- Сопоставление товаров с моделями (10 вариантов)
- Фильтрацию аксессуаров
- Расчёт падения цен
- Антидубль уведомлений

## Безопасность

- Только ваш `TELEGRAM_CHAT_ID` может управлять ботом
- Токен хранится в `.env` (в `.gitignore`)
- Уведомления идут через Telegram API (нет публичных endpoints)
- Long polling безопаснее webhook (нет экспозиции)

## Расширение в будущем

Структура позволяет легко добавить:
- Другие каналы (Discord, Slack, Email)
- Web-интерфейс для управления (FastAPI)
- Аналитику по ценам
- Правила по комбинациям моделей
- Экспорт истории (CSV, JSON)
- Интеграцию с другими магазинами

## Если что-то не работает

1. **Telegram не получает уведомления:**
   - Проверьте `.env` (токен и chat_id)
   - Выключите Privacy Mode бота (@BotFather)
   - Тест: `python main.py test-telegram`

2. **Бот не отвечает на кнопки:**
   - Проверьте chat_id в `.env` (должен быть ваш личный чат)
   - Смотрите логи в консоли
   - Перезагрузите: Ctrl+C и `python main.py bot`

3. **Цены не парсятся:**
   - WB, вероятно, изменил HTML
   - Смотрите `src/wb_price_monitor/wb_client.py`
   - Обновите селекторы CSS

4. **Товары не совпадают с моделями:**
   - Смотрите `src/wb_price_monitor/matcher.py`
   - Добавьте тестовый случай в `tests/test_matcher.py`
   - Проверьте нормализацию названия товара

## Вы готовы!

Проект полностью готов к использованию на ноутбуке. Просто:

```bash
python main.py bot
```

И управляйте через Telegram кнопки. 🎉

---

**Автор:** GitHub Copilot
**Статус:** Production Ready
**Последнее обновление:** 16 мая 2026
