"""psyche.config — her engine's settings file (psyche.json in her profile).

Settings writes this file through 556d; the engine reads it at start and records a version row, so a
change applies at her next start — the same rule as tool extensions. Missing keys fall back to the
defaults below (research values from inner-life.md Appendix E; overridable, see §0 時間常數).
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

FILE = "psyche.json"

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "character": {
        # L0 — Big Five 0..1 and the six character constants (glossary E.1). Human-set per character.
        "big5": {"openness": 0.6, "conscientiousness": 0.7, "extraversion": 0.55, "agreeableness": 0.65, "neuroticism": 0.4},
        "self_esteem_stability": 0.6,
        "expressiveness": 0.6,
        "humor_coping": 0.5,
        "clinginess_cap": 0.5,
        "tsundere_tendency": 0.3,
        "assertiveness": 0.6,
        "chronotype": 0.0,
        "pronoun": "她",            # 她 | 他 — used in the state block and the event cues
    },
    # What she cares about (preference profile read by appraisal A — not her personality, which is B's).
    "cares_about": [
        "答應的事有沒有做到（約好的聊天、說會回來）",
        "對方有沒有記得她說過的事",
        "她的工作與作品被認真看待",
        "對方的身心狀況（累不累、順不順）",
        "對話是不是被敷衍帶過",
    ],
    "time": {
        "tick_s": 60,
        "snapshot_interval_min": 5,
        "affect_half_life_h": None,      # None = from neuroticism (2–6 h)
        "mood_regress_tau_h": 3.0,
        "mood_rise_max": 0.4,            # per hour
        "mood_fall_max": 0.25,
        "timezone_offset_h": 8,          # Asia/Taipei for the energy curve until the life sim owns it
    },
    "impact": {
        "prototype_width": 0.35,
        "prototype_threshold": 0.6,     # 0.5 in the design; 0.6 after the first live run (an apology also spawned a weak joy)
        "max_instances_per_event": 3,
        "secondary_factor": 0.7,
        "alpha_u": 0.6,
        "stack_multiplier": {"pos": 0.7, "neg": 0.8, "hurt": 0.85},
        "stack_limit": 4,
        "mood_congruence_coef": 0.2,
        "bond_default": 0.5,             # until L5 (0.7.0): one fixed closeness for happy_for / sorry_for
    },
    "expression": {
        "expression_threshold": 0.2,
        "max_lines": 8,
    },
    "appraisal": {
        "recent_turns": 4,
        "max_events": 3,
        "timeout_s": 60,
        "retries": 1,
    },
    "life": {  # §14 her own life: the schedule template (local hours), busyness mode, projects, small events (rule table)
        "schedule": {"bedtime": 23.5, "wake": 7.5, "bedtime_delay_max_h": 1.5,
                     "work": [[9.5, 12.5], [14.0, 18.0]], "hobby": [[10.0, 12.0], [15.0, 17.0]], "meals": [[12.5, 13.5], [18.5, 19.5]]},
        "busyness_mode": "work",          # work | hobby | none
        "wake_on_message": True,
        "projects": [{"title": "新歌的 demo", "stage": "錄音", "difficulty": 0.5, "progress": 0.0}],
        "small_events": [
            {"text": "錄音一次就過，很順", "v": 0.5, "R": 0.4, "p": 0.12, "kind": "work", "share": True},
            {"text": "咖啡店新出的季節限定很好喝", "v": 0.3, "R": 0.2, "p": 0.15, "kind": "life", "share": True},
            {"text": "耳機突然壞了", "v": -0.3, "R": 0.3, "p": 0.06, "kind": "life", "share": True},
            {"text": "有點頭痛，應該是睡不夠", "v": -0.4, "R": 0.4, "p": 0.05, "kind": "unwell", "share": True},
            {"text": "下午的會議臨時取消，多了一段空檔", "v": 0.2, "R": 0.2, "p": 0.1, "kind": "work", "share": False},
        ],
    },
    "needs": {"k_aff": 0.08, "protest_end_h": 24, "despair_end_h": 120, "need_mood_coupling": 0.1,
              "attachment_strength": 0.4},   # fixed until L5 grows it (0.7.0)
    "proactive": {  # §16 — these apply without a restart (the engine re-reads them each tick)
        "enabled": True,
        "no_disturb": [[23.0, 8.0]],     # local hours; a reminder you asked for still passes
        "daily_cap": 3,
        "usage_threshold_min": 90,       # talked this long today -> no proactive (usage awareness)
        "min_gap_min": 90,
        "urge_gain": 2.5,
        "occasion_floor": 0.1,
        "reply_timeout_default_h": 6.0,  # until the latency model has 5 samples
        "speak": "follow",               # app: speak proactive messages? follow (the current voice mode) | always | never
        "inter_agent": True,             # may she start a conversation with another character
        "inter_agent_min_gap_min": 240,
        "inter_agent_turn_cap": 6,       # exchanges per conversation (cost control, not a script)
        "inter_agent_visibility": True,  # the 狀態 page may show their conversations
        "promise_requires_agreement": True,  # a promise opens a loop only when she agreed in her reply
        "ask_retry_max": 3,              # a promise that needs another character: how many times she tries to reach them
        "ask_timeout_h": 3.0,            # ... and how long she waits for an answer before trying again
        "report_only_when_awake": True,  # the answer comes back to you outside your no-disturb hours, when you are likely around
    },
    "tom": {"weekly_decay": 0.92},
    "relation": {"k_bond": 0.004, "k_attachment": 0.0004, "trust_forget_days": 60},
    # per counterpart priors (id -> fields of relation.fresh): 你, or another character's profile id
    "relationships": {},
    "llm": None,  # None = the llm block of kokoro.json (same lane as the memory observe)
}


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(home: Path, write_defaults: bool = True) -> Dict[str, Any]:
    p = Path(home) / FILE
    raw: Dict[str, Any] = {}
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8-sig")) or {}
        except Exception:
            raw = {}
    elif write_defaults:
        try:
            p.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
    return _merge(DEFAULTS, raw)


def version(cfg: Dict[str, Any]) -> str:
    """Short hash of the parameters that shape the dynamics (psyche.db params table)."""
    keep = {k: cfg.get(k) for k in ("character", "time", "impact", "expression", "needs", "life", "relation", "relationships")}
    return hashlib.sha1(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
