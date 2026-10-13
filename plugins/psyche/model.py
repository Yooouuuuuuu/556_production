"""psyche.model — the deterministic part of her inner life (inner-life.md §3, §5, §6, §11, Appendix A).

Pure functions and tables, no I/O, no clock: the same inputs always give the same outputs, which is
what makes the engine replayable and the golden cases meaningful.

    personality (L0)  -> derive()            : Big Five + character constants -> every other layer's parameters
    core affect (L2)  -> ou_step()           : Ornstein–Uhlenbeck exact solution for any step
    mood (L2)         -> mood_step()         : PAD pull–push toward the active instances, regression otherwise
    emotions (L3)     -> appraise_to_instances(): impact model B — prototype matching, intensity, half-life, PAD
    words             -> octant(), intensity_word(), EMOTION_ZH
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- L0: personality

BIG5 = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def derive(character: Dict[str, Any], time_cfg: Dict[str, Any]) -> Dict[str, float]:
    """L0 -> derived parameters (glossary E.1). Overrides in time_cfg win (e.g. affect_half_life_h)."""
    b5 = character.get("big5", {})
    O, C, E, A, N = (float(b5.get(k, 0.5)) for k in BIG5)
    # Big Five to -1..1 for the ALMA / Mehrabian mood formula
    o, c, e, a, n = ((2 * x - 1) for x in (O, C, E, A, N))
    p0 = 0.21 * e + 0.59 * a + 0.19 * n
    a0 = 0.15 * o + 0.30 * a - 0.57 * n
    d0 = 0.25 * o + 0.17 * c + 0.60 * e - 0.32 * a
    half = time_cfg.get("affect_half_life_h") or _c(2.0 + 4.0 * N, 2.0, 6.0)   # 2–6 h, N lengthens
    return {
        "mu_pos_base": 0.25 + 0.5 * E,          # positive-affect baseline (E)
        "mu_neg_base": 0.08 + 0.4 * N,          # negative-affect baseline (N)
        "mu_ar_base": 0.35 + 0.2 * E,           # arousal baseline (E), modulated by energy at runtime
        "sigma_affect": 0.02 + 0.08 * N,        # OU volatility per sqrt(hour) (N)
        "theta_affect": math.log(2) / float(half),  # pull-back; half-life in hours
        "affect_half_life_h": float(half),
        "mood_default": (_c(p0, -1, 1), _c(a0, -1, 1), _c(d0, -1, 1)),
        "gain_pos": 0.7 + 0.6 * E,
        "gain_neg": 0.7 + 0.6 * N,
        "gain_anger": 0.5 + 0.8 * (1 - A),
        "gain_social": 0.7 + 0.6 * A,           # gratitude, happy_for, sorry_for
        "gain_hurt": 0.5 + 0.5 * N,
        "forbearance": 0.3 + 0.5 * A,
        "boredom_rate": 0.02 + 0.08 * O,
    }


# --------------------------------------------------------------------------- L2: core affect and mood

def ou_step(x: float, mu: float, theta: float, sigma: float, dt_h: float, z: float) -> float:
    """Exact OU solution for one step of dt_h hours with standard normal draw z."""
    e = math.exp(-theta * dt_h)
    sd = sigma * math.sqrt(max(0.0, (1.0 - e * e) / (2.0 * theta))) if theta > 0 else sigma * math.sqrt(dt_h)
    return _c(mu + (x - mu) * e + sd * z)


def mood_step(mood: Tuple[float, float, float], center: Optional[Tuple[float, float, float]],
              default: Tuple[float, float, float], dt_h: float, regress_tau_h: float,
              rise_max: float, fall_max: float) -> Tuple[float, float, float]:
    """ALMA pull–push: with active emotions the mood moves toward their PAD center (pulled when it is
    between the origin and the center, pushed deeper when it is beyond); without them it regresses to
    the personality default. Rates are capped per hour, rising faster than falling (RimWorld-style)."""
    out = []
    for i in range(3):
        m = mood[i]
        if center is None:
            target = default[i]
            delta = (target - m) * (1 - math.exp(-dt_h / max(0.05, regress_tau_h)))
        else:
            c = center[i]
            same_side = (m * c) >= 0 and abs(m) > abs(c)   # beyond the center: push deeper (capped)
            target = c * 1.25 if same_side else c
            delta = (target - m) * (1 - math.exp(-dt_h / 0.5))  # emotions move the mood within ~30 min
        cap = (rise_max if delta > 0 else fall_max) * dt_h
        delta = max(-cap, min(cap, delta))
        out.append(_c(m + delta, -1.0, 1.0))
    return (out[0], out[1], out[2])


OCTANTS = {  # sign of (P, A, D) -> name, Chinese word
    (1, 1, 1): ("Exuberant", "興致勃勃"), (1, 1, -1): ("Dependent", "撒嬌黏人"),
    (1, -1, 1): ("Relaxed", "自在"), (1, -1, -1): ("Docile", "溫和乖巧"),
    (-1, 1, 1): ("Hostile", "不爽"), (-1, 1, -1): ("Anxious", "不安"),
    (-1, -1, 1): ("Disdainful", "冷淡"), (-1, -1, -1): ("Bored", "悶"),
}


def octant(mood: Tuple[float, float, float]) -> Tuple[str, str, float]:
    """(name, zh word, strength 0..1); strength < 0.2 reads as calm."""
    p, a, d = mood
    key = (1 if p >= 0 else -1, 1 if a >= 0 else -1, 1 if d >= 0 else -1)
    name, zh = OCTANTS[key]
    return name, zh, _c(math.sqrt(p * p + a * a + d * d) / math.sqrt(3))


def intensity_word(x: float) -> str:
    """Strength words of the state block: nothing below 0.2, then 有點 / 蠻 / 很."""
    return "" if x < 0.2 else "有點" if x < 0.45 else "蠻" if x < 0.7 else "很"


# --------------------------------------------------------------------------- L3: emotions

EMOTION_ZH = {
    "joy": "開心", "distress": "難過", "hope": "期待", "fear": "擔心", "satisfaction": "滿足",
    "disappointment": "失望", "relief": "鬆了口氣", "gratitude": "感激", "anger": "生氣", "pride": "得意",
    "shame": "不好意思", "liking": "喜歡", "disliking": "反感", "happy_for": "替對方高興",
    "sorry_for": "替對方難過", "longing": "想念", "hurt": "委屈",
}
POSITIVE = {"joy", "hope", "satisfaction", "relief", "gratitude", "pride", "liking", "happy_for"}
NEGATIVE = {"distress", "fear", "disappointment", "anger", "shame", "disliking", "sorry_for", "longing", "hurt"}

# Appendix A.2 prototypes: only the listed fields count ("blank = does not care").
# agent is one of self / other / circ; weights make v and agent matter most (A.4 field weights).
PROTOTYPES: Dict[str, Dict[str, Any]] = {
    "joy":            {"v": 0.7, "cert": 1.0, "other_focus": 0.0},
    "distress":       {"v": -0.7, "cert": 1.0, "agent": "circ", "other_focus": 0.0},
    "hope":           {"v": 0.6, "cert": 0.2},
    "fear":           {"v": -0.6, "cert": 0.2},
    "satisfaction":   {"v": 0.6, "cert": 1.0, "u": 0.2},
    "disappointment": {"v": -0.6, "cert": 1.0, "u": 0.7},
    "relief":         {"v": 0.5, "cert": 1.0},
    "gratitude":      {"v": 0.7, "cert": 1.0, "agent": "other", "intent": 0.7},
    "anger":          {"v": -0.7, "cert": 1.0, "agent": "other", "intent": 0.8},
    "pride":          {"v": 0.6, "cert": 1.0, "agent": "self"},
    "shame":          {"v": -0.5, "cert": 1.0, "agent": "self"},
    "liking":         {"appeal": 0.7},
    "disliking":      {"appeal": -0.7},
    "happy_for":      {"other_focus": 1.0, "other_v": 0.7},
    "sorry_for":      {"other_focus": 1.0, "other_v": -0.7},
    "hurt":           {"v": -0.6, "cert": 1.0, "agent": "other", "intent": 0.4, "devalue": 0.8},
}
FIELD_WEIGHTS = {"v": 2.0, "agent": 2.0, "intent": 1.5, "devalue": 1.5, "cert": 1.0, "u": 0.5,
                 "other_focus": 1.5, "other_v": 2.0, "appeal": 2.0}

# Hard gates (the OCC structure the distances alone cannot carry)
EXPECT_KINDS_NEG = {"promise_broken", "forgot_detail", "ignored", "dismissed"}
EXPECT_KINDS_POS = {"promise_kept", "loop_resolved", "return_after_absence"}


def _gate(kind: str, ap: Dict[str, Any], active_types: set) -> bool:
    v, cert = ap["v"], ap["cert"]
    of = ap.get("other_focus", 0.0)
    ag = ap.get("agent", "circ")
    if kind in ("joy", "distress"):
        return cert >= 0.5 and of < 0.5 and (v > 0) == (kind == "joy")
    if kind in ("hope", "fear"):
        return cert <= 0.5 and (v > 0) == (kind == "hope")
    if kind == "satisfaction":
        return v > 0 and cert >= 0.5 and ("hope" in active_types or bool(ap.get("loop_id")) or ap["event_kind"] in EXPECT_KINDS_POS)
    if kind == "disappointment":
        return v < 0 and cert >= 0.5 and ("hope" in active_types or bool(ap.get("loop_id")) or ap["event_kind"] in EXPECT_KINDS_NEG)
    if kind == "relief":
        return v > 0 and cert >= 0.5 and ("fear" in active_types or ap["event_kind"] in ("apology", "false_belief_corrected", "loop_resolved"))
    if kind == "gratitude":  # something done for her, on purpose — not merely his own good news
        return v > 0 and ag == "other" and of < 0.5 and ap.get("intent", 0.0) >= 0.5
    if kind == "anger":
        return v < 0 and ag == "other" and of < 0.5 and ap.get("intent", 0.0) >= 0.5
    if kind in ("pride", "shame"):
        return ag == "self" and of < 0.5 and (v > 0) == (kind == "pride")
    if kind in ("liking", "disliking"):
        a = ap.get("appeal", 0.0)
        return abs(a) >= 0.4 and (a > 0) == (kind == "liking")
    if kind in ("happy_for", "sorry_for"):
        ov = ap.get("other_v", 0.0)
        return of >= 0.5 and abs(ov) >= 0.2 and (ov > 0) == (kind == "happy_for")
    if kind == "hurt":
        return v < 0 and ag == "other" and of < 0.5 and ap.get("devalue", 0.0) >= 0.4
    return False


def similarity(kind: str, ap: Dict[str, Any], width: float) -> float:
    proto = PROTOTYPES[kind]
    num = den = 0.0
    for f, pv in proto.items():
        w = FIELD_WEIGHTS.get(f, 1.0)
        if f == "agent":
            d = 0.0 if ap.get("agent") == pv else 1.0
        elif f not in ap or ap[f] is None:
            continue
        else:
            d = float(ap[f]) - float(pv)
        num += w * d * d
        den += w
    if den == 0:
        return 0.0
    d2 = num / den
    return math.exp(-d2 / (2 * width * width))


# Appendix A.5: base half-life (hours) and PAD coordinates (ALMA table as remembered; verify before 0.7.0)
T_BASE = {"joy": 9, "distress": 9, "hope": 9, "fear": 9, "satisfaction": 9, "disappointment": 9, "relief": 4,
          "gratitude": 9, "anger": 1.5, "pride": 9, "shame": 0.4, "liking": 12, "disliking": 6, "happy_for": 9,
          "sorry_for": 24, "longing": 36, "hurt": 30}
PAD = {"joy": (0.40, 0.20, 0.10), "distress": (-0.40, -0.20, -0.50), "hope": (0.20, 0.20, -0.10),
       "fear": (-0.64, 0.60, -0.43), "satisfaction": (0.30, -0.20, 0.40), "disappointment": (-0.30, 0.10, -0.40),
       "relief": (0.20, -0.30, 0.40), "gratitude": (0.40, 0.20, -0.30), "anger": (-0.51, 0.59, 0.25),
       "pride": (0.40, 0.30, 0.30), "shame": (-0.30, 0.10, -0.60), "liking": (0.40, 0.16, -0.24),
       "disliking": (-0.40, 0.20, 0.10), "happy_for": (0.40, 0.20, 0.20), "sorry_for": (-0.40, -0.20, -0.50),
       "longing": (-0.20, -0.10, -0.30), "hurt": (-0.40, 0.10, -0.40)}

# What resolves what (resolved_by): event kind -> {emotion type: remaining fraction}
RESOLVES = {
    "apology": {"hurt": 0.4, "disappointment": 0.5, "anger": 0.3},
    "promise_kept": {"disappointment": 0.0, "fear": 0.0, "hope": 0.0},
    "loop_resolved": {"hope": 0.0, "fear": 0.0},
    "return_after_absence": {"longing": 0.0},
    "false_belief_corrected": {"hurt": 0.2, "disappointment": 0.2, "anger": 0.1},
}


def stack_key(kind: str, ap: Dict[str, Any]) -> str:
    return f"{kind}:{ap.get('event_kind') or 'other'}"


def appraise_to_instances(ap: Dict[str, Any], derived: Dict[str, float], impact: Dict[str, Any],
                          active: Sequence[Dict[str, Any]], stack_counts: Dict[str, int],
                          mood_valence: float = 0.0, bond: float = 0.5,
                          modulators: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Impact model B: one appraisal vector + the current state -> 0..3 emotion instances
    (type, intensity0, half_life_h, pad, stack_key, cause). Deterministic."""
    ap = dict(ap)
    # mood congruence only colours ambiguous events (Forgas AIM), before matching
    ap["v"] = _c(float(ap.get("v", 0.0)) + impact.get("mood_congruence_coef", 0.2) * float(ap.get("ambiguity", 0.0)) * mood_valence, -1, 1)
    ap.setdefault("cert", 1.0)
    ap.setdefault("event_kind", "other")
    active_types = {i["type"] for i in active}
    width = float(impact.get("prototype_width", 0.35))
    threshold = float(impact.get("prototype_threshold", 0.5))
    cands: List[Tuple[str, float]] = []
    for kind in PROTOTYPES:
        if not _gate(kind, ap, active_types):
            continue
        s = similarity(kind, ap, width)
        if s >= threshold:
            cands.append((kind, s))
    cands.sort(key=lambda t: -t[1])
    # mutually exclusive pairs never come from the same event
    chosen: List[Tuple[str, float]] = []
    for kind, s in cands:
        if any({kind, k2} in ({"joy", "distress"}, {"hope", "fear"}) for k2, _ in chosen):
            continue
        chosen.append((kind, s))
        if len(chosen) >= int(impact.get("max_instances_per_event", 3)):
            break
    R = _c(float(ap.get("R", 0.5)))
    u = _c(float(ap.get("u", 0.0)))
    cert = _c(float(ap["cert"]))
    alpha_u = float(impact.get("alpha_u", 0.6))
    mods = modulators or {}
    m_all = _c(float(mods.get("all", 1.0)), 0.6, 1.5)
    out: List[Dict[str, Any]] = []
    sm = impact.get("stack_multiplier", {"pos": 0.7, "neg": 0.8, "hurt": 0.85})
    for rank, (kind, sim) in enumerate(chosen):
        if kind in ("happy_for", "sorry_for"):
            v_star = abs(float(ap.get("other_v", 0.0))) * (0.4 + 0.6 * bond)
        elif kind in ("liking", "disliking"):
            v_star = abs(float(ap.get("appeal", 0.0)))
        else:
            v_star = abs(float(ap["v"]))
        pi = 1.0 if cert >= 0.5 else _c(0.4 + 1.2 * cert)          # π(cert): unlikely outcomes weigh less
        if kind == "anger":
            g = derived["gain_anger"]
        elif kind in ("gratitude", "happy_for", "sorry_for"):
            g = derived["gain_social"]
        elif kind == "hurt":
            g = derived["gain_hurt"] * (0.5 + float(ap.get("intent", 0.3))) * (1.0 - 0.5 * derived["forbearance"]) * 1.6
        elif kind in POSITIVE:
            g = derived["gain_pos"]
        else:
            g = derived["gain_neg"]
        key = stack_key(kind, ap)
        n = stack_counts.get(key, 0)
        r = sm["hurt"] if kind == "hurt" else sm["pos"] if kind in POSITIVE else sm["neg"]
        rho = r ** min(n, int(impact.get("stack_limit", 4)))
        I = sim * R * v_star * (1 + alpha_u * u) * pi * g * m_all * rho
        if rank > 0:
            I *= float(impact.get("secondary_factor", 0.7))
        I = _c(I)
        if I < 0.05:
            continue
        half = T_BASE[kind] * (0.5 + R) * (0.75 + 0.5 * I)
        out.append({"type": kind, "intensity0": round(I, 4), "half_life_h": round(half, 3), "pad": PAD[kind],
                    "stack_key": key, "sim": round(sim, 3), "cause": ap.get("cause") or ap.get("summary") or "",
                    "target": ap.get("counterpart") or "", "loop_id": ap.get("loop_id")})
    return out


def resolutions(event_kind: str, loop_id: Optional[str], active: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """instance id -> remaining fraction for the instances this event resolves (RESOLVES table, plus
    a closed loop ending the hope / fear bound to it)."""
    out: Dict[str, float] = {}
    table = RESOLVES.get(event_kind, {})
    for inst in active:
        if inst["type"] in table:
            out[inst["id"]] = table[inst["type"]]
        if loop_id and inst.get("loop_id") == loop_id and inst["type"] in ("hope", "fear"):
            out[inst["id"]] = 0.0
    return out


def decayed(intensity0: float, half_life_h: float, hours: float) -> float:
    return intensity0 * (0.5 ** (max(0.0, hours) / max(1e-6, half_life_h)))


def energy_at(hour_local: float, chronotype: float) -> float:
    """L1 placeholder until the two-process model (0.6.0): a circadian curve with an afternoon dip,
    shifted by chronotype (-1 morning … 1 evening)."""
    w = 2 * math.pi / 24
    phi = 15.0 + 2.0 * chronotype
    return _c(0.55 + 0.30 * math.cos(w * (hour_local - phi)) - 0.10 * math.cos(2 * w * (hour_local - 14.0)))


def energy_word(e: float) -> str:
    return "精神很好" if e >= 0.75 else "精神還不錯" if e >= 0.55 else "有點累" if e >= 0.35 else "很累"
