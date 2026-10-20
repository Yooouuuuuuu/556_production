"""Simulator scenarios (inner-life.md §20, §21 stage 3–4 acceptance): no LLM, a fake clock, the real
engine. 失聯 7 天 · 連續熬夜 · 工作中被打擾 · 半夜傳訊息 · 忙碌度 0 · 全天每小時聊 · 提醒準時 · 等我一下 ·
replay with a life."""
import copy
from datetime import datetime, timedelta, timezone

from psyche import config, urge as U
from psyche.engine import Engine

TZ = timezone(timedelta(hours=8))
T0 = datetime(2026, 10, 12, 20, 0, tzinfo=TZ).timestamp()  # a Monday evening, awake, after work


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def cfg(**over):
    c = copy.deepcopy(config.DEFAULTS)
    for k, v in over.items():
        c[k] = {**c[k], **v} if isinstance(v, dict) else v
    return c


def make(tmp_path, name, clock, c=None):
    e = Engine(tmp_path, "test", c or cfg(), db_path=tmp_path / f"{name}.db", now_fn=clock, llm=None)
    e.owner = True
    e.load()
    e.live = True  # urges are decided live only (nothing is sent: no worker consumes the queue)
    return e


def turn(e, clock, text="哈囉"):
    e.on_turn(text, "嗯。", turn_id=f"t{int(clock.t)}", platform="api_server", session_id="s1")


def run(e, clock, hours, step_min=1, on_fire=None):
    seen = set()
    for _ in range(int(hours * 60 / step_min)):
        clock.t += step_min * 60
        e.step_to(clock.t)
        if on_fire and e.contact.get("pending"):
            key = e.contact["pending"]["tick"]
            if key not in seen:
                seen.add(key)
                on_fire(e, clock)


def fires(e):
    return e.conn.execute("select count(*) from events where kind='proactive_fired'").fetchone()[0]


def hour_of(e, t):
    return e.local(t).hour + e.local(t).minute / 60


# --------------------------------------------------------------------------- 失聯 7 天

def test_lost_contact_7_days(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "lost", clock)
    turn(e, clock, "我先去忙了")
    phases = {}

    def she_sent_you_never_answered(eng, ck):  # every urge becomes a message; you never reply
        eng.on_event_reply("【事件】…", "在嗎？今天過得怎麼樣？", platform="api_server")

    for day in range(7):
        run(e, clock, 24, on_fire=she_sent_you_never_answered)
        phases[day] = e.contact["phase"]
    assert phases[0] == "protest" and phases[3] == "despair" and phases[6] == "detachment"
    assert e.needs["affiliation_person"] > 0.3
    # one unanswered -> wait long, two -> wait for you, never a third
    assert fires(e) <= 2
    assert e.contact["unanswered"] >= 1
    assert "沒跟製作人說到話" in e.state_block()


# --------------------------------------------------------------------------- sleep, late nights, waking

def test_sleep_cycle_and_late_nights(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "sleep", clock)
    run(e, clock, 24)
    ev = [r[0] for r in e.conn.execute("select payload from events where kind='sleep' order by id").fetchall()]
    assert any('"fell_asleep"' in p for p in ev) and any('"woke_up"' in p for p in ev)
    at3 = T0 + 7 * 3600                    # 03:00 the first night
    e2 = make(tmp_path, "sleep2", Clock(T0))
    c2 = Clock(T0)
    run(e2, c2, 7)
    assert e2.activity == "sleep" and e2.sleep["asleep"]
    assert "在睡覺" in e2.state_block()
    # a conversation that runs past bedtime keeps her up, and the morning carries a debt
    c3 = Clock(T0)
    e3 = make(tmp_path, "late", c3)
    for _ in range(4 * 12):                  # 20:00 → 00:00 a message every 5 min
        c3.t += 300
        turn(e3, c3)
        e3.step_to(c3.t)
    assert not e3.sleep["asleep"]            # still up for you at midnight
    run(e3, c3, 12)                          # → noon next day
    assert e3.sleep["debt"] > 0.05 and e3.sleep.get("late_nights", 0) >= 1


def test_midnight_message_wakes_her(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "wake", clock)
    run(e, clock, 7)                         # 03:00, asleep
    assert e.sleep["asleep"]
    turn(e, clock, "你睡了嗎")
    assert not e.sleep["asleep"] and e.activity == "woken"
    assert "被吵醒" in e.state_block() and "很睏" in e.state_block()
    assert any(i["type"] in ("joy", "distress") for i in e.active(clock.t))
    run(e, clock, 0.5)                       # 15 min later she drifts back
    assert e.sleep["asleep"] and e.sleep["debt"] > 0.1


# --------------------------------------------------------------------------- work, boredom, usage

def test_work_block_and_interruptibility(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "work", clock)
    run(e, clock, 14.5)                      # Tuesday 10:30
    assert e.activity == "work"
    b = e.state_block()
    assert "在工作" in b and "等她一下" in b
    run(e, clock, 9.5)                       # 20:00
    assert e.activity == "rest"
    allowed, why = U.gates(cfg=e.cfg["proactive"], hour=10.5, activity="work", chatting=False, proactive_today=0, minutes_today=0,
                           last_sent_at=None, t=clock.t, farewell_until=None, running=True, due_reminder=False)
    assert allowed


def test_busyness_none_gets_boring(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "bored", clock, cfg(life={**config.DEFAULTS["life"], "busyness_mode": "none"}))
    run(e, clock, 36)
    assert e.needs["novelty"] >= 0.3
    assert "無聊" in e.state_block()


def test_usage_awareness_gates_proactive(tmp_path):
    clock = Clock(T0 + 14 * 3600)            # Tuesday 10:00
    e = make(tmp_path, "usage", clock)
    for _ in range(18):                      # 3 h of chatting, a turn every 10 min
        clock.t += 600
        turn(e, clock)
        e.step_to(clock.t)
    assert e.contact["minutes_today"] >= 90
    ok, why = U.gates(cfg=e.cfg["proactive"], hour=13.0, activity="rest", chatting=False, proactive_today=0,
                      minutes_today=e.contact["minutes_today"], last_sent_at=None, t=clock.t, farewell_until=None, running=True, due_reminder=False)
    assert not ok and why == "usage"
    before = fires(e)
    run(e, clock, 8)                         # the rest of the day: nothing spontaneous
    assert fires(e) == before


# --------------------------------------------------------------------------- loops: reminders on time, her promise

def test_reminder_fires_on_time_through_no_disturb(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "rem", clock)
    cue = e.local(T0 + 11 * 3600).strftime("%Y-%m-%dT%H:%M")   # 07:00 next morning, inside no-disturb
    e.conn.execute("insert into commands(op, payload, requested_at, requested_by) values ('add_loop', ?, ?, 'test')",
                   ('{"what": "提醒我繳電費", "cue_time": "%s"}' % cue, clock.t))
    e.conn.commit()
    e.drain_commands()
    lid = next(iter(e.loops))
    assert e.loops[lid]["state"] == "waiting" and "掛念：提醒我繳電費" in e.state_block()
    def reminders():
        return [r for r in e.conn.execute("select payload from events where kind='proactive_fired'").fetchall() if '"reminder"' in r[0]]
    run(e, clock, 10.9)
    assert reminders() == []                # a spontaneous urge may happen, the reminder may not
    run(e, clock, 0.2)
    assert len(reminders()) == 1
    assert e.loops[lid]["state"] == "closed" and e.loops[lid]["outcome"] == "ok"   # said it: done
    assert abs(hour_of(e, e.contact["pending"]["at"]) - 7.0) < 0.05


def test_her_promise_comes_back(tmp_path):
    clock = Clock(T0 + 14.5 * 3600)          # Tuesday 10:30, at work
    e = make(tmp_path, "promise", clock)
    e.record_appraisal({"events": [], "loops": {"new": [{"what": "等她忙完回來找製作人", "origin": "her_promise", "cue_time": None,
                                                           "importance": 0.8}], "closed": []}, "farewell": False},
                       turn_id="t1", counterpart="製作人", platform="api_server")
    lid = next(iter(e.loops))
    assert e.loops[lid]["cue_time"]
    run(e, clock, 0.6)
    rows = e.conn.execute("select payload from events where kind='proactive_fired'").fetchall()
    assert len(rows) == 1 and '"return_promise"' in rows[0][0]


def _promise(e, what, ask, cp="製作人", cue=None):
    e.record_appraisal({"events": [], "loops": {"new": [{"what": what, "origin": "her_promise", "cue_time": cue, "importance": 0.8,
                                                           "agreed": True, "ask": ask}], "closed": []}, "farewell": False},
                       turn_id=f"t{len(e.loops)}", counterpart=cp, platform="api_server")
    return list(e.loops)[-1]


def _fired(e, kind):
    return [r for r in e.conn.execute("select payload, counterpart from events where kind='proactive_fired'").fetchall() if f'"{kind}"' in r[0]]


def test_promise_needs_agreement(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "agree", clock)
    e.record_appraisal({"events": [], "loops": {"new": [{"what": "幫製作人問角色丙", "origin": "her_promise", "cue_time": None, "importance": 0.8,
                                                           "agreed": False, "ask": ["c"]}], "closed": []}, "farewell": False},
                       turn_id="t1", counterpart="製作人", platform="api_server")
    assert e.loops == {}                      # she did not commit: nothing to come back to
    e.record_appraisal({"events": [], "loops": {"new": [{"what": "明早八點提醒製作人", "origin": "counterpart_said", "cue_time": None,
                                                           "importance": 0.8, "agreed": False, "ask": []}], "closed": []}, "farewell": False},
                       turn_id="t2", counterpart="製作人", platform="api_server")
    assert e.loops == {}


def test_promise_to_you_is_forced_even_at_night(tmp_path):
    clock = Clock(T0 + 3 * 3600)              # 23:00, inside no-disturb
    e = make(tmp_path, "forced", clock)
    lid = _promise(e, "等她忙完回來找製作人", [])
    run(e, clock, 0.6)
    assert len(_fired(e, "return_promise")) == 1 and e.loops[lid]["state"] == "closed"


def test_promise_through_another_character(tmp_path):
    clock = Clock(T0)                         # Monday 20:00, awake, free
    c = cfg(relationships={"c": {}})
    e = make(tmp_path, "ask", clock, c)
    lid = _promise(e, "幫製作人問角色丙有沒有對象", ["c"])
    assert e.loops[lid]["ask"] == ["c"] and "c" in e.others
    run(e, clock, 0.6)                        # the cue time (30 min) passes: she goes to ask, never speaks to you
    assert _fired(e, "return_promise") == [] and _fired(e, "report_back") == []
    asks = _fired(e, "ask_other")
    assert len(asks) == 1 and asks[0][1] == "c"
    assert e.loops[lid]["state"] == "asking" and e.loops[lid]["asking"] == "c" and e.loops[lid]["tries"] == 0
    assert "替製作人問的" in e.state_block(counterpart="c") and "已去問c" in e.state_block()
    # her question went out; 角色丙 answers, and the appraisal of THAT conversation closes the loop with the answer
    e.on_event_reply("【事件】…", "你現在有對象嗎？", platform="api_server", counterpart="c")
    assert e.loops[lid]["tries"] == 1               # it went out (556d keeps it if he is down)
    e.record_appraisal({"events": [{"event_kind": "loop_resolved", "cause": "角色丙說他目前單身", "v": 0.2, "R": 0.5, "u": 0.1, "cert": 1.0,
                                    "agent": "other", "intent": 0.5, "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.5, "other_v": 0.0,
                                    "appeal": 0.0, "q": 0.5, "loop_id": lid}],
                        "loops": {"new": [], "closed": [lid]}, "farewell": False}, turn_id="t9", counterpart="c", platform="api_server")
    assert e.loops[lid]["state"] == "answered" and e.loops[lid]["answer"] == "角色丙說他目前單身"
    assert "問到了：角色丙說他目前單身" in e.state_block()
    # the report waits for a decent hour: it is 20:40, allowed; it fires at once and is one of her messages to you
    run(e, clock, 0.1)
    reps = _fired(e, "report_back")
    assert len(reps) == 1 and reps[0][1] == "你"                                        # events for you carry the subject 你
    assert e.loops[lid]["state"] == "closed" and e.loops[lid]["outcome"] == "ok"        # told you what he said: done


def test_ask_once_then_wait_then_give_up_in_the_morning(tmp_path):
    clock = Clock(T0 + 2.5 * 3600)            # 22:30
    c = cfg(relationships={"c": {}}, proactive={"ask_give_up_h": 20.0})
    e = make(tmp_path, "giveup", clock, c)
    lid = _promise(e, "幫製作人問角色丙週末有沒有空", ["c"])
    run(e, clock, 0.6)                        # asked once; 556d keeps the message if 角色丙 is down, so she only waits
    assert len(_fired(e, "ask_other")) == 1 and e.loops[lid]["state"] == "asking"
    e.on_event_reply("【事件】…", "你週末有空嗎？", platform="api_server", counterpart="c")
    assert e.loops[lid]["tries"] == 1
    run(e, clock, 30)                         # no answer for 20 h: she gives up, and tells you in the morning, once
    assert len(_fired(e, "ask_other")) == 1
    assert e.loops[lid]["state"] == "closed" and e.loops[lid]["outcome"] == "failed" and e.loops[lid]["answer"] is None   # told you: no luck
    reps = _fired(e, "report_back")
    assert len(reps) == 1
    h = hour_of(e, e.conn.execute("select at from events where kind='proactive_fired' order by id desc limit 1").fetchone()[0])
    assert 8 <= h < 23


def test_forgetting_toggle_rate_and_importance(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "noforget", clock, cfg(character={"forgets": False}))   # switched off: never forgets
    cue = e.local(T0 + 1800).strftime("%Y-%m-%dT%H:%M")
    lid = _promise(e, "提醒製作人繳電費", [], cue=cue)
    run(e, clock, 1)
    assert e.loops[lid]["state"] == "closed"
    c = cfg(character={"forgets": True, "memory_reliability": 0.0})
    e2 = make(tmp_path, "forgets", clock, c)
    lid2 = _promise(e2, "提醒製作人繳電費", [], cue=e2.local(clock.t + 1800).strftime("%Y-%m-%dT%H:%M"))
    e2.loops[lid2]["importance"] = 0.0          # nothing holds it: certain to slip
    run(e2, clock, 1)
    assert e2.loops[lid2]["state"] == "forgot" and e2.loops[lid2]["why"] == "forgot"
    assert e2.conn.execute("select count(*) from events where kind='loop_forgot'").fetchone()[0] == 1
    assert "繳電費" not in e2.state_block()      # she does not see what she forgot
    e2.cfg["character"]["memory_reliability"] = 0.7   # an important item adds 0.3: at 0.7 it is always remembered
    lid3 = _promise(e2, "七點叫製作人起床", [], cue=e2.local(clock.t + 1800).strftime("%Y-%m-%dT%H:%M"))
    e2.loops[lid3]["importance"] = 1.0
    run(e2, clock, 1)
    assert e2.loops[lid3]["state"] == "closed"
    # the default: 記性 0.8 (+ the little her mood sits above its baseline right now)
    e3 = make(tmp_path, "rate", clock)
    mood_bad = max(0.0, min(1.0, (e3.affect["neg"] - e3.derived["mu_neg_base"]) / 0.5))
    assert abs(e3._forget_p({"importance": 0.0, "created_at": clock.t}, clock.t) - (0.2 + 0.3 * mood_bad)) < 1e-6
    assert abs(e3._forget_p({"importance": 0.9, "created_at": clock.t}, clock.t) - max(0.0, 0.3 * mood_bad - 0.1)) < 1e-6
    e3.affect["neg"] = e3.derived["mu_neg_base"] + 0.5                  # a really bad day: the full −0.3
    assert abs(e3._forget_p({"importance": 0.0, "created_at": clock.t}, clock.t) - 0.5) < 1e-6
    assert abs(e3._forget_p({"importance": 0.9, "created_at": clock.t}, clock.t) - 0.2) < 1e-6


def test_undelivered_due_item_backs_off_then_is_forgotten(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "undelivered", clock, cfg(proactive={"undelivered_window_h": 2.0}))
    lid = _promise(e, "提醒製作人繳電費", [], cue=e.local(T0 + 600).strftime("%Y-%m-%dT%H:%M"))
    run(e, clock, 0.3)
    assert len(_fired(e, "return_promise")) == 1 and e.loops[lid]["state"] == "closed"
    # the platform failed to deliver: not used up — back to due with a backoff, retried, then 忘了 after the window
    e._record_and_apply("send_failed", {"why": "agent error: HTTP 502", "kind": "return_promise", "what": "提醒製作人繳電費", "counterpart": "你", "loop": lid}, counterpart="你")
    assert e.loops[lid]["state"] == "due" and e.loops[lid]["fails"] == 1 and e._held(e.loops[lid], clock.t)
    run(e, clock, 0.04)
    assert len(_fired(e, "return_promise")) == 1       # held for 5 min
    run(e, clock, 0.1)
    assert len(_fired(e, "return_promise")) == 2       # retried

    def still_down(eng, ck):                            # every retry fails the same way while the lane is down
        pend = eng.contact.get("pending") or {}
        eng._record_and_apply("send_failed", {"why": "agent error: HTTP 502", "kind": pend.get("kind"), "what": pend.get("what"), "counterpart": "你", "loop": pend.get("loop")}, counterpart="你")
    still_down(e, clock)
    run(e, clock, 2.5, on_fire=still_down)
    assert e.loops[lid]["state"] == "forgot" and e.loops[lid]["why"] == "undelivered"
    assert 2 <= len(_fired(e, "return_promise")) <= 6   # backoff: a handful of tries, not one per minute


def test_same_thing_twice_is_one_loop(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "dup", clock, cfg(character={"forgets": False}))
    cue = e.local(T0 + 12 * 3600).strftime("%Y-%m-%dT%H:%M")
    def ask(what, cue_time, turn):
        e.record_appraisal({"events": [], "loops": {"new": [{"what": what, "origin": "counterpart_said", "cue_time": cue_time, "importance": 0.6,
                                                               "agreed": True, "ask": []}], "closed": []}, "farewell": False},
                           turn_id=turn, counterpart="製作人", platform="api_server")
    ask("明早八點提醒製作人繳電費", cue, "t1")
    ask("提醒製作人明天早上八點要繳電費", cue, "t2")       # the same thing said again: the engine's backstop merges it
    assert len(e.loops) == 1
    lid = next(iter(e.loops))
    # the appraisal itself can say "same as X" and move the time
    later = e.local(T0 + 14 * 3600).strftime("%Y-%m-%dT%H:%M")
    e.record_appraisal({"events": [], "loops": {"new": [], "refresh": [{"id": lid, "cue_time": later}], "closed": []}, "farewell": False},
                       turn_id="t3", counterpart="製作人", platform="api_server")
    assert len(e.loops) == 1 and e.loops[lid]["cue_time"] == later and e.loops[lid]["state"] == "waiting"
    ask("週五的面試", None, "t4")                            # a different thing is a second loop
    assert len(e.loops) == 2


def _memory_db(tmp_path, turn_id):
    """A minimal KeepsakeDB file: one memory from the turn, the command queue the engine writes to."""
    import sqlite3
    p = tmp_path / "mem.db"
    c = sqlite3.connect(str(p))
    c.executescript("""CREATE TABLE memories(id INTEGER PRIMARY KEY, text TEXT, tokens TEXT, tags TEXT DEFAULT '[]', meta TEXT DEFAULT '{}',
                       archived INTEGER DEFAULT 0, archive_reason TEXT, created_at REAL, updated_at REAL, layer TEXT DEFAULT 'long');
                       CREATE TABLE memory_tags(memory_id INTEGER, tag TEXT);
                       CREATE TABLE commands(id INTEGER PRIMARY KEY, op TEXT, payload TEXT DEFAULT '{}', requested_at REAL, requested_by TEXT, done_at REAL, result TEXT);""")
    c.execute("INSERT INTO memories(text, tokens, tags, meta, created_at, updated_at) VALUES (?, '', '[]', ?, 0, 0)",
              ("他建議我走露一點的路線", '{"turn_id": "%s"}' % turn_id))
    c.commit(); c.close()
    return p


def _commands(path):
    import sqlite3, json as _j
    c = sqlite3.connect(str(path))
    try:
        return [(op, _j.loads(pl)) for op, pl in c.execute("SELECT op, payload FROM commands ORDER BY id")]
    finally:
        c.close()


def _slight(e, turn_id, cp="製作人", v=-0.6, R=0.7, intent=0.8):
    e.record_appraisal({"events": [{"event_kind": "dismissed", "cause": "製作人建議她走露一點的路線吸引流量", "v": v, "R": R, "u": 0.3, "cert": 1.0,
                                    "agent": "other", "intent": intent, "devalue": 0.6, "ambiguity": 0.1, "other_focus": 0.0, "other_v": 0.0,
                                    "appeal": 0.0, "q": 0.3, "loop_id": None}], "loops": {"new": [], "closed": []}, "farewell": False},
                       turn_id=turn_id, counterpart=cp, platform="api_server")


def test_hurt_ledger_holds_memory_then_releases_as_old_account(tmp_path):
    clock = Clock(T0)
    mem = _memory_db(tmp_path, "t1")
    e = Engine(tmp_path, "test", cfg(character={"forgets": False}), db_path=tmp_path / "led.db", now_fn=clock, llm=None, memory_db=mem)
    e.owner = True
    e.load()
    e.live = True
    e._rel("你")["bond"] = 0.6                      # a friend's slight registers; a careless small one would stay below the threshold
    _slight(e, "t1")
    entries = [x for x in e.ledger["你"] if x.get("resolved_at") is None]
    assert len(entries) == 1 and entries[0]["avoidance"] >= 0.1 and entries[0]["turn_id"] == "t1"
    assert "心裡還記著一筆" in e.state_block()            # on the ledger = in the prompt, no gate
    assert _commands(mem) == [("hold", {"turn_id": "t1", "on": True, "reason": f"委屈帳 {entries[0]['id']}"})]
    # brought up again without being owned: the entry comes back up; the feelings see a dismissal
    av = entries[0]["avoidance"]
    e.record_appraisal({"events": [{"event_kind": "revisited_hurt", "cause": "製作人又提了一次那條路線", "v": -0.3, "R": 0.5, "u": 0.1, "cert": 1.0,
                                    "agent": "other", "intent": 0.7, "devalue": 0.3, "ambiguity": 0.1, "other_focus": 0.0, "other_v": 0.0,
                                    "appeal": 0.0, "q": 0.3, "loop_id": None, "ledger_id": entries[0]["id"]}],
                        "loops": {"new": [], "closed": []}, "farewell": False}, turn_id="t2", counterpart="製作人", platform="api_server")
    assert entries[0]["avoidance"] > av and entries[0]["revisits"] == 1
    # time forgives: the entry closes and the turn's memories come back as 舊帳 with the date
    run(e, clock, 24 * 4)
    assert entries[0]["resolved_at"] is not None and not entries[0].get("repaired")
    ops = _commands(mem)[1:]
    assert ops[0] == ("hold", {"turn_id": "t1", "on": False, "reason": entries[0]["resolved_by"]})
    assert ops[1][0] == "patch" and ops[1][1]["add_tags"] == ["舊帳"] and ops[1][1]["meta"]["prefix"].startswith("（舊帳 2026/10/1")
    assert "心裡還記著一筆" not in e.state_block()


def test_hurt_ledger_repaired_comes_back_plain_and_small_slights_never_open(tmp_path):
    clock = Clock(T0)
    mem = _memory_db(tmp_path, "t1")
    e = Engine(tmp_path, "test", cfg(character={"forgets": False}), db_path=tmp_path / "rep.db", now_fn=clock, llm=None, memory_db=mem)
    e.owner = True
    e.load()
    e.live = True
    _slight(e, "t1", v=-0.3, R=0.4, intent=0.1)        # a careless small one: below hurt_open_min — nothing opens, nothing is held
    assert [x for x in e.ledger.get("你", []) if x.get("resolved_at") is None] == [] and _commands(mem) == []
    e._rel("你")["bond"] = 0.6
    _slight(e, "t1")
    entry = [x for x in e.ledger["你"] if x.get("resolved_at") is None][0]
    e.record_appraisal({"events": [{"event_kind": "apology", "cause": "製作人說他不該那樣講，對不起", "v": 0.5, "R": 0.6, "u": 0.2, "cert": 1.0,
                                    "agent": "other", "intent": 0.9, "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.0, "other_v": 0.0,
                                    "appeal": 0.0, "q": 0.6, "loop_id": None, "apology_components": 5}],
                        "loops": {"new": [], "closed": []}, "farewell": False}, turn_id="t3", counterpart="製作人", platform="api_server")
    assert entry["repaired"]
    run(e, clock, 24 * 3.5)
    assert entry["resolved_at"] is not None
    ops = _commands(mem)
    assert ops[0][0] == "hold" and ops[-1] == ("hold", {"turn_id": "t1", "on": False, "reason": "repaired"})
    assert all(op != "patch" for op, _ in ops)       # repaired: plain memory again, no 舊帳


def test_farewell_mode(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "bye", clock)
    e.record_appraisal({"events": [{"event_kind": "farewell", "cause": "製作人說要去睡了", "v": 0.1, "R": 0.3, "u": 0.0, "cert": 1.0,
                                    "agent": "other", "intent": 0.3, "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.0,
                                    "other_v": 0.0, "appeal": 0.0, "q": 0.4, "loop_id": None}],
                        "loops": {"new": [], "closed": []}, "farewell": True}, turn_id="t1", counterpart="製作人", platform="api_server")
    assert "剛道過別" in e.state_block()
    ok, why = U.gates(cfg=e.cfg["proactive"], hour=21.0, activity="rest", chatting=False, proactive_today=0, minutes_today=0,
                      last_sent_at=None, t=clock.t + 60, farewell_until=e.contact["farewell_until"], running=True, due_reminder=False)
    assert not ok and why == "farewell"


# --------------------------------------------------------------------------- determinism with a whole life in it

def rounded(st):
    return {"tick": st["tick"], "affect": {k: round(v, 9) for k, v in st["affect"].items()}, "mood": [round(x, 9) for x in st["mood"]],
            "energy": round(st["energy"], 9), "activity": st["activity"], "needs": {k: round(v, 9) for k, v in st["needs"].items()},
            "sleep": (st["sleep"]["asleep"], round(st["sleep"]["S"], 9), round(st["sleep"]["debt"], 9)),
            "instances": sorted((i["id"], i["type"], round(i["intensity"], 9)) for i in st["instances"]),
            "fires": None}


def test_replay_and_fast_forward_with_a_life(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "life", clock)
    turn(e, clock, "晚安")
    run(e, clock, 30)                        # a night, a work day, a life event or two, maybe an urge
    clock.t += 60
    turn(e, clock, "我回來了")
    run(e, clock, 6)
    live = rounded(e.status())
    live["fires"] = fires(e)
    e2 = Engine(tmp_path, "test", cfg(), db_path=tmp_path / "life.db", now_fn=clock, llm=None)
    e2.owner = True
    e2.load()                                # snapshot + replay of turns / events at their ticks
    r2 = rounded(e2.status())
    r2["fires"] = fires(e2)
    assert r2 == live
    # fast-forward: the same 36 h in one step_to, same turns recorded at the same times
    c3 = Clock(T0)
    e3 = make(tmp_path, "ff", c3)
    e3._event("turn", {"turn_id": "x", "platform": "api_server", "session": "s1", "user": "晚安", "assistant": "嗯。"}, T0, counterpart="製作人")
    e3._event("turn", {"turn_id": "y", "platform": "api_server", "session": "s1", "user": "我回來了", "assistant": "嗯。"}, T0 + 30 * 3600 + 60, counterpart="製作人")
    c3.t = T0 + 36 * 3600 + 60
    e3.step_to(c3.t)
    r3 = rounded(e3.status())
    r3["fires"] = live["fires"]  # a fast-forward never decides urges (nothing is back-filled); the dynamics must still match
    assert r3 == live
