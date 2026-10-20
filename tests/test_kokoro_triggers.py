"""Keyword triggers (plugins/kokoro, tier 3 of docs/prompt/prompt.md §2.2): a name in the message fires an exact
BM25 lookup; rows similarity already brought are not repeated; off with kokoro.json `triggers: false`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "hermes-agent"))
sys.path.insert(0, str(ROOT / "plugins"))
import importlib.util

spec = importlib.util.spec_from_file_location("kokoro_mod", ROOT / "plugins" / "kokoro" / "__init__.py")
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


class Row:
    def __init__(self, text, archived=False, superseded=False, held=False):
        self.text, self.archived, self.superseded, self.held = text, archived, superseded, held


class FakeStore:
    def __init__(self, by_name):
        self.by_name = by_name
        self.calls = []

    def search(self, query, k=5, mode="hybrid", phrase=False, **kw):
        self.calls.append((query, k, mode, phrase))
        return list(self.by_name.get(query, []))[:k]

    def context(self, query, k, mode="bm25"):
        return ""


class FakePipeline:
    class cfg:
        context_k = 5
    subject = "你"

    def context_for(self, query, k):
        return "Memory:\nFacts (long-term):\n- 角色乙是小明的朋友"   # the pipeline renders 你 as her term for you


def make(tmp_path, cfg=None, store=None):
    home = tmp_path / "profiles" / "a"
    (home / "people").mkdir(parents=True, exist_ok=True)
    (home / "people" / "角色乙.md").write_text("# 角色乙\n- 朋友", encoding="utf-8")
    (home / "people" / "你.md").write_text("# 你", encoding="utf-8")
    for sib, name in (("b", "角色甲"), ("c", "角色乙")):
        (tmp_path / "profiles" / sib).mkdir(parents=True, exist_ok=True)
        (tmp_path / "profiles" / sib / "companion.json").write_text(json.dumps({"display_name": name}), encoding="utf-8")
    p = k.KokoroMemoryProvider()
    p._home = home
    p._cfg = {"address_default": "製作人", "your_name": "小明", **(cfg or {})}
    p._store = store if store is not None else FakeStore({})
    p._pipeline = FakePipeline()
    return p


def test_names_come_from_the_roster_the_people_files_and_your_name(tmp_path):
    p = make(tmp_path)
    assert p._trigger_names() == ["小明", "角色乙", "角色甲"]   # sorted


def test_a_name_in_the_message_adds_its_rows_without_repeating_similarity_hits(tmp_path):
    store = FakeStore({"角色甲": [Row("角色甲在圖書館上班"), Row("角色甲覺得你應該多休息", archived=True)],
                       "角色乙": [Row("角色乙是你的朋友"), Row("角色乙幫你搬家")]})
    p = make(tmp_path, store=store)
    block = p.prefetch("角色甲跟角色乙週末會來嗎", session_id="")
    assert block.startswith("Memory:")
    assert "By name:" in block and "- 角色甲在圖書館上班" in block and "- 角色乙幫小明搬家" in block   # 你 rendered as her term
    assert block.count("角色乙是小明的朋友") == 1          # already there from similarity, rendered the same way
    assert "多休息" not in block                         # archived rows stay out
    assert ("角色甲", 3, "bm25", True) in store.calls      # an exact lookup, k = trigger_k


def test_no_name_no_lookup_and_the_switch_turns_it_off(tmp_path):
    store = FakeStore({"角色甲": [Row("角色甲在圖書館上班")]})
    p = make(tmp_path, store=store)
    assert "By name" not in p.prefetch("今天好累喔", session_id="")
    assert store.calls == []
    p2 = make(tmp_path, cfg={"triggers": False}, store=store)
    assert "By name" not in p2.prefetch("角色甲好嗎", session_id="")
    assert store.calls == []
