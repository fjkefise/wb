import os
from src.wb_price_monitor.db import DB
from src.wb_price_monitor.notify import _chat_ids

def test_notifications_antispam(tmp_path):
    db_path = tmp_path / 'testdb.sqlite'
    db = DB(path=str(db_path))
    wb_id = 'n1'
    db.record_notification(wb_id, 'CHEAP_PRICE', 1000, ts=1000)
    # last_notification within window
    res = db.last_notification(wb_id, 'CHEAP_PRICE', since_ts=900)
    assert res and res['price']==1000

def test_chat_ids_split_comma_separated_values():
    assert _chat_ids('123, 456') == ['123', '456']
