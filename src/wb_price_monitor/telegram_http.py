import os


def telegram_proxies():
    proxy_url = os.environ.get('TELEGRAM_PROXY_URL') or os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    if not proxy_url:
        return None
    return {
        'http': proxy_url,
        'https': proxy_url,
    }
