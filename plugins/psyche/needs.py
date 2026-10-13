"""psyche.needs — L4 needs and motivation (inner-life.md §7), one counterpart in 0.6.0.

Needs are accumulating gaps (0..1) that only satisfaction lowers. The person-specific affiliation gap
grows only when the presence model expects you around and you are not (Peplau & Perlman: loneliness is
the gap, not the clock); its setpoint is clinginess_cap × attachment_strength. Separation runs through
Bowlby's three phases by hours since the last contact: protest (urge up), despair (urge down, mood
down), detachment (urge ≈ 0). Needs change the mood only through a small coupling.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

NEEDS = ("affiliation_general", "affiliation_person", "competence", "autonomy", "certainty", "novelty")


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def fresh() -> Dict[str, float]:
    return {n: 0.0 for n in NEEDS}


def step(needs: Dict[str, float], *, dt_h: float, p_expected: float, activity: str, chatting: bool,
         waiting_importance: float, busyness: str, derived: Dict[str, float], cfg: Dict[str, Any],
         clinginess_eff: float, fatigue: float) -> None:
    k_aff = float(cfg.get("k_aff", 0.08))
    big5_e = float(derived.get("mu_pos_base", 0.5))  # proxy for E (0.25 + 0.5E)
    if not chatting:
        needs["affiliation_person"] = _c(needs["affiliation_person"] + k_aff * p_expected * (0.5 + clinginess_eff) * dt_h)
        needs["affiliation_general"] = _c(needs["affiliation_general"] + k_aff * 0.6 * big5_e * dt_h)
    else:  # company lowers both; too much of it pushes the general need into surplus (fatigue)
        needs["affiliation_person"] = _c(needs["affiliation_person"] - 0.5 * dt_h)
        needs["affiliation_general"] = _c(needs["affiliation_general"] - 0.4 * dt_h - 0.3 * fatigue * dt_h, -0.5, 1.0)
    if activity in ("work", "hobby"):
        needs["competence"] = _c(needs["competence"] - 0.15 * dt_h)
    elif busyness == "none":
        needs["competence"] = _c(needs["competence"] + 0.02 * dt_h)
    else:
        needs["competence"] = _c(needs["competence"] + 0.01 * dt_h)
    needs["autonomy"] = _c(needs["autonomy"] - 0.05 * dt_h)
    needs["certainty"] = _c(0.25 * waiting_importance)
    if activity == "rest" or busyness == "none":
        needs["novelty"] = _c(needs["novelty"] + float(derived.get("boredom_rate", 0.05)) * dt_h)
    elif activity in ("chat", "hobby"):
        needs["novelty"] = _c(needs["novelty"] - 0.2 * dt_h)


def satisfy(needs: Dict[str, float], *, q: float, event_kind: str, other_focus: float) -> None:
    """A turn's quality q satisfies the affiliation needs; some events touch the others (§7, A.6)."""
    needs["affiliation_person"] = _c(needs["affiliation_person"] - 0.6 * q)
    needs["affiliation_general"] = _c(needs["affiliation_general"] - 0.4 * q, -0.5, 1.0)
    if event_kind in ("praised_her", "asked_about_her", "remembered_detail"):
        needs["competence"] = _c(needs["competence"] - 0.3)
    if event_kind in ("criticized_her", "dismissed"):
        needs["competence"] = _c(needs["competence"] + 0.2)
        needs["autonomy"] = _c(needs["autonomy"] + 0.2)
    if event_kind in ("shared_news_good", "shared_news_bad", "disclosed_personal") or other_focus >= 0.5:
        needs["novelty"] = _c(needs["novelty"] - 0.3)


def phase(hours_since_contact: float, cfg: Dict[str, Any], clinginess_eff: float, anxiety: float) -> str:
    """Bowlby's separation phases from the hours since the last contact; clinginess and attachment
    anxiety stretch the protest phase (§7)."""
    if hours_since_contact < 0:
        return "ok"
    protest_end = float(cfg.get("protest_end_h", 24)) * (1.0 + 0.5 * clinginess_eff + 0.5 * anxiety)
    despair_end = float(cfg.get("despair_end_h", 120))
    if hours_since_contact < 2.0:
        return "ok"
    if hours_since_contact < protest_end:
        return "protest"
    if hours_since_contact < despair_end:
        return "despair"
    return "detachment"


def mood_pull(needs: Dict[str, float], coupling: float) -> float:
    """Unmet needs lower the positive attractor a little (need_mood_coupling)."""
    gap = max(0.0, (needs["affiliation_person"] + needs["affiliation_general"] + needs["competence"] + needs["novelty"]) / 4.0)
    return coupling * gap


def words(needs: Dict[str, float], phase_name: str, term: str) -> str:
    """One short line for the state block, only when something is actually felt."""
    bits = []
    ap = needs["affiliation_person"]
    if phase_name == "detachment":
        bits.append(f"很久沒跟{term}說到話了，不太知道怎麼開口")
    elif phase_name == "despair":
        bits.append(f"好幾天沒跟{term}說到話，有點悶")
    elif ap >= 0.6:
        bits.append(f"蠻想跟{term}說話")
    elif ap >= 0.35:
        bits.append(f"有點想找{term}")
    if needs["novelty"] >= 0.6:
        bits.append("有點無聊")
    if needs["competence"] >= 0.6:
        bits.append("覺得自己最近沒什麼進展")
    if needs["affiliation_general"] <= -0.2:
        bits.append("聊得有點累了，想安靜一下")
    return "、".join(bits)
