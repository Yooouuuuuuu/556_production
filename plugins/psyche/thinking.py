"""psyche.thinking — the thinking module (docs/prompt/prompt.md §2.5; the 2026-10-14 brief).

Six stable dimensions of how a person thinks. Three of them are numbers the engine reads (`psyche.json`
`thinking`: rationality, experientiality, promotion, prevention, maximizing — five meters), two are recorded
choices (`thinking_choices`: the medium of thought, the context weighting) that only the SOUL text carries
today, and one (interpretation bias) falls out of the emotion side. The module is separate from the emotion
engine on purpose: it READS emotion state (energy, fatigue, arousal, pleasure, anxiety, the hurt gate,
closeness) and never writes any of it; its meters never change an emotion's intensity or half-life.

Words only, in two layers: the trait text lives in the SOUL (written by the author or the soul skill); the
engine renders ONE optional line, 想法：…, only when this turn differs from her trait — a meter read against
the moment crosses a threshold. Below the thresholds the line is absent and the SOUL sentence stands. The
moment is what is known before her reply (prefetch never waits for the appraisal).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

METERS = ("rationality", "experientiality", "promotion", "prevention", "maximizing")
CHOICES = ("medium_primary", "medium_secondary", "first_look", "contradiction", "cause")


def _c(x: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return (lo + hi) / 2
    return min(hi, max(lo, v))


def meters(cfg: Dict[str, Any]) -> Dict[str, float]:
    """The five meters with Big Five defaults for the blanks: promotion ≈ extraversion, prevention ≈ neuroticism
    (the same pair the impact gains come from), rationality ≈ conscientiousness, the rest 0.5."""
    th = cfg.get("thinking") or {}
    b5 = (cfg.get("character") or {}).get("big5") or {}
    defaults = {
        "rationality": _c(b5.get("conscientiousness", 0.5)),
        "experientiality": 0.5,
        "promotion": _c(b5.get("extraversion", 0.5)),
        "prevention": _c(b5.get("neuroticism", 0.5)),
        "maximizing": 0.5,
    }
    out = {}
    for k in METERS:
        v = th.get(k)
        out[k] = _c(v) if v is not None else defaults[k]
    return out


def choices(cfg: Dict[str, Any]) -> Dict[str, Optional[str]]:
    ch = cfg.get("thinking_choices") or {}
    return {k: (str(ch[k]) if ch.get(k) else None) for k in CHOICES}


def reading_care(*, rationality: float, bond: float, fatigue: float, stakes: float) -> float:
    """How carefully she reads the other person this turn (the 2026-10-14 brief, mechanism 2.2: people anchor on
    their own reading and adjust outward; adjustment stops early when tired or close — intimates are assumed to
    understand — and runs longer when the stakes are high or the person is a think-first type)."""
    care = 0.5 + 0.3 * rationality - 0.3 * bond - 0.3 * fatigue + 0.3 * stakes
    return min(1.0, max(0.0, care))


def line(*, m: Dict[str, float], energy: float, fatigue: float, arousal: float, pleasure: float, anxiety: float,
         hurt_gate: float, bond: float, open_hurt: bool, pronoun: str = "她") -> Optional[str]:
    """At most one 想法 line, the first rule that fires; None when the moment matches her trait. Order: how she
    reads (dial 4, the emotion side) → the stakes → no energy to think → mood lifting or dropping her default
    framing (dial 3) → reading care (2.2) → the maximizer's clarifying question (dial 5)."""
    tired = energy < 0.35 or fatigue > 0.6
    stakes = 1.0 if hurt_gate >= 0.15 else 0.0
    # dial 4 — interpretation bias: anxious + something open or a low mood → ambiguity reads as rejection
    if anxiety >= 0.6 and (open_hurt or pleasure < -0.3):
        return "想法：今天特別容易往壞處想"
    # stakes: a reply-first person slows down when something heavy is on the table
    if stakes and m["rationality"] <= 0.45:
        return "想法：這件事不小，會想一下再回"
    # no energy: the deliberation budget collapses
    if tired and m["rationality"] >= 0.6:
        return "想法：今天沒力氣想，會先回再想"
    if tired and m["experientiality"] >= 0.6 and anxiety < 0.6:
        return "想法：今天沒力氣猜，直接問對方"
    # dial 3 — regulatory focus lifted or dropped by mood
    if m["prevention"] >= 0.6 and pleasure > 0.4:
        return "想法：心情好，先看能變成什麼"
    if m["promotion"] >= 0.6 and (pleasure < -0.3 or anxiety >= 0.6):
        return "想法：這題先看會不會出錯"
    # 2.2 — reading care at the extremes
    care = reading_care(rationality=m["rationality"], bond=bond, fatigue=fatigue, stakes=stakes)
    if care < 0.25:
        return "想法：懶得猜對方的意思，直接當對方懂"
    if care > 0.85:
        return "想法：會多想一下對方是什麼意思"
    # dial 5 — a maximizer with energy asks before answering
    if m["maximizing"] >= 0.6 and energy >= 0.5 and arousal >= 0.6:
        return "想法：會問清楚再答，不想隨便"
    return None
