import requests
import logging
import time

from src.wb_price_monitor.telegram_http import telegram_proxies

logger = logging.getLogger(__name__)

def _chat_ids(chat_id):
    return [part.strip() for part in str(chat_id).split(',') if part.strip()]

def send_telegram(bot_token, chat_id, text):
    if not bot_token or not chat_id:
        logger.warning('Telegram not configured')
        return False
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    proxies = telegram_proxies()
    ok = False
    for target_chat_id in _chat_ids(chat_id):
        payload = {'chat_id': target_chat_id, 'text': text, 'parse_mode': 'HTML'}
        for attempt in range(1, 4):
            try:
                r = requests.post(url, data=payload, timeout=15, proxies=proxies)
                if r.status_code == 200:
                    ok = True
                    break
                logger.warning('Telegram send failed for chat_id ending %s: %s %s', target_chat_id[-4:], r.status_code, r.text)
                if r.status_code < 500 and r.status_code != 429:
                    break
            except requests.RequestException as e:
                logger.warning('Telegram send exception for chat_id ending %s on attempt %s: %s', target_chat_id[-4:], attempt, type(e).__name__)
            except Exception:
                logger.exception('Unexpected Telegram send exception')
                break
            time.sleep(attempt * 2)
    return ok
