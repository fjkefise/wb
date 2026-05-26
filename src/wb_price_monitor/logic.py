import time
import logging
import os
import random
from datetime import datetime
from html import escape
from src.wb_price_monitor.config import load_config, get_telegram_settings
from src.wb_price_monitor.wb_client import WildberriesClient
from src.wb_price_monitor.matcher import is_accessory_name, match_product_to_model
from src.wb_price_monitor.db import DB
from src.wb_price_monitor.notify import send_telegram

logger = logging.getLogger(__name__)

class Monitor:
    def __init__(self, config_path='config.yaml'):
        self.cfg = load_config(config_path)
        self.telegram = get_telegram_settings(self.cfg)
        self.db = DB(path=os.environ.get('WB_DB_PATH', 'db.sqlite3'))
        self.wb = WildberriesClient(
            rate_limit_delay=float(self.cfg.get('request_delay_seconds', 2.0)),
            jitter=float(self.cfg.get('request_jitter_seconds', 2.5)),
            max_requests=self.cfg.get('max_requests_per_cycle', 50),
            max_requests_per_hour=self.cfg.get('max_requests_per_hour'),
        )
        self.interval = int(self.cfg.get('interval_seconds', 3600))
        self.cycle_jitter = int(self.cfg.get('cycle_jitter_seconds', 0))
        self.search_pages = int(self.cfg.get('search_pages', 1))
        self.discovery_interval = int(self.cfg.get('discovery_interval_seconds', 12 * 3600))
        self.monitor_interval = int(self.cfg.get('monitor_interval_seconds', self.interval))
        self.monitor_jitter = int(self.cfg.get('monitor_jitter_seconds', self.cycle_jitter))
        self.discovery_search_pages = int(self.cfg.get('discovery_search_pages', self.search_pages))
        self.search_sorts = self.cfg.get('search_sorts') or ['popular']
        self.models_per_cycle = int(self.cfg.get('models_per_cycle', 0) or 0)
        self.wb_cooldown_after_429 = int(self.cfg.get('wb_cooldown_after_429_seconds', 2700))
        self._wb_cooldown_until = 0
        self._model_cursor = 0
        self._last_discovery_ts = 0

    def _is_accessory(self, name: str) -> bool:
        return is_accessory_name(name)

    def evaluate_product(self, prod, model_key, model_cfg):
        wb_id = prod.get('wb_id')
        price = prod.get('price')
        if not wb_id or price is None:
            return

        # save product basic
        self.db.upsert_product(wb_id, prod.get('name'), prod.get('brand'), prod.get('seller'))

        now = int(time.time())
        prev_price = self.db.last_price(wb_id)

        # Calculate history metrics before inserting the current price, otherwise
        # a fresh discount dilutes the baseline it is being compared against.
        median_24h = self.db.median_price(wb_id, now - 24*3600)
        median_7d = self.db.median_price(wb_id, now - 7*24*3600)
        min_24h = self.db.min_price(wb_id, now - 24*3600)
        min_7d = self.db.min_price(wb_id, now - 7*24*3600)

        self.db.add_snapshot(wb_id, price, prod.get('old_price'), prod.get('rating'), prod.get('reviews'), prod.get('link'), model_key, prod.get('query'), ts=now)

        def drop_pct(old, cur):
            if not old: return None
            try:
                return (old - cur) / old * 100
            except Exception:
                return None

        reasons = []
        interesting = model_cfg.get('interesting_price')
        max_reasonable = model_cfg.get('max_reasonable_price')

        def is_reasonable(cur):
            return max_reasonable is None or cur < max_reasonable

        if prev_price is None and interesting is not None and price < interesting:
            reasons.append('NEW_CHEAP_PRODUCT')

        if interesting is not None and price < interesting:
            reasons.append('CHEAP_PRICE')

        if prev_price is not None:
            dp = drop_pct(prev_price, price)
            if dp is not None and dp >= model_cfg.get('sharp_drop_from_previous_pct', 20) and is_reasonable(price):
                reasons.append('SHARP_DROP_FROM_PREVIOUS')

        if median_24h is not None:
            dp24 = drop_pct(median_24h, price)
            if dp24 is not None and dp24 >= model_cfg.get('drop_from_24h_median_pct', 20) and is_reasonable(price):
                reasons.append('DROP_FROM_24H_MEDIAN')

        if median_7d is not None:
            dp7 = drop_pct(median_7d, price)
            if dp7 is not None and dp7 >= model_cfg.get('drop_from_7d_median_pct', 25) and is_reasonable(price):
                reasons.append('DROP_FROM_7D_MEDIAN')

        if not reasons:
            return

        # priority
        priority = ['NEW_CHEAP_PRODUCT','CHEAP_PRICE','SHARP_DROP_FROM_PREVIOUS','DROP_FROM_24H_MEDIAN','DROP_FROM_7D_MEDIAN']
        chosen = next((r for r in priority if r in reasons), reasons[0])

        # anti-spam: check last 6 hours
        six_hours_ago = int(time.time()) - 6*3600
        last = self.db.last_notification(wb_id, chosen, six_hours_ago)
        if last:
            last_price = last['price']
            if price >= last_price * 0.97:
                logger.info('Skip notification for %s: similar alert sent recently', wb_id)
                return

        # build message
        text_lines = []
        text_lines.append('🔥 Выгодная цена на Яндекс Станцию')
        text_lines.append('')
        text_lines.append(f"Модель: {escape(str(model_cfg.get('name','-')))}")
        text_lines.append(f"Цена сейчас: {price or 'нет данных'} ₽")
        text_lines.append(f"Уведомлять ниже: {interesting or 'нет данных'} ₽")
        text_lines.append('')
        text_lines.append('Динамика:')
        text_lines.append(f"Предыдущая цена: {prev_price or 'нет данных'} ₽")
        if prev_price:
            dpv = drop_pct(prev_price, price)
            text_lines.append(f"Падение от прошлой: {dpv:.2f}%")
        else:
            text_lines.append('Падение от прошлой: нет данных')
        text_lines.append(f"Медиана 24ч: {median_24h or 'нет данных'} ₽")
        text_lines.append(f"Минимум 24ч: {min_24h or 'нет данных'} ₽")
        text_lines.append(f"Медиана 7д: {median_7d or 'нет данных'} ₽")
        text_lines.append(f"Минимум 7д: {min_7d or 'нет данных'} ₽")
        text_lines.append('')
        text_lines.append(f"Причина: {escape(chosen)}")
        text_lines.append('')
        text_lines.append(f"Товар: {escape(str(prod.get('name') or 'нет данных'))}")
        text_lines.append(f"Рейтинг: {escape(str(prod.get('rating') or 'нет данных'))}")
        text_lines.append(f"Отзывы: {escape(str(prod.get('reviews') or 'нет данных'))}")
        text_lines.append(f"Продавец: {escape(str(prod.get('seller') or 'нет данных'))}")
        text_lines.append(f"Ссылка: {escape(str(prod.get('link') or ''))}")

        text = '\n'.join(text_lines)
        ok = send_telegram(self.telegram.get('bot_token'), self.telegram.get('chat_id'), text)
        if ok:
            self.db.record_notification(wb_id, chosen, price)
        else:
            logger.warning('Failed to send telegram for %s', wb_id)

    def _search_model_products(self, query, model_cfg=None):
        products = []
        seen = set()
        max_price = (model_cfg or {}).get('interesting_price')
        for sort in self.search_sorts:
            for prod in self.wb.search(query, pages=self.search_pages, sort=sort, max_price=max_price):
                wb_id = prod.get('wb_id')
                if not wb_id or wb_id in seen:
                    continue
                seen.add(wb_id)
                products.append(prod)
            if self.wb.is_backing_off():
                break
        return products

    def _discover_model_products(self, query):
        products = []
        seen = set()
        for sort in self.search_sorts:
            for prod in self.wb.search(query, pages=self.discovery_search_pages, sort=sort, max_price=None):
                wb_id = prod.get('wb_id')
                if not wb_id or wb_id in seen:
                    continue
                seen.add(wb_id)
                products.append(prod)
            if self.wb.is_backing_off():
                break
        return products

    @staticmethod
    def _is_below_model_threshold(prod, model_cfg):
        threshold = model_cfg.get('interesting_price')
        price = prod.get('price')
        return threshold is None or (price is not None and price < threshold)

    def _is_wb_cooling_down(self):
        return time.time() < self._wb_cooldown_until

    def _wb_cooldown_remaining(self):
        return max(0, int(self._wb_cooldown_until - time.time()))

    def _activate_wb_cooldown(self):
        self._wb_cooldown_until = time.time() + self.wb_cooldown_after_429 + random.randint(0, 300)
        logger.warning('WB cooldown activated for %s seconds', self._wb_cooldown_remaining())

    def _next_model_batch(self, models):
        items = list(models.items())
        if not items:
            return []
        batch_size = self.models_per_cycle if self.models_per_cycle > 0 else len(items)
        batch_size = min(batch_size, len(items))
        start = self._model_cursor % len(items)
        batch = [items[(start + offset) % len(items)] for offset in range(batch_size)]
        self._model_cursor = (start + batch_size) % len(items)
        return batch

    @staticmethod
    def _base_stats(models_count=0):
        return {
            'queries': 0,
            'total_models': models_count,
            'checked_models': 0,
            'raw_products': 0,
            'below_price': 0,
            'accessories_filtered': 0,
            'matched_products': 0,
            'evaluated_products': 0,
            'tracked_products': 0,
            'discovered_products': 0,
            'rejected_below_price': [],
            'rate_limited_queries': 0,
            'failed_queries': 0,
            'stopped_by_backoff': False,
            'stopped_at_query': None,
            'skipped_due_cooldown': False,
            'cooldown_remaining_seconds': 0,
        }

    def _cooldown_stats(self, stats):
        stats['skipped_due_cooldown'] = True
        stats['cooldown_remaining_seconds'] = self._wb_cooldown_remaining()
        stats['notifications'] = 0
        logger.warning('Skip cycle: WB cooldown active for %s seconds', stats['cooldown_remaining_seconds'])
        return stats

    def run_discovery_once(self, model_keys=None):
        self.wb.reset_cycle()
        all_models = self.cfg.get('models', {})
        models = {k: v for k, v in all_models.items() if not model_keys or k in model_keys}
        stats = self._base_stats(len(models))
        stats['notifications_before'] = self.db.count_notifications_since(0)
        if self._is_wb_cooling_down():
            return self._cooldown_stats(stats)

        for model_key, model_cfg in models.items():
            stats['checked_models'] += 1
            for q in model_cfg.get('queries', []):
                stats['queries'] += 1
                prods = self._discover_model_products(q)
                if self.wb.last_error == 'rate_limited':
                    stats['rate_limited_queries'] += 1
                    self._activate_wb_cooldown()
                    stats['stopped_by_backoff'] = True
                    stats['stopped_at_query'] = q
                    stats['cooldown_remaining_seconds'] = self._wb_cooldown_remaining()
                    stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
                    return stats
                if self.wb.last_error:
                    stats['failed_queries'] += 1
                stats['raw_products'] += len(prods)

                for p in prods:
                    if self._is_accessory(p.get('name')):
                        stats['accessories_filtered'] += 1
                        continue
                    if not match_product_to_model(p.get('name', ''), model_key):
                        continue
                    stats['matched_products'] += 1
                    wb_id = p.get('wb_id')
                    if not wb_id:
                        continue
                    self.db.track_product(wb_id, model_key, q)
                    stats['tracked_products'] += 1
                    stats['discovered_products'] += 1
                    self.evaluate_product(p, model_key, model_cfg)
                    stats['evaluated_products'] += 1

        self._last_discovery_ts = int(time.time())
        stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
        return stats

    def run_tracked_once(self, model_keys=None):
        self.wb.reset_cycle()
        all_models = self.cfg.get('models', {})
        tracked = self.db.tracked_products(model_keys=model_keys)
        stats = self._base_stats(len(model_keys or all_models))
        stats['tracked_products'] = len(tracked)
        stats['notifications_before'] = self.db.count_notifications_since(0)
        if self._is_wb_cooling_down():
            return self._cooldown_stats(stats)
        if not tracked:
            stats['notifications'] = 0
            return stats

        by_id = {item['wb_id']: item for item in tracked}
        products = self.wb.fetch_by_ids(by_id.keys(), query='tracked')
        if self.wb.last_error == 'rate_limited':
            stats['rate_limited_queries'] += 1
            self._activate_wb_cooldown()
            stats['stopped_by_backoff'] = True
            stats['stopped_at_query'] = 'tracked products'
            stats['cooldown_remaining_seconds'] = self._wb_cooldown_remaining()
            stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
            return stats
        if self.wb.last_error:
            stats['failed_queries'] += 1

        stats['raw_products'] = len(products)
        seen_models = set()
        for p in products:
            tracked_item = by_id.get(p.get('wb_id'))
            if not tracked_item:
                continue
            model_key = tracked_item.get('model_key')
            model_cfg = all_models.get(model_key)
            if not model_cfg:
                continue
            seen_models.add(model_key)
            if self._is_accessory(p.get('name')):
                stats['accessories_filtered'] += 1
                continue
            if not match_product_to_model(p.get('name', ''), model_key):
                continue
            stats['matched_products'] += 1
            self.db.track_product(p.get('wb_id'), model_key, tracked_item.get('query'))
            self.evaluate_product(p, model_key, model_cfg)
            stats['evaluated_products'] += 1
            if self._is_below_model_threshold(p, model_cfg):
                stats['below_price'] += 1
        stats['checked_models'] = len(seen_models)
        stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
        return stats

    def run_once(self):
        # Manual runs do both: refresh discovery, then immediately re-check the
        # tracked set. Background monitoring uses these modes separately.
        discovery = self.run_discovery_once()
        tracked = self.run_tracked_once()
        merged = dict(discovery)
        for key in ('raw_products', 'below_price', 'accessories_filtered', 'matched_products',
                    'evaluated_products', 'tracked_products', 'rate_limited_queries', 'failed_queries'):
            merged[key] = discovery.get(key, 0) + tracked.get(key, 0)
        merged['notifications'] = discovery.get('notifications', 0) + tracked.get('notifications', 0)
        merged['stopped_by_backoff'] = discovery.get('stopped_by_backoff') or tracked.get('stopped_by_backoff')
        merged['stopped_at_query'] = discovery.get('stopped_at_query') or tracked.get('stopped_at_query')
        merged['cooldown_remaining_seconds'] = max(
            discovery.get('cooldown_remaining_seconds', 0),
            tracked.get('cooldown_remaining_seconds', 0),
        )
        return merged

    def run_search_once_legacy(self):
        self.wb.reset_cycle()
        models = self.cfg.get('models', {})
        stats = {
            'queries': 0,
            'total_models': len(models),
            'checked_models': 0,
            'raw_products': 0,
            'below_price': 0,
            'accessories_filtered': 0,
            'matched_products': 0,
            'evaluated_products': 0,
            'rejected_below_price': [],
            'rate_limited_queries': 0,
            'failed_queries': 0,
            'notifications_before': self.db.count_notifications_since(0),
            'stopped_by_backoff': False,
            'stopped_at_query': None,
            'skipped_due_cooldown': False,
            'cooldown_remaining_seconds': 0,
        }
        if self._is_wb_cooling_down():
            stats['skipped_due_cooldown'] = True
            stats['cooldown_remaining_seconds'] = self._wb_cooldown_remaining()
            stats['notifications'] = 0
            logger.warning('Skip cycle: WB cooldown active for %s seconds', stats['cooldown_remaining_seconds'])
            return stats
        total_requests = 0
        model_items = self._next_model_batch(models)
        for model_key, model_cfg in model_items:
            stats['checked_models'] += 1
            queries = model_cfg.get('queries', [])
            for q in queries:
                stats['queries'] += 1
                try:
                    prods = self._search_model_products(q, model_cfg)
                except Exception:
                    logger.exception('search failed')
                    continue
                if self.wb.last_error == 'rate_limited':
                    stats['rate_limited_queries'] += 1
                    logger.warning('Query was rate limited by WB: %s', q)
                    self._activate_wb_cooldown()
                    stats['stopped_by_backoff'] = True
                    stats['stopped_at_query'] = q
                    stats['cooldown_remaining_seconds'] = self._wb_cooldown_remaining()
                    stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
                    return stats
                elif self.wb.last_error:
                    stats['failed_queries'] += 1
                    logger.warning('Query failed with WB error=%s: %s', self.wb.last_error, q)
                stats['raw_products'] += len(prods)
                if self.wb.is_backing_off():
                    logger.warning('Stopping current cycle because WB backoff is active')
                    stats['stopped_by_backoff'] = True
                    stats['stopped_at_query'] = q
                    stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
                    return stats

                for p in prods:
                    if not self._is_below_model_threshold(p, model_cfg):
                        continue
                    stats['below_price'] += 1
                    if self._is_accessory(p.get('name')):
                        stats['accessories_filtered'] += 1
                        self._remember_rejected(stats, p, model_cfg, 'аксессуар')
                        continue
                    if not match_product_to_model(p.get('name',''), model_key):
                        self._remember_rejected(stats, p, model_cfg, 'не совпала модель')
                        continue
                    stats['matched_products'] += 1
                    if not p.get('wb_id'):
                        continue
                    stats['evaluated_products'] += 1
                    self.evaluate_product(p, model_key, model_cfg)

                total_requests += 1
                if total_requests >= self.cfg.get('max_requests_per_cycle', 50):
                    logger.info('Reached max requests for cycle')
                    stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
                    return stats
        stats['notifications'] = self.db.count_notifications_since(0) - stats['notifications_before']
        return stats

    @staticmethod
    def _remember_rejected(stats, prod, model_cfg, reason):
        if len(stats['rejected_below_price']) >= 5:
            return
        stats['rejected_below_price'].append({
            'reason': reason,
            'model': model_cfg.get('name', '-'),
            'name': prod.get('name') or 'нет данных',
            'price': prod.get('price'),
            'link': prod.get('link') or '',
        })

    def monitor(self):
        logger.info(
            'Start monitor loop, tracked interval %s seconds, discovery interval %s seconds',
            self.monitor_interval,
            self.discovery_interval,
        )
        while True:
            try:
                now = int(time.time())
                if not self._last_discovery_ts or now - self._last_discovery_ts >= self.discovery_interval:
                    logger.info('Starting discovery cycle')
                    self.run_discovery_once()
                logger.info('Starting tracked price cycle')
                self.run_tracked_once()
            except Exception:
                logger.exception('error in run_once')
            delay = self.monitor_interval
            if self.monitor_jitter > 0:
                delay += random.randint(0, self.monitor_jitter)
            logger.info('Next monitor cycle in %s seconds', delay)
            time.sleep(delay)

    def test_telegram(self):
        send_telegram(self.telegram.get('bot_token'), self.telegram.get('chat_id'), 'Test message from WB price monitor')

    def show_last(self, model_key=None):
        if not model_key:
            print('Provide model_key, e.g. station_light')
            return
        snaps = self.db.last_snapshots(model_key)
        for s in snaps:
            ts = datetime.fromtimestamp(s['ts']).isoformat()
            print(ts, s['wb_id'], s['price'], s.get('name'))
