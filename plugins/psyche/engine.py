"""psyche.engine — her state over time (inner-life.md §2, §17): the single writer of psyche.db.

One Engine per character, living inside her Hermes process. Time is a fixed grid of ticks
(tick_s, default 60 s); every tick is a deterministic function of (state, the appraisals due at that
tick, a seeded noise draw), so the same events always rebuild the same state: replay == live, and a
stop of any length is just the missed ticks run in one go (fast-forward, world time continuous).

    load()            restore the last snapshot, then step through every tick up to now
    step_to(t)        advance the grid to time t (applies appraisals at their tick)
    on_turn(...)      record a turn event, queue appraisal A (background thread, never waited for)
    record_appraisal  append A's result; it is applied at the next tick (or right away when live)
    state_block()     the 【她現在】 lines for her prompt (expression layer, minimal in 0.5.0)
"""
from __future__ import annotations

import json
import logging
import queue
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import model
from . import appraisal as A

logger = logging.getLogger("psyche")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL NOT NULL, tick INTEGER NOT NULL,
    kind TEXT NOT NULL, counterpart TEXT, payload TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);
CREATE TABLE IF NOT EXISTS appraisals(id INTEGER PRIMARY KEY, at REAL NOT NULL, turn_id TEXT, counterpart TEXT,
    platform TEXT, raw TEXT, data TEXT, error TEXT, ms REAL, applied_tick INTEGER);
CREATE INDEX IF NOT EXISTS idx_appraisals_at ON appraisals(at);
CREATE TABLE IF NOT EXISTS instances(id TEXT PRIMARY KEY, born_at REAL NOT NULL, born_tick INTEGER NOT NULL,
    type TEXT NOT NULL, target TEXT, cause TEXT, appraisal_id INTEGER, intensity0 REAL NOT NULL,
    half_life_h REAL NOT NULL, pad TEXT NOT NULL, stack_key TEXT, loop_id TEXT,
    resolved_at REAL, resolved_tick INTEGER, resolved_by TEXT);
CREATE TABLE IF NOT EXISTS loops(id TEXT PRIMARY KEY, what TEXT NOT NULL, origin TEXT, cue_time TEXT,
    importance REAL, state TEXT NOT NULL, created_at REAL NOT NULL, closed_at REAL, counterpart TEXT);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, at REAL NOT NULL, tick INTEGER NOT NULL, state TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_snapshots_tick ON snapshots(tick);
CREATE TABLE IF NOT EXISTS params(id INTEGER PRIMARY KEY, at REAL NOT NULL, version TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY CHECK(id = 1), pid INTEGER, heartbeat REAL);
"""

FADE = 0.02           # an instance below this intensity is dead
OWNER_STALE_S = 20.0


class Engine:
    def __init__(self, home: Path, character_id: str, cfg: Dict[str, Any], *, db_path: Optional[Path] = None,
                 now_fn: Callable[[], float] = time.time, llm: Any = None, term_fn: Optional[Callable[[], str]] = None,
                 memory_db: Optional[Path] = None) -> None:
        self.home = Path(home)
        self.char = character_id
        self.cfg = cfg
        self.now_fn = now_fn
        self.llm = llm
        self.term_fn = term_fn or (lambda: "製作人")
        self.memory_db = memory_db
        self.tick_s = int(cfg["time"]["tick_s"])
        self.snap_every = max(1, int(cfg["time"]["snapshot_interval_min"] * 60 // self.tick_s))
        self.derived = model.derive(cfg["character"], cfg["time"])
        self.tz = timezone(timedelta(hours=float(cfg["time"].get("timezone_offset_h", 8))))
        self.db_path = Path(db_path) if db_path else self.home / "psyche.db"
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()
        self.owner = False
        self._stop = threading.Event()
        self._tick_thread: Optional[threading.Thread] = None
        self._worker: Optional[threading.Thread] = None
        self._q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.recent: List[Tuple[str, str]] = []
        self._pending_annot: List[Tuple[str, str, float]] = []  # (turn_id, patch json, give-up time): the observe may land after A
        # --- state (everything a snapshot holds) ---
        self.tick = 0
        self.affect = {"pos": self.derived["mu_pos_base"], "neg": self.derived["mu_neg_base"], "ar": self.derived["mu_ar_base"]}
        self.mood: Tuple[float, float, float] = tuple(self.derived["mood_default"])  # type: ignore[assignment]
        self.energy = 0.6
        self.instances: Dict[str, Dict[str, Any]] = {}
        self.loops: Dict[str, Dict[str, Any]] = {}
        self.stack_counts: Dict[str, int] = {}
        self.last_block: Dict[str, Any] = {}

    # ------------------------------------------------------------------ time helpers
    def tick_of(self, t: float) -> int:
        return int(t // self.tick_s)

    def time_of(self, k: int) -> float:
        return float(k * self.tick_s)

    def local_hour(self, t: float) -> float:
        d = datetime.fromtimestamp(t, self.tz)
        return d.hour + d.minute / 60.0

    def _rng(self, k: int) -> random.Random:
        day = datetime.fromtimestamp(self.time_of(k), self.tz).strftime("%Y-%m-%d")
        return random.Random(f"{self.char}:{day}:{k}")

    # ------------------------------------------------------------------ persistence
    def _event(self, kind: str, payload: Dict[str, Any], t: Optional[float] = None, counterpart: str = "") -> None:
        t = self.now_fn() if t is None else t
        self.conn.execute("INSERT INTO events(at, tick, kind, counterpart, payload) VALUES (?,?,?,?,?)",
                          (t, self.tick_of(t), kind, counterpart, json.dumps(payload, ensure_ascii=False)))
        self.conn.commit()

    def snapshot_state(self) -> Dict[str, Any]:
        return {"tick": self.tick, "t": self.time_of(self.tick), "affect": dict(self.affect), "mood": list(self.mood),
                "energy": self.energy, "instances": list(self.instances.values()), "loops": list(self.loops.values()),
                "stack_counts": dict(self.stack_counts), "last_block": self.last_block}

    def _restore(self, state: Dict[str, Any]) -> None:
        self.tick = int(state["tick"])
        self.affect = dict(state["affect"])
        self.mood = tuple(state["mood"])  # type: ignore[assignment]
        self.energy = float(state.get("energy", 0.6))
        self.instances = {i["id"]: i for i in state.get("instances", [])}
        self.loops = {l["id"]: l for l in state.get("loops", [])}
        self.stack_counts = dict(state.get("stack_counts", {}))
        self.last_block = dict(state.get("last_block", {}))

    def snapshot(self) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO snapshots(at, tick, state) VALUES (?,?,?)",
                              (self.time_of(self.tick), self.tick, json.dumps(self.snapshot_state(), ensure_ascii=False)))
            self.conn.commit()

    def latest_snapshot(self) -> Optional[Dict[str, Any]]:
        r = self.conn.execute("SELECT state FROM snapshots ORDER BY tick DESC, id DESC LIMIT 1").fetchone()
        return json.loads(r[0]) if r else None

    def acquire_owner(self, pid: int) -> bool:
        now = self.now_fn()
        r = self.conn.execute("SELECT pid, heartbeat FROM owner WHERE id = 1").fetchone()
        if r and r[0] != pid and r[1] and now - float(r[1]) < OWNER_STALE_S:
            return False
        self.conn.execute("INSERT INTO owner(id, pid, heartbeat) VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET pid=excluded.pid, heartbeat=excluded.heartbeat", (pid, now))
        self.conn.commit()
        return True

    def heartbeat(self, pid: int) -> None:
        self.conn.execute("UPDATE owner SET heartbeat = ? WHERE id = 1 AND pid = ?", (self.now_fn(), pid))
        self.conn.commit()

    # ------------------------------------------------------------------ load / replay
    def load(self) -> None:
        """Restore the last snapshot (or start fresh at the first tick) and run every tick to now:
        appraisals already applied re-apply at their recorded tick (replay), pending ones at the first
        tick after they landed; the noise comes from the seeded grid, so the result is the same whether
        she was running or stopped meanwhile."""
        from . import config as C
        with self.lock:
            snap = self.latest_snapshot()
            now = self.now_fn()
            if snap:
                self._restore(snap)
            else:
                self.tick = self.tick_of(now) - 1
                self.energy = model.energy_at(self.local_hour(now), self.cfg["character"].get("chronotype", 0.0))
            v = C.version(self.cfg)
            r = self.conn.execute("SELECT version FROM params ORDER BY id DESC LIMIT 1").fetchone()
            if not r or r[0] != v:
                self.conn.execute("INSERT INTO params(at, version, data) VALUES (?,?,?)",
                                  (now, v, json.dumps({k: self.cfg.get(k) for k in ("character", "time", "impact", "expression")}, ensure_ascii=False)))
                self.conn.commit()
            gap = self.tick_of(now) - self.tick
            self._event("start", {"from_tick": self.tick, "gap_ticks": gap, "snapshot": bool(snap)}, now)
            self.step_to(now, snapshots=False)
            self.snapshot()

    def _due_appraisals(self, after_tick: int, upto_tick: int) -> List[Tuple[int, sqlite3.Row]]:
        """(tick to apply at, row) for appraisals applied after after_tick or still pending, in order."""
        rows = self.conn.execute(
            "SELECT id, at, data, counterpart, turn_id, applied_tick FROM appraisals WHERE data IS NOT NULL AND error IS NULL "
            "AND (applied_tick IS NULL OR applied_tick > ?) ORDER BY COALESCE(applied_tick, 0), at, id", (after_tick,)).fetchall()
        out = []
        for r in rows:
            k = int(r[5]) if r[5] is not None else max(after_tick + 1, self.tick_of(float(r[1])))
            if k <= upto_tick:
                out.append((k, r))
        out.sort(key=lambda x: (x[0], x[1][0]))
        return out

    def step_to(self, t: float, snapshots: bool = True) -> int:
        """Advance the grid to time t. Returns the number of ticks run."""
        with self.lock:
            target = self.tick_of(t)
            if target <= self.tick:
                return 0
            due = self._due_appraisals(self.tick, target)
            di = 0
            n = 0
            for k in range(self.tick + 1, target + 1):
                self._step_one(k)
                # an appraisal lands AFTER the step of its tick — the same order as the live path in
                # record_appraisal (step_to(at), then apply), so replay and fast-forward match it exactly
                while di < len(due) and due[di][0] <= k:
                    self._apply_appraisal(due[di][1], k)
                    di += 1
                n += 1
                if snapshots and k % self.snap_every == 0:
                    self.snapshot()
            return n

    # ------------------------------------------------------------------ one tick
    def active(self, t: Optional[float] = None) -> List[Dict[str, Any]]:
        t = self.time_of(self.tick) if t is None else t
        out = []
        for inst in self.instances.values():
            if inst.get("resolved_at") is not None:
                continue
            I = model.decayed(inst["intensity0"], inst["half_life_h"], (t - inst["born_at"]) / 3600.0)
            if I >= FADE:
                d = dict(inst)
                d["intensity"] = I
                out.append(d)
        out.sort(key=lambda i: -i["intensity"])
        return out

    def _step_one(self, k: int) -> None:
        t = self.time_of(k)
        dt_h = self.tick_s / 3600.0
        d = self.derived
        self.energy = model.energy_at(self.local_hour(t), float(self.cfg["character"].get("chronotype", 0.0)))
        act = self.active(t)
        pos = sum(i["intensity"] for i in act if i["type"] in model.POSITIVE)
        neg = sum(i["intensity"] for i in act if i["type"] in model.NEGATIVE)
        ar = sum(i["intensity"] * abs(i["pad"][1]) for i in act)
        mu_pos = min(1.0, d["mu_pos_base"] + min(0.6, pos))
        mu_neg = min(1.0, d["mu_neg_base"] + min(0.6, neg))
        mu_ar = min(1.0, d["mu_ar_base"] * (0.6 + 0.8 * self.energy) + min(0.5, ar))
        rng = self._rng(k)
        z = [rng.gauss(0, 1) for _ in range(3)]
        self.affect["pos"] = model.ou_step(self.affect["pos"], mu_pos, d["theta_affect"], d["sigma_affect"], dt_h, z[0])
        self.affect["neg"] = model.ou_step(self.affect["neg"], mu_neg, d["theta_affect"], d["sigma_affect"], dt_h, z[1])
        self.affect["ar"] = model.ou_step(self.affect["ar"], mu_ar, d["theta_affect"], d["sigma_affect"] * 0.5, dt_h, z[2])
        center = None
        if act:
            w = sum(i["intensity"] for i in act)
            center = tuple(sum(i["intensity"] * i["pad"][j] for i in act) / w for j in range(3))  # type: ignore[assignment]
        tc = self.cfg["time"]
        self.mood = model.mood_step(self.mood, center, tuple(d["mood_default"]), dt_h, float(tc["mood_regress_tau_h"]),
                                    float(tc["mood_rise_max"]), float(tc["mood_fall_max"]))
        # death by fading
        for inst in self.instances.values():
            if inst.get("resolved_at") is None:
                I = model.decayed(inst["intensity0"], inst["half_life_h"], (t - inst["born_at"]) / 3600.0)
                if I < FADE:
                    inst["resolved_at"], inst["resolved_tick"], inst["resolved_by"] = t, k, "faded"
                    self.conn.execute("UPDATE instances SET resolved_at=?, resolved_tick=?, resolved_by=? WHERE id=?",
                                      (t, k, "faded", inst["id"]))
        self.tick = k

    # ------------------------------------------------------------------ B: apply an appraisal
    def _apply_appraisal(self, row: Any, k: int) -> None:
        aid, _at, data_s, counterpart, turn_id = row[0], row[1], row[2], row[3], row[4]
        t = self.time_of(k)
        data = json.loads(data_s)
        term = counterpart or self.term_fn()
        imp = self.cfg["impact"]
        born: List[str] = []
        touched: List[Tuple[str, float]] = []
        for n, ev in enumerate(data.get("events", [])):
            ev = dict(ev)
            ev["counterpart"] = term
            act = self.active(t)
            for iid, frac in model.resolutions(ev["event_kind"], ev.get("loop_id"), act).items():
                self._resolve(iid, frac, t, k, ev["event_kind"])
                touched.append((iid, frac))
            act = self.active(t)
            new = model.appraise_to_instances(ev, self.derived, imp, act, self.stack_counts,
                                              mood_valence=self.mood[0], bond=float(imp.get("bond_default", 0.5)))
            for i, inst in enumerate(new):
                iid = f"em_{k}_{aid}_{n}_{i}"
                rec = {"id": iid, "born_at": t, "born_tick": k, "type": inst["type"], "target": term, "cause": inst["cause"],
                       "appraisal_id": aid, "intensity0": inst["intensity0"], "half_life_h": inst["half_life_h"],
                       "pad": list(inst["pad"]), "stack_key": inst["stack_key"], "loop_id": inst.get("loop_id"),
                       "resolved_at": None, "resolved_tick": None, "resolved_by": None}
                self.instances[iid] = rec
                self.stack_counts[inst["stack_key"]] = self.stack_counts.get(inst["stack_key"], 0) + 1
                self.conn.execute("INSERT OR REPLACE INTO instances(id, born_at, born_tick, type, target, cause, appraisal_id, "
                                  "intensity0, half_life_h, pad, stack_key, loop_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (iid, t, k, rec["type"], term, rec["cause"], aid, rec["intensity0"], rec["half_life_h"],
                                   json.dumps(rec["pad"]), rec["stack_key"], rec["loop_id"]))
                born.append(iid)
        loops = data.get("loops") or {}
        for i, l in enumerate(loops.get("new") or []):
            lid = f"ol_{k}_{aid}_{i}"
            rec = {"id": lid, "what": l["what"], "origin": l.get("origin", "counterpart_said"), "cue_time": l.get("cue_time"),
                   "importance": float(l.get("importance", 0.5)), "state": "waiting", "created_at": t, "closed_at": None,
                   "counterpart": term}
            self.loops[lid] = rec
            self.conn.execute("INSERT OR REPLACE INTO loops(id, what, origin, cue_time, importance, state, created_at, counterpart) "
                              "VALUES (?,?,?,?,?,?,?,?)", (lid, rec["what"], rec["origin"], rec["cue_time"], rec["importance"], "waiting", t, term))
        for lid in loops.get("closed") or []:
            if lid in self.loops and self.loops[lid]["state"] != "closed":
                self.loops[lid]["state"], self.loops[lid]["closed_at"] = "closed", t
                self.conn.execute("UPDATE loops SET state='closed', closed_at=? WHERE id=?", (t, lid))
        self.conn.execute("UPDATE appraisals SET applied_tick=? WHERE id=?", (k, aid))
        self.conn.execute("INSERT INTO events(at, tick, kind, counterpart, payload) VALUES (?,?,?,?,?)",
                          (t, k, "appraisal_applied", term, json.dumps({"appraisal_id": aid, "born": born, "resolved": touched,
                                                                        "events": [e.get("event_kind") for e in data.get("events", [])]}, ensure_ascii=False)))
        self.conn.commit()
        if turn_id and self.memory_db and data.get("events"):
            self._annotate_memory(turn_id, data["events"], born)

    def _resolve(self, iid: str, frac: float, t: float, k: int, by: str) -> None:
        inst = self.instances.get(iid)
        if not inst or inst.get("resolved_at") is not None:
            return
        I = model.decayed(inst["intensity0"], inst["half_life_h"], (t - inst["born_at"]) / 3600.0)
        if frac <= 0.0 or I * frac < FADE:
            inst["resolved_at"], inst["resolved_tick"], inst["resolved_by"] = t, k, by
            self.conn.execute("UPDATE instances SET resolved_at=?, resolved_tick=?, resolved_by=? WHERE id=?", (t, k, by, iid))
        else:  # partial repair: the emotion restarts from the reduced level
            inst["intensity0"], inst["born_at"], inst["born_tick"] = round(I * frac, 4), t, k
            self.conn.execute("UPDATE instances SET intensity0=?, born_at=?, born_tick=?, resolved_by=? WHERE id=?",
                              (inst["intensity0"], t, k, f"reduced:{by}", iid))

    def _annotate_memory(self, turn_id: str, events: List[Dict[str, Any]], born: List[str]) -> None:
        """KeepsakeDB 0.3.0 alignment: valence / arousal / instance ids onto the memories of this turn
        (meta only, by turn id). Direct SQL on her memory file: json_patch, no re-embedding."""
        try:
            if not Path(self.memory_db).exists():
                return
            v = sum(e["v"] * e["R"] for e in events) / max(1e-6, sum(e["R"] for e in events))
            arousal = max((self.instances[i]["intensity0"] for i in born), default=0.0)
            patch = json.dumps({"valence": round(v, 3), "arousal": round(arousal, 3), "instance_ids": born}, ensure_ascii=False)
            if self._annotate_rows(turn_id, patch) == 0:  # the observe of this turn has not written yet: retry on later ticks
                self._pending_annot.append((turn_id, patch, self.now_fn() + 900))
        except Exception as exc:  # noqa: BLE001
            logger.warning("psyche: memory annotation skipped: %s", exc)

    def _annotate_rows(self, turn_id: str, patch: str) -> int:
        c = sqlite3.connect(str(self.memory_db), timeout=5)
        try:
            cur = c.execute("UPDATE memories SET meta = json_patch(meta, ?) WHERE json_extract(meta, '$.turn_id') = ?", (patch, turn_id))
            c.commit()
            return cur.rowcount
        finally:
            c.close()

    def _retry_annotations(self) -> None:
        if not self._pending_annot or not self.memory_db:
            return
        now = self.now_fn()
        keep = []
        for turn_id, patch, deadline in self._pending_annot:
            try:
                if self._annotate_rows(turn_id, patch) > 0 or now > deadline:
                    continue
            except Exception:  # noqa: BLE001
                pass
            keep.append((turn_id, patch, deadline))
        self._pending_annot = keep

    # ------------------------------------------------------------------ inputs
    def record_appraisal(self, data: Optional[Dict[str, Any]], *, raw: str = "", error: Optional[str] = None, ms: float = 0.0,
                         turn_id: str = "", counterpart: str = "", platform: str = "", at: Optional[float] = None,
                         apply_now: bool = True) -> int:
        at = self.now_fn() if at is None else at
        with self.lock:
            cur = self.conn.execute("INSERT INTO appraisals(at, turn_id, counterpart, platform, raw, data, error, ms) VALUES (?,?,?,?,?,?,?,?)",
                                    (at, turn_id, counterpart, platform, raw[:20000], json.dumps(data, ensure_ascii=False) if data else None, error, ms))
            self.conn.commit()
            aid = int(cur.lastrowid)
            if apply_now and data and error is None and self.owner:
                self.step_to(at)   # catch up first …
                row = self.conn.execute("SELECT id, at, data, counterpart, turn_id, applied_tick FROM appraisals WHERE id=?", (aid,)).fetchone()
                if row and row[5] is None:  # … then apply at the current tick, so the next turn already sees it
                    self._apply_appraisal(row, self.tick)
                    self.snapshot()  # the latest snapshot must include it (replay skips applied ticks ≤ snapshot)
            return aid

    def on_turn(self, user_text: str, assistant_text: str, *, turn_id: str, platform: str, session_id: str) -> None:
        """A finished turn: an event row, the recent-turns ring, and appraisal A queued."""
        term = self.term_fn()
        with self.lock:
            self._event("turn", {"turn_id": turn_id, "platform": platform, "session": session_id[:24],
                                 "user": user_text[:500], "assistant": assistant_text[:500]}, counterpart=term)
        if self.owner and self.llm is not None:
            self._q.put({"user": user_text, "assistant": assistant_text, "turn_id": turn_id, "platform": platform,
                         "recent": list(self.recent), "term": term, "at": self.now_fn()})
        self.recent = (self.recent + [(user_text, assistant_text)])[-int(self.cfg["appraisal"]["recent_turns"]):]

    def _appraise_worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                loops = [l for l in self.loops.values() if l["state"] in ("waiting", "due")]
                today = datetime.fromtimestamp(job["at"], self.tz).strftime("%Y-%m-%d %H:%M")
                ac = self.cfg["appraisal"]
                data, raw, err, ms = A.run(self.llm, term=job["term"], cares_about=self.cfg.get("cares_about", []), loops=loops,
                                           recent=job["recent"], user_text=job["user"], assistant_text=job["assistant"], today=today,
                                           max_events=int(ac["max_events"]), retries=int(ac["retries"]))
                self.record_appraisal(data, raw=raw, error=err, ms=ms, turn_id=job["turn_id"], counterpart=job["term"],
                                      platform=job["platform"], at=job["at"])
                if err:
                    logger.warning("psyche appraisal failed: %s", err)
                else:
                    logger.info("psyche appraisal: %s (%.0f ms)", [e["event_kind"] for e in data["events"]], ms)
            except Exception:  # noqa: BLE001
                logger.exception("psyche appraisal worker error")
            finally:
                self._q.task_done()

    def pending_appraisals(self) -> int:
        return self._q.qsize()

    # ------------------------------------------------------------------ lifecycle
    def start(self, pid: int) -> bool:
        self.owner = self.acquire_owner(pid)
        if not self.owner:
            logger.info("psyche: another process owns %s; read-only here", self.db_path)
            return False
        self.load()
        self._stop.clear()
        self._tick_thread = threading.Thread(target=self._tick_loop, args=(pid,), name="psyche-tick", daemon=True)
        self._tick_thread.start()
        if self.llm is not None:
            self._worker = threading.Thread(target=self._appraise_worker, name="psyche-appraise", daemon=True)
            self._worker.start()
        return True

    def _tick_loop(self, pid: int) -> None:
        while not self._stop.wait(timeout=max(1.0, self.tick_s / 4)):
            try:
                self.step_to(self.now_fn())
                self.heartbeat(pid)
                self._retry_annotations()
            except Exception:  # noqa: BLE001
                logger.exception("psyche tick failed")

    def stop(self, drain_s: float = 20.0) -> None:
        deadline = time.time() + drain_s
        while self._q.unfinished_tasks and time.time() < deadline:
            time.sleep(0.2)
        self._stop.set()
        if self.owner:
            try:
                with self.lock:
                    self.step_to(self.now_fn(), snapshots=False)
                    self._event("stop", {"tick": self.tick})
                    self.snapshot()
            except Exception:  # noqa: BLE001
                logger.exception("psyche stop snapshot failed")

    # ------------------------------------------------------------------ expression layer (0.5.0: the state block)
    def state_block(self, *, t: Optional[float] = None, term: Optional[str] = None) -> str:
        """【她現在】 — at most max_lines lines, words not numbers; names a transition when the dominant
        feeling changed since the last block, so the history's tone inertia does not win."""
        t = self.now_fn() if t is None else t
        term = term or self.term_fn()
        with self.lock:
            if self.owner:
                self.step_to(t)
            else:  # read-only process: show the owner's latest snapshot
                snap = self.latest_snapshot()
                if snap:
                    self._restore(snap)
            ch = self.cfg["character"]
            ex = self.cfg["expression"]
            thr = float(ex["expression_threshold"])
            act = [i for i in self.active(t) if i["intensity"] >= thr]
            lines = ["【她現在】", f"精神：{model.energy_word(self.energy)}"]
            _, oct_zh, strength = model.octant(self.mood)
            mood_word = f"{model.intensity_word(strength)}{oct_zh}" if strength >= 0.2 else "平靜"
            feelings = []
            for i in act[:2]:
                w = model.intensity_word(i["intensity"])
                zh = model.EMOTION_ZH.get(i["type"], i["type"]).replace("對方", term)
                cause = (i.get("cause") or "").strip()
                feelings.append(f"{w}{zh}" + (f"（{cause}）" if cause else ""))
            lines.append("心情：" + (f"整體{mood_word}；" if feelings else f"整體{mood_word}") + "、".join(feelings))
            # 表現 — regulation and strategy, minimal: expressiveness, energy, mixed feelings, tsundere
            how = []
            how.append("直說" if float(ch.get("expressiveness", 0.6)) >= 0.5 else "收斂，點到為止")
            if self.energy < 0.35:
                how.append("話少一點")
            if len(act) >= 2 and ((act[0]["type"] in model.POSITIVE) != (act[1]["type"] in model.POSITIVE)):
                how.append("兩種情緒並存時先回應對方說的，再帶到自己的")
            vulnerable = {"liking", "longing", "gratitude"}
            if float(ch.get("tsundere_tendency", 0.3)) >= 0.5 and any(i["type"] in vulnerable for i in act):
                how.append("真心話可以用反話帶過，但要留破綻")
            if float(ch.get("humor_coping", 0.5)) >= 0.6 and any(i["type"] in model.NEGATIVE for i in act):
                how.append("不開心的事可以用玩笑帶過")
            lines.append("表現：" + "；".join(how))
            waiting = [l for l in self.loops.values() if l["state"] in ("waiting", "due")]
            waiting.sort(key=lambda l: -float(l.get("importance", 0.5)))
            if waiting:
                lines.append("掛念：" + "、".join(l["what"] for l in waiting[:2]))
            # transition since the last block
            dominant = act[0]["type"] if act else None
            prev = self.last_block.get("dominant")
            prev_word = self.last_block.get("word")
            if prev and prev != dominant:
                now_word = (model.intensity_word(act[0]["intensity"]) + model.EMOTION_ZH[act[0]["type"]]) if act else "已經平復了"
                lines.append(f"轉變：剛才{prev_word}，現在{now_word}")
            lines.append("原則：情緒是底色，內容以對方的話題為主；不提沒做過的事；有自己的看法，不用附和")
            self.last_block = {"dominant": dominant, "word": (model.intensity_word(act[0]["intensity"]) + model.EMOTION_ZH[act[0]["type"]]) if act else "平靜",
                               "at": t, "mood": mood_word}
            return "\n".join(lines[: int(ex.get("max_lines", 8))])

    def status(self) -> Dict[str, Any]:
        """For the 狀態 page / tests: current words plus the raw numbers."""
        with self.lock:
            t = self.time_of(self.tick)
            name, zh, strength = model.octant(self.mood)
            return {"tick": self.tick, "t": t, "energy": self.energy, "affect": dict(self.affect), "mood": list(self.mood),
                    "octant": name, "octant_zh": zh, "strength": strength,
                    "instances": [{k: v for k, v in i.items() if k != "pad"} for i in self.active(t)],
                    "loops": [l for l in self.loops.values() if l["state"] != "closed"]}
