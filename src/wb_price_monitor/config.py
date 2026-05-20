import os
import yaml

def load_config(path='config.yaml'):
    if not os.path.exists(path):
        path = os.path.join(os.getcwd(), 'config.yaml')
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    return cfg

def get_telegram_settings(cfg):
    tel = cfg.get('telegram', {})
    token = os.environ.get(tel.get('bot_token_env', 'TELEGRAM_BOT_TOKEN'))
    chat_id = os.environ.get(tel.get('chat_id_env', 'TELEGRAM_CHAT_ID'))
    return {'bot_token': token, 'chat_id': chat_id}
