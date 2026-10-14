"""psyche.relation — L5 relationship and L6 hurt / repair, per counterpart (inner-life.md §8, §9, §15).

Every variable here is indexed by the person she is dealing with: you, or another character.
    warmth      recent heat, a leaky integral of quality-weighted contact (friend-type decay, half-life 21 d)
    bond        long-term, pulled up slowly by warmth, almost never decays (kin-type)
    hours       quality-weighted closeness hours (50 / 90 / 200 = acquaintance / friend / close friend)
    disclosure  how deep she lets this person see (1–4), unlocked by bond, +1 for a day when they open up first
    attachment  0→1 over months, pushed by bond and perceived responsiveness; the multiplier of clinginess
    anxiety / avoidance   the working model, moved slowly by experience from the L0 base
    trust       a Beta count of kept / broken promises, slowly forgotten
    commitment  the investment model: satisfaction + investment − alternatives (none yet)
    ppr         perceived partner responsiveness: understood / validated / cared (EMA of A's reading)
The hurt ledger (TRIM): avoidance and resentment per entry, opened only by a relational devaluation,
forgiven by trend (slope from agreeableness and commitment), cut by an apology that owns the fault,
nearly erased by a false-belief correction; the maximum open avoidance gates inverted expression.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

WARMTH_HALF_LIFE_H = 21 * 24.0
Q_SMALL_TALK, Q_DEEP = 0.2, 1.5
TEXT_HOURS_FACTOR = 0.7
LEDGER_MAX_DAYS = 3.0


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def fresh(prior: Dict[str, Any], character: Dict[str, Any]) -> Dict[str, Any]:
    b5 = character.get("big5", {})
    N, A = float(b5.get("neuroticism", 0.4)), float(b5.get("agreeableness", 0.6))
    anx_base = _c(0.15 + 0.5 * N)
    avo_base = _c(0.15 + 0.5 * (1 - A))
    return {
        "warmth": float(prior.get("warmth", 0.0)), "bond": float(prior.get("bond", 0.0)), "hours": float(prior.get("hours", 0.0)),
        "disclosure": int(prior.get("disclosure", 1)), "attachment": float(prior.get("attachment_strength", 0.0)),
        "anxiety": float(prior.get("anxiety", anx_base)), "avoidance": float(prior.get("avoidance", avo_base)),
        "anxiety_base": anx_base, "avoidance_base": avo_base,
        "trust": [float(prior.get("trust_alpha", 2.0)), float(prior.get("trust_beta", 1.0))],
        "trust_prior": [float(prior.get("trust_alpha", 2.0)), float(prior.get("trust_beta", 1.0))],
        "commitment": 0.0, "ppr": {"understood": 0.5, "validated": 0.5, "cared": 0.5}, "ppr_n": 0,
        "reciprocal_until": None, "kept": 0, "broken": 0,
    }


def trust_value(rel: Dict[str, Any]) -> float:
    a, b = rel["trust"]
    return a / max(1e-6, a + b)


def ppr_mean(rel: Dict[str, Any]) -> float:
    p = rel["ppr"]
    return (p["understood"] + p["validated"] + p["cared"]) / 3.0


def tick(rel: Dict[str, Any], dt_h: float, cfg: Dict[str, Any]) -> None:
    """Slow dynamics: warmth cools, bond follows warmth up, attachment grows with bond × responsiveness,
    the working model and trust relax toward their priors."""
    rel["warmth"] *= 0.5 ** (dt_h / WARMTH_HALF_LIFE_H)
    k_b = float(cfg.get("k_bond", 0.004))
    rel["bond"] = _c(rel["bond"] + k_b * max(0.0, rel["warmth"] - rel["bond"]) * dt_h - 0.00002 * dt_h)  # kin-type: ~0.015 a month
    k_att = float(cfg.get("k_attachment", 0.0004))
    rel["attachment"] = _c(rel["attachment"] + k_att * rel["bond"] * ppr_mean(rel) * dt_h)
    for key in ("anxiety", "avoidance"):
        base = rel[key + "_base"]
        rel[key] = _c(rel[key] + (base - rel[key]) * (1 - math.exp(-dt_h / (30 * 24.0))))
    tau = float(cfg.get("trust_forget_days", 60)) * 24.0
    for i in range(2):
        rel["trust"][i] = rel["trust_prior"][i] + (rel["trust"][i] - rel["trust_prior"][i]) * math.exp(-dt_h / tau)
    rel["disclosure"] = 1 + (rel["bond"] >= 0.25) + (rel["bond"] >= 0.5) + (rel["bond"] >= 0.75)
    sat = 0.5 * ppr_mean(rel) + 0.5 * rel["warmth"]
    rel["commitment"] = _c(0.5 * sat + 0.5 * min(1.0, rel["hours"] / 200.0))


def turn(rel: Dict[str, Any], *, q: float, minutes: float, event_kind: str, ppr: Optional[Dict[str, float]],
         she_disclosed: bool, other_disclosed: bool, t: float) -> None:
    """One exchange with this person (A.6): closeness hours and warmth from quality, responsiveness when
    she opened up, promises into trust, the working model nudged by what happened."""
    qf = Q_SMALL_TALK + (Q_DEEP - Q_SMALL_TALK) * _c(q)
    rel["hours"] += max(0.5, minutes) / 60.0 * qf * TEXT_HOURS_FACTOR
    rel["warmth"] = _c(rel["warmth"] + 0.02 * qf)
    if ppr and (she_disclosed or event_kind in ("asked_about_her", "remembered_detail", "praised_her")):
        a = 0.3
        for k in ("understood", "validated", "cared"):
            rel["ppr"][k] = (1 - a) * rel["ppr"][k] + a * _c(float(ppr.get(k, 0.5)))
        rel["ppr_n"] = int(rel["ppr_n"]) + 1
        if rel["ppr"]["cared"] >= 0.7:
            rel["anxiety"] = _c(rel["anxiety"] - 0.005)
        if she_disclosed and rel["ppr"]["validated"] >= 0.6:
            rel["avoidance"] = _c(rel["avoidance"] - 0.01)
    if event_kind == "promise_kept":
        rel["trust"][0] += 1.0
        rel["kept"] = int(rel["kept"]) + 1
    elif event_kind == "promise_broken":
        rel["trust"][1] += 1.0
        rel["broken"] = int(rel["broken"]) + 1
        rel["anxiety"] = _c(rel["anxiety"] + 0.03)
    if event_kind in ("dismissed", "criticized_her", "compared_her", "ignored"):
        rel["avoidance"] = _c(rel["avoidance"] + 0.02)
    if event_kind in ("forgot_detail",):
        rel["anxiety"] = _c(rel["anxiety"] + 0.01)
    if other_disclosed:
        rel["reciprocal_until"] = t + 24 * 3600


def disclosure_now(rel: Dict[str, Any], t: float) -> int:
    d = int(rel["disclosure"])
    if rel.get("reciprocal_until") and t < float(rel["reciprocal_until"]):
        d += 1
    return min(4, d)


def closeness_words(rel: Dict[str, Any], term: str) -> str:
    b, h, tr, att = rel["bond"], rel["hours"], trust_value(rel), rel["attachment"]
    if h < 10 and b < 0.15:
        base = "剛認識，還在摸索"
    elif h < 50 or b < 0.3:
        base = "還不算熟"
    elif h < 90 or b < 0.5:
        base = "算是朋友了"
    elif h < 200 or b < 0.75:
        base = "很熟"
    else:
        base = "很親近"
    bits = [base]
    if tr >= 0.75:
        bits.append("很放心")
    elif tr <= 0.45:
        bits.append("有點防備")
    if att >= 0.6:
        bits.append("很依賴他")
    elif att >= 0.3:
        bits.append("開始在意他")
    return "、".join(bits)


# --------------------------------------------------------------------------- L6: the hurt ledger

def open_entry(*, cause: str, severity: float, intent: float, forbearance: float, anxiety: float, bond: float,
               t: float, eid: str, cap: float = 0.5) -> Dict[str, Any]:
    intent_factor = 0.1 if intent < 0.2 else 0.5 if intent < 0.6 else 1.0   # 不可控 / 無心 / 故意
    base = _c(severity * intent_factor * (1.0 - forbearance) * (0.5 + anxiety) * (0.5 + bond) * 2.5)
    return {"id": eid, "at": t, "cause": cause, "severity": round(severity, 3), "intent": round(intent, 2),
            "avoidance": round(base, 4), "resentment": round(min(cap, base * 0.8), 4), "benevolence_drop": round(base * 0.5, 4),
            "avoidance0": round(base, 4), "resentment0": round(min(cap, base * 0.8), 4), "repaired": False, "revisits": 0,
            "resolved_at": None, "resolved_by": None}


def ledger_revisit(e: Dict[str, Any], t: float, cap: float = 0.5) -> None:
    """The matter is brought up again without being owned (justified, repeated, brushed off): the entry
    comes back up by half of what it opened with."""
    e["avoidance"] = round(min(1.0, e["avoidance"] + 0.5 * float(e.get("avoidance0", e["avoidance"]))), 4)
    e["resentment"] = round(min(cap, e["resentment"] + 0.5 * float(e.get("resentment0", e["resentment"]))), 4)
    e["revisits"] = int(e.get("revisits", 0)) + 1
    e["revisited_at"] = t


def ledger_tick(entries: List[Dict[str, Any]], dt_h: float, *, agreeableness: float, commitment: float, t: float) -> None:
    """Trend forgiveness: a linear slide, steeper with agreeableness and commitment; entries close when
    nothing is left or after the ledger's maximum lifetime (temporary forgiveness lives in rumination)."""
    slope = (0.001 + 0.003 * agreeableness + 0.002 * commitment) * dt_h   # an entry of ~0.17 slides away in two to three days
    for e in entries:
        if e.get("resolved_at") is not None:
            continue
        e["avoidance"] = max(0.0, e["avoidance"] - slope)
        e["resentment"] = max(0.0, e["resentment"] - slope)
        e["benevolence_drop"] = max(0.0, e["benevolence_drop"] - slope * 0.7)
        if (e["avoidance"] + e["resentment"]) < 0.02 or (t - float(e["at"])) > LEDGER_MAX_DAYS * 86400:
            e["resolved_at"], e["resolved_by"] = t, "forgiven" if (e["avoidance"] + e["resentment"]) < 0.02 else "faded"


def ledger_repair(entries: List[Dict[str, Any]], kind: str, components: int, t: float) -> float:
    """An apology that owns the fault cuts every open entry once (Lewicki: acknowledging responsibility
    weighs most); a false-belief correction nearly erases them. Returns the factor applied."""
    if kind == "false_belief_corrected":
        f = 0.2
    elif kind == "apology":
        f = 1.0 - min(0.9, 0.3 + 0.1 * max(0, min(6, components)))
    else:
        return 1.0
    for e in entries:
        if e.get("resolved_at") is None:
            e["avoidance"] = round(e["avoidance"] * f, 4)
            e["resentment"] = round(e["resentment"] * f, 4)
            e["repaired"] = True   # closed by repair, not by time: its memories come back plain, not as 舊帳
            e["benevolence_drop"] = round(e["benevolence_drop"] * f, 4)
            if (e["avoidance"] + e["resentment"]) < 0.02:
                e["resolved_at"], e["resolved_by"] = t, kind
    return f


def hurt_gate(entries: List[Dict[str, Any]]) -> float:
    return max((e["avoidance"] for e in entries if e.get("resolved_at") is None), default=0.0)


def resentment(entries: List[Dict[str, Any]]) -> float:
    return max((e["resentment"] for e in entries if e.get("resolved_at") is None), default=0.0)


def olive_branch_due(entries: List[Dict[str, Any]], *, t: float, last_contact: Optional[float], clinginess_eff: float,
                     avoidance: float) -> Optional[Dict[str, Any]]:
    """After a hurt, if nobody has spoken for olive_branch_delay_h = (8 + 28·(1 − clinginess)) × (1 + avoidance)
    hours, she offers the step down herself (§9: 自己給台階)."""
    delay_h = (8.0 + 28.0 * (1.0 - clinginess_eff)) * (1.0 + avoidance)
    for e in entries:
        if e.get("resolved_at") is None and (t - float(e["at"])) / 3600.0 >= delay_h and (last_contact is None or last_contact <= float(e["at"])):
            if not e.get("olive_offered"):
                return e
    return None


# --------------------------------------------------------------------------- expression layer helpers

VULNERABLE = {"liking", "longing", "gratitude", "happy_for", "joy", "pride"}
V_COST = {"longing": 1.0, "liking": 0.9, "gratitude": 0.6, "happy_for": 0.4, "joy": 0.5, "pride": 0.6}


def expressed_level(felt: float, *, expressiveness: float, bond: float, suppressed: bool) -> float:
    """Display rules: expressed = felt × g_expressiveness × g_disclosure(bond) × (1 − suppressed)."""
    if suppressed:
        return 0.0
    return felt * (0.6 + 0.4 * expressiveness) * (0.5 + 0.5 * bond)


def strategy(dominant: Optional[Dict[str, Any]], *, character: Dict[str, Any], rel: Dict[str, Any], gate: float,
             other_tired: bool, rng_u: float, negative_types: set, shown: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, List[str]]:
    """(strategy name, lines for the 表現 line). Strategy by §15: direct / reserved / humor / inverted / denial;
    hurt closes the inverted route; a tired counterpart suppresses her own negatives (delayed, not cancelled)."""
    lines: List[str] = []
    expr = float(character.get("expressiveness", 0.6))
    tsun = float(character.get("tsundere_tendency", 0.3))
    humor = float(character.get("humor_coping", 0.5))
    assertive = float(character.get("assertiveness", 0.6))
    name = "direct"
    vul = next((i for i in (shown or ([dominant] if dominant else [])) if i["type"] in VULNERABLE), None)
    if dominant is not None:
        kind = dominant["type"]
        neg = kind in negative_types
        if neg and other_tired:
            lines.append("對方看起來很累：自己的不開心先不提（延後，不是取消）")
            name = "suppress"
        elif gate >= 0.1 and neg:
            name = "reserved"
            lines.append("心裡有委屈：不說反話，話少一點、語氣淡一點，不追討；被問到可以說「沒事啊」")
        elif vul is not None and tsun >= 0.3 and rng_u < tsun * V_COST.get(vul["type"], 0.5) * (0.3 + 0.7 * rel["bond"]) * (1.0 - gate):
            name = "inverted"
            lines.append("真心話用反話帶過，但一定要留破綻讓他看得出來")
        elif neg and humor >= 0.6:
            name = "humor"
            lines.append("不開心的事用玩笑帶過")
        elif expr < 0.5 or rel["bond"] < 0.25:
            name = "reserved"
            lines.append("收斂，點到為止" + ("（還不熟）" if rel["bond"] < 0.25 else ""))
        else:
            lines.append("直說")
    else:
        lines.append("直說" if expr >= 0.5 else "收斂，點到為止")
    lines.append("不同意時直說自己的看法" if assertive >= 0.5 else "不同意時先收著，不附和也不爭")
    return name, lines
