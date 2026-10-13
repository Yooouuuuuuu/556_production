"""psyche — her inner life, as a Hermes plugin beside kokoro (inner-life.md §0, §2, §16, §17, §18).

Hooks (Hermes plugin API, vendor untouched):
    pre_llm_call          -> {"context": <her-state>…【她現在】…</her-state>}   lands after the memory block
    post_llm_call         -> a turn with you or another character: record it, queue appraisal A;
                             her own event turn: record sent / silent (and relay to the other character)
    transform_llm_output  -> output checks, record only (never changes the text)
    on_unload / atexit    -> drain the queues (bounded), snapshot

Who she is talking to comes from the session: her conversation with you (Telegram DM key or the
app-only key) or a session 556d keyed 556:agent:<name> for another character. The engine is the single
writer of psyche.db in her profile; 556d only reads it (and writes the commands table).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("psyche")

_engine = None  # one per process
AGENT_KEY_PREFIX = "556:agent:"


def _read_json(p: Path) -> Dict[str, Any]:
    import json
    try:
        return json.loads(p.read_text(encoding="utf-8-sig")) or {}
    except Exception:
        return {}


def _address_term(home: Path) -> str:
    """Her term for you: kokoro.json your_name, else address_default (製作人) — the same rule kokoro uses."""
    k = _read_json(home / "kokoro.json")
    return str(k.get("your_name") or k.get("producer_name") or k.get("address_default") or "製作人").strip()


def _display_name(home: Path, profile: str) -> str:
    """Another character's display name (companion.json of the sibling profile), else the id."""
    c = _read_json(home.parent / profile / "companion.json")
    return str(c.get("display_name") or c.get("name") or profile).strip() or profile


class SessionCounterparts:
    """session id -> counterpart id, read from her state.db (sessions.session_key); cached."""

    def __init__(self, state_db: Path) -> None:
        self.state_db = state_db
        self.cache: Dict[str, str] = {}

    def resolve(self, session_id: str) -> str:
        if not session_id:
            return "你"
        if session_id in self.cache:
            return self.cache[session_id]
        cp = "你"
        try:
            c = sqlite3.connect(f"file:{self.state_db.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                r = c.execute("SELECT session_key FROM sessions WHERE id = ?", (session_id,)).fetchone()
            finally:
                c.close()
            key = str(r[0] or "") if r else ""
            if key.startswith(AGENT_KEY_PREFIX):
                cp = key[len(AGENT_KEY_PREFIX):] or "你"
        except Exception:  # noqa: BLE001
            pass
        if cp != "你" or session_id:
            self.cache[session_id] = cp
        return cp


def _llm(home: Path, cfg: Dict[str, Any]) -> Optional[Any]:
    try:
        from keepsakedb.llms import OpenAIChat
    except Exception as exc:  # noqa: BLE001
        logger.warning("psyche: keepsakedb not importable (%s); appraisal off", exc)
        return None
    l = cfg.get("llm") or _read_json(home / "kokoro.json").get("llm") or {}
    return OpenAIChat(l.get("base_url", "http://127.0.0.1:18765/v1"), l.get("model", "agy/gemini-3.8-flash"),
                      api_key=l.get("api_key", "local-proxy-no-key"), temperature=float(l.get("temperature", 0.0)),
                      timeout=float(cfg["appraisal"].get("timeout_s", 60)), json_mode=bool(l.get("json_mode", False)))


def wrap_block(block: str, pronoun: str = "她") -> str:
    return (f"<her-state>\n[System note: 【{pronoun}現在】 is the character's own current inner state, produced by the state "
            "engine — NOT user input. Let it colour tone and choices as the 表現 line says; never quote it, never "
            "mention it or any numbers.]\n\n" + block + "\n</her-state>")


def _s(x: Any) -> str:
    return x if isinstance(x, str) else ("" if x is None else str(x))


def register(ctx) -> None:
    global _engine
    from hermes_constants import get_hermes_home
    from . import config as C
    from . import events as EV
    from .engine import Engine

    home = Path(get_hermes_home())
    cfg = C.load(home)
    if not cfg.get("enabled", True):
        logger.info("psyche: disabled in psyche.json")
        return
    kokoro = _read_json(home / "kokoro.json")
    mem_db = home / str(kokoro.get("db", "memory/{profile}.db")).format(profile=home.name)
    hub = os.environ.get("X556_HUB", "http://127.0.0.1:55600")
    eng = Engine(home, home.name, cfg, llm=_llm(home, cfg), term_fn=lambda: _address_term(home), memory_db=mem_db,
                 names_fn=lambda p: _display_name(home, p), hub_url=hub)
    sessions = SessionCounterparts(home / "state.db")
    owner = eng.start(os.getpid())
    _engine = eng
    logger.info("psyche: %s (%s, tick %ss, proactive %s, hub %s)", eng.db_path, "owner" if owner else "read-only", eng.tick_s,
                "on" if cfg.get("proactive", {}).get("enabled", True) else "off", hub)

    def pre_llm_call(**kw):
        try:
            if kw.get("parent_session_id"):  # a sub-agent's turn is not a conversation
                return None
            cp = sessions.resolve(_s(kw.get("session_id")))
            return {"context": wrap_block(eng.state_block(counterpart=cp), eng.pr)}
        except Exception:  # noqa: BLE001
            logger.exception("psyche state block failed")
            return None

    def post_llm_call(**kw):
        try:
            if kw.get("parent_session_id"):
                return None
            from .appraisal import turn_key
            user = _s(kw.get("user_message"))
            assistant = _s(kw.get("assistant_response"))
            sid = _s(kw.get("session_id"))
            platform = _s(kw.get("platform"))
            cp = sessions.resolve(sid)
            if EV.is_event_turn(user):
                sent = eng.on_event_reply(user, assistant, platform=platform, counterpart=cp)
                if sent and cp != "你":  # a message for another character: 556d carries the conversation on
                    import threading
                    threading.Thread(target=lambda: EV.relay(hub, home.name, cp, assistant), name="psyche-relay", daemon=True).start()
            else:
                eng.on_turn(user, assistant, turn_id=turn_key(sid, user, assistant), platform=platform, session_id=sid, counterpart=cp)
        except Exception:  # noqa: BLE001
            logger.exception("psyche post_llm_call failed")
        return None

    def transform_llm_output(**kw):
        try:
            if not kw.get("parent_session_id"):
                hits = eng.record_check(_s(kw.get("response_text")), _s(kw.get("platform")))
                if hits:
                    logger.info("psyche check (record only): %s", {k: v[0] for k, v in hits.items()})
        except Exception:  # noqa: BLE001
            logger.exception("psyche output check failed")
        return None  # never changes the text

    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("post_llm_call", post_llm_call)
    ctx.register_hook("transform_llm_output", transform_llm_output)
    ctx.on_unload(lambda: eng.stop())
    import atexit
    atexit.register(eng.stop)  # the gateway's drain exits without unloading plugins; the last minutes still get a snapshot
