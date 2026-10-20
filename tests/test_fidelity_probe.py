"""The fidelity probe's scoring with a scripted model (no proxy); the live comparison runs by hand:
    python tools/fidelity_probe.py --gold tests/fidelity/<id>.json --soul characters/<id>/SOUL.md --lineup a=…,b=…,c=… --target a
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "vendor" / "keepsakedb"))
import fidelity_probe as fp  # noqa: E402


class Scripted:
    """A model that knows her: answers by prefix of the system prompt / user text so the three measurements can be
    driven without the proxy."""
    model = "scripted"

    def __init__(self, gold):
        self.calls = []
        self.gold = gold

    def complete(self, system, user):
        self.calls.append((system, user))
        if system.startswith("你是盲測的評審"):
            # the lineup is shuffled: find the letter whose SOUL is the target's
            for block in user.split("=== 角色 ")[1:]:
                letter, body = block[0], block.split("===", 1)[1]
                if body.lstrip().startswith("# 角色甲"):
                    return json.dumps({"who": letter, "why": "像角色甲"})
            return json.dumps({"who": "A", "why": "?"})
        if "像不像你會說的話" in system:
            lines = [ln.split(". ", 1)[1] if ". " in ln else ln for ln in user.splitlines()]
            return json.dumps({"answers": [ln in self.gold["would_say"] for ln in lines]})
        if "兩句看法" in system:
            hers = {it["hers"] for it in self.gold["takes"]}
            qs = [q.strip()[3:] for q in user.split("\n") if q.strip().startswith(("A.", "B."))]
            return json.dumps({"answers": ["A" if qs[i] in hers else "B" for i in range(0, len(qs), 2)]})
        return "還沒啦，我這兩天都在對採購的單子。"


def gold_fixture():
    """A synthetic gold: eight prompts, ten lines she would say, ten she would not, ten takes — no real character."""
    return {"name": "角色甲", "term": "你", "note": "synthetic",
            "prompts": [f"話題{i}" for i in range(8)],
            "would_say": [f"會說的第{i}句" for i in range(10)],
            "would_not_say": [f"不會說的第{i}句" for i in range(10)],
            "takes": [{"topic": f"題目{i}", "hers": f"看法甲{i}", "not": f"看法乙{i}"} for i in range(10)]}


def test_probe_scores_a_soul_against_the_gold():
    gold = gold_fixture()
    assert len(gold["would_say"]) == 10 and len(gold["would_not_say"]) == 10 and len(gold["takes"]) == 10 and len(gold["prompts"]) == 8
    lineup = {"a": "# 角色甲\n\n你是角色甲，三十歲。", "b": "# 角色乙\n\n你是二十五歲的角色乙。", "c": "# 角色丙\n\n你是角色丙，二十五歲。"}
    llm = Scripted(gold)
    r = fp.probe(llm, llm, soul=lineup["a"], people="# 你\n- 角色甲的朋友", gold=gold, lineup=lineup, target="a", seed=3)
    assert r["recognition"]["score"] == 1.0 and len(r["recognition"]["rows"]) == 8
    assert r["voice"]["score"] == 1.0 and len(r["voice"]["rows"]) == 20
    assert r["takes"]["score"] == 1.0 and len(r["takes"]["rows"]) == 10
    assert r["total"] == 1.0
    md = fp.report({"a": r}, "tests/fidelity/a.json", "scripted", "scripted")
    assert "| a |" in md and "認得出來" in md


def test_a_model_that_does_not_know_her_scores_low():
    gold = gold_fixture()
    wrong = {**gold, "would_say": gold["would_not_say"], "takes": [{**it, "hers": it["not"], "not": it["hers"]} for it in gold["takes"]]}
    lineup = {"a": "# 角色甲\n\n你是角色甲。", "b": "# 角色乙\n\n你是角色乙。", "c": "# 角色丙\n\n你是角色丙。"}
    llm = Scripted(wrong)
    r = fp.probe(llm, llm, soul=lineup["a"], people="", gold=gold, lineup=lineup, target="a", seed=3)
    assert r["voice"]["score"] == 0.0 and r["takes"]["score"] == 0.0


def test_reply_system_carries_the_person_file_and_a_quiet_block():
    s = fp.reply_system("# 角色甲\n你是角色甲。", "# 你\n- 角色甲的朋友", "角色甲的朋友")
    assert s.startswith("# 角色甲") and "現在跟你說話的是角色甲的朋友" in s and "【她現在】" in s and "心情：整體平靜" in s
