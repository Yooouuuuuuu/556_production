"""Engine: replay == live, fast-forward == tick by tick, the state block, repair, loops, ownership."""
import copy

import pytest

from psyche import config
from psyche.engine import Engine

T0 = 1_790_000_000.0 - (1_790_000_000.0 % 60)  # on the grid, 2026-09-21 Asia/Taipei


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def cfg():
    c = copy.deepcopy(config.DEFAULTS)
    c["time"]["snapshot_interval_min"] = 15
    return c


def make(tmp_path, name, clock):
    e = Engine(tmp_path, "test", cfg(), db_path=tmp_path / f"{name}.db", now_fn=clock, llm=None)
    e.owner = True
    e.load()
    return e


def broken_promise(cause="「製作人」說晚上回來聊，沒有回來"):
    return {"events": [{"event_kind": "promise_broken", "cause": cause, "v": -0.6, "R": 0.7, "u": 0.6, "cert": 1.0,
                        "agent": "other", "intent": 0.3, "devalue": 0.6, "ambiguity": 0.1, "other_focus": 0.0,
                        "other_v": 0.0, "appeal": 0.0, "q": 0.3, "loop_id": None}],
            "loops": {"new": [], "closed": []}, "farewell": False}


def apology():
    return {"events": [{"event_kind": "apology", "cause": "「製作人」為昨晚的事道歉，承認是自己忘了", "v": 0.5, "R": 0.7, "u": 0.3,
                        "cert": 1.0, "agent": "other", "intent": 0.8, "devalue": 0.0, "ambiguity": 0.0, "other_focus": 0.0,
                        "other_v": 0.0, "appeal": 0.0, "q": 0.8, "loop_id": None}],
            "loops": {"new": [], "closed": []}, "farewell": False}


def rounded(st):
    return {"tick": st["tick"], "affect": {k: round(v, 9) for k, v in st["affect"].items()},
            "mood": [round(x, 9) for x in st["mood"]], "energy": round(st["energy"], 9),
            "instances": sorted((i["id"], i["type"], round(i["intensity"], 9)) for i in st["instances"])}


def test_replay_rebuilds_the_same_state(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "a", clock)
    clock.t = T0 + 120
    e.record_appraisal(broken_promise(), turn_id="t1", counterpart="製作人", platform="api_server")
    clock.t = T0 + 5 * 3600
    e.step_to(clock.t)
    live = rounded(e.status())
    assert any(i[1] == "disappointment" for i in live["instances"])
    e2 = Engine(tmp_path, "test", cfg(), db_path=tmp_path / "a.db", now_fn=clock, llm=None)  # a restart: snapshot + replay
    e2.owner = True
    e2.load()
    assert rounded(e2.status()) == live


def test_fast_forward_equals_tick_by_tick(tmp_path):
    ca, cb = Clock(T0), Clock(T0)
    a = make(tmp_path, "live", ca)
    b = make(tmp_path, "ff", cb)
    for _ in range(6 * 60):           # six hours, one tick at a time
        ca.t += 60
        if ca.t == T0 + 2 * 3600:
            a.record_appraisal(broken_promise(), turn_id="t1", counterpart="製作人", platform="api_server")
        a.step_to(ca.t)
    cb.t = T0 + 2 * 3600
    b.record_appraisal(broken_promise(), turn_id="t1", counterpart="製作人", platform="api_server", apply_now=False)
    cb.t = T0 + 6 * 3600
    b.step_to(cb.t)                   # she was "stopped" for six hours: one call runs the missed ticks
    assert rounded(a.status()) == rounded(b.status())


def test_state_block_shape_and_transition(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "s", clock)
    b0 = e.state_block()
    assert b0.startswith("【她現在】") and len(b0.splitlines()) <= 10 and "心情：" in b0 and "原則：" in b0   # title + clock + 8
    assert b0.splitlines()[1].startswith("現在：") and "（" in b0.splitlines()[1]  # the clock line, first after the title
    clock.t = T0 + 60
    e.record_appraisal(broken_promise(), turn_id="t1", counterpart="製作人", platform="api_server")
    b1 = e.state_block()
    assert "失望" in b1 and "沒有回來" in b1 and "轉變" not in b1  # first feeling after calm: no transition line yet
    clock.t = T0 + 600
    e.record_appraisal(apology(), turn_id="t2", counterpart="製作人", platform="api_server")
    b2 = e.state_block()
    assert "轉變：剛才" in b2 and len(b2.splitlines()) <= 10
    assert all("0." not in ln for ln in b2.splitlines())  # words, not numbers


def test_the_cap_counts_state_lines_and_never_drops_the_principle(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "cap", clock)
    clock.t = T0 + 60
    e.record_appraisal(broken_promise(), turn_id="t1", counterpart="製作人", platform="api_server")
    e.state_block()                                                      # remembers the dominant feeling for the transition line
    clock.t = T0 + 600
    e.record_appraisal(apology(), turn_id="t2", counterpart="製作人", platform="api_server")
    full = e.state_block().splitlines()
    assert "轉變：" in "".join(full) and full[-1].startswith("原則：") and len(full) <= 10
    e.cfg.setdefault("expression", {})["max_lines"] = 3                  # squeeze: the transition goes first, 原則 stays last
    e.last_block = {"dominant": "disappointment", "word": "有點失望", "at": clock.t, "mood": "", "text": "", "counterpart": "製作人", "strategy": ""}
    short = e.state_block().splitlines()
    assert short[0].startswith("【她現在】") and short[1].startswith("現在：") and short[-1].startswith("原則：")
    assert not any(x.startswith("轉變：") or x.startswith("心裡：") for x in short)


def test_apology_repairs_at_least_half(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "r", clock)
    clock.t = T0 + 60
    e.record_appraisal(broken_promise(), turn_id="t1", counterpart="製作人", platform="api_server")
    hurt_before = next(i["intensity"] for i in e.active() if i["type"] == "hurt")
    clock.t = T0 + 1800
    e.record_appraisal(apology(), turn_id="t2", counterpart="製作人", platform="api_server")
    st = e.status()
    hurt_after = next((i["intensity"] for i in st["instances"] if i["type"] == "hurt"), 0.0)
    assert hurt_after <= 0.5 * hurt_before
    assert any(i["type"] == "relief" for i in st["instances"])


def test_loops_show_as_things_on_her_mind(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "l", clock)
    clock.t = T0 + 60
    data = {"events": [], "loops": {"new": [{"what": "「製作人」週五的面試", "origin": "counterpart_said", "cue_time": "2026-09-25T19:00",
                                             "importance": 0.8}], "closed": []}, "farewell": False}
    e.record_appraisal(data, turn_id="t1", counterpart="製作人", platform="api_server")
    assert "掛念：「製作人」週五的面試" in e.state_block()
    lid = next(iter(e.loops))
    clock.t = T0 + 120
    e.record_appraisal({"events": [], "loops": {"new": [], "closed": [lid]}, "farewell": False}, turn_id="t2",
                       counterpart="製作人", platform="api_server")
    assert "掛念" not in e.state_block() and e.loops[lid]["state"] == "closed"


def test_second_process_is_read_only(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "o", clock)
    assert e.acquire_owner(111)
    other = Engine(tmp_path, "test", cfg(), db_path=tmp_path / "o.db", now_fn=clock, llm=None)
    assert not other.acquire_owner(222)
    clock.t = T0 + 60
    assert other.acquire_owner(222)  # the heartbeat went stale: ownership moves


def test_failed_appraisal_changes_nothing(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "f", clock)
    before = rounded(e.status())
    e.record_appraisal(None, raw="garbage", error="ValueError: no JSON", turn_id="t1", counterpart="製作人", platform="api_server")
    assert rounded(e.status()) == before
