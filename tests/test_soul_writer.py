"""Unit tests for tools/soul_writer.py — the deterministic parts (reading describe/, assembling the six-part
SOUL, seeds with dates, people files, psyche.json, the checks, the lock) with a scripted LLM.

    D:\\dev\\KeepsakeDB\\.venv\\Scripts\\python -m pytest tests/test_soul_writer.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import soul_writer as sw  # noqa: E402
from keepsakedb.llms import ScriptedLLM  # noqa: E402


def _j(d: dict) -> str:
    return "```json\n" + json.dumps(d, ensure_ascii=False) + "\n```"


STRUCTURE = {
    "events": [{"at": "2023-11", "text": "角色甲的圖第一次被轉貼", "left": "你被看見的時候會先躲起來。", "tags": ["comic"]},
               {"at": "2026-09-02", "text": "角色甲在畫畫課認識你", "left": "你記得第一個問你貓是誰的人。", "tags": ["history"]}],
    "seeds": [{"text": "你在畫畫課坐角色甲旁邊", "tags": ["you"]}, {"text": "角色甲在畫畫課認識你", "tags": ["dup"]}],
    "stances": ["斷更不是罪"], "refusals": ["不畫免費的 logo"], "tensions": ["嘴上說隨便畫，心裡在意"],
    "cares_about": ["畫的東西有沒有被當真", "答應的事有沒有做到"], "vague": [],
    "closeness": "還不算熟", "closeness_why": "畫畫課認識一個多月",
}
THINKING = {"big5": {"openness": 0.7, "conscientiousness": 0.4, "extraversion": 0.35, "agreeableness": 0.55, "neuroticism": 0.6},
            "constants": {"self_esteem_stability": 0.4, "expressiveness": 0.3, "humor_coping": 0.6, "clinginess_cap": 0.5,
                          "tsundere_tendency": 0.5, "assertiveness": 0.4, "chronotype": 0.9},
            "thinking": {"rationality": 0.3, "experientiality": 0.7, "promotion": 0.4, "prevention": 0.7, "maximizing": 0.3},
            "choices": {"medium_primary": "imagery", "medium_secondary": None, "first_look": "people", "contradiction": "hold_both", "cause": "situation"},
            "evidence": {"rationality": "先回再想"}}
VOICE = {"expression": "你的訊息很短，常常一句拆兩三則。", "catchphrases": ["欸", "吼", "啦"], "never_say": ["我是認真的"],
         "lines_yes": ["欸 你那個藍色太乾淨了", "先這樣 我要去補貨", "吼 不要講", "大夜最好的是沒人說早安", "貓不會問我在幹嘛"],
         "lines_no": ["謝謝你的肯定！", "請問有什麼可以幫你的嗎", "我會努力的", "親愛的你好嗎", "加油喔"]}
REACTIONS = {"reactions": "生氣的時候你會變得很有禮貌。", "fallback": [{"when": "對方要你做助理的事", "she": "你會轉去講貓"}]}
PARTS = {"part1": "你是角色甲，二十七歲，在圖書館上班。你被看見的時候會先躲起來。", "part2": "- 喜歡無糖綠\n- 受不了「畫畫很療癒吧」",
         "thinking": "想事情的時候你腦子裡是畫面。你先回再想。", "judging": "- 遇到有預算的人，就不送免費的圖。",
         "people": {"你": "她在畫畫課認識你，叫你的名字。", "小文": "店長，裝沒看到她在畫圖。"}}
INTAKE = {"enough": True, "missing": []}
VERIFY = {"medium_primary": "imagery", "first_look": "people", "contradiction": "hold_both", "cause": "situation",
          "rationality": "low", "experientiality": "high", "promotion": "mid", "prevention": "high", "maximizing": "low", "note": "從先回再想判斷"}


def _make_char(tmp: Path, monkeypatch) -> Path:
    monkeypatch.setattr(sw, "CHARS", tmp)
    d = tmp / "t1"
    (d / "describe").mkdir(parents=True)
    for stem in sw.DESCRIBE:
        (d / "describe" / f"{stem}.md").write_text(f"# x\n<!-- 提示 -->\n{stem} 的內容\n", encoding="utf-8")
    sw.write_json(d / "companion.json", {"display_name": "角色甲", "avatar_model": "hiyori/Hiyori.model3.json"})
    prof = json.loads((sw.TPL / "profile.json").read_text(encoding="utf-8"))
    sw.write_json(d / "profile.json", prof)
    return d


def test_read_describe_strips_prompts(tmp_path, monkeypatch):
    d = _make_char(tmp_path, monkeypatch)
    parts = sw.read_describe(d)
    assert parts["01-她是誰"] == "01-她是誰 的內容"
    assert "提示" not in sw.describe_text(parts)
    (d / "describe" / "10-其他.md").write_text("# 其他\n<!-- 只有提示 -->\n", encoding="utf-8")
    assert "（未填）" in sw.describe_text(sw.read_describe(d))


def test_full_pipeline_with_scripted_llm(tmp_path, monkeypatch):
    d = _make_char(tmp_path, monkeypatch)
    llm = ScriptedLLM([_j(INTAKE), _j(STRUCTURE), _j(THINKING), _j(VOICE), _j(REACTIONS), _j(PARTS), _j(VERIFY)])
    llm.model = "scripted"
    sw.phase_intake(llm, d)
    sw.phase_structure(llm, d)
    sw.phase_thinking(llm, d, accept=True)
    prof = sw.read_json(d / "profile.json")
    assert prof["thinking"]["rationality"] == 0.3 and prof["choices"]["medium_primary"] == "imagery"
    assert prof["proposed"]["evidence"]["rationality"] == "先回再想"
    sw.phase_voice(llm, d)
    sw.phase_reactions(llm, d)
    sw.phase_parts(llm, d)
    found = sw.phase_assemble(d, force=True, model="scripted")
    soul = (d / "SOUL.md").read_text(encoding="utf-8")
    # six-part order
    idx = [soul.index(h) for h in ("# 角色甲", "## 喜歡與不喜歡", "## 怎麼聽、怎麼想、怎麼回", "## 怎麼判斷、怎麼決定", "## 說話的方式", "## 遇到事情的時候", "## 誰在跟你說話")]
    assert idx == sorted(idx)
    assert "你會這樣說：" in soul and "欸 你那個藍色太乾淨了" in soul
    assert "| 對方要你做助理的事 | 你會轉去講貓 |" in soul
    assert sw.GUARDRAILS[0] in soul
    # the scripted text is short, so the only finding is the size
    assert found and all("太短" in f for f in found)
    # seeds: events first with the date in the text and the `at` field; duplicates dropped
    rows = [json.loads(ln) for ln in (d / "seeds.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["at"] == "2023-11" and rows[0]["text"].startswith("2023 年 11 月，")
    assert rows[0]["tags"][0] == "timeline" and "comic" in rows[0]["tags"]   # events are the pinned timeline
    assert rows[1]["at"] == "2026-09-02"
    texts = [r["text"] for r in rows]
    assert len(texts) == len(set(texts)) and any(t == "你在畫畫課坐角色甲旁邊" for t in texts)
    # people
    you = (d / "people" / "你.md").read_text(encoding="utf-8")
    assert you.startswith("# 你\n- 名字：（尚未設定）") and "叫你的名字" in you
    assert (d / "people" / "小文.md").exists()
    # psyche.json carries the numbers and the recorded choices; cares_about from the structure
    ps = sw.read_json(d / "psyche.json")
    assert ps["character"]["big5"]["neuroticism"] == 0.6 and ps["character"]["chronotype"] == 0.9 and ps["character"]["pronoun"] == "她"
    assert ps["thinking"]["prevention"] == 0.7 and ps["thinking_choices"]["first_look"] == "people"
    assert ps["cares_about"][0] == "畫的東西有沒有被當真"
    assert ps["relationships"]["你"] == {"bond": 0.2, "hours": 30.0}      # the structure's closeness band → the prior
    prof = sw.read_json(d / "profile.json")
    prof["closeness"] = "很親近"                                            # profile.json overrides the band
    sw.write_json(d / "profile.json", prof)
    assert sw.build_psyche(d)["relationships"]["你"]["bond"] == 0.8
    # lock + status
    lock = sw.read_json(d / "soul.lock.json")
    assert lock["version"] == sw.VERSION and lock["inputs"]["profile.json"] and lock["outputs"]["SOUL.md"]
    # verify compares bands and choices
    sw.phase_verify(llm, d)
    v = sw.read_json(d / "build" / "verify.json")
    assert v["matches"] == v["total"] == 9


def test_timeline_and_influences_live_in_the_soul():
    st = {"events": [{"at": "2023-11", "text": "角色甲的圖第一次被轉貼"}, {"text": "沒有日期的事"}, {"at": "2019", "text": "搬到新的城市"}],
          "influences": [{"text": "高中的美術老師，說你的線條有脾氣"}]}
    out = "\n".join(sw.timeline_sections(st))
    assert "## 時間線" in out and out.index("2019 年，搬到新的城市") < out.index("2023 年 11 月，角色甲的圖第一次被轉貼") < out.index("沒有日期的事")
    assert "## 影響過你的人與事" in out and "美術老師" in out
    assert sw.timeline_sections({}) == []
    soul = ("# x\n\n你是她。\n\n" + out + "\n## 喜歡與不喜歡\n- x\n\n## 怎麼聽、怎麼想、怎麼回\n- y\n\n## 怎麼判斷、怎麼決定\n- z\n\n"
            "## 說話的方式\n" + "\n".join(sw.GUARDRAILS) + "\n\n## 遇到事情的時候\n- w\n\n## 誰在跟你說話\n" + sw.WHO_LINE)
    found = sw.checks(soul)
    assert not any("阿拉伯數字" in f for f in found)        # the years in 時間線 are the point
    assert any("太短" in f for f in found)                    # and they do not count toward the prose budget


def test_checks_catch_theory_words_digits_and_missing_sections():
    soul = "# x\n\n她的神經質很高，參數 0.7。\n\n## 說話的方式\n" + "\n".join(sw.GUARDRAILS)
    found = sw.checks(soul)
    assert any("神經質" in f for f in found) and any("參數" in f for f in found)
    assert any("阿拉伯數字" in f for f in found)
    assert any("缺少段落 ## 喜歡與不喜歡" in f for f in found)
    assert any("太短" in f for f in found)
    # the fixed guardrail bullets are exempt even though they say 程式 / 引擎
    assert not any("引擎" in f for f in found)


def test_accept_proposals_fills_only_nulls():
    prof = {"big5": {"openness": 0.9}, "constants": {}, "thinking": {"rationality": None}, "choices": {},
            "proposed": {"big5": {"openness": 0.2, "neuroticism": 0.5}, "thinking": {"rationality": 0.3}, "choices": {"cause": "person"}}}
    n = sw.accept_proposals(prof)
    assert prof["big5"]["openness"] == 0.9 and prof["big5"]["neuroticism"] == 0.5
    assert prof["thinking"]["rationality"] == 0.3 and prof["choices"]["cause"] == "person" and n == 3


def test_date_zh_and_band():
    assert sw._date_zh("2024") == "2024 年" and sw._date_zh("2024-03") == "2024 年 3 月" and sw._date_zh("2024-03-09") == "2024 年 3 月 9 日"
    assert sw._date_zh("sometime") == ""
    assert sw.band(0.1) == "偏低" and sw.band(0.5) == "中等" and sw.band(0.9) == "偏高" and sw.band(None) == "沒說"


def test_assemble_never_overwrites_a_hand_written_soul(tmp_path, monkeypatch):
    d = _make_char(tmp_path, monkeypatch)
    for name, data in (('structure', STRUCTURE), ('voice', VOICE), ('reactions', REACTIONS), ('parts', PARTS)):
        sw.write_json(d / 'build' / f'{name}.json', data)
    (d / 'SOUL.md').write_text('# 手寫的' + chr(10), encoding='utf-8')
    found = sw.phase_assemble(d, force=False)
    assert found and '手寫' in found[0]
    assert (d / 'SOUL.md').read_text(encoding='utf-8') == '# 手寫的' + chr(10)
    sw.phase_assemble(d, force=True)
    assert (d / 'SOUL.md').read_text(encoding='utf-8').startswith('# 角色甲')


def test_checks_allow_words_the_author_used():
    soul = '# x' + chr(10) * 2 + '你不喜歡 AI，覺得它比你聰明。' + chr(10) * 2 + '## 說話的方式' + chr(10) + chr(10).join(sw.GUARDRAILS)
    assert any('AI' in f for f in sw.checks(soul))
    assert not any('AI' in f for f in sw.checks(soul, allowed='不喜歡AI 因為感覺比他聰明'))


def test_simple_path_compiles_from_sliders_and_three_boxes(tmp_path, monkeypatch):
    d = _make_char(tmp_path, monkeypatch)
    prof = sw.read_json(d / "profile.json")
    prof["thinking"] = {"rationality": 0.2, "experientiality": 0.8, "promotion": 0.5, "prevention": 0.7, "maximizing": 0.3}
    prof["choices"] = {"medium_primary": "imagery", "medium_secondary": None, "first_look": "people", "contradiction": "hold_both", "cause": "situation"}
    prof["constants"] = {"self_esteem_stability": 0.5, "expressiveness": 0.3, "humor_coping": 0.7, "clinginess_cap": 0.5, "tsundere_tendency": 0.2, "assertiveness": 0.7, "chronotype": 0.5}
    prof["simple"] = {"who": "你是角色甲，在圖書館上班，偷畫貓。", "talk": "訊息很短，常常一句拆兩三則。", "refuses": "不畫免費的 logo\n不接客服工作"}
    prof["closeness"] = "朋友"
    sw.write_json(d / "profile.json", prof)
    found = sw.phase_simple(d)
    assert not [x for x in found if x.startswith(("太短", "太長"))]
    soul = (d / "SOUL.md").read_text(encoding="utf-8")
    assert soul.startswith("# 角色甲\n\n你是角色甲，在圖書館上班，偷畫貓。")
    for h in ("## 喜歡與不喜歡", "## 怎麼聽、怎麼想、怎麼回", "## 怎麼判斷、怎麼決定", "## 說話的方式", "## 遇到事情的時候", "## 誰在跟你說話"):
        assert h in soul
    assert "你先回再想" in soul and "你憑感覺" in soul and "想事情的時候你腦子裡是畫面" in soul and "第一眼看這件事跟誰有關" in soul
    assert "- 不畫免費的 logo" in soul and "- 不接客服工作" in soul and "訊息很短" in soul
    assert "心裡的事你不太說出來" in soul and "不開心的事你用玩笑帶過" in soul and "不同意的時候你直說" in soul
    assert "<think>" not in soul                         # the scratch is off by default
    assert (d / "people" / "你.md").exists() and (d / "seeds.jsonl").exists()
    ps = sw.read_json(d / "psyche.json")
    assert ps["thinking"]["prevention"] == 0.7 and ps["relationships"]["你"]["bond"] == 0.4
    assert sw.read_json(d / "soul.lock.json")["model"] == "simple"
    # the simple path never overwrites a hand-written SOUL
    (d / "soul.lock.json").unlink()
    (d / "SOUL.md").write_text("# 手寫的", encoding="utf-8")
    assert "手寫" in sw.phase_simple(d)[0] and (d / "SOUL.md").read_text(encoding="utf-8") == "# 手寫的"


def test_scratch_line_is_compiled_only_when_asked():
    assert sw.scratch_line({}) == "" and sw.scratch_line({"scratch": False, "choices": {"medium_primary": "sound"}}) == ""
    line = sw.scratch_line({"scratch": True, "choices": {"medium_primary": "sound", "first_look": "people", "contradiction": "pick_one"}})
    assert line.startswith(sw.SCRATCH_HEAD) and "語氣和節奏" in line and "他現在是什麼狀態" in line and "選一邊" in line
    # the checks do not flag the instruction's own tag words
    soul = ("# 她\n\n你是她。\n\n## 喜歡與不喜歡\n- x\n\n## 怎麼聽、怎麼想、怎麼回\n- " + line + "\n\n## 怎麼判斷、怎麼決定\n- y\n\n"
            "## 說話的方式\n- z\n\n## 遇到事情的時候\n- w\n\n## 誰在跟你說話\n" + sw.WHO_LINE)
    assert not [x for x in sw.checks(soul) if "理論字或機器字" in x]

