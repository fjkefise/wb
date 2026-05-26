import os
import time
import logging
import requests
from datetime import datetime
from html import escape
from typing import Dict, List, Optional

from src.wb_price_monitor.monitor_manager import MonitorManager
from src.wb_price_monitor.config import load_config
from src.wb_price_monitor.telegram_http import telegram_proxies

logger = logging.getLogger(__name__)


class TelegramBotController:
    """Telegram bot controller with long polling"""

    def __init__(self, config_path='config.yaml', token_env='TELEGRAM_BOT_TOKEN', chat_id_env='TELEGRAM_CHAT_ID'):
        self.config = load_config(config_path)
        self.token = os.environ.get(token_env)
        raw_chat_ids = os.environ.get(chat_id_env, '')
        self.chat_ids = [int(x.strip()) for x in raw_chat_ids.split(',') if x.strip().isdigit()]
        self.default_chat_id = self.chat_ids[0] if self.chat_ids else None
        self.manager = MonitorManager(config_path)
        self.base_url = f'https://api.telegram.org/bot{self.token}'
        self.proxies = telegram_proxies()
        self._offset = 0
        self._user_states: Dict[int, Dict] = {}  # user_id -> state

        if not self.token or not self.chat_ids:
            raise ValueError('TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set')

    def _is_authorized(self, chat_id: int) -> bool:
        return chat_id in self.chat_ids

    def _get_target_chat(self, chat_id: Optional[int] = None) -> int:
        return chat_id if chat_id is not None else self.default_chat_id

    def _send_message(self, text: str, reply_markup=None, chat_id: Optional[int] = None) -> bool:
        """Send message to configured chat"""
        target_chat = self._get_target_chat(chat_id)
        data = {
            'chat_id': target_chat,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_markup:
            import json
            data['reply_markup'] = json.dumps(reply_markup)
        for attempt in range(1, 4):
            try:
                resp = requests.post(f'{self.base_url}/sendMessage', data=data, timeout=15, proxies=self.proxies)
                if resp.status_code == 200:
                    return True
                logger.warning('Failed to send Telegram message: %s %s', resp.status_code, resp.text)
                if resp.status_code < 500 and resp.status_code != 429:
                    return False
            except requests.RequestException as e:
                logger.warning('Failed to send Telegram message on attempt %s: %s', attempt, type(e).__name__)
            except Exception as e:
                logger.exception(f'Failed to send message: {e}')
                return False
            time.sleep(attempt * 2)
        return False

    def _edit_message(self, message_id: int, text: str, reply_markup=None, chat_id: Optional[int] = None) -> bool:
        """Edit existing message"""
        try:
            target_chat = self._get_target_chat(chat_id)
            data = {
                'chat_id': target_chat,
                'message_id': message_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            if reply_markup:
                import json
                data['reply_markup'] = json.dumps(reply_markup)
            resp = requests.post(f'{self.base_url}/editMessageText', data=data, timeout=10, proxies=self.proxies)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.warning('Failed to edit Telegram message: %s', type(e).__name__)
            return False
        except Exception as e:
            logger.exception(f'Failed to edit message: {e}')
            return False

    def _answer_callback(self, callback_query_id: str, text: str = '', show_alert: bool = False) -> bool:
        """Answer callback query"""
        try:
            data = {
                'callback_query_id': callback_query_id,
                'text': text,
                'show_alert': show_alert
            }
            resp = requests.post(f'{self.base_url}/answerCallbackQuery', data=data, timeout=10, proxies=self.proxies)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.warning('Failed to answer Telegram callback: %s', type(e).__name__)
            return False
        except Exception as e:
            logger.exception(f'Failed to answer callback: {e}')
            return False

    def _get_main_menu(self) -> Dict:
        """Get main menu inline keyboard"""
        return {
            'inline_keyboard': [
                [{'text': '🔍 Проверить все', 'callback_data': 'action:run_all'}],
                [{'text': '♾ Мониторинг всех', 'callback_data': 'action:monitor_all'}],
                [{'text': '🎛 Выбрать модели', 'callback_data': 'action:select_models'}],
                [{'text': '📊 Статус', 'callback_data': 'action:status'}],
                [{'text': '🧾 Последние цены', 'callback_data': 'action:last_prices'}],
                [{'text': '⛔ Остановить', 'callback_data': 'action:stop'}],
            ]
        }

    def _start_text(self, authorized: bool) -> str:
        interval = int(self.config.get('monitor_interval_seconds', self.config.get('interval_seconds', 900)))
        jitter = int(self.config.get('monitor_jitter_seconds', self.config.get('cycle_jitter_seconds', 0)))
        interval_text = f'{interval//60} мин'
        if jitter:
            interval_text += f' + до {jitter//60} мин случайно'
        if not authorized:
            return (
                '👋 WB Price Monitor\n\n'
                'Бот работает, но этот чат не добавлен в TELEGRAM_CHAT_ID.\n'
                f'chat_id этого чата: <code>{escape(str(self._last_seen_chat_id or ""))}</code>\n\n'
                'Добавьте этот id в .env и перезапустите бота.'
            )
        return (
            '👋 WB Price Monitor\n\n'
            'Варианты запуска:\n'
            '• 🔍 Проверить все — разовая проверка всех моделей\n'
            '• ♾ Мониторинг всех — проверять все модели по расписанию\n'
            '• 🎛 Выбрать модели — проверять только часть моделей\n'
            '• 📊 Статус — посмотреть, запущен ли мониторинг\n'
            '• 🧾 Последние цены — последние найденные товары\n\n'
            f'Текущий интервал мониторинга: {interval_text}.'
        )

    def _get_models_menu(self) -> Dict:
        """Get model selection menu"""
        models = self.config.get('models', {})
        selected = set(self.manager.get_selected_models())

        buttons = []
        for key, cfg in models.items():
            name = cfg.get('name', key)
            is_sel = '✅' if key in selected else '☐'
            buttons.append([{'text': f'{is_sel} {name}', 'callback_data': f'model_toggle:{key}'}])

        buttons.append([{'text': '🔍 Проверить выбранные', 'callback_data': 'action:run_selected'}])
        buttons.append([{'text': '♾ Мониторить выбранные', 'callback_data': 'action:monitor_selected'}])
        buttons.append([{'text': '⬅️ Назад', 'callback_data': 'action:main_menu'}])

        return {'inline_keyboard': buttons}

    def _handle_command(self, message: Dict) -> bool:
        """Handle text commands"""
        chat_id = message.get('chat', {}).get('id')
        self._last_seen_chat_id = chat_id
        text = message.get('text', '').strip()

        if text in ['/start', '/help']:
            authorized = self._is_authorized(chat_id)
            if not authorized:
                logger.warning(f'/start from unauthorized user {chat_id}')
                self._send_message(self._start_text(False), chat_id=chat_id)
                return True
            self._send_message(
                self._start_text(True),
                self._get_main_menu(),
                chat_id=chat_id
            )
            return True

        if not self._is_authorized(chat_id):
            logger.warning(f'Message from unauthorized user {chat_id}')
            return False

        msg_id = message.get('message_id')

        if text == '/status':
            self._send_status(chat_id=chat_id)
            return True
        elif text == '/stop':
            if self.manager.stop():
                self._send_message('⛔ Мониторинг остановлен', chat_id=chat_id)
            else:
                self._send_message('Мониторинг не был запущен', chat_id=chat_id)
            return True
        elif text == '/run_all':
            self._send_message('🔄 Проверяю все модели...', chat_id=chat_id)
            results = self.manager.run_once_all()
            self._report_cycle(results, chat_id=chat_id)
            return True
        elif text == '/monitor_all':
            if self.manager.start_all():
                self._send_message('✅ Запущен мониторинг всех моделей', chat_id=chat_id)
            else:
                self._send_message('⚠️ Мониторинг уже запущен', chat_id=chat_id)
            return True
        return False

    def _handle_callback(self, callback: Dict) -> bool:
        """Handle button callbacks"""
        chat_id = callback.get('from', {}).get('id')
        if not self._is_authorized(chat_id):
            logger.warning(f'Callback from unauthorized user {chat_id}')
            return False

        data = callback.get('data', '')
        msg_id = callback.get('message', {}).get('message_id')
        callback_id = callback.get('id')

        if data.startswith('action:'):
            action = data.split(':')[1]

            if action == 'main_menu':
                self._edit_message(msg_id, '👋 WB Price Monitor', self._get_main_menu(), chat_id=chat_id)
            elif action == 'run_all':
                self._answer_callback(callback_id, '🔄 Проверяю...', False)
                self._send_message('🔄 Проверяю все модели...', chat_id=chat_id)
                results = self.manager.run_once_all()
                self._report_cycle(results, chat_id=chat_id)
            elif action == 'monitor_all':
                if self.manager.start_all():
                    self._answer_callback(callback_id, '✅ Запущено', False)
                    self._send_message('✅ Запущен мониторинг всех моделей', chat_id=chat_id)
                else:
                    self._answer_callback(callback_id, '⚠️ Уже запущен', True)
            elif action == 'select_models':
                self._answer_callback(callback_id, '', False)
                self._edit_message(msg_id, '🎛 Выберите модели:', self._get_models_menu(), chat_id=chat_id)
            elif action == 'run_selected':
                self._answer_callback(callback_id, '🔄 Проверяю...', False)
                selected = self.manager.get_selected_models()
                if selected:
                    self._send_message('🔄 Проверяю выбранные модели...', chat_id=chat_id)
                    results = self.manager.run_once_selected(selected)
                    self._report_cycle(results, chat_id=chat_id)
                else:
                    self._send_message('⚠️ Не выбраны модели', chat_id=chat_id)
            elif action == 'monitor_selected':
                self._answer_callback(callback_id, '', False)
                selected = self.manager.get_selected_models()
                if selected and self.manager.start_selected(selected):
                    self._send_message(f'✅ Мониторинг выбранных: {", ".join([self.config["models"][k]["name"] for k in selected])}', chat_id=chat_id)
                else:
                    self._send_message('⚠️ Ошибка запуска или модели не выбраны', chat_id=chat_id)
            elif action == 'status':
                self._answer_callback(callback_id, '', False)
                self._send_status(chat_id=chat_id)
            elif action == 'last_prices':
                self._answer_callback(callback_id, '', False)
                self._send_last_prices(chat_id=chat_id)
            elif action == 'stop':
                if self.manager.stop():
                    self._answer_callback(callback_id, '✅ Остановлено', False)
                    self._send_message('⛔ Мониторинг остановлен', chat_id=chat_id)
                else:
                    self._answer_callback(callback_id, 'Не запущен', True)
            return True

        elif data.startswith('model_toggle:'):
            key = data.split(':')[1]
            selected = set(self.manager.get_selected_models())
            if key in selected:
                selected.discard(key)
            else:
                selected.add(key)
            self.manager._selected_models = list(selected)
            self._edit_message(msg_id, '🎛 Выберите модели:', self._get_models_menu(), chat_id=chat_id)
            return True

        return False

    def _send_status(self, chat_id: Optional[int] = None):
        """Send status message"""
        status = self.manager.get_status()
        running = '✅ Работает' if status['running'] else '⛔ Остановлен'
        interval = status['interval']
        last_run = status['last_run'] or 'нет'
        models_list = ', '.join([self.config['models'][k]['name'] for k in status['models']]) if status['models'] else 'не выбраны'

        results = status['cycle_results']
        manual_cd = status.get('manual_cooldown_remaining', 0)
        text = f"""📊 Статус мониторинга

Статус: {running}
Модели: {models_list}
Интервал: {interval} сек ({interval//60} мин)
Ручная проверка доступна через: {manual_cd} сек
Последняя проверка: {last_run}

Последний цикл:
Проверено моделей: {results.get('checked_models', 0)}/{results.get('total_models', 0)}
WB отдал товаров: {results.get('raw_products', results.get('products', 0))}
Ниже порога: {results.get('below_price', 0)}
Прошло фильтр модели: {results.get('matched_products', results.get('products', 0))}
Отправлено уведомлений: {results.get('notifications', 0)}
WB backoff: {'да' if results.get('stopped_by_backoff') else 'нет'}
Ошибок: {len(results.get('errors', []))}
"""
        if results.get('errors'):
            text += '\nОшибки:\n' + '\n'.join(results['errors'][:3])

        self._send_message(text, chat_id=chat_id)

    def _send_last_prices(self, chat_id: Optional[int] = None):
        """Send last found products"""
        results = self.manager.get_last_results()
        if not results:
            self._send_message('📭 Нет найденных товаров', chat_id=chat_id)
            return

        text = '🧾 Последние найденные товары:\n\n'
        for i, snap in enumerate(results[:15], 1):
            model_key = snap.get('model_key', '?')
            model_name = escape(str(self.config['models'].get(model_key, {}).get('name', model_key)))
            price = escape(str(snap.get('price', '?')))
            name = escape(str(snap.get('name', 'Unknown'))[:40])
            url = escape(str(snap.get('url', '')), quote=True)

            if url:
                text += f'{i}. <a href="{url}">{model_name}: {price}₽</a>\n{name}\n\n'
            else:
                text += f'{i}. {model_name}: {price}₽\n{name}\n\n'

        self._send_message(text, chat_id=chat_id)

    def _report_cycle(self, results: Dict, chat_id: Optional[int] = None):
        """Report cycle results"""
        products = results.get('products', 0)
        notifications = results.get('notifications', 0)
        errors = results.get('errors', [])
        raw_products = results.get('raw_products', products)
        below_price = results.get('below_price', 0)
        matched = results.get('matched_products', products)
        backoff = 'да' if results.get('stopped_by_backoff') else 'нет'
        stopped_at = results.get('stopped_at_query')
        rate_limited = results.get('rate_limited_queries', 0)
        failed_queries = results.get('failed_queries', 0)
        if results.get('skipped_due_manual_cooldown'):
            remaining = int(results.get('manual_cooldown_remaining_seconds', 0))
            self._send_message(
                f'⏳ Ручная проверка недавно уже запускалась.\nПодожди еще примерно {remaining // 60 + 1} мин.',
                chat_id=chat_id,
            )
            return
        if results.get('skipped_due_cooldown'):
            remaining = int(results.get('cooldown_remaining_seconds', 0))
            self._send_message(
                f'⏳ WB временно ограничил запросы. Парсер на паузе примерно {remaining // 60 + 1} мин.',
                chat_id=chat_id,
            )
            return

        title = '⚠️ WB временно ограничил запросы' if results.get('stopped_by_backoff') and raw_products == 0 else '✅ Проверка завершена'
        text = f"""{title}

Проверено моделей: {results.get('checked_models', 0)}/{results.get('total_models', 0)}
WB отдал товаров: {raw_products}
Ниже порога: {below_price}
Прошло фильтр модели: {matched}
Отправлено уведомлений: {notifications}
Запросов с 429: {rate_limited}
Других ошибок запросов: {failed_queries}
WB backoff: {backoff}
"""
        if stopped_at:
            text += f'\nОстановился на запросе: {escape(str(stopped_at))}\n'
        if results.get('cooldown_remaining_seconds'):
            remaining = int(results.get('cooldown_remaining_seconds', 0))
            text += f'\nПауза перед следующим WB-запросом: ~{remaining // 60 + 1} мин.\n'
        rejected = results.get('rejected_below_price') or []
        if rejected:
            text += '\nОтброшено ниже порога:\n'
            for item in rejected[:5]:
                reason = escape(str(item.get('reason', '-')))
                model = escape(str(item.get('model', '-')))
                price = escape(str(item.get('price', '-')))
                name = escape(str(item.get('name', '-'))[:90])
                link = escape(str(item.get('link', '')), quote=True)
                if link:
                    text += f'• {reason}: <a href="{link}">{price}₽</a> — {model}\n{name}\n'
                else:
                    text += f'• {reason}: {price}₽ — {model}\n{name}\n'
        if errors:
            text += f'\n⚠️ Ошибки:\n' + '\n'.join(errors[:2])

        self._send_message(text, chat_id=chat_id)

    def _get_updates(self) -> List[Dict]:
        """Fetch updates from Telegram"""
        try:
            resp = requests.get(
                f'{self.base_url}/getUpdates',
                params={'offset': self._offset, 'timeout': 30},
                timeout=35,
                proxies=self.proxies,
            )
            data = resp.json()
            if data.get('ok'):
                return data.get('result', [])
        except requests.RequestException as e:
            logger.warning('Error fetching Telegram updates: %s', type(e).__name__)
        except Exception:
            logger.exception('Error fetching Telegram updates')
        return []

    def run(self):
        """Start bot long polling loop"""
        logger.info(f'Starting Telegram bot (chat_ids: {self.chat_ids})')
        if self.proxies:
            logger.info('Telegram proxy is enabled')
        logger.info('Send /start to the bot to open controls')

        while True:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._offset = update.get('update_id', 0) + 1

                    # Handle text message
                    if 'message' in update:
                        msg = update['message']
                        self._handle_command(msg)

                    # Handle button callback
                    elif 'callback_query' in update:
                        cb = update['callback_query']
                        self._handle_callback(cb)

                # Small delay if no updates
                if not updates:
                    time.sleep(0.1)

            except KeyboardInterrupt:
                logger.info('Bot interrupted')
                self.manager.stop()
                break
            except Exception as e:
                logger.exception(f'Error in bot loop: {e}')
                time.sleep(5)
