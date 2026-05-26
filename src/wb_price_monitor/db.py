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

CREATE TABLE IF NOT EXISTS tracked_products (
  wb_id TEXT PRIMARY KEY,
  model_key TEXT,
  query TEXT,
  first_seen_ts INTEGER,
  last_seen_ts INTEGER,
  active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_wb_ts ON price_snapshots(wb_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_price_snapshots_model_ts ON price_snapshots(model_key, ts DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_wb_type_ts ON notifications(wb_id, notif_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_ts ON notifications(ts DESC);
CREATE INDEX IF NOT EXISTS idx_tracked_products_model_active ON tracked_products(model_key, active);
'''

class DB:
    def __init__(self, path='db.sqlite3'):
        self.path = path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.conn() as c:
            c.executescript(SCHEMA)
            c.execute(
                '''
                INSERT OR IGNORE INTO tracked_products(wb_id, model_key, query, first_seen_ts, last_seen_ts, active)
                SELECT wb_id, model_key, query, MIN(ts), MAX(ts), 1
                FROM price_snapshots
                WHERE wb_id IS NOT NULL AND model_key IS NOT NULL
                GROUP BY wb_id, model_key
                '''
            )

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

    def track_product(self, wb_id, model_key, query=None, ts=None):
        if not wb_id or not model_key:
            return
        ts = ts or int(time.time())
        with self.conn() as c:
            c.execute(
                '''
                INSERT INTO tracked_products(wb_id, model_key, query, first_seen_ts, last_seen_ts, active)
                VALUES(?,?,?,?,?,1)
                ON CONFLICT(wb_id) DO UPDATE SET
                  model_key=excluded.model_key,
                  query=COALESCE(excluded.query, tracked_products.query),
                  last_seen_ts=excluded.last_seen_ts,
                  active=1
                ''',
                (str(wb_id), model_key, query, ts, ts),
            )

    def tracked_products(self, model_keys=None, limit=None):
        with self.conn() as c:
            params = []
            where = 'WHERE tp.active=1'
            if model_keys:
                placeholders = ','.join('?' for _ in model_keys)
                where += f' AND tp.model_key IN ({placeholders})'
                params.extend(model_keys)
            sql = f'''
                SELECT tp.wb_id, tp.model_key, tp.query, p.name, p.brand, p.seller
                FROM tracked_products tp
                LEFT JOIN products p ON p.wb_id=tp.wb_id
                {where}
                ORDER BY tp.last_seen_ts DESC
            '''
            if limit:
                sql += ' LIMIT ?'
                params.append(int(limit))
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def count_tracked_products(self, model_keys=None):
        with self.conn() as c:
            params = []
            where = 'WHERE active=1'
            if model_keys:
                placeholders = ','.join('?' for _ in model_keys)
                where += f' AND model_key IN ({placeholders})'
                params.extend(model_keys)
            r = c.execute(f'SELECT COUNT(*) as cnt FROM tracked_products {where}', params).fetchone()
            return r['cnt'] if r else 0

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
