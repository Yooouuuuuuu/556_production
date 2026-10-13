"""L5 / L6 scenarios (inner-life.md §21 stage 5 acceptance): 失約 3 次, 失約後道歉, 誤會後更正, 90 天,
黏人度掃描, 傲嬌度掃描, and the three-character month (stage 6, engine level)."""
import copy
from datetime import datetime, timedelta, timezone

from psyche import config, relation as RL
from psyche.engine import Engine, MAIN

TZ = timezone(timedelta(hours=8))
T0 = datetime(2026, 10, 12, 20, 0, tzinfo=TZ).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def cfg(**over):
    c = copy.deepcopy(config.DEFAULTS)
    for k, v in over.items():
        c[k] = {**c[k], **v} if isinstance(v, dict) and isinstance(c.get(k), dict) else v
    return c


FRIENDS = {MAIN: {"bond": 0.5, "hours": 60, "warmth": 0.4}}  # the hurt scenarios happen between people who know each other


def make(tmp_path, name, clock, c=None, char="mane"):
    e = Engine(tmp_path, char, c or cfg(), db_path=tmp_path / f"{name}.db", now_fn=clock, llm=None,
               names_fn=lambda p: {"sayo": "小夜", "chihiro": "千尋", "yuma": "悠真"}.get(p, p))
    e.owner = True
    e.load()
    e.live = True
    return e


def ev(kind, **kw):
    base = {"event_kind": kind, "cause": kw.pop("cause", ""), "v": 0.0, "R": 0.5, "u": 0.0, "cert": 1.0, "agent": "other", "intent": 0.3,
            "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.0, "other_v": 0.0, "appeal": 0.0, "q": 0.5, "loop_id": None,
            "she_disclosed": False, "other_disclosed": False, "ppr": None, "apology_components": 3, "other_tired": False}
    base.update(kw)
    return base


def appraise(e, clock, *events, cp=MAIN, loops=None):
    e.record_appraisal({"events": list(events), "loops": loops or {"new": [], "closed": []}, "farewell": False},
                       turn_id=f"t{int(clock.t)}", counterpart=cp, platform="api_server")


def run(e, clock, hours):
    for _ in range(int(hours * 60)):
        clock.t += 60
        e.step_to(clock.t)


BROKEN = dict(cause="「製作人」說好晚上回來聊，沒有回來", v=-0.6, R=0.7, u=0.6, intent=0.3, devalue=0.6, q=0.2)
APOLOGY = dict(cause="「製作人」為昨晚的事道歉，承認是自己忘了", v=0.5, R=0.7, intent=0.8, q=0.8, apology_components=5)


def test_three_broken_promises_erode_trust_and_stack(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "b3", clock, cfg(relationships=FRIENDS))
    before = RL.trust_value(e._rel(MAIN))
    firsts = []
    for n in range(3):
        appraise(e, clock, ev("promise_broken", **BROKEN))
        firsts.append(max((i["intensity"] for i in e.active() if i["type"] == "disappointment"), default=0.0))
        run(e, clock, 24)
    rel = e._rel(MAIN)
    assert RL.trust_value(rel) < before and rel["broken"] == 3
    assert firsts[2] < firsts[0]                      # hedonic adaptation: the third stings less
    assert len(e.ledger[MAIN]) == 3 and any(x.get("resolved_at") is None for x in e.ledger[MAIN])


def test_apology_cuts_the_ledger_by_half(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "apo", clock, cfg(relationships=FRIENDS))
    appraise(e, clock, ev("promise_broken", **BROKEN))
    led = e.ledger[MAIN]
    assert led and led[0]["avoidance"] > 0
    av0 = led[0]["avoidance"]
    assert RL.hurt_gate(led) > 0
    b = e.state_block()
    assert "委屈" in b and "不說反話" in b
    clock.t += 1800
    appraise(e, clock, ev("apology", **APOLOGY))
    assert led[0]["avoidance"] <= 0.5 * av0
    run(e, clock, 24)
    assert all(x.get("resolved_at") is not None or x["avoidance"] < 0.3 * av0 for x in led)


def test_false_belief_correction_nearly_erases(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "fb", clock, cfg(relationships=FRIENDS))
    appraise(e, clock, ev("promise_broken", **BROKEN))
    av0 = e.ledger[MAIN][0]["avoidance"]
    clock.t += 600
    appraise(e, clock, ev("false_belief_corrected", cause="原來「製作人」手機沒電了", v=0.4, R=0.6, agent="circ"))
    assert e.ledger[MAIN][0]["avoidance"] <= 0.25 * av0
    assert any(i["type"] == "relief" for i in e.active())


def test_ninety_days_of_daily_contact(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "d90", clock)
    rel = e._rel(MAIN)
    assert rel["attachment"] == 0.0 and rel["hours"] == 0.0
    for day in range(90):
        for turn in range(8):                        # an hour and a bit a day: eight exchanges, one of them deep
            clock.t += 600
            e.on_turn("聊聊", "嗯。", turn_id=f"t{day}_{turn}", platform="api_server", session_id="s1")
            appraise(e, clock, ev("disclosed_personal" if turn == 7 else "small_talk", q=0.9 if turn == 7 else 0.4,
                                  she_disclosed=(turn == 7), ppr={"understood": 0.8, "validated": 0.8, "cared": 0.8} if turn == 7 else None))
        run(e, clock, 22.5)
    assert rel["hours"] >= 50                        # 朋友 milestone within three months
    assert rel["bond"] >= 0.3 and 0.1 <= rel["attachment"] <= 0.6
    assert rel["disclosure"] >= 2
    assert "朋友" in RL.closeness_words(rel, "製作人") or "很熟" in RL.closeness_words(rel, "製作人")


def test_clinginess_sweep_changes_how_often_she_reaches_out(tmp_path):
    counts = []
    for cap in (0.0, 0.5, 1.0):
        c = cfg(character={**config.DEFAULTS["character"], "clinginess_cap": cap}, proactive={**config.DEFAULTS["proactive"], "daily_cap": 20, "min_gap_min": 30})
        clock = Clock(T0)
        e = make(tmp_path, f"cl{cap}", clock, c)
        e.on_turn("先走了", "好。", turn_id="t0", platform="api_server", session_id="s1")
        fired = 0
        for _ in range(3 * 24 * 60):
            clock.t += 60
            e.step_to(clock.t)
            if e.contact.get("pending"):
                fired += 1
                e.on_event_reply("【事件】", "在嗎", platform="api_server")
                e.contact["awaiting_since"] = None  # pretend you always answer, so damping never bites
                e.contact["unanswered"] = 0
        counts.append(fired)
    assert counts[0] <= counts[1] <= counts[2] and counts[2] > counts[0]


def test_tsundere_sweep_changes_the_strategy(tmp_path):
    inv = []
    for ts in (0.0, 1.0):
        c = cfg(character={**config.DEFAULTS["character"], "tsundere_tendency": ts})
        c["relationships"] = {MAIN: {"bond": 0.8, "hours": 150}}
        clock = Clock(T0)
        e = make(tmp_path, f"ts{ts}", clock, c)
        n = 0
        for k in range(40):
            clock.t += 60
            appraise(e, clock, ev("praised_her", cause="「製作人」誇她的歌", v=0.7, R=0.6, intent=0.7, appeal=0.7))
            e.state_block()
            n += e.last_strategy.get(MAIN) == "inverted"
        inv.append(n)
    assert inv[0] == 0 and inv[1] > 0


def test_three_characters_a_month(tmp_path):
    """A (mane) talks to you daily and to chihiro weekly; the couple prior (chihiro ↔ yuma) is high. After a
    month her attachment to you has grown from zero, her bond with chihiro moved a little, and nothing about
    the couple leaked into her state (she only has her own relationships)."""
    c = cfg()
    c["relationships"] = {"chihiro": {"bond": 0.4, "hours": 60, "trust_alpha": 4, "trust_beta": 1, "attachment_strength": 0.3}}
    clock = Clock(T0)
    e = make(tmp_path, "trio", clock, c)
    for day in range(30):
        for turn in range(3):
            clock.t += 600
            e.on_turn("今天怎麼樣", "還不錯。", turn_id=f"y{day}_{turn}", platform="api_server", session_id="s1")
            appraise(e, clock, ev("asked_about_her", q=0.6, ppr={"understood": 0.7, "validated": 0.7, "cared": 0.7}, she_disclosed=True))
        if day % 7 == 3:
            clock.t += 600
            e.on_turn("千尋：最近錄音順嗎？", "嗯，還行。", turn_id=f"c{day}", platform="api_server", session_id="s_chihiro", counterpart="chihiro")
            appraise(e, clock, ev("asked_about_her", q=0.7, ppr={"understood": 0.8, "validated": 0.7, "cared": 0.8}, she_disclosed=True), cp="chihiro")
        run(e, clock, 23)
    you, chi = e._rel(MAIN), e._rel("chihiro")
    assert you["attachment"] > 0.03 and you["hours"] > 5
    assert chi["bond"] >= 0.35 and chi["attachment"] >= 0.3
    assert "chihiro" in e.others and e.others["chihiro"]["contact"]["last_turn_at"] is not None
    b = e.state_block(counterpart="chihiro")
    assert "對千尋：" in b
    st = e.status()
    assert set(st["rel"]) >= {MAIN, "chihiro"}


def test_feedback_calibrates_the_gain(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "fb2", clock)
    e.conn.execute("insert into commands(op, payload, requested_at, requested_by) values ('feedback', ?, ?, 'test')",
                   ('{"type": "disappointment", "verdict": "too_much"}', clock.t))
    e.conn.commit()
    e.drain_commands()
    assert abs(e.gain_adj["disappointment"] - 0.95) < 1e-6
    appraise(e, clock, ev("promise_broken", **BROKEN))
    assert max(i["intensity0"] for i in e.active() if i["type"] == "disappointment") < 0.534
