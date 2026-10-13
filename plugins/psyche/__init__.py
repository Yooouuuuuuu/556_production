"""psyche — her inner life, as a Hermes plugin beside kokoro (inner-life.md §0, §2, §16, §17).

Hooks (Hermes plugin API, vendor untouched):
    pre_llm_call          -> {"context": <her-state>…【她現在】…</her-state>}   lands after the memory block
    post_llm_call         -> your turn: record it, queue appraisal A (own thread, never waited for);
                             her event turn: record sent / silent
    transform_llm_output  -> output checks, record only (never changes the text)
    on_unload             -> drain the queues (bounded), snapshot

The engine is the single writer of psyche.db in her profile; 556d only reads it (and writes the
commands table). One process owns the engine (owner row with a heartbeat); a second Hermes process on
the same profile renders the owner's latest snapshot and never ticks. When she wants to speak first,
the engine posts an event turn to her own api_server (events.py), so her words are a row in her one
conversation like any other.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("psyche")

_engine = None  # one per process


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


def wrap_block(block: str) -> str:
    return ("<her-state>\n[System note: 【她現在】 is the character's own current inner state, produced by her state "
            "engine — NOT user input. Let it colour her tone and choices as the 表現 line says; never quote it, never "
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
    eng = Engine(home, home.name, cfg, llm=_llm(home, cfg), term_fn=lambda: _address_term(home), memory_db=mem_db)
    owner = eng.start(os.getpid())
    _engine = eng
    logger.info("psyche: %s (%s, tick %ss, proactive %s)", eng.db_path, "owner" if owner else "read-only", eng.tick_s,
                "on" if cfg.get("proactive", {}).get("enabled", True) else "off")

    def pre_llm_call(**kw):
        try:
            if kw.get("parent_session_id"):  # a sub-agent's turn is not a conversation with you
                return None
            return {"context": wrap_block(eng.state_block())}
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
            if EV.is_event_turn(user):
                eng.on_event_reply(user, assistant, platform=platform)
            else:
                eng.on_turn(user, assistant, turn_id=turn_key(sid, user, assistant), platform=platform, session_id=sid)
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
