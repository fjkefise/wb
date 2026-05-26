import time
import random
import logging

import requests

logger = logging.getLogger(__name__)

SEARCH_API = 'https://search.wb.ru/exactmatch/ru/common/v18/search'
DETAIL_API = 'https://card.wb.ru/cards/v2/detail'
# Region used by WB for price calculation (Moscow).
DEFAULT_DEST = -1257786

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': '*/*',
    'Origin': 'https://www.wildberries.ru',
    'Referer': 'https://www.wildberries.ru/',
}


class WildberriesClient:
    def __init__(
        self,
        session=None,
        rate_limit_delay=1.0,
        jitter=0.5,
        max_requests=100,
        max_requests_per_hour=None,
        dest=None,
        retry_base_delay=30,
        retry_max_delay=1800,
        backoff_after_errors=3,
    ):
        self.session = session or requests.Session()
        if hasattr(self.session, 'trust_env'):
            # WB traffic must go directly from the server IP. Telegram has its own
            # explicit proxy path; global proxy env vars should not affect WB.
            self.session.trust_env = False

        self.rate_limit_delay = rate_limit_delay
        self.jitter = jitter
        self.max_requests = max_requests
        self.max_requests_per_hour = max_requests_per_hour
        self.dest = dest if dest is not None else DEFAULT_DEST
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.backoff_after_errors = backoff_after_errors
        self._blocked_until = 0
        self._consecutive_errors = 0
        self.last_error = None
        self.last_status_code = None
        self._requests_made = 0
        self._request_times = []
        self._cache = {}

    def reset_cycle(self, clear_cache=True):
        self._requests_made = 0
        self.last_error = None
        self.last_status_code = None
        if clear_cache:
            self._cache.clear()

    def is_backing_off(self):
        return time.time() < self._blocked_until

    def _throttle(self):
        now = time.time()
        if now < self._blocked_until:
            wait_for = int(self._blocked_until - now)
            logger.warning('WB client is backing off for %s more seconds', wait_for)
            raise RuntimeError('WB client backoff active')

        if self._requests_made >= self.max_requests:
            logger.warning('max requests per cycle reached')
            raise RuntimeError('max requests reached')

        if self.max_requests_per_hour:
            self._request_times = [ts for ts in self._request_times if now - ts < 3600]
            if len(self._request_times) >= self.max_requests_per_hour:
                logger.warning('max requests per hour reached')
                raise RuntimeError('max hourly requests reached')

        delay = self.rate_limit_delay + random.random() * self.jitter
        time.sleep(delay)

        self._requests_made += 1
        if self.max_requests_per_hour:
            self._request_times.append(time.time())

    def _activate_backoff(self, retry_after=None):
        delay = None

        if retry_after:
            try:
                delay = int(retry_after)
            except (TypeError, ValueError):
                delay = None

        if delay is None:
            delay = min(
                self.retry_max_delay,
                self.retry_base_delay * (2 ** min(self._consecutive_errors, 5)),
            )

        delay += random.random() * min(delay, 30)
        self._blocked_until = time.time() + delay
        self._consecutive_errors += 1

        logger.warning('WB client backoff activated for %.1f seconds', delay)

    def _record_request_error(self, error, status_code=None, retry_after=None):
        self.last_error = error
        self.last_status_code = status_code
        self._consecutive_errors += 1

        if self._consecutive_errors >= self.backoff_after_errors:
            self._consecutive_errors -= 1
            self._activate_backoff(retry_after)

    def _request_search_page(self, query, page=1, sort='popular', max_price=None):
        self._throttle()

        params = {
            'appType': 1,
            'curr': 'rub',
            'dest': self.dest,
            'query': query,
            'resultset': 'catalog',
            'sort': sort,
            'spp': 30,
            'page': page,
        }

        if max_price is not None:
            try:
                max_price_rub = int(max_price)
            except (TypeError, ValueError):
                max_price_rub = None

            if max_price_rub is not None and max_price_rub > 0:
                params['priceU'] = f'0;{max_price_rub * 100}'

        try:
            resp = self.session.get(
                SEARCH_API,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=20,
            )
        except requests.RequestException:
            logger.warning(
                'WB search request failed for query=%r page=%s sort=%s',
                query,
                page,
                sort,
            )
            self._record_request_error('request_failed')
            return []

        if resp.status_code == 429:
            retry = resp.headers.get('Retry-After')
            logger.warning(
                'WB search 429 for query=%r page=%s sort=%s; Retry-After=%s',
                query,
                page,
                sort,
                retry,
            )
            self._record_request_error(
                'rate_limited',
                status_code=429,
                retry_after=retry,
            )
            return []

        if resp.status_code >= 500:
            logger.warning(
                'WB search returned %s for query=%r page=%s sort=%s',
                resp.status_code,
                query,
                page,
                sort,
            )
            self._record_request_error(
                'server_error',
                status_code=resp.status_code,
            )
            return []

        if resp.status_code != 200:
            self.last_error = 'bad_status'
            self.last_status_code = resp.status_code
            logger.warning(
                'WB search returned %s for query=%r page=%s sort=%s',
                resp.status_code,
                query,
                page,
                sort,
            )
            return []

        try:
            data = resp.json()
        except ValueError:
            logger.warning(
                'WB search returned non-JSON for query=%r page=%s sort=%s',
                query,
                page,
                sort,
            )
            return []

        self._consecutive_errors = 0
        self._blocked_until = 0
        self.last_error = None
        self.last_status_code = None

        products = data.get('products')
        if not isinstance(products, list):
            products = (data.get('data') or {}).get('products') or []

        return products if isinstance(products, list) else []

    def _request_detail(self, wb_ids):
        self._throttle()
        ids = [str(wb_id).strip() for wb_id in wb_ids if str(wb_id).strip()]
        if not ids:
            return []

        params = {
            'appType': 1,
            'curr': 'rub',
            'dest': self.dest,
            'spp': 30,
            'nm': ','.join(ids),
        }
        try:
            resp = self.session.get(
                DETAIL_API,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=20,
            )
        except requests.RequestException:
            logger.warning('WB detail request failed for %s ids', len(ids))
            self._record_request_error('request_failed')
            return []

        if resp.status_code == 429:
            retry = resp.headers.get('Retry-After')
            logger.warning('WB detail 429 for %s ids; Retry-After=%s', len(ids), retry)
            self._record_request_error('rate_limited', status_code=429, retry_after=retry)
            return []
        if resp.status_code >= 500:
            logger.warning('WB detail returned %s for %s ids', resp.status_code, len(ids))
            self._record_request_error('server_error', status_code=resp.status_code)
            return []
        if resp.status_code != 200:
            self.last_error = 'bad_status'
            self.last_status_code = resp.status_code
            logger.warning('WB detail returned %s for %s ids', resp.status_code, len(ids))
            return []

        try:
            data = resp.json()
        except ValueError:
            logger.warning('WB detail returned non-JSON for %s ids', len(ids))
            return []

        self._consecutive_errors = 0
        self._blocked_until = 0
        self.last_error = None
        self.last_status_code = None
        products = (data.get('data') or {}).get('products') or data.get('products') or []
        return products if isinstance(products, list) else []

    @staticmethod
    def _kopecks_to_rub(value):
        if value is None:
            return None

        try:
            value = int(value)
        except (TypeError, ValueError):
            return None

        return value // 100 if value >= 1000 else value

    @classmethod
    def _extract_prices(cls, product):
        sizes = product.get('sizes') or []

        if sizes:
            for size in sizes:
                if not isinstance(size, dict):
                    continue

                price_obj = size.get('price') or {}
                current = cls._kopecks_to_rub(price_obj.get('product'))
                old = cls._kopecks_to_rub(price_obj.get('basic'))

                if current is not None:
                    return current, old

        current = cls._kopecks_to_rub(product.get('salePriceU') or product.get('sale'))
        old = cls._kopecks_to_rub(product.get('priceU'))

        return current, old

    @staticmethod
    def _extract_seller(product):
        supplier = product.get('supplier')

        if isinstance(supplier, dict):
            return supplier.get('name') or supplier.get('supplierName')

        if supplier:
            return str(supplier)

        return None

    def _parse_product(self, product, query):
        nm = product.get('id')
        price, old_price = self._extract_prices(product)

        return {
            'wb_id': str(nm) if nm is not None else None,
            'name': product.get('name') or '',
            'brand': product.get('brand') or '',
            'seller': self._extract_seller(product),
            'price': price,
            'old_price': old_price,
            'rating': product.get('rating') or product.get('reviewRating'),
            'reviews': product.get('feedbacks') or product.get('nmFeedbacks'),
            'link': f'https://www.wildberries.ru/catalog/{nm}/detail.aspx' if nm else '',
            'query': query,
        }

    def search(self, query, pages=1, sort='popular', max_price=None):
        key = ('search', query, pages, sort, max_price)

        if key in self._cache:
            return self._cache[key]

        results = []
        seen = set()

        for page in range(1, max(1, int(pages)) + 1):
            try:
                products = self._request_search_page(
                    query,
                    page=page,
                    sort=sort,
                    max_price=max_price,
                )
            except RuntimeError:
                break

            if not products:
                break

            for product in products:
                if not isinstance(product, dict):
                    continue

                try:
                    parsed = self._parse_product(product, query)
                    wb_id = parsed.get('wb_id')

                    if wb_id and wb_id not in seen:
                        seen.add(wb_id)
                        results.append(parsed)

                except Exception:
                    logger.exception(
                        'Error parsing WB product for query=%r page=%s sort=%s',
                        query,
                        page,
                        sort,
                    )

        logger.info(
            'WB search query=%r sort=%s pages=%s: %s products parsed',
            query,
            sort,
            pages,
            len(results),
        )

        self._cache[key] = results
        return results

    def fetch_by_ids(self, wb_ids, query='tracked', batch_size=80):
        ids = [str(wb_id) for wb_id in wb_ids if wb_id]
        results = []
        seen = set()
        for start in range(0, len(ids), max(1, int(batch_size))):
            batch = ids[start:start + max(1, int(batch_size))]
            try:
                products = self._request_detail(batch)
            except RuntimeError:
                break
            if not products:
                if self.last_error:
                    break
                continue
            for product in products:
                if not isinstance(product, dict):
                    continue
                try:
                    parsed = self._parse_product(product, query)
                    wb_id = parsed.get('wb_id')
                    if wb_id and wb_id not in seen:
                        seen.add(wb_id)
                        results.append(parsed)
                except Exception:
                    logger.exception('Error parsing WB detail product')
            if self.is_backing_off():
                break
        logger.info('WB detail fetched %s/%s tracked products', len(results), len(ids))
        return results
