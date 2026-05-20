#!/usr/bin/env python3
import sys
import os
import logging
from dotenv import load_dotenv

load_dotenv()

from src.wb_price_monitor.logic import Monitor
from src.wb_price_monitor.telegram_bot import TelegramBotController

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('wb_monitor.log')
        ]
    )

def main():
    if len(sys.argv) < 2:
        print('Usage: main.py <mode>')
        print('modes: bot, run-once, monitor, test-telegram, show-last')
        return

    setup_logging()
    mode = sys.argv[1]

    try:
        if mode == 'bot':
            bot = TelegramBotController()
            bot.run()
        elif mode == 'run-once':
            monitor = Monitor()
            monitor.run_once()
        elif mode == 'monitor':
            monitor = Monitor()
            monitor.monitor()
        elif mode == 'test-telegram':
            monitor = Monitor()
            monitor.test_telegram()
        elif mode == 'show-last':
            key = sys.argv[2] if len(sys.argv) > 2 else None
            monitor = Monitor()
            monitor.show_last(key)
        else:
            print(f'Unknown mode: {mode}')
    except KeyboardInterrupt:
        print('\nShutdown...')
    except Exception as e:
        logging.exception(f'Fatal error: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
