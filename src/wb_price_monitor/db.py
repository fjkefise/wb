import sqlite3
import threading
import time
from contextlib import contextmanager
from statistics import median

SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
  wb_id TEXT PRIMARY KEY,
  name TEXT,
  brand TEXT,
  seller TEXT
);

CREATE TABLE IF NOT EXISTS price_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wb_id TEXT,
  price INTEGER,
  old_price INTEGER,
  rating REAL,
  reviews INTEGER,
  url TEXT,
  model_key TEXT,
  query TEXT,
  ts INTEGER
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wb_id TEXT,
  notif_type TEXT,
  price INTEGER,
  ts INTEGER
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_wb_ts ON price_snapshots(wb_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_price_snapshots_model_ts ON price_snapshots(model_key, ts DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_wb_type_ts ON notifications(wb_id, notif_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_ts ON notifications(ts DESC);
'''

class DB:
    def __init__(self, path='db.sqlite3'):
        self.path = path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        with self._lock:
            con = sqlite3.connect(self.path)
            try:
                con.row_factory = sqlite3.Row
                yield con
                con.commit()
            finally:
                con.close()

    def upsert_product(self, wb_id, name, brand, seller):
        with self.conn() as c:
            c.execute(
                '''
                INSERT INTO products(wb_id,name,brand,seller) VALUES(?,?,?,?)
                ON CONFLICT(wb_id) DO UPDATE SET
                  name=excluded.name,
                  brand=excluded.brand,
                  seller=excluded.seller
                ''',
                (wb_id, name, brand, seller),
            )

    def add_snapshot(self, wb_id, price, old_price, rating, reviews, url, model_key, query, ts=None):
        ts = ts or int(time.time())
        with self.conn() as c:
            c.execute('INSERT INTO price_snapshots(wb_id,price,old_price,rating,reviews,url,model_key,query,ts) VALUES(?,?,?,?,?,?,?,?,?)',
                      (wb_id, price, old_price, rating, reviews, url, model_key, query, ts))

    def last_price(self, wb_id):
        with self.conn() as c:
            r = c.execute('SELECT price FROM price_snapshots WHERE wb_id=? ORDER BY ts DESC LIMIT 1', (wb_id,)).fetchone()
            return r['price'] if r else None

    def snapshots_in_range(self, wb_id, since_ts):
        with self.conn() as c:
            rows = c.execute('SELECT price FROM price_snapshots WHERE wb_id=? AND ts>=? ORDER BY ts', (wb_id, since_ts)).fetchall()
            return [r['price'] for r in rows if r['price'] is not None]

    def count_snapshots_since(self, since_ts, model_keys=None):
        with self.conn() as c:
            if model_keys:
                placeholders = ','.join('?' for _ in model_keys)
                params = list(model_keys) + [since_ts]
                r = c.execute(
                    f'SELECT COUNT(*) as cnt FROM price_snapshots WHERE model_key IN ({placeholders}) AND ts>=?',
                    params,
                ).fetchone()
            else:
                r = c.execute('SELECT COUNT(*) as cnt FROM price_snapshots WHERE ts>=?', (since_ts,)).fetchone()
            return r['cnt'] if r else 0

    def min_price(self, wb_id, since_ts):
        prices = self.snapshots_in_range(wb_id, since_ts)
        return min(prices) if prices else None

    def median_price(self, wb_id, since_ts):
        prices = self.snapshots_in_range(wb_id, since_ts)
        if not prices:
            return None
        return int(median(prices))

    def record_notification(self, wb_id, notif_type, price, ts=None):
        ts = ts or int(time.time())
        with self.conn() as c:
            c.execute('INSERT INTO notifications(wb_id,notif_type,price,ts) VALUES(?,?,?,?)', (wb_id, notif_type, price, ts))

    def count_notifications_since(self, since_ts):
        with self.conn() as c:
            r = c.execute('SELECT COUNT(*) as cnt FROM notifications WHERE ts>=?', (since_ts,)).fetchone()
            return r['cnt'] if r else 0

    def last_notification(self, wb_id, notif_type, since_ts):
        with self.conn() as c:
            r = c.execute('SELECT price,ts FROM notifications WHERE wb_id=? AND notif_type=? AND ts>=? ORDER BY ts DESC LIMIT 1', (wb_id, notif_type, since_ts)).fetchone()
            return dict(r) if r else None

    def recent_notifications(self, wb_id, since_ts):
        with self.conn() as c:
            rows = c.execute('SELECT notif_type,price,ts FROM notifications WHERE wb_id=? AND ts>=?', (wb_id, since_ts)).fetchall()
            return [dict(r) for r in rows]

    def last_snapshots(self, model_key, limit=20):
        with self.conn() as c:
            rows = c.execute('SELECT * FROM price_snapshots WHERE model_key=? ORDER BY ts DESC LIMIT ?', (model_key, limit)).fetchall()
            return [dict(r) for r in rows]
