"""Golden cases (inner-life.md Appendix A.7) for the impact model B — pure, no clock, no LLM."""
from psyche import config, model

D = model.derive(config.DEFAULTS["character"], config.DEFAULTS["time"])
IMP = config.DEFAULTS["impact"]


def ap(**kw):
    base = {"event_kind": "other", "cause": "", "v": 0.0, "R": 0.5, "u": 0.0, "cert": 1.0, "agent": "circ", "intent": 0.3,
            "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.0, "other_v": 0.0, "appeal": 0.0, "q": 0.5, "loop_id": None}
    base.update(kw)
    return base


def born(a, active=(), stacks=None, mood_v=0.0):
    return {i["type"]: i["intensity0"] for i in model.appraise_to_instances(a, D, IMP, list(active), dict(stacks or {}), mood_valence=mood_v)}


def test_derive_is_in_range():
    assert 0 < D["mu_pos_base"] < 1 and 0 < D["mu_neg_base"] < 1 and D["theta_affect"] > 0
    assert all(-1 <= x <= 1 for x in D["mood_default"])
    assert 2.0 <= D["affect_half_life_h"] <= 6.0


def test_forgot_the_date():  # 他忘了約好的聊天 -> 失望「蠻」；委屈「有點」；無憤怒
    r = born(ap(event_kind="promise_broken", v=-0.6, R=0.7, u=0.6, agent="other", intent=0.3, devalue=0.6))
    assert 0.45 <= r["disappointment"] < 0.7
    assert 0.2 <= r["hurt"] < 0.45
    assert "anger" not in r and "distress" not in r


def test_deliberate_no_show():  # 他故意不來 -> 憤怒出現；委屈明顯更大
    a = born(ap(event_kind="promise_broken", v=-0.6, R=0.7, u=0.6, agent="other", intent=0.3, devalue=0.6))
    b = born(ap(event_kind="promise_broken", v=-0.6, R=0.7, u=0.6, agent="other", intent=0.9, devalue=0.6))
    assert "anger" in b and b["anger"] >= 0.2
    assert b["hurt"] / a["hurt"] >= 1.3


def test_third_time_stacks():  # 同一件事第 3 次 -> 失望 < 第 1 次
    a = born(ap(event_kind="promise_broken", v=-0.6, R=0.7, u=0.6, agent="other", intent=0.3, devalue=0.6))
    c = born(ap(event_kind="promise_broken", v=-0.6, R=0.7, u=0.6, agent="other", intent=0.3, devalue=0.6),
             stacks={"disappointment:promise_broken": 2, "hurt:promise_broken": 2})
    assert c["disappointment"] < a["disappointment"] and c["hurt"] < a["hurt"]


def test_his_interview_passed_with_loop():  # 他面試過了（有 loop）-> 為他高興 + 滿足；希望結束
    hope = {"id": "h1", "type": "hope", "loop_id": "ol_1", "intensity": 0.4}
    a = ap(event_kind="loop_resolved", v=0.5, R=0.7, other_focus=1.0, other_v=0.8, agent="other", loop_id="ol_1")
    r = born(a, active=[hope])
    assert "happy_for" in r and "satisfaction" in r
    assert "gratitude" not in r and "joy" not in r
    assert model.resolutions("loop_resolved", "ol_1", [hope]) == {"h1": 0.0}


def test_he_praised_her_song():  # 喜悅 + 感激
    r = born(ap(event_kind="praised_her", v=0.7, R=0.6, agent="other", intent=0.7))
    assert "joy" in r and "gratitude" in r and r["joy"] >= 0.3


def test_he_is_tired():  # 為他難過，強度隨 B（0.5.0 固定 0.5）
    r = born(ap(event_kind="shared_news_bad", v=-0.2, R=0.5, other_focus=1.0, other_v=-0.5))
    assert set(r) == {"sorry_for"} and 0.1 < r["sorry_for"] < 0.45


def test_rain_is_nothing():  # 下雨 -> 苦惱 < 0.2（甚至不產生）
    r = born(ap(event_kind="other", v=-0.2, R=0.2, agent="circ"))
    assert all(v < 0.2 for v in r.values())


def test_ambiguous_when_in_a_bad_mood():  # 不熟時他說「隨便」-> v 被染色但低強度；無委屈帳
    r = born(ap(event_kind="dismissed", v=-0.2, R=0.3, agent="other", intent=0.2, devalue=0.2, ambiguity=0.8), mood_v=-0.5)
    assert "hurt" not in r and all(v < 0.2 for v in r.values())


def test_apology_and_correction_tables():
    assert model.RESOLVES["apology"]["hurt"] <= 0.5          # 道歉後 24 小時內降到 50% 以下
    assert model.RESOLVES["false_belief_corrected"]["hurt"] <= 0.3


def test_words():
    assert model.intensity_word(0.1) == "" and model.intensity_word(0.3) == "有點"
    assert model.intensity_word(0.5) == "蠻" and model.intensity_word(0.9) == "很"
    assert model.octant((0.5, 0.5, -0.5))[1] == "撒嬌黏人" and model.octant((-0.3, -0.3, -0.3))[1] == "悶"
    assert model.energy_word(0.2) == "很累" and model.energy_word(0.8) == "精神很好"


def test_ou_exact_solution_is_stable_and_pulls_back():
    x = 0.9
    for _ in range(3000):  # 50 h at θ = 0.3/h: e^-15 of the gap is left
        x = model.ou_step(x, 0.3, 0.3, 0.0, 1 / 60, 0.0)
    assert abs(x - 0.3) < 1e-3
    assert 0.0 <= model.ou_step(0.5, 0.5, 0.3, 0.05, 1 / 60, 3.0) <= 1.0


def test_mood_rises_faster_than_it_falls():
    up = model.mood_step((0.0, 0.0, 0.0), (0.8, 0.2, 0.2), (0, 0, 0), 1.0, 3.0, 0.4, 0.25)
    down = model.mood_step((0.0, 0.0, 0.0), (-0.8, 0.2, 0.2), (0, 0, 0), 1.0, 3.0, 0.4, 0.25)
    assert up[0] == 0.4 and down[0] == -0.25
