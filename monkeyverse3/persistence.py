"""The planet's written history — one SQLite database per world.

Beyond genealogy, time-series, species and milestones (v2), v3 adds a durable,
filterable log of individual **interactions** — the raw material for the
Interacciones tab. To keep the database from growing forever on a 24/7 box, the
interactions table (like frames and snapshots) keeps only the most recent N
rows; the coarser story survives indefinitely in the stats/milestones/species
tables, which are already periodic summaries, not per-tick logs.
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
    agent_id INTEGER PRIMARY KEY, parent_id INTEGER, generation INTEGER,
    species_id INTEGER, birth_tick INTEGER, birth_x INTEGER, birth_y INTEGER,
    genes TEXT, death_tick INTEGER, death_age INTEGER, death_x INTEGER,
    death_y INTEGER, death_cause TEXT
);
CREATE INDEX IF NOT EXISTS idx_agents_parent ON agents(parent_id);
CREATE INDEX IF NOT EXISTS idx_agents_species ON agents(species_id);

CREATE TABLE IF NOT EXISTS stats (
    tick INTEGER PRIMARY KEY, population INTEGER, births INTEGER, deaths INTEGER,
    avg_energy REAL, avg_age REAL, avg_generation REAL, max_generation INTEGER,
    species INTEGER, herbivores INTEGER, carnivores INTEGER,
    language_diversity REAL, genetic_diversity REAL, pher_activity REAL,
    veg_total REAL, weather TEXT, climate REAL, data TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER, type TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER, kind TEXT, label TEXT, data TEXT
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER, agent_id INTEGER,
    target_id INTEGER, type TEXT, signal INTEGER, result TEXT,
    energy_delta REAL, x INTEGER, y INTEGER
);
CREATE INDEX IF NOT EXISTS idx_inter_tick ON interactions(tick);
CREATE INDEX IF NOT EXISTS idx_inter_agent ON interactions(agent_id);
CREATE INDEX IF NOT EXISTS idx_inter_type ON interactions(type);

CREATE TABLE IF NOT EXISTS frames (
    tick INTEGER PRIMARY KEY, created REAL, data TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    tick INTEGER PRIMARY KEY, created REAL, blob BLOB
);
"""


class Persistence:
    def __init__(self, db_path: str, keep_snapshots: int = 3, keep_frames: int = 600,
                 keep_interactions: int = 20000):
        self.db_path = db_path
        self.keep_snapshots = keep_snapshots
        self.keep_frames = keep_frames
        self.keep_interactions = keep_interactions
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._births: list = []
        self._deaths: list = []
        self._stats: list = []
        self._events: list = []
        self._milestones: list = []
        self._interactions: list = []
        self._tick_count = 0

    # ------------------------------------------------------------- write side
    def log_birth(self, r):
        self._births.append((r["agent_id"], r["parent_id"], r["generation"], r["species_id"],
                             r["birth_tick"], r["birth_x"], r["birth_y"], json.dumps(r["genes"])))

    def log_death(self, aid, tick, age, gen, x, y, cause):
        self._deaths.append((tick, age, x, y, cause, aid))

    def log_stats(self, r):
        extra = {"gene_means": r["gene_means"], "deaths_starve": r["deaths_starve"],
                 "deaths_pred": r["deaths_pred"], "deaths_age": r["deaths_age"],
                 "deaths_disaster": r["deaths_disaster"]}
        self._stats.append((r["tick"], r["population"], r["births"], r["deaths"], r["avg_energy"],
                            r["avg_age"], r["avg_generation"], r["max_generation"], r["species"],
                            r["herbivores"], r["carnivores"], r["language_diversity"],
                            r["genetic_diversity"], r["pher_activity"], r["veg_total"],
                            r["weather"], r["climate"], json.dumps(extra)))

    def log_event(self, tick, type_, data):
        self._events.append((tick, type_, json.dumps(data)))

    def log_milestone(self, m):
        self._milestones.append((m["tick"], m["kind"], m.get("label", ""), json.dumps(m.get("data", {}))))

    def log_interaction(self, ev: dict[str, Any]):
        self._interactions.append((ev["tick"], ev["agent_id"], ev.get("target_id"), ev["type"],
                                   ev.get("signal"), ev.get("result", ""), ev.get("energy_delta", 0.0),
                                   ev.get("x", 0), ev.get("y", 0)))
        self._tick_count += 1

    def flush(self):
        with self._lock:
            if self._births:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO agents (agent_id,parent_id,generation,species_id,"
                    "birth_tick,birth_x,birth_y,genes) VALUES (?,?,?,?,?,?,?,?)", self._births)
                self._births.clear()
            if self._deaths:
                self.conn.executemany(
                    "UPDATE agents SET death_tick=?,death_age=?,death_x=?,death_y=?,death_cause=? "
                    "WHERE agent_id=?", self._deaths)
                self._deaths.clear()
            if self._stats:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self._stats)
                self._stats.clear()
            if self._events:
                self.conn.executemany("INSERT INTO events (tick,type,data) VALUES (?,?,?)", self._events)
                self._events.clear()
            if self._milestones:
                self.conn.executemany(
                    "INSERT INTO milestones (tick,kind,label,data) VALUES (?,?,?,?)", self._milestones)
                self._milestones.clear()
            if self._interactions:
                self.conn.executemany(
                    "INSERT INTO interactions (tick,agent_id,target_id,type,signal,result,"
                    "energy_delta,x,y) VALUES (?,?,?,?,?,?,?,?,?)", self._interactions)
                self._interactions.clear()
            if self._tick_count > 400:   # bound growth periodically, not every flush
                self.conn.execute(
                    "DELETE FROM interactions WHERE id NOT IN "
                    "(SELECT id FROM interactions ORDER BY id DESC LIMIT ?)", (self.keep_interactions,))
                self._tick_count = 0
            self.conn.commit()

    def save_frame(self, tick, frame):
        self.flush()
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO frames (tick,created,data) VALUES (?,?,?)",
                              (tick, time.time(), json.dumps(frame)))
            self.conn.execute("DELETE FROM frames WHERE tick NOT IN "
                              "(SELECT tick FROM frames ORDER BY tick DESC LIMIT ?)", (self.keep_frames,))
            self.conn.commit()

    def save_snapshot(self, tick, snapshot):
        self.flush()
        blob = pickle.dumps(snapshot, protocol=pickle.HIGHEST_PROTOCOL)
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO snapshots (tick,created,blob) VALUES (?,?,?)",
                              (tick, time.time(), blob))
            self.conn.execute("DELETE FROM snapshots WHERE tick NOT IN "
                              "(SELECT tick FROM snapshots ORDER BY tick DESC LIMIT ?)", (self.keep_snapshots,))
            self.conn.commit()

    def load_latest_snapshot(self):
        with self._lock:
            row = self.conn.execute("SELECT blob FROM snapshots ORDER BY tick DESC LIMIT 1").fetchone()
        return pickle.loads(row[0]) if row else None

    def close(self):
        try:
            self.flush(); self.conn.close()
        except Exception:
            pass

    # -------------------------------------------------------------- read side
    def _rc(self):
        c = sqlite3.connect(self.db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def stats_series(self, since=0, limit=4000):
        c = self._rc()
        try:
            rows = c.execute("SELECT * FROM stats WHERE tick>=? ORDER BY tick ASC LIMIT ?",
                             (since, limit)).fetchall()
        finally:
            c.close()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d.update(json.loads(d.pop("data")))
            except Exception:
                pass
            out.append(d)
        return out

    def milestones_list(self, limit=200):
        c = self._rc()
        try:
            rows = c.execute("SELECT tick,kind,label,data FROM milestones ORDER BY tick ASC LIMIT ?",
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

    def recent_events(self, limit=80):
        c = self._rc()
        try:
            rows = c.execute("SELECT tick,type,data FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
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

    def interactions_query(self, agent_id=None, species_map=None, itype=None, signal=None,
                           limit=150) -> list[dict[str, Any]]:
        """Filter by agent, interaction type and/or symbol. `species_map` (id->species_id)
        lets the caller filter by species without denormalising the table."""
        q = "SELECT * FROM interactions WHERE 1=1"
        args: list[Any] = []
        if agent_id is not None:
            q += " AND (agent_id=? OR target_id=?)"
            args += [agent_id, agent_id]
        if itype:
            q += " AND type=?"
            args.append(itype)
        if signal is not None:
            q += " AND signal=?"
            args.append(signal)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        c = self._rc()
        try:
            rows = [dict(r) for r in c.execute(q, args).fetchall()]
        finally:
            c.close()
        if species_map:
            rows = [r for r in rows if species_map.get(r["agent_id"]) is not None]
        return rows

    def frame_ticks(self):
        c = self._rc()
        try:
            rows = c.execute("SELECT tick FROM frames ORDER BY tick ASC").fetchall()
        finally:
            c.close()
        return [r[0] for r in rows]

    def get_frame(self, tick):
        c = self._rc()
        try:
            row = c.execute("SELECT data FROM frames WHERE tick<=? ORDER BY tick DESC LIMIT 1",
                            (tick,)).fetchone()
            if row is None:
                row = c.execute("SELECT data FROM frames ORDER BY tick ASC LIMIT 1").fetchone()
        finally:
            c.close()
        return json.loads(row[0]) if row else None

    def species_tree(self):
        c = self._rc()
        try:
            rows = c.execute(
                "SELECT species_id, COUNT(*) n, MIN(birth_tick) first_seen, "
                "SUM(CASE WHEN death_tick IS NULL THEN 1 ELSE 0 END) alive "
                "FROM agents GROUP BY species_id ORDER BY n DESC LIMIT 60").fetchall()
        finally:
            c.close()
        return [dict(r) for r in rows]

    def agent_genealogy(self, agent_id, depth=14):
        c = self._rc()
        try:
            def fetch(aid):
                r = c.execute("SELECT * FROM agents WHERE agent_id=?", (aid,)).fetchone()
                return dict(r) if r else None
            node = fetch(agent_id)
            if not node:
                return {}
            ancestors, cur = [], node
            for _ in range(depth):
                pid = cur.get("parent_id")
                if not pid:
                    break
                p = fetch(pid)
                if not p:
                    break
                ancestors.append(p); cur = p
            children = [dict(r) for r in c.execute(
                "SELECT * FROM agents WHERE parent_id=? LIMIT 60", (agent_id,)).fetchall()]
        finally:
            c.close()
        for d in [node, *ancestors, *children]:
            if d and isinstance(d.get("genes"), str):
                try:
                    d["genes"] = json.loads(d["genes"])
                except Exception:
                    pass
        return {"agent": node, "ancestors": ancestors, "children": children}

    def summary(self):
        c = self._rc()
        try:
            total = c.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            deaths = c.execute("SELECT COUNT(*) FROM agents WHERE death_tick IS NOT NULL").fetchone()[0]
            spp = c.execute("SELECT COUNT(DISTINCT species_id) FROM agents").fetchone()[0]
            ms = c.execute("SELECT COUNT(*) FROM milestones").fetchone()[0]
            inter = c.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
            last = c.execute("SELECT * FROM stats ORDER BY tick DESC LIMIT 1").fetchone()
        finally:
            c.close()
        return {"total_agents_ever": total, "total_deaths": deaths, "species_ever": spp,
                "milestones": ms, "interactions_logged": inter,
                "last_stats": dict(last) if last else None}

    def export_all(self, interaction_limit=5000) -> dict[str, Any]:
        """Everything needed for an external-analysis dump."""
        c = self._rc()
        try:
            agents = [dict(r) for r in c.execute("SELECT * FROM agents").fetchall()]
            interactions = [dict(r) for r in c.execute(
                "SELECT * FROM interactions ORDER BY id DESC LIMIT ?", (interaction_limit,)).fetchall()]
            stats = [dict(r) for r in c.execute("SELECT * FROM stats ORDER BY tick ASC").fetchall()]
            milestones = [dict(r) for r in c.execute("SELECT * FROM milestones ORDER BY tick ASC").fetchall()]
        finally:
            c.close()
        for a in agents:
            if isinstance(a.get("genes"), str):
                try:
                    a["genes"] = json.loads(a["genes"])
                except Exception:
                    pass
        for m in milestones:
            if isinstance(m.get("data"), str):
                try:
                    m["data"] = json.loads(m["data"])
                except Exception:
                    pass
        for s in stats:
            if isinstance(s.get("data"), str):
                try:
                    s.update(json.loads(s.pop("data")))
                except Exception:
                    pass
        return {"agents": agents, "interactions": interactions, "stats": stats, "milestones": milestones}
