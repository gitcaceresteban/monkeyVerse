"""Structured, durable logging for a Simple Island run.

Every observable event (birth, death, move, eat, sound emitted/heard,
interaction, follow, avoid, reproduction attempt/success, ...) and every periodic
metrics snapshot is written to one SQLite database per run. Writes are batched so
a slow 24/7 box on a Raspberry Pi isn't hammered every tick, and the event log is
capped to the most recent N rows so the file can't grow without bound.

The store only *records*; it never interprets. Exports (full-run JSON, events CSV,
metrics CSV, genealogy, living agents) turn that record into the downloadable
artefacts the spec asks for.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER, type TEXT, agent INTEGER, target INTEGER,
    x REAL, y REAL, sound INTEGER, e_before REAL, e_after REAL,
    result TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);

CREATE TABLE IF NOT EXISTS metrics (
    tick INTEGER PRIMARY KEY, data TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY, value TEXT
);
"""

EVENT_COLS = ["tick", "type", "agent", "target", "x", "y", "sound",
              "e_before", "e_after", "result", "extra"]


class LoggingStore:
    def __init__(self, path: str, max_events: int = 200_000, flush_every: float = 2.0):
        self.path = path
        self.max_events = max_events
        self.flush_every = flush_every
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._ev_buf: list[tuple] = []
        self._metric_buf: list[tuple] = []
        self._last_flush = time.time()
        self._events_written = 0
        self._trim_counter = 0

    # ---------------------------------------------------------------- meta
    def set_meta(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                               (key, json.dumps(value, default=_json_default)))
            self._conn.commit()

    def get_meta(self, key: str, default=None):
        cur = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else default

    # ---------------------------------------------------------------- writes
    def log_event(self, ev: dict[str, Any]) -> None:
        row = (
            ev.get("tick"), ev.get("type"), ev.get("agent"), ev.get("target"),
            ev.get("x"), ev.get("y"), ev.get("sound"),
            ev.get("e_before"), ev.get("e_after"), ev.get("result"),
            json.dumps(ev.get("extra") or {}, default=_json_default),
        )
        with self._lock:
            self._ev_buf.append(row)
            self._maybe_flush()

    def log_metrics(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._metric_buf.append((row.get("tick"), json.dumps(row, default=_json_default)))
            self._maybe_flush()

    def _maybe_flush(self) -> None:
        now = time.time()
        if (len(self._ev_buf) + len(self._metric_buf) >= 256
                or now - self._last_flush >= self.flush_every):
            self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self._ev_buf:
            self._conn.executemany(
                f"INSERT INTO events({','.join(EVENT_COLS)}) "
                f"VALUES({','.join('?' for _ in EVENT_COLS)})", self._ev_buf)
            self._events_written += len(self._ev_buf)
            self._ev_buf.clear()
        if self._metric_buf:
            self._conn.executemany(
                "INSERT OR REPLACE INTO metrics(tick, data) VALUES(?, ?)", self._metric_buf)
            self._metric_buf.clear()
        self._conn.commit()
        self._last_flush = time.time()
        # occasionally trim the event log so the DB stays bounded on a 24/7 box
        self._trim_counter += 1
        if self._trim_counter % 20 == 0:
            self._trim_events()

    def _trim_events(self) -> None:
        cur = self._conn.execute("SELECT COUNT(*) FROM events")
        n = cur.fetchone()[0]
        if n > self.max_events:
            cutoff = self._conn.execute(
                "SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?",
                (self.max_events,)).fetchone()
            if cutoff:
                self._conn.execute("DELETE FROM events WHERE id <= ?", (cutoff[0],))
                self._conn.commit()

    # ---------------------------------------------------------------- reads
    def recent_events(self, limit: int = 200, type_: Optional[str] = None,
                      agent: Optional[int] = None) -> list[dict[str, Any]]:
        self.flush()
        q = "SELECT " + ",".join(EVENT_COLS) + " FROM events"
        conds, args = [], []
        if type_:
            conds.append("type=?"); args.append(type_)
        if agent is not None:
            conds.append("agent=?"); args.append(agent)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(r) -> dict[str, Any]:
        d = dict(zip(EVENT_COLS, r))
        try:
            d["extra"] = json.loads(d["extra"]) if d["extra"] else {}
        except (json.JSONDecodeError, TypeError):
            d["extra"] = {}
        return d

    def all_metrics(self) -> list[dict[str, Any]]:
        self.flush()
        with self._lock:
            rows = self._conn.execute("SELECT data FROM metrics ORDER BY tick").fetchall()
        return [json.loads(r[0]) for r in rows]

    def all_events(self) -> list[dict[str, Any]]:
        self.flush()
        with self._lock:
            rows = self._conn.execute(
                "SELECT " + ",".join(EVENT_COLS) + " FROM events ORDER BY id").fetchall()
        return [self._row_to_event(r) for r in rows]

    # ---------------------------------------------------------------- exports
    def export_events_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(EVENT_COLS)
        for e in self.all_events():
            w.writerow([e["tick"], e["type"], e["agent"], e["target"], e["x"], e["y"],
                        e["sound"], e["e_before"], e["e_after"], e["result"],
                        json.dumps(e["extra"], ensure_ascii=False)])
        return buf.getvalue()

    def export_metrics_csv(self) -> str:
        rows = self.all_metrics()
        buf = io.StringIO()
        if not rows:
            return ""
        # flatten gene_means into columns
        cols: list[str] = []
        flat_rows = []
        for r in rows:
            fr = {k: v for k, v in r.items() if k != "gene_means"}
            for gk, gv in (r.get("gene_means") or {}).items():
                fr[f"gene_{gk}"] = gv
            flat_rows.append(fr)
            for k in fr:
                if k not in cols:
                    cols.append(k)
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for fr in flat_rows:
            w.writerow(fr)
        return buf.getvalue()

    def export_genealogy(self) -> dict[str, Any]:
        """Reconstruct the family tree from birth/death events."""
        births = {}
        for e in self.all_events():
            if e["type"] == "agent_birth":
                ex = e["extra"]
                births[e["agent"]] = {
                    "id": e["agent"], "sex": ex.get("sex"),
                    "generation": ex.get("generation", 0),
                    "parent_a": ex.get("parent_a", 0), "parent_b": ex.get("parent_b", 0),
                    "birth_tick": e["tick"], "genes": ex.get("genes"),
                    "death_tick": None, "death_cause": None, "children": [],
                }
            elif e["type"] == "agent_death":
                b = births.get(e["agent"])
                if b:
                    b["death_tick"] = e["tick"]
                    b["death_cause"] = e["result"]
                    b["death_age"] = e["extra"].get("age")
                    b["n_children"] = e["extra"].get("children")
        for b in births.values():
            for p in (b["parent_a"], b["parent_b"]):
                if p and p in births:
                    births[p]["children"].append(b["id"])
        return {"agents": list(births.values()), "count": len(births)}

    # ---------------------------------------------------------------- lifecycle
    def close(self) -> None:
        with self._lock:
            self._flush_locked()
            self._conn.close()


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)
