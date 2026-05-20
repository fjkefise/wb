from src.wb_price_monitor.matcher import match_product_to_model
from src.wb_price_monitor.logic import Monitor
from src.wb_price_monitor.monitor_manager import MonitorManager

def test_accessory_filter(monkeypatch, tmp_path):
    monkeypatch.setenv('WB_DB_PATH', str(tmp_path / 'test.sqlite3'))
    m = Monitor()
    assert m._is_accessory('Чехол для станции')
    assert m._is_accessory('Полка для умной колонки "Яндекс Станции Миди"')
    assert m._is_accessory('Кронштейн настенный для Яндекс Станция Макс')
    assert not m._is_accessory('Яндекс Станция Лайт')

def test_drop_pct_and_no_alert_when_too_expensive(monkeypatch, tmp_path):
    monkeypatch.setenv('WB_DB_PATH', str(tmp_path / 'test.sqlite3'))
    m = Monitor()
    # simulate db snapshots
    db = m.db
    wb_id = 'test123'
    db.upsert_product(wb_id, 'Яндекс Станция Лайт 2', '', '')
    db.add_snapshot(wb_id, 45000, None, None, None, '', 'station_light_2', 'q')
    # now current price still high but dropped
    prod = {'wb_id': wb_id, 'name': 'Яндекс Станция Лайт 2', 'price': 39000, 'link': 'https://'}
    cfg = {'name':'test','interesting_price':5000,'max_reasonable_price':20000,'sharp_drop_from_previous_pct':10,'drop_from_24h_median_pct':10,'drop_from_7d_median_pct':10}
    # should not raise
    m.evaluate_product(prod, 'station_light_2', cfg)

def test_equal_threshold_does_not_notify(monkeypatch, tmp_path):
    monkeypatch.setenv('WB_DB_PATH', str(tmp_path / 'test.sqlite3'))
    monkeypatch.setattr('src.wb_price_monitor.logic.send_telegram', lambda *args: True)
    m = Monitor()
    prod = {'wb_id': 'eq1', 'name': 'Яндекс Станция Лайт', 'price': 2600, 'link': 'https://'}
    cfg = {'name':'test','interesting_price':2600,'max_reasonable_price':2600}

    m.evaluate_product(prod, 'station_light', cfg)

    assert not m.db.recent_notifications('eq1', 0)

def test_above_threshold_is_skipped_before_evaluation(monkeypatch, tmp_path):
    monkeypatch.setenv('WB_DB_PATH', str(tmp_path / 'test.sqlite3'))
    m = Monitor()
    prod = {'wb_id': 'expensive', 'name': 'Яндекс Станция Миди', 'price': 9850}
    cfg = {'interesting_price': 9850}

    assert not m._is_below_model_threshold(prod, cfg)

def test_manager_counts_recent_products_by_model(monkeypatch, tmp_path):
    db_path = tmp_path / 'test.sqlite3'
    monkeypatch.setenv('WB_DB_PATH', str(db_path))
    manager = MonitorManager()
    manager.monitor.db.add_snapshot('wb1', 1000, None, None, None, '', 'station_midi', 'q')
    assert manager._count_recent_products() == 1
