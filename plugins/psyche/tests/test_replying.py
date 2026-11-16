"""Not every message gets a reply (when-to-reply.md): markers, the Telegram emoji set, the lean, the 回不回 line."""
from psyche import events as EV
from psyche import replying as RP
from psyche.engine import MAIN

from test_engine import T0, Clock, make


def test_whole_markers_are_silence_and_words_are_not():
    for t in ("NO_REPLY", " no_reply ", "[SILENT]", "NO REPLY", "*NO_REPLY*"):
        assert RP.parse(t)[0] == "silent", t
    assert RP.parse("好啦，晚安")[0] == "text"
    assert RP.parse("我才不要 NO_REPLY 咧")[0] == "text"            # mixed: the words go out, the marker is dropped
    words = RP.parse("我才不要 NO_REPLY 咧")[2]
    assert "NO_REPLY" not in words and words.startswith("我才不要") and words.endswith("咧")


def test_a_reaction_is_one_emoji_telegram_accepts():
    assert RP.parse("[REACT 🤣]") == ("react", "🤣", "")
    assert RP.parse("[REACT 😂]") == ("react", "🤣", "")              # mapped to the nearest allowed one
    assert RP.parse("[react 👍🏻]") == ("react", "👍", "")             # skin tone dropped
    assert RP.parse("[REACT ❤️]") == ("react", "❤", "")               # variation selector dropped
    assert RP.parse("[REACT 🦖]")[0] == "silent"                      # nothing close: silence, never the raw marker
    kind, emoji, words = RP.parse("[REACT 🤣] 笑死")
    assert kind == "text" and words == "笑死" and emoji is None


def test_event_turn_silence_accepts_the_marker():
    assert EV.is_silence("NO_REPLY") and EV.is_silence("（沉默）") and not EV.is_silence("欸，我剛畫完")


def test_the_lean_moves_with_the_moment_not_a_per_character_value():
    base = dict(extraversion=0.55, agreeableness=0.65, busy=False, said_wait=False, low_energy=False, pleasure=0.0,
                want_talk=0.0, bond=0.3, worn_out=False)
    calm = RP.tendency(**base)
    assert -0.3 < calm < 0.3                                         # an ordinary moment: no hint, the rule alone
    assert RP.tendency(**dict(base, busy=True, said_wait=True)) <= -0.3
    assert RP.tendency(**dict(base, low_energy=True, worn_out=True)) <= -0.3
    assert RP.tendency(**dict(base, extraversion=0.9, want_talk=0.8, pleasure=0.5, bond=0.7)) >= 0.3
    assert RP.tendency(**dict(base, extraversion=0.2, agreeableness=0.3)) < calm


def test_the_line_names_both_ways_and_the_streak_forces_words():
    line = RP.line(pr="她", term="哥", lean=-0.5, silent_streak=0)
    assert line.startswith("回不回：") and "NO_REPLY" in line and "[REACT" in line and "一定要用文字回" in line and "多半不回" in line
    assert "想聊" in RP.line(pr="他", term="哥", lean=0.5, silent_streak=0)
    assert "這則有內容就回" in RP.line(pr="她", term="哥", lean=-0.9, silent_streak=2)
    assert RP.silent_streak([("a", "好"), ("b", "（沒回）"), ("c", "（沒回字，按了 🤣）")]) == 2


def test_state_block_carries_the_rule_for_you_only_and_not_on_her_event_turn(tmp_path):
    e = make(tmp_path, "r", Clock(T0))
    assert "回不回：" in e.state_block()
    assert "回不回：" not in e.state_block(reply_rule=False)


def test_a_silent_turn_is_recorded_as_one(tmp_path):
    e = make(tmp_path, "t", Clock(T0))
    e.on_turn("好啦 晚安", RP.recent_answer("NO_REPLY", "react", "🥰"), turn_id="x1", platform="telegram", session_id="s1",
              counterpart=MAIN, answer="react", reaction="🥰")
    row = e.conn.execute("SELECT payload FROM events WHERE kind='turn' ORDER BY id DESC LIMIT 1").fetchone()
    assert '"answer": "react"' in row[0] and "🥰" in row[0]
    assert e.recent[-1][1].startswith("（沒回")
