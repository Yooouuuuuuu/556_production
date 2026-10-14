"""psyche.engine — her state over time (inner-life.md §2, §17): the single writer of psyche.db.

One Engine per character, living inside her Hermes process. Time is a fixed grid of ticks (tick_s,
default 60 s); every tick is a deterministic function of (state, the records due at that tick, a
seeded noise draw), so the same records always rebuild the same state: replay == live, and a stop of
any length is just the missed ticks run in one go (fast-forward, world time continuous).

Records that are replayed at their tick (after that tick's step, same order as the live path):
    appraisals            A's result for a turn                  -> impact model B, needs, loops
    events kind=turn      a turn happened (you, or her own)       -> contact, presence, sleep (woken)
    events kind=sent/silent/send_failed  what came of a proactive urge
    events kind=cmd_*     a command from the 狀態 page (close a loop, add a reminder or a life event)
Everything the tick itself generates (sleep, life events, rumination, the urge decision) is
recomputed from the seeded grid, so it is never stored as a replayable record — only as a visible one.

    load()            restore the last snapshot, then step through every tick up to now
    step_to(t)        advance the grid to time t
    on_turn(...)      record a turn, queue appraisal A (its own thread, never waited for)
    on_event_reply()  her answer to an event turn: sent, or silent
    state_block()     the 【她現在】 lines for her prompt (expression layer)
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
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import appraisal as A
from . import checks as CK
from . import events as EV
from . import life as L
from . import model
from . import needs as N
from . import relation as RL
from . import tom as T
from . import urge as U

logger = logging.getLogger("psyche")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL NOT NULL, tick INTEGER NOT NULL,
    kind TEXT NOT NULL, counterpart TEXT, payload TEXT NOT NULL DEFAULT '{}', applied_tick INTEGER, dedup TEXT);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup);
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
CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY, at REAL NOT NULL, tick INTEGER NOT NULL, platform TEXT,
    hits TEXT NOT NULL, excerpt TEXT);
CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY, op TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}',
    requested_at REAL NOT NULL, requested_by TEXT, done_at REAL, result TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

FADE = 0.02           # an instance below this intensity is dead
OWNER_STALE_S = 20.0
REPLAY_KINDS = ("turn", "sent", "silent", "send_failed", "proactive_fired", "cmd_close_loop", "cmd_add_loop", "cmd_life_event", "cmd_feedback")
MAIN = "你"  # the counterpart id of the person at the keyboard; other counterparts are character ids
PENDING_TTL_S = 3600.0


class Engine:
    def __init__(self, home: Path, character_id: str, cfg: Dict[str, Any], *, db_path: Optional[Path] = None,
                 now_fn: Callable[[], float] = time.time, llm: Any = None, term_fn: Optional[Callable[[], str]] = None,
                 memory_db: Optional[Path] = None, state_db: Optional[Path] = None,
                 names_fn: Optional[Callable[[str], str]] = None, hub_url: str = "") -> None:
        self.home = Path(home)
        self.char = character_id
        self.cfg = cfg
        self.now_fn = now_fn
        self.llm = llm
        self.term_fn = term_fn or (lambda: "製作人")
        self.names_fn = names_fn or (lambda p: p)   # display name of another character
        self.hub_url = hub_url                       # 556d, for counterpart sessions and the relay
        self.pr = str(cfg["character"].get("pronoun", "她"))
        self.memory_db = memory_db
        self.state_db = state_db or (self.home / "state.db")
        self.tick_s = int(cfg["time"]["tick_s"])
        self.snap_every = max(1, int(cfg["time"]["snapshot_interval_min"] * 60 // self.tick_s))
        self.derived = model.derive(cfg["character"], cfg["time"])
        self.tz = timezone(timedelta(hours=float(cfg["time"].get("timezone_offset_h", 8))))
        self.db_path = Path(db_path) if db_path else self.home / "psyche.db"
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.lock = threading.RLock()
        self.owner = False
        self.live = False                      # True only while the tick thread runs (sends happen)
        self._stop = threading.Event()
        self._tick_thread: Optional[threading.Thread] = None
        self._worker: Optional[threading.Thread] = None
        self._sender: Optional[threading.Thread] = None
        self._q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._send_q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.recent: List[Tuple[str, str]] = []
        self._pending_annot: List[Tuple[str, str, float]] = []
        self._intervals: List[Tuple[int, Optional[int]]] = []   # ticks she was running (from start/stop events)
        self.session_id: Optional[str] = None
        self._last_cfg_mtime: Optional[float] = None
        # --- state (everything a snapshot holds) ---
        self.tick = 0
        self.affect = {"pos": self.derived["mu_pos_base"], "neg": self.derived["mu_neg_base"], "ar": self.derived["mu_ar_base"]}
        self.mood: Tuple[float, float, float] = tuple(self.derived["mood_default"])  # type: ignore[assignment]
        self.energy = 0.6
        self.instances: Dict[str, Dict[str, Any]] = {}
        self.loops: Dict[str, Dict[str, Any]] = {}
        self.stack_counts: Dict[str, int] = {}
        self.last_block: Dict[str, Any] = {}
        self.sleep = L.SleepState.fresh()
        self.fatigue = 0.0
        self.activity = "rest"
        self.needs = N.fresh()
        self.contact: Dict[str, Any] = {"last_turn_at": None, "last_sent_at": None, "awaiting_since": None, "unanswered": 0,
                                        "phase": "ok", "turns_today": 0, "minutes_today": 0.0, "proactive_today": 0,
                                        "farewell_until": None, "pending": None, "answered_14d": [1.0] * 4}
        self.pm = T.fresh()
        self.share_backlog: List[Dict[str, Any]] = []
        self.projects: List[Dict[str, Any]] = [dict(p) for p in cfg.get("life", {}).get("projects", [])]
        self.day: Dict[str, Any] = {"date": None, "hour": None, "weekday": None, "event": None}
        self.rel: Dict[str, Dict[str, Any]] = {}        # L5 per counterpart
        self.ledger: Dict[str, List[Dict[str, Any]]] = {}  # L6 per counterpart
        self.others: Dict[str, Dict[str, Any]] = {}     # other characters: contact, pm, need
        self.gain_adj: Dict[str, float] = {}            # your feedback: per emotion type, 0.5–2×
        self.last_strategy: Dict[str, str] = {}
        self._turn_minutes: Dict[str, float] = {}       # minutes of conversation the last turn with p represented

    # ------------------------------------------------------------------ counterparts
    def _name(self, p: str) -> str:
        return self.term_fn() if p == MAIN else self.names_fn(p)

    def _rel(self, p: str) -> Dict[str, Any]:
        if p not in self.rel:
            self.rel[p] = RL.fresh(self.cfg.get("relationships", {}).get(p, {}), self.cfg["character"])
            self.ledger.setdefault(p, [])
        return self.rel[p]

    def _other(self, p: str) -> Dict[str, Any]:
        if p not in self.others:
            self.others[p] = {"contact": {"last_turn_at": None, "last_sent_at": None, "awaiting_since": None, "unanswered": 0,
                                          "phase": "ok", "pending": None, "answered_14d": [1.0] * 4}, "pm": T.fresh(), "need": 0.0}
        return self.others[p]

    def _contact_of(self, p: str) -> Dict[str, Any]:
        return self.contact if p == MAIN else self._other(p)["contact"]

    def _pm_of(self, p: str) -> Dict[str, Any]:
        return self.pm if p == MAIN else self._other(p)["pm"]

    def _need_of(self, p: str) -> float:
        return self.needs["affiliation_person"] if p == MAIN else float(self._other(p)["need"])

    def _loop_cp(self, l: Dict[str, Any]) -> str:
        cp = l.get("counterpart") or MAIN
        return cp if cp == MAIN or cp in self.others else MAIN

    def counterparts(self) -> List[str]:
        return [MAIN] + [p for p in self.others if p != MAIN]

    # ------------------------------------------------------------------ helpers
    def _migrate(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(events)").fetchall()}
        if "applied_tick" not in cols:
            self.conn.execute("ALTER TABLE events ADD COLUMN applied_tick INTEGER")
        if "dedup" not in cols:
            self.conn.execute("ALTER TABLE events ADD COLUMN dedup TEXT")
            self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup)")
        lcols = {r[1] for r in self.conn.execute("PRAGMA table_info(loops)").fetchall()}
        for col, typ in (("ask", "TEXT"), ("asking", "TEXT"), ("answer", "TEXT"), ("tries", "INTEGER"), ("asked_at", "REAL"),
                         ("fails", "INTEGER"), ("next_try", "REAL"), ("why", "TEXT")):
            if col not in lcols:
                self.conn.execute(f"ALTER TABLE loops ADD COLUMN {col} {typ}")
        self.conn.commit()

    def _save_loop(self, l: Dict[str, Any]) -> None:
        """Mirror a loop into the loops table (the 狀態 page reads it; the snapshot is the source of truth)."""
        self.conn.execute("INSERT OR REPLACE INTO loops(id, what, origin, cue_time, importance, state, created_at, closed_at, counterpart, "
                          "ask, asking, answer, tries, asked_at, fails, next_try, why) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (l["id"], l["what"], l.get("origin"), l.get("cue_time"), float(l.get("importance", 0.5)), l["state"], l["created_at"],
                           l.get("closed_at"), l.get("counterpart") or MAIN, json.dumps(l.get("ask") or [], ensure_ascii=False),
                           l.get("asking"), l.get("answer"), int(l.get("tries") or 0), l.get("asked_at"),
                           int(l.get("fails") or 0), l.get("next_try"), l.get("why")))

    def _held(self, l: Dict[str, Any], t: float) -> bool:
        """A due item backing off after a failed delivery waits for its next try."""
        nt = l.get("next_try")
        return nt is not None and t < float(nt)

    def _forget_p(self, l: Dict[str, Any], t: float) -> float:
        """Chance that she forgets this item as it comes due (character.forgets): the base rate from
        conscientiousness unless set by hand, lower for important things, higher when tired or low, higher
        the longer it has been waiting."""
        ch = self.cfg["character"]
        if not ch.get("forgets", False):
            return 0.0
        rate = ch.get("forget_rate")
        base = float(rate) if rate is not None else 0.3 * (1.0 - float(ch["big5"].get("conscientiousness", 0.7)))
        weeks = max(0.0, (t - float(l.get("created_at", t))) / (7 * 86400))
        p = base * (1.0 - float(l.get("importance", 0.5))) * (1.0 + 0.5 * self.fatigue + 0.5 * float(self.affect.get("neg", 0.0))) * (1.3 ** weeks)
        return max(0.0, min(0.95, p))

    def _forget(self, l: Dict[str, Any], t: float, why: str) -> None:
        l["state"], l["why"], l["next_try"] = "forgot", why, None
        self._save_loop(l)
        self._event("loop_forgot", {"loop": l["id"], "what": l["what"], "why": why}, t, dedup=f"forgot:{l['id']}")

    def _loops_for(self, p: str, states: Tuple[str, ...]) -> List[Dict[str, Any]]:
        """The loops that belong to a conversation with p: the ones opened there (for you: including the ones she is
        asking someone else about on your behalf), and for another character the ones she is asking them about."""
        out = []
        for l in self.loops.values():
            if l["state"] not in states:
                continue
            if p != MAIN and l.get("asking") == p:
                out.append(l)
            elif self._loop_cp(l) == p:
                out.append(l)
        return out

    def _known_others(self) -> Dict[str, str]:
        ids = [p for p in list(self.others) + list((self.cfg.get("relationships") or {}).keys()) if p != MAIN]
        return {p: self._name(p) for p in dict.fromkeys(ids)}

    def tick_of(self, t: float) -> int:
        return int(t // self.tick_s)

    def time_of(self, k: int) -> float:
        return float(k * self.tick_s)

    def local(self, t: float) -> datetime:
        return datetime.fromtimestamp(t, self.tz)

    def local_hour(self, t: float) -> float:
        d = self.local(t)
        return d.hour + d.minute / 60.0 + d.second / 3600.0

    def _rng(self, k: int, salt: str = "") -> random.Random:
        day = self.local(self.time_of(k)).strftime("%Y-%m-%d")
        return random.Random(f"{self.char}:{day}:{k}:{salt}")

    @property
    def clinginess_eff(self) -> float:
        return float(self.cfg["character"].get("clinginess_cap", 0.5)) * float(self.cfg.get("needs", {}).get("attachment_strength", 0.4))

    def _meta(self, key: str, value: Optional[str] = None) -> Optional[str]:
        if value is None:
            r = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r[0] if r else None
        self.conn.execute("INSERT INTO meta(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()
        return value

    # ------------------------------------------------------------------ persistence
    def _event(self, kind: str, payload: Dict[str, Any], t: Optional[float] = None, counterpart: str = "",
               dedup: Optional[str] = None, applied_tick: Optional[int] = None) -> Optional[int]:
        t = self.now_fn() if t is None else t
        try:
            cur = self.conn.execute("INSERT OR IGNORE INTO events(at, tick, kind, counterpart, payload, applied_tick, dedup) VALUES (?,?,?,?,?,?,?)",
                                    (t, self.tick_of(t), kind, counterpart, json.dumps(payload, ensure_ascii=False), applied_tick, dedup))
            self.conn.commit()
            return int(cur.lastrowid) if cur.rowcount else None
        except sqlite3.Error as exc:
            logger.warning("psyche event write failed: %s", exc)
            return None

    def snapshot_state(self) -> Dict[str, Any]:
        return {"tick": self.tick, "t": self.time_of(self.tick), "affect": dict(self.affect), "mood": list(self.mood),
                "energy": self.energy, "instances": list(self.instances.values()), "loops": list(self.loops.values()),
                "stack_counts": dict(self.stack_counts), "last_block": self.last_block, "sleep": dict(self.sleep),
                "fatigue": self.fatigue, "activity": self.activity, "needs": dict(self.needs), "contact": dict(self.contact),
                "pm": {k: (list(v) if isinstance(v, list) else v) for k, v in self.pm.items()},
                "share_backlog": list(self.share_backlog), "projects": [dict(p) for p in self.projects], "day": dict(self.day),
                "rel": self.rel, "ledger": self.ledger, "others": self.others, "gain_adj": dict(self.gain_adj), "last_strategy": dict(self.last_strategy)}

    def _restore(self, s: Dict[str, Any]) -> None:
        self.tick = int(s["tick"])
        self.affect = dict(s["affect"])
        self.mood = tuple(s["mood"])  # type: ignore[assignment]
        self.energy = float(s.get("energy", 0.6))
        self.instances = {i["id"]: i for i in s.get("instances", [])}
        self.loops = {l["id"]: l for l in s.get("loops", [])}
        self.stack_counts = dict(s.get("stack_counts", {}))
        self.last_block = dict(s.get("last_block", {}))
        self.sleep = {**L.SleepState.fresh(), **s.get("sleep", {})}
        self.fatigue = float(s.get("fatigue", 0.0))
        self.activity = str(s.get("activity", "rest"))
        self.needs = {**N.fresh(), **s.get("needs", {})}
        self.contact = {**self.contact, **s.get("contact", {})}
        if s.get("pm"):
            self.pm = {**T.fresh(), **s["pm"]}
        seen: set = set()
        self.share_backlog = [x for x in s.get("share_backlog", []) if not (x.get("what") in seen or seen.add(x.get("what")))]
        if s.get("projects"):
            self.projects = [dict(p) for p in s["projects"]]
        self.day = {**self.day, **s.get("day", {})}
        self.rel = {p: {**RL.fresh(self.cfg.get("relationships", {}).get(p, {}), self.cfg["character"]), **r} for p, r in s.get("rel", {}).items()}
        self.ledger = {p: list(v) for p, v in s.get("ledger", {}).items()}
        self.others = {p: v for p, v in s.get("others", {}).items()}
        self.gain_adj = dict(s.get("gain_adj", {}))
        self.last_strategy = dict(s.get("last_strategy", {}))

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
        self._meta("last_heartbeat_tick", str(self.tick))

    # ------------------------------------------------------------------ running intervals (replay gating)
    def _load_intervals(self) -> None:
        rows = self.conn.execute("SELECT kind, tick FROM events WHERE kind IN ('start','stop') ORDER BY id").fetchall()
        iv: List[Tuple[int, Optional[int]]] = []
        for kind, tick in rows:
            if kind == "start":
                if iv and iv[-1][1] is None:            # a crash: close the previous run at its last heartbeat
                    hb = self._meta("last_heartbeat_tick")
                    iv[-1] = (iv[-1][0], int(hb) if hb and int(hb) >= iv[-1][0] else iv[-1][0])
                iv.append((int(tick), None))
            elif iv and iv[-1][1] is None:
                iv[-1] = (iv[-1][0], int(tick))
        self._intervals = iv

    def _running_at(self, k: int) -> bool:
        if self.live:
            return True
        for a, b in self._intervals:
            if a <= k and (b is None or k < b):
                return True
        return False

    # ------------------------------------------------------------------ load / replay
    def load(self) -> None:
        from . import config as C
        with self.lock:
            snap = self.latest_snapshot()
            now = self.now_fn()
            if snap:
                self._restore(snap)
            else:
                self.tick = self.tick_of(now) - 1
                self.day["date"] = None
            v = C.version(self.cfg)
            r = self.conn.execute("SELECT version FROM params ORDER BY id DESC LIMIT 1").fetchone()
            if not r or r[0] != v:
                self.conn.execute("INSERT INTO params(at, version, data) VALUES (?,?,?)",
                                  (now, v, json.dumps({k: self.cfg.get(k) for k in ("character", "time", "impact", "expression", "needs", "life", "proactive")}, ensure_ascii=False)))
                self.conn.commit()
            self.session_id = self._meta("session_id")
            gap = self.tick_of(now) - self.tick
            self._event("start", {"from_tick": self.tick, "gap_ticks": gap, "snapshot": bool(snap)}, now)
            self._load_intervals()
            self.step_to(now, snapshots=False)
            self.contact["pending"] = None  # a fire the previous run never sent is dead; due loops fire again live
            self.snapshot()

    def _due_items(self, after_tick: int, upto_tick: int) -> List[Tuple[int, int, str, Any]]:
        """(tick to apply at, order, kind, row) for appraisals and replayable events applied after
        after_tick or still pending — ordered so a replay walks them exactly as the live path did."""
        out: List[Tuple[int, int, str, Any]] = []
        for r in self.conn.execute(
                "SELECT id, at, data, counterpart, turn_id, applied_tick FROM appraisals WHERE data IS NOT NULL AND error IS NULL "
                "AND (applied_tick IS NULL OR applied_tick > ?) ORDER BY id", (after_tick,)).fetchall():
            k = int(r[5]) if r[5] is not None else max(after_tick, self.tick_of(float(r[1])))
            if k <= upto_tick:
                out.append((k, 1, "appraisal", r))
        marks = ",".join("?" * len(REPLAY_KINDS))
        for r in self.conn.execute(
                f"SELECT id, at, kind, payload, applied_tick, counterpart FROM events WHERE kind IN ({marks}) "
                "AND (applied_tick IS NULL OR applied_tick > ?) ORDER BY id", (*REPLAY_KINDS, after_tick)).fetchall():
            k = int(r[4]) if r[4] is not None else max(after_tick, self.tick_of(float(r[1])))
            if k <= upto_tick:
                out.append((k, 0, "event", r))
        out.sort(key=lambda x: (x[0], x[1], x[3][0]))
        return out

    def step_to(self, t: float, snapshots: bool = True) -> int:
        with self.lock:
            target = max(self.tick_of(t), self.tick)
            due = self._due_items(self.tick, target)
            di = n = 0
            while di < len(due) and due[di][0] <= self.tick:  # landed at the current tick: apply now, same as the live path
                _, _, kind, row = due[di]
                if kind == "appraisal":
                    self._apply_appraisal(row, self.tick)
                else:
                    self._apply_event_row(row, self.tick)
                di += 1
            for k in range(self.tick + 1, target + 1):
                self._step_one(k)
                while di < len(due) and due[di][0] <= k:
                    _, _, kind, row = due[di]
                    if kind == "appraisal":
                        self._apply_appraisal(row, k)
                    else:
                        self._apply_event_row(row, k)
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

    def _chatting(self, t: float) -> bool:
        lt = self.contact.get("last_turn_at")
        return lt is not None and (t - lt) < L.CHAT_WINDOW_MIN * 60

    def _step_one(self, k: int) -> None:
        t = self.time_of(k)
        d = self.local(t)
        hour = d.hour + d.minute / 60.0
        weekday = d.weekday()
        dt_h = self.tick_s / 3600.0
        dv = self.derived
        ch = self.cfg["character"]
        life = self.cfg.get("life", {})
        running = self._running_at(k)
        rng = self._rng(k)
        # --- day and hour boundaries
        date = d.strftime("%Y-%m-%d")
        if self.day.get("date") != date:
            self.day.update({"date": date, "event": None})
            self.contact.update({"turns_today": 0, "minutes_today": 0.0, "proactive_today": 0})
            day_tick0 = self.tick_of(datetime(d.year, d.month, d.day, tzinfo=self.tz).timestamp())
            self.day["event"] = L.plan_day_event(self._rng(k, "day"), life, float(self.sleep.get("debt", 0.0)), day_tick0, self.tick_s)
            for pm_ in [self.pm] + [o["pm"] for o in self.others.values()]:
                T.weekly_decay(pm_, d.strftime("%G-%V"), float(self.cfg.get("tom", {}).get("weekly_decay", 0.92)))
        if self.day.get("hour") != d.hour:
            if self.day.get("hour") is not None:
                for pm_ in [self.pm] + [o["pm"] for o in self.others.values()]:
                    T.hour_boundary(pm_, int(self.day.get("weekday", weekday)), float(self.day["hour"]), running)
            self.day["hour"], self.day["weekday"] = d.hour, weekday
        chatting = self._chatting(t)
        # --- L1: sleep, fatigue, activity, energy
        act_now = self.active(t)
        neg_load = sum(i["intensity"] for i in act_now if i["type"] in model.NEGATIVE)
        ev = L.SleepState.step(self.sleep, t=t, hour=hour, dt_h=dt_h, sched=life.get("schedule", {}), chatting=chatting,
                               negative_load=neg_load, clinginess_eff=self.clinginess_eff, rng_u=rng.random())
        if ev:
            self._event("sleep", {"what": ev, "S": round(self.sleep["S"], 3), "debt": round(self.sleep["debt"], 3)}, t, dedup=f"sleep:{ev}:{k}")
            if ev == "woke_up":
                self._reboot()
        if chatting:
            self.fatigue = min(1.0, self.fatigue + dt_h * (1.3 - 0.6 * self.clinginess_eff) / 1.0)
        else:
            self.fatigue *= 2.718281828 ** (-dt_h / 1.0)
        self.activity = L.activity_for(hour, self.sleep, chatting, life)
        self.energy = L.energy_from(self.sleep["S"], L.circadian(hour, float(ch.get("chronotype", 0.0))), self.fatigue)
        # --- L4 needs and the separation phase
        waiting = [l for l in self.loops.values() if l["state"] in ("waiting", "due")]
        N.step(self.needs, dt_h=dt_h, p_expected=T.p_expected(self.pm, weekday, hour), activity=self.activity, chatting=chatting,
               waiting_importance=sum(float(l.get("importance", 0.5)) for l in waiting), busyness=str(life.get("busyness_mode", "work")),
               derived=dv, cfg=self.cfg.get("needs", {}), clinginess_eff=self.clinginess_eff, fatigue=self.fatigue)
        lt = self.contact.get("last_turn_at")
        hours_since = (t - lt) / 3600.0 if lt is not None else -1.0
        self.contact["phase"] = N.phase(hours_since, self.cfg.get("needs", {}), self.clinginess_eff, 0.5 * float(ch["big5"].get("neuroticism", 0.4)))
        # --- the other characters: their gap grows when they are usually around and quiet; L5 / L6 tick for everyone
        k_aff = float(self.cfg.get("needs", {}).get("k_aff", 0.08))
        for p, o in self.others.items():
            c = o["contact"]
            lt_ = c.get("last_turn_at")
            chatting_p = lt_ is not None and (t - lt_) < L.CHAT_WINDOW_MIN * 60
            att = self._rel(p)["attachment"]
            if chatting_p:
                o["need"] = max(0.0, float(o["need"]) - 0.5 * dt_h)
            else:
                o["need"] = min(1.0, float(o["need"]) + k_aff * T.p_expected(o["pm"], weekday, hour) * (0.3 + 0.7 * att) * dt_h)
            hs = (t - lt_) / 3600.0 if lt_ is not None else -1.0
            c["phase"] = N.phase(hs, self.cfg.get("needs", {}), float(ch.get("clinginess_cap", 0.5)) * att, 0.5 * float(ch["big5"].get("neuroticism", 0.4)))
            aw_ = c.get("awaiting_since")
            if aw_ is not None and (t - aw_) / 3600.0 > T.latency_p90_h(o["pm"], 6.0):
                c["awaiting_since"], c["unanswered"] = None, int(c.get("unanswered", 0)) + 1
            pend_ = c.get("pending")
            if pend_ and t - float(pend_.get("at", t)) > PENDING_TTL_S:
                c["pending"] = None
        rcfg = self.cfg.get("relation", {})
        for p in list(self.rel):
            RL.tick(self.rel[p], dt_h, rcfg)
            RL.ledger_tick(self.ledger.setdefault(p, []), dt_h, agreeableness=float(ch["big5"].get("agreeableness", 0.6)),
                           commitment=self.rel[p]["commitment"], t=t)
        # --- her life: the day's small event, project progress during work
        de = self.day.get("event")
        if de and int(de["tick"]) == k and self.activity not in ("sleep", "lying", "woken"):
            self._life_event(de, k, t, dedup=f"life:{k}")
        if self.activity == "work":
            m = L.project_progress(self.projects, dt_h, rng.random())
            if m:
                self._life_event(m, k, t, dedup=f"project:{k}")
        # --- L3 rumination (idle attention) — each unresolved negative instance may come back a little
        attention = L.ACTIVITIES.get(self.activity, L.ACTIVITIES["rest"])[0]
        if self.activity not in ("sleep", "chat"):
            for inst in list(self.instances.values()):
                if inst.get("resolved_at") is not None or inst["type"] not in model.NEGATIVE or int(inst.get("rumination", 0)) >= 3:
                    continue
                I = model.decayed(inst["intensity0"], inst["half_life_h"], (t - inst["born_at"]) / 3600.0)
                if I < 0.08:
                    continue
                p = 0.6 * I * float(ch["big5"].get("neuroticism", 0.4)) * (1.0 - attention) * dt_h
                if rng.random() < p:
                    inst["intensity0"], inst["born_at"], inst["born_tick"] = round(min(1.0, I * 1.15), 4), t, k
                    inst["rumination"] = int(inst.get("rumination", 0)) + 1
                    self.conn.execute("UPDATE instances SET intensity0=?, born_at=?, born_tick=? WHERE id=?", (inst["intensity0"], t, k, inst["id"]))
                    self._event("rumination", {"instance": inst["id"], "type": inst["type"], "count": inst["rumination"]}, t, dedup=f"rum:{k}:{inst['id']}")
        # --- L2 core affect and mood
        act = self.active(t)
        pos = sum(i["intensity"] for i in act if i["type"] in model.POSITIVE)
        neg = sum(i["intensity"] for i in act if i["type"] in model.NEGATIVE)
        ar = sum(i["intensity"] * abs(i["pad"][1]) for i in act)
        pull = N.mood_pull(self.needs, float(self.cfg.get("needs", {}).get("need_mood_coupling", 0.1)))
        phase_pull = {"despair": 0.08, "detachment": 0.05}.get(self.contact["phase"], 0.0)
        mu_pos = model._c(dv["mu_pos_base"] - pull - phase_pull + min(0.6, pos))
        mu_neg = model._c(dv["mu_neg_base"] + 0.5 * pull + phase_pull + 0.1 * float(self.sleep.get("debt", 0.0)) + min(0.6, neg))
        mu_ar = model._c(dv["mu_ar_base"] * (0.6 + 0.8 * self.energy) + min(0.5, ar))
        z = [rng.gauss(0, 1) for _ in range(3)]
        self.affect["pos"] = model.ou_step(self.affect["pos"], mu_pos, dv["theta_affect"], dv["sigma_affect"], dt_h, z[0])
        self.affect["neg"] = model.ou_step(self.affect["neg"], mu_neg, dv["theta_affect"], dv["sigma_affect"], dt_h, z[1])
        self.affect["ar"] = model.ou_step(self.affect["ar"], mu_ar, dv["theta_affect"], dv["sigma_affect"] * 0.5, dt_h, z[2])
        center = None
        if act:
            w = sum(i["intensity"] for i in act)
            center = tuple(sum(i["intensity"] * i["pad"][j] for i in act) / w for j in range(3))  # type: ignore[assignment]
        tc = self.cfg["time"]
        self.mood = model.mood_step(self.mood, center, tuple(dv["mood_default"]), dt_h, float(tc["mood_regress_tau_h"]),
                                    float(tc["mood_rise_max"]), float(tc["mood_fall_max"]))
        # --- loops: due by cue time, expiry
        pcfg = self.cfg.get("proactive", {})
        for l in self.loops.values():
            if l["state"] == "waiting" and l.get("cue_time"):
                ct = self._parse_cue(l["cue_time"])
                if ct is not None and t >= ct:
                    if rng.random() < self._forget_p(l, t):  # it slipped her mind (character.forgets)
                        self._forget(l, t, "forgot")
                        continue
                    l["state"] = "due"
                    self.conn.execute("UPDATE loops SET state='due' WHERE id=?", (l["id"],))
                    self._event("loop_due", {"loop": l["id"], "what": l["what"]}, t, dedup=f"due:{l['id']}")
            if l["state"] == "asking" and l.get("asked_at") is not None and \
                    t - float(l["asked_at"]) > float(pcfg.get("ask_give_up_h", 48.0)) * 3600:
                self._ask_outcome(l, None, t, gave_up=True)   # asked once, waited long enough: she will tell you she could not
            if l["state"] in ("due", "answered") and l.get("first_fail_at") is not None and \
                    t - float(l["first_fail_at"]) > float(pcfg.get("undelivered_window_h", 6.0)) * 3600:
                self._forget(l, t, "undelivered")               # could not be delivered for hours: to her, she forgot
            if l["state"] in ("waiting", "due", "asked", "asking", "answered", "forgot") and t - float(l["created_at"]) > 7 * 86400:
                l["state"], l["closed_at"] = "expired", t
                self.conn.execute("UPDATE loops SET state='expired', closed_at=? WHERE id=?", (t, l["id"]))
        # --- waiting for your answer: past your usual latency, a small disappointment, never a follow-up
        aw = self.contact.get("awaiting_since")
        if aw is not None and (t - aw) / 3600.0 > T.latency_p90_h(self.pm, float(self.cfg.get("proactive", {}).get("reply_timeout_default_h", 6.0))):
            self.contact["awaiting_since"] = None
            self.contact["unanswered"] = int(self.contact.get("unanswered", 0)) + 1
            self.contact["answered_14d"] = (self.contact.get("answered_14d", []) + [0.0])[-14:]
            anx = 0.5 * float(ch["big5"].get("neuroticism", 0.4))
            self._born_direct("disappointment", 0.12 * (0.8 + 0.4 * anx), f"她主動傳的訊息{self.term_fn()}一直沒回", k, t)
            self._event("reply_timeout", {"unanswered": self.contact["unanswered"]}, t, dedup=f"timeout:{k}")
        pend = self.contact.get("pending")
        if pend and t - float(pend.get("at", t)) > PENDING_TTL_S:
            self.contact["pending"] = None
        # --- the urge
        self._urge(k, t, hour, chatting, running, rng)
        # --- death by fading
        for inst in self.instances.values():
            if inst.get("resolved_at") is None:
                I = model.decayed(inst["intensity0"], inst["half_life_h"], (t - inst["born_at"]) / 3600.0)
                if I < FADE:
                    inst["resolved_at"], inst["resolved_tick"], inst["resolved_by"] = t, k, "faded"
                    self.conn.execute("UPDATE instances SET resolved_at=?, resolved_tick=?, resolved_by=? WHERE id=?", (t, k, "faded", inst["id"]))
        self.tick = k

    def _ask_outcome(self, l: Dict[str, Any], answer: Optional[str], t: float, *, gave_up: bool = False) -> None:
        """A promise that needed another character: an answer (or giving up) makes it 'answered' — she now owes you a
        report; no answer and tries left puts it back to 'due' for her next free slot."""
        if answer is not None or gave_up:
            l["state"], l["answer"], l["asked_at"] = "answered", answer, None
            self._event("loop_answered", {"loop": l["id"], "what": l["what"], "answer": answer, "asked": l.get("asking")}, t,
                        dedup=f"answered:{l['id']}:{int(l.get('tries') or 0)}")
        else:
            l["state"], l["asked_at"] = "due", None
        self._save_loop(l)

    def _parse_cue(self, s: str) -> Optional[float]:
        try:
            dt = datetime.fromisoformat(s[:16])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=self.tz)
            return dt.timestamp()
        except Exception:
            return None

    def _reboot(self) -> None:
        """Waking up (Kismet's motivational reboot): needs partly reset, mood halfway to baseline,
        negative instances lose a quarter (§4)."""
        for n in self.needs:
            self.needs[n] *= 0.6
        dflt = self.derived["mood_default"]
        self.mood = tuple((m + dflt[i]) / 2 for i, m in enumerate(self.mood))  # type: ignore[assignment]
        for inst in self.instances.values():
            if inst.get("resolved_at") is None and inst["type"] in model.NEGATIVE:
                inst["intensity0"] = round(inst["intensity0"] * 0.75, 4)

    def _born_direct(self, kind: str, intensity: float, cause: str, k: int, t: float, half_life_h: Optional[float] = None) -> Optional[str]:
        if intensity < 0.05:
            return None
        iid = f"em_{k}_direct_{kind}"
        if iid in self.instances:
            return None
        rec = {"id": iid, "born_at": t, "born_tick": k, "type": kind, "target": self.term_fn(), "cause": cause, "appraisal_id": None,
               "intensity0": round(min(1.0, intensity), 4), "half_life_h": half_life_h or model.T_BASE[kind], "pad": list(model.PAD[kind]),
               "stack_key": f"{kind}:direct", "loop_id": None, "resolved_at": None, "resolved_tick": None, "resolved_by": None}
        self.instances[iid] = rec
        self.conn.execute("INSERT OR REPLACE INTO instances(id, born_at, born_tick, type, target, cause, appraisal_id, intensity0, half_life_h, pad, stack_key, loop_id) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (iid, t, k, kind, rec["target"], cause, None, rec["intensity0"], rec["half_life_h"], json.dumps(rec["pad"]), rec["stack_key"], None))
        return iid

    def _life_event(self, e: Dict[str, Any], k: int, t: float, dedup: str) -> None:
        if self._event("life", {"text": e["text"], "kind": e.get("kind", "life"), "v": e.get("v", 0.0)}, t, dedup=dedup) is None:
            return  # already recorded (replay)
        ap = {"event_kind": "life_event", "cause": e["text"], "v": float(e.get("v", 0.0)), "R": float(e.get("R", 0.3)), "u": 0.3,
              "cert": 1.0, "agent": "circ", "intent": 0.0, "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.0, "other_v": 0.0,
              "appeal": 0.0, "q": 0.0, "loop_id": None}
        self._born_from(ap, k, t, aid=None, tag=dedup.replace(":", "_"))
        if e.get("share") and float(e.get("R", 0.3)) >= 0.3 and not any(s.get("what") == e["text"] for s in self.share_backlog):
            self.share_backlog = (self.share_backlog + [{"what": e["text"], "at": t, "importance": float(e.get("R", 0.3))}])[-5:]
        if float(e.get("R", 0.3)) >= 0.3:
            self.needs["novelty"] = max(0.0, self.needs["novelty"] - 0.3)

    def _born_from(self, ev: Dict[str, Any], k: int, t: float, aid: Optional[int], tag: str, counterpart: str = MAIN) -> List[str]:
        term = self._name(counterpart)
        imp = self.cfg["impact"]
        ev = dict(ev)
        ev["counterpart"] = term
        act = self.active(t)
        born: List[str] = []
        for iid, frac in model.resolutions(ev["event_kind"], ev.get("loop_id"), act).items():
            self._resolve(iid, frac, t, k, ev["event_kind"])
        act = self.active(t)
        debt = float(self.sleep.get("debt", 0.0))
        mods = {"all": (1.0 - 0.15 * self.fatigue), "neg": 1.0 + 0.2 * debt, "pos": 1.0 - 0.1 * debt}
        new = model.appraise_to_instances(ev, self.derived, imp, act, self.stack_counts, mood_valence=self.mood[0],
                                          bond=self._rel(counterpart)["bond"], modulators=mods)
        for i, inst in enumerate(new):
            inst["intensity0"] = round(min(1.0, inst["intensity0"] * float(self.gain_adj.get(inst["type"], 1.0))), 4)
            iid = f"em_{k}_{tag}_{i}"
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
        return born

    # ------------------------------------------------------------------ the urge
    def _urge(self, k: int, t: float, hour: float, chatting: bool, running: bool, rng: random.Random) -> None:
        """Every counterpart is a candidate: you (gates as §16) and the other characters (their own contact
        state). A due reminder or her own promise to you fires on time; otherwise the strongest λ wins."""
        pc = self.cfg.get("proactive", {})
        if not self.live:
            return  # urges are decided live only; replay re-applies the recorded decision, a stop back-fills nothing
        ch = self.cfg["character"]
        anx = 0.5 * float(ch["big5"].get("neuroticism", 0.4))
        avo = 0.5 * (1.0 - float(ch["big5"].get("agreeableness", 0.6)))
        d_ = self.local(t)
        act = self.active(t)
        cands: List[Tuple[float, str, str, str, Optional[Dict[str, Any]], float, float]] = []  # (lam, p, kind, what, payload, W, O)
        for p in self.counterparts():
            c = self._contact_of(p)
            if c.get("pending"):
                continue
            term = self._name(p)
            # due items: a reminder you asked for or her promise to you (forced through every gate), a promise that
            # needs another character (asked at her free time, never spoken to you), an answer to report back to you
            due = [l for l in self.loops.values() if l["state"] == "due" and self._loop_cp(l) == p and not l.get("ask") and not self._held(l, t)]
            asks = [l for l in self.loops.values() if l["state"] == "due" and p != MAIN and p in (l.get("ask") or []) and not self._held(l, t)]
            reports = [l for l in self.loops.values() if l["state"] == "answered" and self._loop_cp(l) == p and not self._held(l, t)] if p == MAIN else []
            due_reminder = any(l.get("origin") in ("counterpart_said", "her_promise") for l in due)
            if p == MAIN:
                you_awake = (not pc.get("report_only_when_awake", True)) or T.p_expected(self.pm, d_.weekday(), hour) >= 0.12
                ok, _why = U.gates(cfg=pc, hour=hour, activity=self.activity, chatting=chatting, proactive_today=int(self.contact["proactive_today"]),
                                   minutes_today=float(self.contact["minutes_today"]), last_sent_at=c.get("last_sent_at"), t=t,
                                   farewell_until=self.contact.get("farewell_until"), running=running, due_reminder=due_reminder,
                                   due_report=bool(reports) and not due_reminder, you_awake=you_awake)
            else:
                ok = (pc.get("enabled", True) and pc.get("inter_agent", True) and running and self.activity not in ("sleep", "lying", "woken")
                      and not chatting and (bool(asks) or int(self.contact["proactive_today"]) < int(pc.get("daily_cap", 3)))
                      and (c.get("last_sent_at") is None or (t - c["last_sent_at"]) >= float(pc.get("inter_agent_min_gap_min", 240)) * 60))
            if not ok:
                continue
            if asks:  # she has a question to carry to this character; her free slot has come
                l = asks[0]
                cands.append((float("inf"), p, "ask_other", str(l["what"]), l, 1.0, 1.0))
                continue
            care = [l for l in self.loops.values() if l["state"] == "waiting" and l.get("origin") == "counterpart_said" and self._loop_cp(l) == p
                    and l.get("cue_time") and self._parse_cue(l["cue_time"]) is not None and 0 <= (self._parse_cue(l["cue_time"]) - t) <= 2 * 3600]  # type: ignore[operator]
            hurt = sum(i["intensity"] for i in act if i["type"] == "hurt" and i.get("target") == term)
            rel = self._rel(p)
            needs_p = dict(self.needs)
            needs_p["affiliation_person"] = self._need_of(p)
            W = U.willingness(needs=needs_p, phase=c.get("phase", "ok"), share_backlog=self.share_backlog, hurt=hurt, anxiety=anx,
                              avoidance=avo, clinginess_eff=float(ch.get("clinginess_cap", 0.5)) * (rel["attachment"] if p != MAIN else float(self.cfg.get("needs", {}).get("attachment_strength", 0.4))))
            olive = RL.olive_branch_due(self.ledger.get(p, []), t=t, last_contact=c.get("last_turn_at"),
                                        clinginess_eff=self.clinginess_eff, avoidance=rel["avoidance"])
            if olive is not None:
                O, kind, payload = 0.9, "olive_branch", {"what": olive["cause"], "entry": olive["id"]}
            else:
                O, kind, payload = U.occasion(due_loops=due, share_backlog=self.share_backlog, care_loops=care, phase=c.get("phase", "ok"),
                                              needs=needs_p, floor=float(pc.get("occasion_floor", 0.1)), report_loops=reports)
            if kind in ("reminder", "return_promise", "report_back") and payload is not None:
                lam = float("inf")
            else:
                p_hat = T.p_expected(self._pm_of(p), d_.weekday(), hour)
                rate = sum(c.get("answered_14d", [1.0])) / max(1, len(c.get("answered_14d", [1.0])))
                unans = int(c.get("unanswered", 0)) + (1 if c.get("awaiting_since") is not None else 0)
                lam = W * O * p_hat * U.damping(unans, rate) * float(pc.get("urge_gain", 2.5))
            what = str(payload.get("what", "")) if payload is not None else ""
            cands.append((lam, p, kind, what, payload, W, O))
        if not cands:
            return
        cands.sort(key=lambda x: -x[0])
        lam, p, kind, what, payload, W, O = cands[0]
        fire = lam == float("inf") or rng.random() < U.fire_probability(lam, self.tick_s / 3600.0)
        if not fire:
            return
        loop_id = payload.get("id") if (payload is not None and kind in ("reminder", "return_promise", "care", "ask_other", "report_back")) else None
        entry = payload.get("entry") if (payload is not None and kind == "olive_branch") else None
        eid = self._event("proactive_fired", {"kind": kind, "what": what, "loop": loop_id, "entry": entry, "counterpart": p,
                                              "W": round(W, 3), "O": round(O, 3)}, t, counterpart=p, dedup=f"urge:{k}")
        if eid is None:
            return
        row = self.conn.execute("SELECT id, at, kind, payload, applied_tick, counterpart FROM events WHERE id=?", (eid,)).fetchone()
        self._apply_event_row(row, k)
        job: Dict[str, Any] = {"kind": kind, "what": what, "at": t, "counterpart": p, "loop": loop_id}
        if kind == "ask_other" and payload is not None:      # the cue names who asked
            job["fmt"] = {"who": self._name(payload.get("counterpart") or MAIN)}
        elif kind == "report_back" and payload is not None:  # the cue carries what she found out, or that she could not
            who = self._name(payload.get("asking") or (payload.get("ask") or [""])[0] or MAIN)
            job["fmt"] = {"who": who}
            job["extra"] = (f"她問到的結果：{payload['answer']}" if payload.get("answer") else f"她去問了{who}，但一直沒得到回覆，沒問到")
        self._send_q.put(job)

    # ------------------------------------------------------------------ B: apply an appraisal
    def _apply_appraisal(self, row: Any, k: int) -> None:
        aid, _at, data_s, counterpart, turn_id = row[0], row[1], row[2], row[3], row[4]
        t = self.time_of(k)
        data = json.loads(data_s)
        p = counterpart or MAIN
        if p not in (MAIN,) and p not in self.others and p == self.term_fn():
            p = MAIN  # rows written before 0.7.0 stored the display term
        term = self._name(p)
        rel = self._rel(p)
        led = self.ledger.setdefault(p, [])
        ch = self.cfg["character"]
        born: List[str] = []
        for n, ev in enumerate(data.get("events", [])):
            new_ids = self._born_from(ev, k, t, aid, f"{aid}_{n}", counterpart=p)
            born += new_ids
            kind = ev.get("event_kind", "other")
            if p == MAIN:
                N.satisfy(self.needs, q=float(ev.get("q", 0.3)), event_kind=kind, other_focus=float(ev.get("other_focus", 0.0)))
            else:
                self._other(p)["need"] = max(0.0, float(self._other(p)["need"]) - 0.6 * float(ev.get("q", 0.3)))
            RL.turn(rel, q=float(ev.get("q", 0.3)), minutes=float(self._turn_minutes.get(p, 1.5)) if n == 0 else 0.0, event_kind=kind, ppr=ev.get("ppr"),
                    she_disclosed=bool(ev.get("she_disclosed")), other_disclosed=bool(ev.get("other_disclosed")), t=t)
            if ev.get("other_tired"):
                rel["tired_until"] = t + 3 * 3600
            for iid in new_ids:
                inst = self.instances[iid]
                if inst["type"] == "hurt":
                    led.append(RL.open_entry(cause=inst["cause"], severity=float(ev.get("R", 0.5)) * abs(float(ev.get("v", 0.0))),
                                             intent=float(ev.get("intent", 0.3)), forbearance=self.derived["forbearance"], anxiety=rel["anxiety"],
                                             bond=rel["bond"], t=t, eid=iid))
            if kind in ("apology", "false_belief_corrected"):
                RL.ledger_repair(led, kind, int(ev.get("apology_components", 3)), t)
        loops = data.get("loops") or {}
        pc = self.cfg.get("proactive", {})
        known = self._known_others()
        for i, l in enumerate(loops.get("new") or []):
            if l.get("agreed") is False and l.get("origin") in ("her_promise", "counterpart_said") and pc.get("promise_requires_agreement", True):
                continue  # she did not commit: no loop, nothing to come back to
            lid = f"ol_{k}_{aid}_{i}"
            cue = l.get("cue_time")
            if not cue and l.get("origin") == "her_promise":   # 「等我一下」: due when the current block ends, else in 30 min
                cue = self.local(t + 1800).strftime("%Y-%m-%dT%H:%M")
            ask = [x for x in (l.get("ask") or []) if x in known and x != p]
            if not ask:  # the model may name a character instead of the id
                ask = [i_ for i_, n in known.items() if i_ != p and any(str(x) == n for x in (l.get("ask") or []))]
            rec = {"id": lid, "what": l["what"], "origin": l.get("origin", "counterpart_said"), "cue_time": cue,
                   "importance": float(l.get("importance", 0.5)), "state": "waiting", "created_at": t, "closed_at": None, "counterpart": p,
                   "ask": ask, "asking": None, "answer": None, "tries": 0, "asked_at": None}
            for x in ask:
                self._other(x)  # the one to ask becomes a counterpart she will go and talk to
            self.loops[lid] = rec
            self._save_loop(rec)
        answers = {str(e.get("loop_id")): str(e.get("cause") or "") for e in (data.get("events") or []) if e.get("loop_id")}
        for lid in list(loops.get("closed") or []) + [x for x, _ in answers.items() if x not in (loops.get("closed") or [])]:
            if lid not in self.loops or self.loops[lid]["state"] in ("closed", "expired"):
                continue
            l = self.loops[lid]
            if l["state"] == "asking" and l.get("asking") == p:
                # the character she asked answered (closed by the appraisal of THAT conversation): she now owes you a report
                self._ask_outcome(l, answers.get(lid) or "問到了", t)
                continue
            if lid not in (loops.get("closed") or []):
                continue
            l["state"], l["closed_at"] = "closed", t
            self.conn.execute("UPDATE loops SET state='closed', closed_at=? WHERE id=?", (t, lid))
            self.needs["certainty"] = max(0.0, self.needs["certainty"] - 0.2)
        if data.get("farewell"):
            self.contact["farewell_until"] = t + 8 * 3600
        self.conn.execute("UPDATE appraisals SET applied_tick=? WHERE id=?", (k, aid))
        self.conn.execute("INSERT INTO events(at, tick, kind, counterpart, payload) VALUES (?,?,?,?,?)",
                          (t, k, "appraisal_applied", term, json.dumps({"appraisal_id": aid, "born": born,
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
        else:
            inst["intensity0"], inst["born_at"], inst["born_tick"] = round(I * frac, 4), t, k
            self.conn.execute("UPDATE instances SET intensity0=?, born_at=?, born_tick=?, resolved_by=? WHERE id=?",
                              (inst["intensity0"], t, k, f"reduced:{by}", iid))

    # ------------------------------------------------------------------ replayable events
    def _apply_event_row(self, row: Any, k: int) -> None:
        eid, _at, kind, payload_s, _applied, _cp = row[0], row[1], row[2], row[3], row[4], row[5]
        t = self.time_of(k)
        p = json.loads(payload_s or "{}")
        cp = p.get("counterpart") or MAIN
        if kind == "turn":
            if not p.get("event"):
                if cp == MAIN:
                    self._contact_turn(t, k, p)
                else:
                    self._contact_turn_other(cp, t, k)
        elif kind == "cmd_feedback":
            typ, verdict = str(p.get("type") or ""), str(p.get("verdict") or "")
            if typ:
                g = float(self.gain_adj.get(typ, 1.0)) * (1.05 if verdict == "too_little" else 0.95 if verdict == "too_much" else 1.0)
                self.gain_adj[typ] = round(max(0.5, min(2.0, g)), 4)
        elif kind == "proactive_fired":
            fk, what, lid = p.get("kind"), str(p.get("what") or ""), p.get("loop")
            if p.get("entry"):
                for e in self.ledger.get(cp, []):
                    if e["id"] == p["entry"]:
                        e["olive_offered"] = True
            if lid and lid in self.loops and fk in ("reminder", "return_promise", "report_back"):
                self.loops[lid]["state"] = "asked"
                self._save_loop(self.loops[lid])
            elif lid and lid in self.loops and fk == "ask_other":
                l = self.loops[lid]
                l["state"], l["asking"], l["asked_at"] = "asking", cp, t
                self._save_loop(l)
            if fk == "share":
                self.share_backlog = [s for s in self.share_backlog if s.get("what") != what]
            if fk != "ask_other":  # a question carried to another character is not one of her messages to you
                self.contact["proactive_today"] = int(self.contact["proactive_today"]) + 1
            self._contact_of(cp)["pending"] = {"kind": fk, "what": what, "at": t, "tick": k, "loop": lid}
        elif kind == "sent":
            c = self._contact_of(cp)
            c["last_sent_at"], c["awaiting_since"], c["pending"] = t, t, None
            lid = p.get("loop")
            if lid and lid in self.loops:
                l = self.loops[lid]
                l["fails"], l["next_try"], l["first_fail_at"] = 0, None, None
                if p.get("kind") == "ask_other":
                    l["tries"] = int(l.get("tries") or 0) + 1   # the question really went out (556d keeps it if they are down)
                self._save_loop(l)
        elif kind in ("silent", "send_failed"):
            self._contact_of(cp)["pending"] = None
            fk = p.get("kind")
            if kind == "silent" and fk != "ask_other":
                self.contact["proactive_today"] = max(0, int(self.contact["proactive_today"]) - 1)
            lid = p.get("loop")
            if lid and lid in self.loops:
                l = self.loops[lid]
                if kind == "send_failed":
                    # the platform failed, not her: the item is not used up. Back to where it was, with a backoff
                    # (5, 15, 60 min, then hourly); after undelivered_window_h it becomes 忘了
                    l["fails"] = int(l.get("fails") or 0) + 1
                    l["first_fail_at"] = l.get("first_fail_at") or t
                    l["next_try"] = t + [300, 900, 3600][min(2, l["fails"] - 1)] if l["fails"] <= 3 else t + 3600
                    if fk == "report_back":
                        l["state"] = "answered"
                    elif fk in ("reminder", "return_promise"):
                        l["state"] = "due"
                    elif fk == "ask_other":
                        l["state"], l["asked_at"] = "due", None
                    self._save_loop(l)
                elif fk == "ask_other" and l["state"] == "asking":
                    self._ask_outcome(l, None, t)               # she chose not to ask now: next free slot
                elif fk == "report_back" and l["state"] == "asked":
                    l["state"], l["next_try"] = "answered", t + 3600   # not the moment to tell you: in an hour
                    self._save_loop(l)
        elif kind == "cmd_close_loop":
            lid = p.get("loop")
            if lid in self.loops and self.loops[lid]["state"] not in ("closed", "expired"):
                self.loops[lid]["state"], self.loops[lid]["closed_at"] = "closed", t
                self.conn.execute("UPDATE loops SET state='closed', closed_at=? WHERE id=?", (t, lid))
        elif kind == "cmd_add_loop":
            lid = f"ol_{k}_cmd_{eid}"
            rec = {"id": lid, "what": str(p.get("what", ""))[:120], "origin": "counterpart_said", "cue_time": p.get("cue_time"),
                   "importance": float(p.get("importance", 0.7)), "state": "waiting", "created_at": t, "closed_at": None, "counterpart": MAIN}
            self.loops[lid] = rec
            self.conn.execute("INSERT OR REPLACE INTO loops(id, what, origin, cue_time, importance, state, created_at, counterpart) VALUES (?,?,?,?,?,?,?,?)",
                              (lid, rec["what"], rec["origin"], rec["cue_time"], rec["importance"], "waiting", t, rec["counterpart"]))
        elif kind == "cmd_life_event":
            e = {"text": str(p.get("text", ""))[:120], "v": float(p.get("v", -0.2)), "R": float(p.get("R", 0.4)), "kind": "manual", "share": bool(p.get("share", True))}
            self._life_event(e, k, t, dedup=f"life_cmd:{eid}")
        self.conn.execute("UPDATE events SET applied_tick=? WHERE id=?", (k, eid))
        self.conn.commit()

    def _contact_turn(self, t: float, k: int, p: Dict[str, Any]) -> None:
        d = self.local(t)
        lt = self.contact.get("last_turn_at")
        gap_min = (t - lt) / 60.0 if lt is not None else 99.0
        self.contact["minutes_today"] = float(self.contact["minutes_today"]) + (gap_min if gap_min <= L.CHAT_WINDOW_MIN else 1.5)
        self._turn_minutes[MAIN] = gap_min if gap_min <= L.CHAT_WINDOW_MIN else 1.5
        self.contact["turns_today"] = int(self.contact["turns_today"]) + 1
        self.contact["last_turn_at"] = t
        aw = self.contact.get("awaiting_since")
        if aw is not None:
            T.add_latency(self.pm, (t - aw) / 3600.0)
            self.contact["answered_14d"] = (self.contact.get("answered_14d", []) + [1.0])[-14:]
            self.contact["awaiting_since"] = None
        self.contact["unanswered"] = 0
        T.saw_turn(self.pm, d.weekday(), d.hour + d.minute / 60.0)
        if self.sleep.get("asleep") and self.cfg.get("life", {}).get("wake_on_message", True):
            if L.SleepState.wake_by_message(self.sleep, t):
                self._event("sleep", {"what": "woken_by_message"}, t, dedup=f"sleep:woken:{k}")
                self.activity = "woken"
                cl = self.clinginess_eff
                if cl >= 0.3:
                    self._born_direct("joy", 0.15 * cl, f"半夜被{self.term_fn()}的訊息叫醒，但是他來找她", k, t)
                else:
                    self._born_direct("distress", 0.12, f"半夜被{self.term_fn()}的訊息吵醒", k, t)

    def _contact_turn_other(self, p: str, t: float, k: int) -> None:
        o = self._other(p)
        c = o["contact"]
        d = self.local(t)
        lt_ = c.get("last_turn_at")
        gap = (t - lt_) / 60.0 if lt_ is not None else 99.0
        self._turn_minutes[p] = gap if gap <= L.CHAT_WINDOW_MIN else 1.5
        c["last_turn_at"] = t
        if c.get("awaiting_since") is not None:
            T.add_latency(o["pm"], (t - c["awaiting_since"]) / 3600.0)
            c["answered_14d"] = (c.get("answered_14d", []) + [1.0])[-14:]
            c["awaiting_since"] = None
        c["unanswered"] = 0
        T.saw_turn(o["pm"], d.weekday(), d.hour + d.minute / 60.0)

    def _annotate_memory(self, turn_id: str, events: List[Dict[str, Any]], born: List[str]) -> None:
        try:
            if not self.memory_db or not Path(self.memory_db).exists():
                return
            v = sum(e["v"] * e["R"] for e in events) / max(1e-6, sum(e["R"] for e in events))
            arousal = max((self.instances[i]["intensity0"] for i in born if i in self.instances), default=0.0)
            patch = json.dumps({"valence": round(v, 3), "arousal": round(arousal, 3), "instance_ids": born}, ensure_ascii=False)
            if self._annotate_rows(turn_id, patch) == 0:
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

    # ------------------------------------------------------------------ inputs (live)
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
                self.step_to(at)
                row = self.conn.execute("SELECT id, at, data, counterpart, turn_id, applied_tick FROM appraisals WHERE id=?", (aid,)).fetchone()
                if row and row[5] is None:
                    self._apply_appraisal(row, self.tick)
                    self.snapshot()
            return aid

    def _record_and_apply(self, kind: str, payload: Dict[str, Any], at: Optional[float] = None, counterpart: str = "") -> None:
        at = self.now_fn() if at is None else at
        with self.lock:
            eid = self._event(kind, payload, at, counterpart=counterpart)
            if eid is None or not self.owner:
                return
            self.step_to(at)
            row = self.conn.execute("SELECT id, at, kind, payload, applied_tick, counterpart FROM events WHERE id=?", (eid,)).fetchone()
            if row and row[4] is None:
                self._apply_event_row(row, self.tick)
            if self.live:
                self.snapshot()  # the 狀態 page reads the latest snapshot

    def on_turn(self, user_text: str, assistant_text: str, *, turn_id: str, platform: str, session_id: str, counterpart: str = MAIN) -> None:
        """A finished turn (yours, or another character's): a replayable turn event (contact, presence,
        waking), the recent-turns ring, and appraisal A queued."""
        term = self._name(counterpart)
        if counterpart == MAIN and session_id and session_id != self.session_id:
            self.session_id = session_id
            self._meta("session_id", session_id)
        if counterpart != MAIN:
            self._other(counterpart)
        self._record_and_apply("turn", {"turn_id": turn_id, "platform": platform, "session": session_id[:24], "counterpart": counterpart,
                                        "user": user_text[:500], "assistant": assistant_text[:500]}, counterpart=counterpart)
        if self.owner and self.llm is not None:
            self._q.put({"user": user_text, "assistant": assistant_text, "turn_id": turn_id, "platform": platform,
                         "recent": list(self.recent), "term": term, "counterpart": counterpart, "at": self.now_fn()})
        self.recent = (self.recent + [(user_text, assistant_text)])[-int(self.cfg["appraisal"]["recent_turns"]):]

    def on_event_reply(self, event_text: str, reply: str, *, platform: str, counterpart: str = MAIN) -> bool:
        """Her answer to an event turn: she spoke (sent) or decided not to (silent). Returns True when a
        message was sent (the plugin relays it to another character through 556d)."""
        pend = self._contact_of(counterpart).get("pending") or {}
        if EV.is_silence(reply):
            self._record_and_apply("silent", {"kind": pend.get("kind"), "what": pend.get("what"), "counterpart": counterpart, "loop": pend.get("loop")},
                                   counterpart=counterpart)
            return False
        self._record_and_apply("sent", {"kind": pend.get("kind"), "what": pend.get("what"), "text": reply[:500], "platform": platform,
                                        "counterpart": counterpart, "loop": pend.get("loop")}, counterpart=counterpart)
        self.recent = (self.recent + [(f"（{self.pr}主動傳的）", reply)])[-int(self.cfg["appraisal"]["recent_turns"]):]
        return True

    def record_check(self, text: str, platform: str) -> Dict[str, List[str]]:
        hits = CK.run(text)
        if hits:
            with self.lock:
                self.conn.execute("INSERT INTO checks(at, tick, platform, hits, excerpt) VALUES (?,?,?,?,?)",
                                  (self.now_fn(), self.tick, platform, json.dumps(hits, ensure_ascii=False), (text or "")[:200]))
                self.conn.commit()
        return hits

    def drain_commands(self) -> int:
        """Commands from the 狀態 page (556d writes the commands table, like memory deletes): each becomes
        a replayable cmd_* event applied now."""
        rows = self.conn.execute("SELECT id, op, payload FROM commands WHERE done_at IS NULL ORDER BY id").fetchall()
        n = 0
        for cid, op, payload_s in rows:
            try:
                p = json.loads(payload_s or "{}")
                kind = {"close_loop": "cmd_close_loop", "add_loop": "cmd_add_loop", "life_event": "cmd_life_event", "feedback": "cmd_feedback"}.get(op)
                if kind:
                    self._record_and_apply(kind, p)
                    res = "done"
                else:
                    res = f"unknown op {op}"
            except Exception as exc:  # noqa: BLE001
                res = f"error: {exc}"
            self.conn.execute("UPDATE commands SET done_at=?, result=? WHERE id=?", (self.now_fn(), res, cid))
            self.conn.commit()
            n += 1
        return n

    def reload_proactive(self) -> None:
        """Settings that gate behaviour (proactive, busyness) apply without a restart; dynamics do not."""
        from . import config as C
        try:
            p = self.home / C.FILE
            m = p.stat().st_mtime
            if self._last_cfg_mtime is not None and m == self._last_cfg_mtime:
                return
            self._last_cfg_mtime = m
            fresh = C.load(self.home, write_defaults=False)
            self.cfg["proactive"] = fresh.get("proactive", self.cfg.get("proactive", {}))
            self.cfg.setdefault("life", {})["busyness_mode"] = fresh.get("life", {}).get("busyness_mode", "work")
            self.cfg["cares_about"] = fresh.get("cares_about", self.cfg.get("cares_about", []))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ threads
    def _appraise_worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                cp = job.get("counterpart", MAIN)
                loops = []
                for l in self._loops_for(cp, ("waiting", "due", "asked", "asking", "answered", "forgot")):
                    note = ""
                    if l["state"] == "forgot":
                        note = f"（{self.pr}忘了這件事，沒做；若對方提起，回報 promise_broken（agent self）並關閉）"
                    elif l["state"] == "asking" and l.get("asking") == cp:
                        note = f"（代問：{self.pr}正替{self._name(l.get('counterpart') or MAIN)}問{job['term']}這件事；問到答案就關閉）"
                    elif l["state"] == "asking":
                        note = f"（{self.pr}已去問{self._name(l['asking'])}，等回覆）"
                    elif l["state"] == "answered":
                        note = f"（問到了：{l.get('answer') or '對方沒回'}）"
                    loops.append({**l, "note": note})
                today = self.local(job["at"]).strftime("%Y-%m-%d %H:%M")
                ac = self.cfg["appraisal"]
                data, raw, err, ms = A.run(self.llm, term=job["term"], cares_about=self.cfg.get("cares_about", []), loops=loops,
                                           recent=job["recent"], user_text=job["user"], assistant_text=job["assistant"], today=today,
                                           max_events=int(ac["max_events"]), retries=int(ac["retries"]), pronoun=self.pr,
                                           others=self._known_others())
                self.record_appraisal(data, raw=raw, error=err, ms=ms, turn_id=job["turn_id"], counterpart=job.get("counterpart", MAIN),
                                      platform=job["platform"], at=job["at"])
                if err:
                    logger.warning("psyche appraisal failed: %s", err)
                else:
                    logger.info("psyche appraisal: %s (%.0f ms)", [e["event_kind"] for e in data["events"]], ms)
            except Exception:  # noqa: BLE001
                logger.exception("psyche appraisal worker error")
            finally:
                self._q.task_done()

    def _send_worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._send_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                base, key = EV.api_base()
                cp = job.get("counterpart", MAIN)
                if cp == MAIN:
                    sid = self.session_id or EV.live_session_id(self.state_db)
                else:
                    sid = EV.counterpart_session(self.hub_url, self.char, cp)
                if not base or not sid:
                    logger.warning("psyche: cannot send an event turn (api %r, session %r, to %s)", base, sid, cp)
                    self._record_and_apply("send_failed", {"why": "no api or session", "kind": job["kind"], "what": job["what"], "counterpart": cp,
                                                           "loop": job.get("loop")}, counterpart=cp)
                    continue
                now_text = self.local(self.now_fn()).strftime("%Y-%m-%d %H:%M（%a）")
                text = EV.compose(job["kind"], term=self._name(cp), what=job["what"], now_text=now_text, pronoun=self.pr,
                                  extra=str(job.get("extra") or ""), **(job.get("fmt") or {}))
                logger.info("psyche: event turn (%s) -> %s", job["kind"], "her API" if cp == MAIN else f"{cp} via her API")
                t0 = self.now_fn()
                reply, err = EV.send(base, key, sid, text)
                if err:
                    logger.warning("psyche: event turn failed: %s", err)
                    self._record_and_apply("send_failed", {"why": err[:200], "kind": job["kind"], "what": job["what"], "counterpart": cp,
                                                           "loop": job.get("loop")}, counterpart=cp)
                    EV.discard(self.hub_url, self.char, sid, text)
                elif not (reply or "").strip() or EV.looks_error(reply):
                    # the platform answered with an error (or nothing) instead of her words — e.g. every model backend
                    # down. Hermes stores the cue but runs no hook, so no sent / silent would ever be recorded.
                    time.sleep(2.0)
                    with self.lock:
                        seen = self.conn.execute("SELECT 1 FROM events WHERE kind IN ('sent','silent','send_failed') AND at >= ? AND counterpart = ? LIMIT 1",
                                                 (t0 - 1, cp)).fetchone()
                    if not seen:
                        why = ("agent error: " + reply.strip()[:200]) if (reply or "").strip() else "empty reply"
                        logger.warning("psyche: event turn answered with an error: %s", why)
                        self._record_and_apply("send_failed", {"why": why, "kind": job["kind"], "what": job["what"], "counterpart": cp,
                                                               "loop": job.get("loop")}, counterpart=cp)
                        EV.discard(self.hub_url, self.char, sid, text)  # the cue must not re-enter her context later
                # a successful send is recorded by the post_llm_call hook (sent / silent)
            except Exception:  # noqa: BLE001
                logger.exception("psyche send worker error")
            finally:
                self._send_q.task_done()

    def pending_appraisals(self) -> int:
        return self._q.qsize()

    def start(self, pid: int) -> bool:
        self.owner = self.acquire_owner(pid)
        if not self.owner:
            logger.info("psyche: another process owns %s; read-only here", self.db_path)
            return False
        self.load()
        self.live = True
        self._stop.clear()
        self._tick_thread = threading.Thread(target=self._tick_loop, args=(pid,), name="psyche-tick", daemon=True)
        self._tick_thread.start()
        if self.llm is not None:
            self._worker = threading.Thread(target=self._appraise_worker, name="psyche-appraise", daemon=True)
            self._worker.start()
        self._sender = threading.Thread(target=self._send_worker, name="psyche-send", daemon=True)
        self._sender.start()
        return True

    def _tick_loop(self, pid: int) -> None:
        while not self._stop.wait(timeout=max(1.0, self.tick_s / 4)):
            try:
                self.reload_proactive()
                with self.lock:
                    self.step_to(self.now_fn())
                    self.drain_commands()
                self.heartbeat(pid)
                self._retry_annotations()
            except Exception:  # noqa: BLE001
                logger.exception("psyche tick failed")

    def stop(self, drain_s: float = 20.0) -> None:
        deadline = time.time() + drain_s
        while (self._q.unfinished_tasks or self._send_q.unfinished_tasks) and time.time() < deadline:
            time.sleep(0.2)
        self._stop.set()
        self.live = False
        if self.owner:
            try:
                with self.lock:
                    self.step_to(self.now_fn(), snapshots=False)
                    self._event("stop", {"tick": self.tick})
                    self.snapshot()
            except Exception:  # noqa: BLE001
                logger.exception("psyche stop snapshot failed")

    # ------------------------------------------------------------------ expression layer: the state block
    def state_block(self, *, t: Optional[float] = None, term: Optional[str] = None, counterpart: str = MAIN) -> str:
        """【她現在】 for a turn with `counterpart` — at most max_lines lines, words not numbers; feelings
        about this person first; the 表現 line carries the strategy (§15); a transition is named when
        the dominant feeling changed since the last block, so the history's tone inertia does not win."""
        t = self.now_fn() if t is None else t
        term = term or self._name(counterpart)
        with self.lock:
            if self.owner:
                self.step_to(t)
            else:
                snap = self.latest_snapshot()
                if snap:
                    self._restore(snap)
            ch = self.cfg["character"]
            ex = self.cfg["expression"]
            thr = float(ex["expression_threshold"])
            rel = self._rel(counterpart)
            led = self.ledger.get(counterpart, [])
            gate = RL.hurt_gate(led)
            tired = bool(rel.get("tired_until")) and t < float(rel.get("tired_until") or 0)
            expr = float(ch.get("expressiveness", 0.6))
            act_all = self.active(t)
            mine = [i for i in act_all if i.get("target") in (term, "") or i.get("target") is None]
            others_ = [i for i in act_all if i not in mine]
            def shown(i):
                return RL.expressed_level(i["intensity"], expressiveness=expr, bond=rel["bond"], suppressed=(tired and i["type"] in model.NEGATIVE))
            act = [i for i in mine if shown(i) >= thr] + [i for i in others_ if shown(i) >= thr * 1.5]
            act_zh = L.ACTIVITIES.get(self.activity, L.ACTIVITIES["rest"])[4]
            if counterpart != MAIN:
                act_zh = f"正在跟{term}說話（不是跟{self.term_fn()}），本來{act_zh}"
            elif self.activity == "chat":
                act_zh = "在跟" + term + "聊天"
            lines = [f"【{self.pr}現在】", f"在做：{act_zh}，{L.energy_word(self.energy, self.activity)}"]
            _, oct_zh, strength = model.octant(self.mood)
            mood_word = f"{model.intensity_word(strength)}{oct_zh}" if strength >= 0.2 else "平靜"
            feelings = []
            for i in act[:2]:
                w = model.intensity_word(shown(i))
                zh = model.EMOTION_ZH.get(i["type"], i["type"]).replace("對方", i.get("target") or term)
                cause = (i.get("cause") or "").strip()
                feelings.append(f"{w}{zh}" + (f"（{cause}）" if cause else ""))
            lines.append("心情：" + (f"整體{mood_word}；" if feelings else f"整體{mood_word}") + "、".join(feelings))
            heart = N.words(dict(self.needs, affiliation_person=self._need_of(counterpart)), self._contact_of(counterpart).get("phase", "ok"), term)
            if heart:
                lines.append("心裡：" + heart)
            dominant = act[0] if act else None
            name, how = RL.strategy(dominant, character=ch, rel=rel, gate=gate, other_tired=tired, rng_u=self._rng(self.tick, "expr").random(),
                                    negative_types=model.NEGATIVE, shown=act[:2])
            self.last_strategy[counterpart] = name
            if self.activity == "woken":
                how.append("很睏，回一兩句就好")
            elif self.energy < 0.35 or self.fatigue > 0.6 or rel["avoidance"] > 0.6:
                how.append("話少一點")
            elif self.affect["ar"] > 0.75:
                how.append("可以多說一點")
            if self.activity == "work":
                how.append(f"手上在忙，可以回短一點或說等{self.pr}一下，忙完會回來找他")
            if len(act) >= 2 and ((act[0]["type"] in model.POSITIVE) != (act[1]["type"] in model.POSITIVE)):
                how.append("兩種情緒並存時先回應對方說的，再帶到自己的")
            fw = self.contact.get("farewell_until")
            if counterpart == MAIN and fw is not None and t < fw:
                how.append("剛道過別：溫和接受，可以說一次捨不得，不挽留")
            lines.append("表現：" + "；".join(how))
            rel_line = RL.closeness_words(rel, term)
            open_hurt = [e for e in led if e.get("resolved_at") is None]
            if open_hurt and gate >= 0.15:
                rel_line += f"；心裡還記著一筆（{open_hurt[-1]['cause'][:30]}）"
            if rel["hours"] > 0 or rel["bond"] > 0 or counterpart != MAIN:
                lines.append(f"對{term}：{rel_line}")
            waiting = self._loops_for(counterpart, ("waiting", "due", "asked", "asking", "answered"))
            waiting.sort(key=lambda l: (l["state"] not in ("due", "answered"), -float(l.get("importance", 0.5))))

            def tag(l: Dict[str, Any]) -> str:
                if l["state"] == "due":
                    return "（到了）"
                if l["state"] == "asking":
                    who = self._name(l.get("counterpart") or MAIN)
                    return f"（替{who}問的）" if counterpart != MAIN else f"（已去問{self._name(l['asking'])}，等回覆）"
                if l["state"] == "answered":
                    return f"（問到了：{str(l.get('answer'))[:24]}）" if l.get("answer") else "（去問了，沒問到）"
                return ""
            if waiting:
                lines.append("掛念：" + "、".join(l["what"] + tag(l) for l in waiting[:2]))
            dom_type = dominant["type"] if dominant else None
            prev = self.last_block.get("dominant")
            prev_word = self.last_block.get("word")
            if prev and prev != dom_type and self.last_block.get("counterpart", MAIN) == counterpart:
                now_word = (model.intensity_word(shown(dominant)) + model.EMOTION_ZH[dom_type]) if dominant else "已經平復了"
                lines.append(f"轉變：剛才{prev_word}，現在{now_word}")
            lines.append("原則：情緒是底色，內容以對方的話題為主；不提沒做過的事；有自己的看法，不用附和")
            text = "\n".join(lines[: int(ex.get("max_lines", 9))])
            self.last_block = {"dominant": dom_type, "word": (model.intensity_word(shown(dominant)) + model.EMOTION_ZH[dom_type]) if dominant else "平靜",
                               "at": t, "mood": mood_word, "text": text, "counterpart": counterpart, "strategy": name}
            if self.live:
                self.snapshot()
            return text

    def status(self) -> Dict[str, Any]:
        with self.lock:
            t = self.time_of(self.tick)
            name, zh, strength = model.octant(self.mood)
            d = self.local(t)
            return {"tick": self.tick, "t": t, "energy": self.energy, "affect": dict(self.affect), "mood": list(self.mood),
                    "octant": name, "octant_zh": zh, "strength": strength, "activity": self.activity,
                    "sleep": dict(self.sleep), "fatigue": self.fatigue, "needs": dict(self.needs),
                    "contact": {k: v for k, v in self.contact.items() if k != "answered_14d"},
                    "p_expected": T.p_expected(self.pm, d.weekday(), d.hour + d.minute / 60.0),
                    "instances": [{k: v for k, v in i.items() if k != "pad"} for i in self.active(t)],
                    "loops": [l for l in self.loops.values() if l["state"] not in ("closed", "expired")],
                    "share_backlog": list(self.share_backlog), "block": self.last_block.get("text", ""),
                    "rel": {p: {**r, "trust_value": RL.trust_value(r), "words": RL.closeness_words(r, self._name(p))} for p, r in self.rel.items()},
                    "ledger": {p: [e for e in v if e.get("resolved_at") is None] for p, v in self.ledger.items()},
                    "others": {p: {"need": o["need"], "phase": o["contact"].get("phase"), "last_turn_at": o["contact"].get("last_turn_at")} for p, o in self.others.items()},
                    "gain_adj": dict(self.gain_adj), "strategy": dict(self.last_strategy)}
