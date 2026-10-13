"""psyche.tom — theory of mind, minimal (inner-life.md §12): when are you usually around, how fast do
you usually answer. A presence model of 168 weekly cells, each a Beta count of "seen / not seen"
updated hour by hour while she runs; a lognormal reply-latency model from the gaps between her
proactive messages and your next turn. Cold start = a flat prior; the first weeks lean on it only
lightly (p_expected ≈ 0.5). Nothing here is phrased as surveillance in her prompt (§12 表達限制).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def fresh() -> Dict[str, Any]:
    return {"alpha": [1.0] * 168, "beta": [1.0] * 168, "last_hour_cell": None, "hour_seen": False,
            "latency_h": [], "week_decayed": None}


def cell(weekday: int, hour: float) -> int:
    return (weekday % 7) * 24 + int(hour) % 24


def p_expected(pm: Dict[str, Any], weekday: int, hour: float) -> float:
    i = cell(weekday, hour)
    a, b = pm["alpha"][i], pm["beta"][i]
    return a / (a + b)


def saw_turn(pm: Dict[str, Any], weekday: int, hour: float) -> None:
    i = cell(weekday, hour)
    if not pm["hour_seen"] or pm["last_hour_cell"] != i:
        pm["alpha"][i] += 1.0
    pm["hour_seen"], pm["last_hour_cell"] = True, i


def hour_boundary(pm: Dict[str, Any], prev_weekday: int, prev_hour: float, running: bool) -> None:
    """Called when the clock crosses an hour: an hour she ran with no turn from you counts as absent.
    Hours she was stopped are not evidence (offline ratio, §17)."""
    i = cell(prev_weekday, prev_hour)
    if running and not pm["hour_seen"]:
        pm["beta"][i] += 1.0
    pm["hour_seen"], pm["last_hour_cell"] = False, None


def weekly_decay(pm: Dict[str, Any], iso_week: str, factor: float = 0.92) -> None:
    if pm.get("week_decayed") == iso_week:
        return
    pm["alpha"] = [1.0 + (a - 1.0) * factor for a in pm["alpha"]]
    pm["beta"] = [1.0 + (b - 1.0) * factor for b in pm["beta"]]
    pm["week_decayed"] = iso_week


def add_latency(pm: Dict[str, Any], hours: float, keep: int = 50) -> None:
    if hours > 0:
        pm["latency_h"] = (pm["latency_h"] + [hours])[-keep:]


def latency_p90_h(pm: Dict[str, Any], default_h: float = 6.0) -> float:
    xs = [x for x in pm.get("latency_h", []) if x > 0]
    if len(xs) < 5:
        return default_h
    logs = [math.log(x) for x in xs]
    mu = sum(logs) / len(logs)
    sd = math.sqrt(sum((l - mu) ** 2 for l in logs) / max(1, len(logs) - 1))
    return math.exp(mu + 1.2816 * sd)


def presence_word(pm: Dict[str, Any], weekday: int, hour: float) -> str:
    p = p_expected(pm, weekday, hour)
    return "這個時間你通常在" if p >= 0.6 else "這個時間你通常不在" if p <= 0.25 else ""
