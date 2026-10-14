"""psyche.urge — proactive behaviour (inner-life.md §16): one formula decides whether she wants to
speak, one occasion decides what, the gates decide whether now is allowed.

    λ = W (willingness) × O (occasion) × p̂_reply × D (damping) × 1[gates]      per hour
    P(fire in a tick) = 1 − exp(−λ·Δt)

Due loops (a reminder you asked for, her 「等我一下」, a cue that arrived) bypass the probability and
fire on time; they still respect sleep and the daily cap, and a reminder you asked for even passes
the no-disturb window. Damping: one unanswered message → wait long, two → wait for you, never a
third. Nothing here sends anything: the engine records the decision and, when live, posts the turn.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from . import life as L


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def in_no_disturb(hour: float, windows: List[List[float]]) -> bool:
    return L.in_block(hour, windows or [])


def gates(*, cfg: Dict[str, Any], hour: float, activity: str, chatting: bool, proactive_today: int,
          minutes_today: float, last_sent_at: Optional[float], t: float, farewell_until: Optional[float],
          running: bool, due_reminder: bool, due_report: bool = False, you_awake: bool = True) -> Tuple[bool, str]:
    """(allowed, why_not). due_reminder = a reminder you asked for or her promise to you: only off / stopped hold it
    back. due_report = an answer she fetched from another character for you: waits for her to be up, a decent hour
    and you being around, nothing else (no cap, gap, usage or farewell)."""
    if not cfg.get("enabled", True):
        return False, "off"
    if not running:
        return False, "stopped"
    if due_reminder:  # something you asked her to say at this time: only "off" and "stopped" can hold it back
        return True, ""
    if activity in ("sleep", "lying"):
        return False, "asleep"
    if activity == "woken":
        return False, "woken"
    if chatting:
        return False, "in_conversation"
    if due_report:
        if in_no_disturb(hour, cfg.get("no_disturb", [])):
            return False, "no_disturb"
        if not you_awake:
            return False, "you_away"
        return True, ""
    if in_no_disturb(hour, cfg.get("no_disturb", [])) and not due_reminder:
        return False, "no_disturb"
    if proactive_today >= int(cfg.get("daily_cap", 3)) and not due_reminder:
        return False, "daily_cap"
    if minutes_today >= float(cfg.get("usage_threshold_min", 90)) and not due_reminder:
        return False, "usage"
    if last_sent_at is not None and (t - last_sent_at) < float(cfg.get("min_gap_min", 90)) * 60 and not due_reminder:
        return False, "min_gap"
    if farewell_until is not None and t < farewell_until and not due_reminder:
        return False, "farewell"
    return True, ""


def willingness(*, needs: Dict[str, float], phase: str, share_backlog: List[Dict[str, Any]],
                hurt: float, anxiety: float, avoidance: float, clinginess_eff: float) -> float:
    gap = needs.get("affiliation_person", 0.0)
    phase_w = {"ok": 0.6, "protest": 1.2, "despair": 0.5, "detachment": 0.1}.get(phase, 0.6)
    w = gap * phase_w
    w += 0.3 * needs.get("novelty", 0.0)
    w += 0.5 * min(1.0, len(share_backlog) * 0.5)
    w += 0.3 * hurt if hurt < 0.4 else -0.3 * hurt      # a little hurt pulls, a lot pushes away
    w += 0.15 * anxiety - 0.3 * avoidance
    gain = 0.5 + 1.3 * clinginess_eff                   # urge_will_clinginess_gain 0.5–1.8
    return _c(w * gain, 0.0, 2.0)


def occasion(*, due_loops: List[Dict[str, Any]], share_backlog: List[Dict[str, Any]], care_loops: List[Dict[str, Any]],
             phase: str, needs: Dict[str, float], floor: float,
             report_loops: Optional[List[Dict[str, Any]]] = None) -> Tuple[float, str, Optional[Dict[str, Any]]]:
    """(O, kind, payload). Due loops first (they are also handled as 'on time' by the engine), then an answer she
    fetched for you (report_back), then the rest."""
    for l in due_loops:
        if l.get("origin") == "her_promise":
            return 1.0, "return_promise", l
    for l in due_loops:
        if l.get("origin") == "counterpart_said":
            return 1.0, "reminder", l
    for l in report_loops or []:
        return 1.0, "report_back", l
    if care_loops:
        return 0.8, "care", care_loops[0]
    if share_backlog:
        return 0.6 + 0.4 * float(share_backlog[0].get("importance", 0.4)), "share", share_backlog[0]
    if phase in ("protest",) and needs.get("affiliation_person", 0.0) >= 0.5:
        return 0.5, "longing", None
    return floor, "longing", None


def damping(unanswered: int, reply_rate_14d: float) -> float:
    base = 1.0 if unanswered <= 0 else 0.2 if unanswered == 1 else 0.0
    return base * _c(0.4 + 0.6 * reply_rate_14d)


def fire_probability(lam_per_h: float, dt_h: float) -> float:
    return 1.0 - math.exp(-max(0.0, lam_per_h) * dt_h)
