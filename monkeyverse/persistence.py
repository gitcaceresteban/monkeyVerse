"""Everything that happens is written down.

One SQLite database per simulation (data/<id>.db) holding the full history:
genealogy, births, deaths, time-series statistics, climate events and periodic
resumable snapshots. Writes are batched and committed from the simulation thread;
reads (for the observer UI) use short-lived independent connections, which WAL
mode makes safe to do concurrently.
"""

from __future__ import annotations

import json
import pickle
import sqlite3
import threading
import time
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id   INTEGER PRIMARY KEY,
    parent_id  INTEGER,
    generation INTEGER,
    birth_tick INTEGER,
    birth_x    INTEGER,
    birth_y    INTEGER,
    genes      TEXT,
    death_tick INTEGER,
    death_age  INTEGER,
    death_x    INTEGER,
    death_y    INTEGER,
    death_cause TEXT
);
CREATE INDEX IF NOT EXISTS idx_agents_parent ON agents(parent_id);
CREATE INDEX IF NOT EXISTS idx_agents_birth ON agents(birth_tick);

CREATE TABLE IF NOT EXISTS stats (
    tick           INTEGER PRIMARY KEY,
    population      INTEGER,
    births         INTEGER,
    deaths         INTEGER,
    avg_energy     REAL,
    avg_age        REAL,
    avg_generation REAL,
    max_generation INTEGER,
    signal_activity REAL,
    food_total     REAL,
    event          TEXT,
    gene_means     TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER,
    type TEXT,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick);

CREATE TABLE IF NOT EXISTS snapshots (
    tick INTEGER PRIMARY KEY,
    created REAL,
    blob BLOB
);
"""


class Persistence:
    def __init__(self, db_path: str, keep_snapshots: int = 3):
        self.db_path = db_path
        self.keep_snapshots = keep_snapshots
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

        self._births: list[tuple] = []
        self._deaths: list[tuple] = []
        self._stats: list[tuple] = []
        self._events: list[tuple] = []

    # ------------------------------------------------------------- write side
    def log_birth(self, row: dict[str, Any]) -> None:
        self._births.append((
            row["agent_id"], row["parent_id"], row["generation"], row["birth_tick"],
            row["birth_x"], row["birth_y"], json.dumps(row["genes"]),
        ))

    def log_death(self, agent_id: int, tick: int, age: int, generation: int,
                  x: int, y: int, cause: str) -> None:
        self._deaths.append((tick, age, x, y, cause, agent_id))

    def log_stats(self, row: dict[str, Any]) -> None:
        self._stats.append((
            row["tick"], row["population"], row["births"], row["deaths"],
            row["avg_energy"], row["avg_age"], row["avg_generation"],
            row["max_generation"], row["signal_activity"], row["food_total"],
            row["event"], json.dumps(row["gene_means"]),
        ))

    def log_event(self, tick: int, type_: str, data: dict[str, Any]) -> None:
        self._events.append((tick, type_, json.dumps(data)))

    def flush(self) -> None:
        with self._lock:
            if self._births:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO agents "
                    "(agent_id,parent_id,generation,birth_tick,birth_x,birth_y,genes) "
                    "VALUES (?,?,?,?,?,?,?)", self._births)
                self._births.clear()
            if self._deaths:
                self.conn.executemany(
                    "UPDATE agents SET death_tick=?,death_age=?,death_x=?,death_y=?,"
                    "death_cause=? WHERE agent_id=?", self._deaths)
                self._deaths.clear()
            if self._stats:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    self._stats)
                self._stats.clear()
            if self._events:
                self.conn.executemany(
                    "INSERT INTO events (tick,type,data) VALUES (?,?,?)", self._events)
                self._events.clear()
            self.conn.commit()

    def save_snapshot(self, tick: int, snapshot: dict[str, Any]) -> None:
        self.flush()
        blob = pickle.dumps(snapshot, protocol=pickle.HIGHEST_PROTOCOL)
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO snapshots (tick,created,blob) VALUES (?,?,?)",
                              (tick, time.time(), blob))
            # keep only the most recent N
            self.conn.execute(
                "DELETE FROM snapshots WHERE tick NOT IN "
                "(SELECT tick FROM snapshots ORDER BY tick DESC LIMIT ?)",
                (self.keep_snapshots,))
            self.conn.commit()

    def load_latest_snapshot(self) -> Optional[dict[str, Any]]:
        with self._lock:
            cur = self.conn.execute("SELECT blob FROM snapshots ORDER BY tick DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            return None
        return pickle.loads(row[0])

    def close(self) -> None:
        try:
            self.flush()
            self.conn.close()
        except Exception:
            pass

    # -------------------------------------------------------------- read side
    def _read_conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def stats_series(self, since: int = 0, limit: int = 4000) -> list[dict[str, Any]]:
        c = self._read_conn()
        try:
            rows = c.execute(
                "SELECT * FROM stats WHERE tick>=? ORDER BY tick ASC LIMIT ?",
                (since, limit)).fetchall()
        finally:
            c.close()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["gene_means"] = json.loads(d["gene_means"])
            except Exception:
                d["gene_means"] = {}
            out.append(d)
        return out

    def recent_events(self, limit: int = 60) -> list[dict[str, Any]]:
        c = self._read_conn()
        try:
            rows = c.execute("SELECT tick,type,data FROM events ORDER BY id DESC LIMIT ?",
                             (limit,)).fetchall()
        finally:
            c.close()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def agent_genealogy(self, agent_id: int, depth: int = 12) -> dict[str, Any]:
        c = self._read_conn()
        try:
            def fetch(aid):
                r = c.execute("SELECT * FROM agents WHERE agent_id=?", (aid,)).fetchone()
                return dict(r) if r else None
            node = fetch(agent_id)
            if not node:
                return {}
            # ancestors
            ancestors = []
            cur = node
            for _ in range(depth):
                pid = cur.get("parent_id")
                if not pid:
                    break
                parent = fetch(pid)
                if not parent:
                    break
                ancestors.append(parent)
                cur = parent
            children = [dict(r) for r in c.execute(
                "SELECT * FROM agents WHERE parent_id=? LIMIT 50", (agent_id,)).fetchall()]
        finally:
            c.close()
        for d in [node, *ancestors, *children]:
            if d and isinstance(d.get("genes"), str):
                try:
                    d["genes"] = json.loads(d["genes"])
                except Exception:
                    pass
        return {"agent": node, "ancestors": ancestors, "children": children}

    def summary(self) -> dict[str, Any]:
        c = self._read_conn()
        try:
            total = c.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            deaths = c.execute("SELECT COUNT(*) FROM agents WHERE death_tick IS NOT NULL").fetchone()[0]
            last = c.execute("SELECT * FROM stats ORDER BY tick DESC LIMIT 1").fetchone()
        finally:
            c.close()
        return {
            "total_agents_ever": total,
            "total_deaths": deaths,
            "last_stats": dict(last) if last else None,
        }
