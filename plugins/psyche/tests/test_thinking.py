"""The thinking module: meters with defaults, the one optional 想法 line, reading care, the rumination knob."""
import copy

from psyche import config, thinking
from psyche.tests.test_engine import Clock, T0, make


def quiet(**over):
    base = dict(energy=0.7, fatigue=0.1, arousal=0.4, pleasure=0.1, anxiety=0.3, hurt_gate=0.0, bond=0.4, open_hurt=False)
    base.update(over)
    return base


def test_meters_default_from_big_five_and_accept_overrides():
    c = copy.deepcopy(config.DEFAULTS)
    m = thinking.meters(c)
    assert m["rationality"] == c["character"]["big5"]["conscientiousness"]
    assert m["promotion"] == c["character"]["big5"]["extraversion"] and m["prevention"] == c["character"]["big5"]["neuroticism"]
    assert m["experientiality"] == 0.5 and m["maximizing"] == 0.5
    c["thinking"] = {"rationality": 0.9, "maximizing": "0.1", "promotion": None}
    m = thinking.meters(c)
    assert m["rationality"] == 0.9 and m["maximizing"] == 0.1 and m["promotion"] == c["character"]["big5"]["extraversion"]


def test_no_line_on_an_ordinary_turn():
    m = thinking.meters({"thinking": {"rationality": 0.5, "experientiality": 0.5, "promotion": 0.5, "prevention": 0.5, "maximizing": 0.5}})
    assert thinking.line(m=m, **quiet()) is None


def test_lines_fire_in_priority_order():
    m = thinking.meters({"thinking": {"rationality": 0.8, "experientiality": 0.3, "promotion": 0.3, "prevention": 0.8, "maximizing": 0.3}})
    assert thinking.line(m=m, **quiet(anxiety=0.7, open_hurt=True)) == "想法：今天特別容易往壞處想"
    assert thinking.line(m=m, **quiet(energy=0.2)) == "想法：今天沒力氣想，會先回再想"          # think-first, no energy
    assert thinking.line(m=m, **quiet(pleasure=0.6)) == "想法：心情好，先看能變成什麼"           # prevention lifted by mood
    m2 = thinking.meters({"thinking": {"rationality": 0.2, "experientiality": 0.8, "promotion": 0.8, "prevention": 0.2, "maximizing": 0.8}})
    assert thinking.line(m=m2, **quiet(hurt_gate=0.3)) == "想法：這件事不小，會想一下再回"      # reply-first, heavy matter
    assert thinking.line(m=m2, **quiet(energy=0.2)) == "想法：今天沒力氣猜，直接問對方"           # feel-first, no energy → ask
    assert thinking.line(m=m2, **quiet(pleasure=-0.5)) == "想法：這題先看會不會出錯"             # promotion dropped by mood
    assert thinking.line(m=m2, **quiet(arousal=0.8)) == "想法：會問清楚再答，不想隨便"           # maximizer with energy


def test_reading_care_drops_with_closeness_and_fatigue():
    assert thinking.reading_care(rationality=0.5, bond=0.0, fatigue=0.0, stakes=0.0) == 0.65
    close_tired = thinking.reading_care(rationality=0.2, bond=0.9, fatigue=0.8, stakes=0.0)
    assert close_tired < 0.25
    m = thinking.meters({"thinking": {"rationality": 0.2, "experientiality": 0.5, "promotion": 0.5, "prevention": 0.5, "maximizing": 0.5}})
    assert thinking.line(m=m, **quiet(bond=0.9, fatigue=0.8, energy=0.7)) == "想法：懶得猜對方的意思，直接當對方懂"
    m = thinking.meters({"thinking": {"rationality": 0.9, "experientiality": 0.5, "promotion": 0.5, "prevention": 0.5, "maximizing": 0.5}})
    assert thinking.line(m=m, **quiet(bond=0.0, fatigue=0.0, hurt_gate=0.3)) == "想法：會多想一下對方是什麼意思"


def test_state_block_carries_the_line_only_when_it_fires(tmp_path):
    clock = Clock(T0)
    e = make(tmp_path, "think", clock)
    assert "想法：" not in e.state_block()                      # a quiet start: no line
    e.cfg["thinking"] = {"rationality": 0.9, "experientiality": 0.2, "promotion": 0.3, "prevention": 0.7, "maximizing": 0.3}
    e.energy = 0.2                                              # no energy + think-first
    b = e.state_block()
    assert "想法：今天沒力氣想，會先回再想" in b
    assert len(b.splitlines()) <= 9


def test_rumination_knob_overrides_neuroticism():
    c = copy.deepcopy(config.DEFAULTS)
    from psyche.engine import Engine
    e = Engine.__new__(Engine)
    e.cfg = c
    assert e._rumination_coef() == c["character"]["big5"]["neuroticism"]
    c["character"]["rumination"] = 0.05
    assert e._rumination_coef() == 0.05
