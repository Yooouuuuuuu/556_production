"""The five conversation mechanisms (0.8.9; inner-life.md §24, the 2026-10-14 brief part 2): the disclosure depth
rendered and capped, trust uncertainty into 玩笑／反話, the mood's pleasure into 直說 and the length hint, the
withheld register (what she swallowed comes back, pulls her, and is said when the pair is deep enough)."""
import copy

from psyche import appraisal, config, relation as RL, urge as U
from psyche.engine import MAIN
from psyche.tests.test_relation import Clock, T0, appraise, cfg, ev, make, run

CHAR = config.DEFAULTS["character"]


def rel_with(**over):
    r = RL.fresh({}, CHAR)
    r.update(over)
    return r


def strat(dominant, **kw):
    kw.setdefault("rel", rel_with(bond=0.6))
    kw.setdefault("character", CHAR)
    kw.setdefault("gate", 0.0)
    kw.setdefault("other_tired", False)
    kw.setdefault("rng_u", 0.99)
    kw.setdefault("negative_types", {"sad", "hurt", "disappointed", "annoyed"})
    return RL.strategy(dominant, **kw)


SAD = {"type": "sad", "intensity": 0.5}


# --- 2.5 trust uncertainty -------------------------------------------------------------------------------------------

def test_trust_uncertainty_is_neutral_at_the_default_prior_and_settles_with_evidence():
    r = rel_with()
    assert abs(RL.trust_uncertainty(r) - RL.U_DEFAULT) < 1e-9          # (2, 1): the neutral point
    assert RL.trust_uncertainty(rel_with(trust=[1.0, 1.0])) == 1.0       # the flat prior: no idea at all
    for _ in range(4):                                                   # four promises kept
        RL.turn(r, q=0.5, minutes=1.0, event_kind="promise_kept", ppr=None, she_disclosed=False, other_disclosed=False, t=T0)
    assert RL.trust_uncertainty(r) < 0.3


def test_uncertainty_turns_a_mildly_humorous_character_to_jokes_and_evidence_turns_her_direct():
    ch = {**CHAR, "humor_coping": 0.55, "expressiveness": 0.7}
    assert strat(SAD, character=ch)[0] == "direct"                                   # at the default prior: 0.55 < 0.6
    assert strat(SAD, character=ch, uncertainty=1.0)[0] == "humor"                   # she cannot tell how he takes things
    ch2 = {**CHAR, "humor_coping": 0.65, "expressiveness": 0.7}
    assert strat(SAD, character=ch2)[0] == "humor"
    assert strat(SAD, character=ch2, uncertainty=0.1)[0] == "direct"                 # settled: she just says it


# --- 2.1 pleasure ----------------------------------------------------------------------------------------------------

def test_pleasure_moves_the_borderline_between_direct_and_reserved_and_names_the_tone():
    shy = {**CHAR, "expressiveness": 0.45}
    assert strat(None, character=shy)[1][0] == "收斂，點到為止"
    assert strat(None, character=shy, pleasure=0.6)[1][0] == "直說，話可以隨便一點"     # a good mood opens her up
    open_ = {**CHAR, "expressiveness": 0.55}
    assert strat(None, character=open_)[1][0] == "直說"
    assert strat(None, character=open_, pleasure=-0.5)[1][0] == "收斂，點到為止"      # a bad mood closes her
    frank = {**CHAR, "expressiveness": 0.8}
    assert strat(None, character=frank, pleasure=-0.5)[1][0] == "直說，但客氣一點"
    assert strat(None, character=frank, pleasure=0.1)[1][0] == "直說"


def test_pleasure_changes_the_length_hint(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "len", clock)
    e.energy, e.fatigue = 0.7, 0.1
    e.affect["ar"] = 0.4
    e.mood = (0.7, 0.2, 0.0)
    assert "可以多說一點" in e.state_block()
    e.mood = (-0.6, 0.2, 0.0)
    assert "話少一點" in e.state_block()
    e.mood = (0.0, 0.2, 0.0)
    b = e.state_block()
    assert "可以多說一點" not in b and "話少一點" not in b


# --- 2.4 depth -------------------------------------------------------------------------------------------------------

def test_depth_follows_the_bond_reciprocity_and_avoidance():
    r = rel_with(bond=0.4)
    RL.tick(r, 1 / 60, config.DEFAULTS["relation"])
    assert RL.depth_now(r, T0) == 2                               # 看法
    r["reciprocal_until"] = T0 + 3600                             # he just opened up: one layer more for a day
    assert RL.depth_now(r, T0) == 3
    r["avoidance"] = 0.7                                          # avoidance high: one layer less
    assert RL.depth_now(r, T0) == 2
    assert RL.depth_words(4) is None and RL.depth_words(1).startswith("自己的事先不多講")


def test_the_state_block_caps_what_she_opens_up_about_until_the_pair_is_close(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "new", clock)                              # a stranger: bond 0
    run(e, clock, 0.05)
    assert "聊喜好跟日常就好" in e.state_block()
    c = cfg()
    c["relationships"] = {MAIN: {"bond": 0.6, "hours": 150}}      # 很熟: feelings, not the softest part
    e2 = make(tmp_path, "close", clock, c)
    run(e2, clock, 0.05)
    assert "可以講感受，最軟的那塊先留著" in e2.state_block()
    c = cfg()
    c["relationships"] = {MAIN: {"bond": 0.85, "hours": 300}}     # 很親近: nothing to cap
    e3 = make(tmp_path, "deep", clock, c)
    run(e3, clock, 0.05)
    assert "先留著" not in e3.state_block() and "日常就好" not in e3.state_block()


# --- 2.3 the withheld register ----------------------------------------------------------------------------------------

WH = {"what": "其實很在意「製作人」忘了她的生日", "importance": 0.7}


def test_withheld_is_held_until_the_pair_is_deep_enough_then_said(tmp_path):
    clock = Clock(T0)
    c = cfg()
    c["relationships"] = {MAIN: {"bond": 0.4, "hours": 70}}        # 朋友: depth 2 — feelings stay unsaid
    e = make(tmp_path, "wh", clock, c)
    run(e, clock, 0.05)
    e.record_appraisal({"events": [ev("small_talk", R=0.1)], "loops": {"new": [], "closed": []},
                        "withheld": {"new": [WH], "said": []}, "farewell": False}, turn_id="t1", counterpart=MAIN, platform="api_server")
    assert len(e.withheld) == 1 and e.withheld[0]["counterpart"] == MAIN and e.withheld[0]["importance"] == 0.7
    assert "還沒跟" not in e.state_block()                         # held: not in her prompt yet
    kinds = [r[0] for r in e.conn.execute("SELECT kind FROM events").fetchall()]
    assert "withheld_opened" in kinds
    # the same thing swallowed again weighs more, no second entry
    e.record_appraisal({"events": [], "loops": {"new": [], "closed": []},
                        "withheld": {"new": [{"what": "很在意製作人忘了生日", "importance": 0.5}], "said": []}, "farewell": False},
                       turn_id="t2", counterpart=MAIN, platform="api_server")
    assert len(e.withheld) == 1 and e.withheld[0]["importance"] > 0.7
    # the pair reaches the feelings layer: now it sits with what is on her mind, and the urge can carry it
    e.rel[MAIN]["bond"] = 0.6
    RL.tick(e.rel[MAIN], 1 / 60, c["relation"])
    assert "有件事還沒跟製作人說（其實很在意" in e.state_block()
    assert e._unlocked_withheld(MAIN, clock.t)
    # she says it in a reply: the appraisal reports the id, the register empties
    wid = e.withheld[0]["id"]
    e.record_appraisal({"events": [ev("disclosed_personal", she_disclosed=True, R=0.5)], "loops": {"new": [], "closed": []},
                        "withheld": {"new": [], "said": [wid]}, "farewell": False}, turn_id="t3", counterpart=MAIN, platform="api_server")
    assert e.withheld == []
    assert "還沒跟" not in e.state_block()


def test_a_heavy_withheld_thing_comes_out_even_with_a_stranger(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "heavy", clock)
    e.record_appraisal({"events": [], "loops": {"new": [], "closed": []},
                        "withheld": {"new": [{"what": "其實那句話讓她很受傷", "importance": 0.95}], "said": []}, "farewell": False},
                       turn_id="t1", counterpart=MAIN, platform="api_server")
    assert "有件事還沒跟製作人說" in e.state_block()


def test_withheld_fades_when_she_does_not_ruminate_and_grows_when_she_does(tmp_path):
    for rum, name in ((0.0, "calm"), (1.0, "brooding")):
        clock = Clock(T0)
        c = cfg(character={**CHAR, "rumination": rum})
        e = make(tmp_path, name, clock, c)
        e.record_appraisal({"events": [], "loops": {"new": [], "closed": []}, "withheld": {"new": [WH], "said": []}, "farewell": False},
                           turn_id="t1", counterpart=MAIN, platform="api_server")
        run(e, clock, 72)
        if rum == 0.0:
            assert len(e.withheld) == 1 and abs(e.withheld[0]["importance"] - 0.35) < 0.02   # a three-day half-life
            assert e.withheld[0]["rum"] == 0
            run(e, clock, 24 * 7)
            assert e.withheld == []                                                            # gone below a tenth
        else:
            rums = e.conn.execute("SELECT COUNT(*) FROM events WHERE kind='rumination' AND payload LIKE '%withheld%'").fetchone()[0]
            assert rums >= 1
            fired = e.conn.execute("SELECT COUNT(*) FROM events WHERE kind='proactive_fired' AND payload LIKE '%unsaid%'").fetchone()[0]
            # it came back until it had to come out: she reached out with it (and it left the register), or it is still
            # growing on the register — either way it did not simply fade
            assert (fired and e.withheld == []) or (e.withheld and e.withheld[0]["rum"] >= 1 and e.withheld[0]["importance"] > 0.35)


def test_withheld_pulls_the_urge_and_is_an_occasion_once_unlocked():
    needs = {"affiliation_person": 0.3, "novelty": 0.0}
    base = dict(needs=needs, phase="ok", share_backlog=[], hurt=0.0, anxiety=0.3, avoidance=0.3, clinginess_eff=0.4)
    assert U.willingness(**base, withheld=[WH]) > U.willingness(**base)
    O, kind, payload = U.occasion(due_loops=[], share_backlog=[{"what": "咖啡很好喝", "importance": 0.4}], care_loops=[], phase="ok",
                                  needs=needs, floor=0.1, unsaid=[WH])
    assert kind == "unsaid" and payload is WH and abs(O - 0.85) < 1e-9     # before a share
    O2, kind2, _ = U.occasion(due_loops=[], share_backlog=[{"what": "咖啡很好喝", "importance": 0.4}], care_loops=[], phase="ok",
                              needs=needs, floor=0.1, unsaid=[])
    assert kind2 == "share" and O2 < O


def test_an_unsaid_thing_sent_leaves_the_register(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "sent", clock)
    e.withheld = [{"id": "wh_1", "what": WH["what"], "at": clock.t, "counterpart": MAIN, "importance": 0.9, "turn_id": "t1", "rum": 0}]
    e._record_and_apply("proactive_fired", {"kind": "unsaid", "what": WH["what"], "loop": None, "entry": None, "counterpart": MAIN, "W": 1, "O": 1},
                        counterpart=MAIN)
    assert e.withheld == []


def test_withheld_survives_a_snapshot(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "snap", clock)
    e.record_appraisal({"events": [], "loops": {"new": [], "closed": []}, "withheld": {"new": [WH], "said": []}, "farewell": False},
                       turn_id="t1", counterpart=MAIN, platform="api_server")
    e.snapshot()
    s = e.snapshot_state()
    e.withheld = []
    e._restore(copy.deepcopy(s))
    assert len(e.withheld) == 1 and e.withheld[0]["what"] == WH["what"]
    assert e.status()["withheld"][0]["what"] == WH["what"]


def test_appraisal_normalizes_the_withheld_field_and_lists_what_is_held_back():
    d = appraisal.normalize({"events": [], "withheld": {"new": [{"what": " 其實很在意 ", "importance": 3}, "junk", {"what": ""}], "said": ["wh_1", None]}})
    assert d["withheld"] == {"new": [{"what": "其實很在意", "importance": 1.0}], "said": ["wh_1"]}
    assert appraisal.normalize({"events": []})["withheld"] == {"new": [], "said": []}
    assert appraisal.normalize({"events": [], "withheld": "nope"})["withheld"] == {"new": [], "said": []}
    u = appraisal.build_user("製作人", [], [], [], "嗨", "嗯", withheld=[{"id": "wh_1", "what": "其實很在意"}])
    assert "HELD BACK" in u and "wh_1: 其實很在意" in u
    assert "withheld" in appraisal.SYSTEM and "{pronoun}" in appraisal.SYSTEM
    assert "withheld.new" in appraisal.SYSTEM.format(term="x", today="y", kinds="k", max_events=3, pronoun="她")
