from src.wb_price_monitor.wb_client import WildberriesClient


def test_extract_prices_from_sizes():
    product = {
        'id': 123,
        'name': 'Яндекс Станция Лайт',
        'sizes': [{'price': {'basic': 549000, 'product': 391600}}],
    }
    price, old = WildberriesClient._extract_prices(product)
    assert price == 3916
    assert old == 5490


def test_parse_product_shape():
    client = WildberriesClient(rate_limit_delay=0, jitter=0, max_requests=1)
    parsed = client._parse_product(
        {
            'id': 443786302,
            'name': 'Умная колонка Станция Лайт 2',
            'brand': 'Яндекс',
            'feedbacks': 120,
            'rating': 5,
            'sizes': [{'price': {'basic': 549000, 'product': 391600}}],
        },
        'Яндекс Станция Лайт',
    )
    assert parsed['wb_id'] == '443786302'
    assert parsed['price'] == 3916
    assert parsed['old_price'] == 5490
    assert 'wildberries.ru/catalog/443786302' in parsed['link']


def test_reset_cycle_clears_cache_and_request_count():
    client = WildberriesClient(rate_limit_delay=0, jitter=0, max_requests=1)
    client._requests_made = 1
    client._cache[('search', 'x')] = [{'wb_id': '1'}]

    client.reset_cycle()

    assert client._requests_made == 0
    assert client._cache == {}


def test_extract_prices_skips_sizes_without_price():
    product = {
        'sizes': [
            {'price': {}},
            {'price': {'basic': 799000, 'product': 599000}},
        ],
    }
    price, old = WildberriesClient._extract_prices(product)
    assert price == 5990
    assert old == 7990


def test_hourly_request_limit_blocks_after_limit():
    client = WildberriesClient(rate_limit_delay=0, jitter=0, max_requests=10, max_requests_per_hour=1)

    client._throttle()

    assert client._requests_made == 1
    try:
        client._throttle()
    except RuntimeError as exc:
        assert 'hourly' in str(exc)
    else:
        raise AssertionError('hourly limit did not block the second request')


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params.copy())
        return self.responses.pop(0)


def test_search_paginates_and_deduplicates():
    session = FakeSession([
        FakeResponse(payload={'data': {'products': [{'id': 1, 'name': 'Яндекс Станция Миди'}]}}),
        FakeResponse(payload={'data': {'products': [
            {'id': 1, 'name': 'Яндекс Станция Миди'},
            {'id': 2, 'name': 'Яндекс Станция Миди'},
        ]}}),
    ])
    client = WildberriesClient(session=session, rate_limit_delay=0, jitter=0, max_requests=10)

    results = client.search('Яндекс Станция Миди', pages=2, sort='priceup')

    assert [item['wb_id'] for item in results] == ['1', '2']
    assert [call['page'] for call in session.calls] == [1, 2]
    assert all(call['sort'] == 'priceup' for call in session.calls)


def test_search_sends_max_price_filter_to_wb():
    session = FakeSession([
        FakeResponse(payload={'data': {'products': []}}),
    ])
    client = WildberriesClient(session=session, rate_limit_delay=0, jitter=0, max_requests=10)

    client.search('Яндекс Станция Миди', pages=1, sort='priceup', max_price=9850)

    assert session.calls[0]['priceU'] == '0;985000'


def test_single_429_does_not_activate_global_backoff():
    session = FakeSession([FakeResponse(status_code=429, headers={'Retry-After': '60'})])
    client = WildberriesClient(session=session, rate_limit_delay=0, jitter=0, max_requests=10)

    assert client.search('Яндекс Станция Миди') == []
    assert client.last_error == 'rate_limited'
    assert client._blocked_until == 0


def test_repeated_429_activates_global_backoff():
    session = FakeSession([
        FakeResponse(status_code=429, headers={'Retry-After': '60'}),
        FakeResponse(status_code=429, headers={'Retry-After': '60'}),
        FakeResponse(status_code=429, headers={'Retry-After': '60'}),
    ])
    client = WildberriesClient(session=session, rate_limit_delay=0, jitter=0, max_requests=10)

    for index in range(3):
        assert client.search(f'Яндекс Станция Миди {index}') == []

    assert client._blocked_until > 0
