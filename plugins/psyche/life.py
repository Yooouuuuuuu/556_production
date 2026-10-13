"""psyche.life — L1 physiology and her own life (inner-life.md §4, §14).

Two-process sleep (Borbély): pressure S rises while awake (τw 18.2 h) and falls asleep (τs 4.2 h);
circadian C with an afternoon dip; energy from both. Sleep is an ACTIVITY with a planned bedtime that
a late conversation delays; 躺著 before sleep is where rumination peaks and delays falling asleep;
a message can wake her (wake_on_message). The activity state comes from a schedule template and the
busyness mode; each activity carries attention load, interruptibility, an energy cost and the needs
it satisfies. Small life events come from a rule table, chosen by the seeded daily rng — nothing here
calls a model.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

TAU_WAKE_H = 18.2
TAU_SLEEP_H = 4.2
CHAT_WINDOW_MIN = 10.0        # a turn within this many minutes = "in a conversation"
WOKEN_MIN = 15.0              # after a message wakes her she drifts back to sleep after this

# name: (attention_load, interruptibility, energy per hour (+ restores), needs satisfied, zh)
ACTIVITIES: Dict[str, Tuple[float, float, float, List[str], str]] = {
    "sleep": (1.0, 0.05, 0.0, [], "在睡覺"),
    "lying": (0.0, 0.6, 0.02, [], "躺在床上，還沒睡著"),
    "woken": (0.5, 0.9, 0.0, [], "被訊息吵醒，很睏"),
    "work":  (0.9, 0.3, -0.08, ["competence"], "在工作"),
    "hobby": (0.6, 0.8, -0.02, ["competence", "novelty"], "在弄自己的事"),
    "meal":  (0.4, 0.9, 0.02, [], "在吃飯"),
    "rest":  (0.1, 0.95, 0.03, ["novelty"], "在休息"),
    "chat":  (0.8, 1.0, -0.03, ["affiliation_person", "affiliation_general"], "在跟你聊天"),
}


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def in_block(hour: float, blocks: List[List[float]]) -> bool:
    for a, b in blocks:
        if a <= b:
            if a <= hour < b:
                return True
        elif hour >= a or hour < b:  # wraps midnight
            return True
    return False


def circadian(hour: float, chronotype: float) -> float:
    """-1..1 alertness drive: peak mid-afternoon shifted by chronotype, with an early-afternoon dip."""
    w = 2 * math.pi / 24
    phi = 16.0 + 2.0 * chronotype
    return _c(math.cos(w * (hour - phi)) - 0.3 * math.cos(2 * w * (hour - 14.0)), -1, 1)


def energy_from(S: float, C: float, fatigue: float) -> float:
    return _c(0.15 + 0.55 * (1 - S) + 0.3 * (0.5 + 0.5 * C) - 0.15 * fatigue)


def energy_word(e: float, activity: str) -> str:
    if activity == "sleep":
        return "在睡覺"
    if activity == "woken":
        return "被吵醒，很睏"
    return "精神很好" if e >= 0.75 else "精神還不錯" if e >= 0.55 else "有點累" if e >= 0.35 else "很累"


class SleepState:
    """Per-tick sleep bookkeeping; the engine owns the dict so it snapshots cleanly."""

    @staticmethod
    def fresh(S: float = 0.35) -> Dict[str, Any]:
        return {"S": S, "asleep": False, "lying": False, "woken_until": None, "debt": 0.0, "slept_at": None,
                "woke_at": None, "bed_today": None, "late_nights": 0}

    @staticmethod
    def step(st: Dict[str, Any], *, t: float, hour: float, dt_h: float, sched: Dict[str, Any], chatting: bool,
             negative_load: float, clinginess_eff: float, rng_u: float) -> Optional[str]:
        """Advance S and the asleep / lying / woken flags. Returns an event name on a transition
        (fell_asleep / woke_up / woken_by_message is set by the engine) or None."""
        bed = float(sched.get("bedtime", 23.5))
        wake = float(sched.get("wake", 7.5))
        delay_max = float(sched.get("bedtime_delay_max_h", 1.5))
        ev = None
        if st["asleep"]:
            st["S"] = st["S"] * math.exp(-dt_h / TAU_SLEEP_H)
            # wake at the template time (or when pressure is gone and it is morning)
            if _hours_since(hour, wake) < dt_h + 1e-9 or (st["S"] < 0.08 and 5.0 <= hour < 12.0):
                st["asleep"], st["lying"] = False, False
                st["debt"] = _c(st["S"] * 2.0)            # residual pressure at wake = the debt
                st["woke_at"], st["slept_at"] = t, st.get("slept_at")
                st["bed_today"] = None
                ev = "woke_up"
            return ev
        # awake (incl. lying / woken): pressure builds
        st["S"] = 1.0 - (1.0 - st["S"]) * math.exp(-dt_h / TAU_WAKE_H)
        if st.get("woken_until") is not None:
            if chatting:
                st["woken_until"] = t + WOKEN_MIN * 60
            elif t >= st["woken_until"]:
                st["woken_until"] = None
                st["asleep"], st["lying"] = True, False
                return "fell_asleep"
            return None
        if st["bed_today"] is None:
            st["bed_today"] = bed
        # a late conversation delays bedtime, up to delay_max × how clingy she effectively is
        past_bed = _hours_since(st["bed_today"], hour) if _hours_since(st["bed_today"], hour) < 6 else -1
        if past_bed >= 0:
            if chatting and past_bed < delay_max * (0.4 + 0.6 * clinginess_eff):
                return None                         # still up for you
            if not st["lying"]:
                st["lying"] = True
            # falling asleep: likely within ~15 min, rumination (negative load) keeps her up longer
            p = _c(0.08 * (1.0 - 0.8 * _c(negative_load)) + 0.005)
            if past_bed > 2.5 or rng_u < p:
                st["asleep"], st["lying"] = True, False
                st["slept_at"] = t
                if past_bed > 0.5:
                    st["late_nights"] = int(st.get("late_nights", 0)) + 1
                return "fell_asleep"
        return None

    @staticmethod
    def wake_by_message(st: Dict[str, Any], t: float) -> bool:
        if not st["asleep"]:
            return False
        st["asleep"], st["lying"] = False, False
        st["woken_until"] = t + WOKEN_MIN * 60
        st["debt"] = _c(st["debt"] + 0.15)
        return True


def _hours_since(ref_hour: float, hour: float) -> float:
    """Hours from ref_hour forward to hour on a 24 h clock (0..24)."""
    return (hour - ref_hour) % 24.0


def activity_for(hour: float, sleep: Dict[str, Any], chatting: bool, life: Dict[str, Any]) -> str:
    if sleep["asleep"]:
        return "sleep"
    if sleep.get("woken_until") is not None:
        return "woken"
    if chatting:
        return "chat"
    if sleep.get("lying"):
        return "lying"
    sched = life.get("schedule", {})
    mode = str(life.get("busyness_mode", "work"))
    if in_block(hour, sched.get("meals", [])):
        return "meal"
    if mode == "work" and in_block(hour, sched.get("work", [])):
        return "work"
    if mode == "hobby" and in_block(hour, sched.get("hobby", sched.get("work", []))):
        return "hobby"
    return "rest"


def plan_day_event(rng, life: Dict[str, Any], sleep_debt: float, day_tick0: int, tick_s: int) -> Optional[Dict[str, Any]]:
    """Pick at most one small life event for the day (rule table in psyche.json), at a seeded time
    inside the waking day. Sleep debt makes the 'unwell' kind likelier (§14.6)."""
    events = list(life.get("small_events", []))
    if not events:
        return None
    sched = life.get("schedule", {})
    wake = float(sched.get("wake", 7.5))
    for e in events:
        p = float(e.get("p", 0.1))
        if e.get("kind") == "unwell":
            p *= 1.0 + 2.0 * sleep_debt
        if rng.random() < p:
            hour = wake + 1.0 + rng.random() * 10.0
            return {"tick": day_tick0 + int(hour * 3600 // tick_s), "text": e["text"], "v": float(e.get("v", 0.0)),
                    "R": float(e.get("R", 0.3)), "kind": e.get("kind", "life"), "share": bool(e.get("share", True))}
    return None


def project_progress(projects: List[Dict[str, Any]], dt_h: float, rng_u: float) -> Optional[Dict[str, Any]]:
    """Work time advances the first project; crossing a milestone (every 25 %) is a small event she may
    want to tell you (§14.4). Returns the milestone event or None."""
    if not projects:
        return None
    p = projects[0]
    before = float(p.get("progress", 0.0))
    diff = float(p.get("difficulty", 0.5))
    rate = 0.06 * (1.0 - 0.5 * diff)
    after = min(1.0, before + rate * dt_h)
    p["progress"] = after
    if int(after * 4) > int(before * 4) and rng_u < 0.9:
        return {"text": f"{p.get('title', '手上的案子')}（{p.get('stage', '進行中')}）又往前了一段", "v": 0.4, "R": 0.4,
                "kind": "project", "share": True}
    if after >= 1.0 and before < 1.0:
        return {"text": f"{p.get('title', '手上的案子')} 完成了", "v": 0.7, "R": 0.6, "kind": "project", "share": True}
    return None
