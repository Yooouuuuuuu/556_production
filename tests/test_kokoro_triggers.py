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
        return "Memory:\nFacts (long-term):\n- 子睿是阿哲的弟弟"   # the pipeline renders 你 as her term for you


def make(tmp_path, cfg=None, store=None):
    home = tmp_path / "profiles" / "xi"
    (home / "people").mkdir(parents=True, exist_ok=True)
    (home / "people" / "子睿.md").write_text("# 子睿\n- 弟弟", encoding="utf-8")
    (home / "people" / "你.md").write_text("# 你", encoding="utf-8")
    for sib, name in (("ziqing", "子晴"), ("zirui", "子睿")):
        (tmp_path / "profiles" / sib).mkdir(parents=True, exist_ok=True)
        (tmp_path / "profiles" / sib / "companion.json").write_text(json.dumps({"display_name": name}), encoding="utf-8")
    p = k.KokoroMemoryProvider()
    p._home = home
    p._cfg = {"address_default": "製作人", "your_name": "阿哲", **(cfg or {})}
    p._store = store if store is not None else FakeStore({})
    p._pipeline = FakePipeline()
    return p


def test_names_come_from_the_roster_the_people_files_and_your_name(tmp_path):
    p = make(tmp_path)
    assert p._trigger_names() == ["子晴", "子睿", "阿哲"]


def test_a_name_in_the_message_adds_its_rows_without_repeating_similarity_hits(tmp_path):
    store = FakeStore({"子晴": [Row("子晴在板橋教國文"), Row("子晴覺得你應該認真唱", archived=True)],
                       "子睿": [Row("子睿是你的弟弟"), Row("子睿幫你混音")]})
    p = make(tmp_path, store=store)
    block = p.prefetch("子晴跟子睿週末會來嗎", session_id="")
    assert block.startswith("Memory:")
    assert "By name:" in block and "- 子晴在板橋教國文" in block and "- 子睿幫阿哲混音" in block   # 你 rendered as her term
    assert block.count("子睿是阿哲的弟弟") == 1          # already there from similarity, rendered the same way
    assert "認真唱" not in block                         # archived rows stay out
    assert ("子晴", 3, "bm25", True) in store.calls      # an exact lookup, k = trigger_k


def test_no_name_no_lookup_and_the_switch_turns_it_off(tmp_path):
    store = FakeStore({"子晴": [Row("子晴在板橋教國文")]})
    p = make(tmp_path, store=store)
    assert "By name" not in p.prefetch("今天好累喔", session_id="")
    assert store.calls == []
    p2 = make(tmp_path, cfg={"triggers": False}, store=store)
    assert "By name" not in p2.prefetch("子晴好嗎", session_id="")
    assert store.calls == []
