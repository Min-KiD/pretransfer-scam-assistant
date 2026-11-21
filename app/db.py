"""SQLite storage, one file (design doc 8): sessions, messages, reports, account_labels."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from core.lookup import SEED_ACCOUNTS

DB_PATH = Path(os.environ.get("APP_DB", Path(__file__).resolve().parent.parent / "data/app/app.sqlite"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_labels (
  so_tk TEXT PRIMARY KEY, ngan_hang TEXT, chu_tk TEXT, loai TEXT, nhan TEXT NOT NULL,
  dat_boi TEXT NOT NULL, cap_nhat REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, so_tk TEXT NOT NULL, so_tien INTEGER, state TEXT NOT NULL, tao_luc REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT,
  co_anh INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE, so_tk TEXT NOT NULL, muc TEXT NOT NULL,
  kich_ban TEXT, nut TEXT NOT NULL, sdt TEXT NOT NULL, link TEXT NOT NULL, noi_dung TEXT NOT NULL, tao_luc REAL NOT NULL);
"""


class DB:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock, self.conn:
            self.conn.executescript(SCHEMA)
            if not self.conn.execute("SELECT 1 FROM account_labels LIMIT 1").fetchone():
                self.conn.executemany(
                    "INSERT INTO account_labels VALUES (?,?,?,?,?, 'du_lieu_mau', ?)",
                    [(*a, time.time()) for a in SEED_ACCOUNTS])

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock, self.conn:
            return self.conn.execute(sql, args).lastrowid

    # accounts
    def account(self, so_tk: str) -> dict | None:
        r = self.q("SELECT * FROM account_labels WHERE so_tk=?", (so_tk,))
        return r[0] if r else None

    def set_label(self, so_tk: str, nhan: str, by: str):
        if self.account(so_tk):
            self.x("UPDATE account_labels SET nhan=?, dat_boi=?, cap_nhat=? WHERE so_tk=?", (nhan, by, time.time(), so_tk))
        else:
            self.x("INSERT INTO account_labels VALUES (?,NULL,NULL,NULL,?,?,?)", (so_tk, nhan, by, time.time()))

    # sessions
    def save_session(self, sid: str, so_tk: str, so_tien, state: dict):
        self.x("INSERT INTO sessions VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
               (sid, so_tk, so_tien, json.dumps(state, ensure_ascii=False), time.time()))

    def session(self, sid: str) -> dict | None:
        r = self.q("SELECT * FROM sessions WHERE id=?", (sid,))
        if not r:
            return None
        r[0]["state"] = json.loads(r[0]["state"])
        return r[0]

    def add_message(self, sid: str, role: str, text: str, co_anh: bool = False):
        self.x("INSERT INTO messages (session_id, role, text, co_anh, ts) VALUES (?,?,?,?,?)",
               (sid, role, text, int(co_anh), time.time()))

    def messages(self, sid: str) -> list[dict]:
        return self.q("SELECT role, text, co_anh, ts FROM messages WHERE session_id=? ORDER BY id", (sid,))

    # reports
    def add_report(self, sid, so_tk, muc, kich_ban, nut, sdt, link, noi_dung) -> int:
        return self.x("INSERT INTO reports (session_id, so_tk, muc, kich_ban, nut, sdt, link, noi_dung, tao_luc) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (sid, so_tk, muc, kich_ban, nut, json.dumps(sdt), json.dumps(link),
                       json.dumps(noi_dung, ensure_ascii=False), time.time()))

    def reports(self) -> list[dict]:
        rows = self.q("SELECT * FROM reports ORDER BY id")
        for r in rows:
            r["sdt"], r["link"], r["noi_dung"] = json.loads(r["sdt"]), json.loads(r["link"]), json.loads(r["noi_dung"])
        return rows
