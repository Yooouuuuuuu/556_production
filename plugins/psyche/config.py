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
        "snapshot_interval_min": 15,
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
    keep = {k: cfg.get(k) for k in ("character", "time", "impact", "expression")}
    return hashlib.sha1(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
