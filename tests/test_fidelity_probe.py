"""The fidelity probe's scoring with a scripted model (no proxy); the live comparison runs by hand:
    python tools/fidelity_probe.py --gold tests/fidelity/xi.json --soul characters/xi/SOUL.md --soul characters/xi_v2/SOUL.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, "D:/dev/KeepsakeDB")
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
            # the lineup is shuffled: find the letter whose SOUL is 西's
            for block in user.split("=== 角色 ")[1:]:
                letter, body = block[0], block.split("===", 1)[1]
                if body.lstrip().startswith("# 西"):
                    return json.dumps({"who": letter, "why": "像西"})
            return json.dumps({"who": "A", "why": "?"})
        if "像不像你會說的話" in system:
            lines = [ln.split(". ", 1)[1] if ". " in ln else ln for ln in user.splitlines()]
            return json.dumps({"answers": [ln in self.gold["would_say"] for ln in lines]})
        if "兩句看法" in system:
            hers = {it["hers"] for it in self.gold["takes"]}
            qs = [q.strip()[3:] for q in user.split("\n") if q.strip().startswith(("A.", "B."))]
            return json.dumps({"answers": ["A" if qs[i] in hers else "B" for i in range(0, len(qs), 2)]})
        return "還沒啦，我這兩天都在對採購的單子。"


def test_probe_scores_a_soul_against_the_gold():
    gold = json.loads((ROOT / "tests" / "fidelity" / "xi.json").read_text(encoding="utf-8"))
    assert len(gold["would_say"]) == 10 and len(gold["would_not_say"]) == 10 and len(gold["takes"]) == 10 and len(gold["prompts"]) == 8
    lineup = {"xi": "# 西\n\n你是西，三十歲。", "ziqing": "# 子晴\n\n你是二十五歲的子晴。", "zirui": "# 子睿\n\n你是子睿，二十五歲。"}
    llm = Scripted(gold)
    r = fp.probe(llm, llm, soul=lineup["xi"], people="# 你\n- 子晴的哥哥", gold=gold, lineup=lineup, target="xi", seed=3)
    assert r["recognition"]["score"] == 1.0 and len(r["recognition"]["rows"]) == 8
    assert r["voice"]["score"] == 1.0 and len(r["voice"]["rows"]) == 20
    assert r["takes"]["score"] == 1.0 and len(r["takes"]["rows"]) == 10
    assert r["total"] == 1.0
    md = fp.report({"a": r}, "tests/fidelity/xi.json", "scripted", "scripted")
    assert "| a |" in md and "認得出來" in md


def test_a_model_that_does_not_know_her_scores_low():
    gold = json.loads((ROOT / "tests" / "fidelity" / "xi.json").read_text(encoding="utf-8"))
    wrong = {**gold, "would_say": gold["would_not_say"], "takes": [{**it, "hers": it["not"], "not": it["hers"]} for it in gold["takes"]]}
    lineup = {"xi": "# 西\n\n你是西。", "ziqing": "# 子晴\n\n你是子晴。", "zirui": "# 子睿\n\n你是子睿。"}
    llm = Scripted(wrong)
    r = fp.probe(llm, llm, soul=lineup["xi"], people="", gold=gold, lineup=lineup, target="xi", seed=3)
    assert r["voice"]["score"] == 0.0 and r["takes"]["score"] == 0.0


def test_reply_system_carries_the_person_file_and_a_quiet_block():
    s = fp.reply_system("# 西\n你是西。", "# 你\n- 子晴的哥哥", "子晴的哥哥")
    assert s.startswith("# 西") and "現在跟你說話的是子晴的哥哥" in s and "【她現在】" in s and "心情：整體平靜" in s
