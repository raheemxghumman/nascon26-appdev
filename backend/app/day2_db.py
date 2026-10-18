"""Durable Phase II records. Transactions serialize read/modify/write operations."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager


class Database:
    def __init__(self):
        self.lock = threading.RLock()
        path = os.environ.get("DAY2_DB", ":memory:")
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, value TEXT, PRIMARY KEY(kind,id))")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def get(self, kind, key, default=None):
        with self.lock:
            row = self.conn.execute("SELECT value FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, kind, key, value):
        with self.lock:
            self.conn.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value",
                              (kind, key, json.dumps(value, ensure_ascii=False)))

    def all(self, kind):
        with self.lock:
            return {r[0]: json.loads(r[1]) for r in self.conn.execute("SELECT id,value FROM records WHERE kind=?", (kind,))}

    def clear(self):
        with self.lock:
            self.conn.execute("DELETE FROM records")
