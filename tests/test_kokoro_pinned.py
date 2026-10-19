"""render_pinned (plugins/kokoro): the pinned groups block, with a fake store."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "hermes-agent"))
sys.path.insert(0, str(ROOT / "plugins"))
import importlib.util

spec = importlib.util.spec_from_file_location("kokoro_mod", ROOT / "plugins" / "kokoro" / "__init__.py")
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


class Row:
    def __init__(self, text, created_at, superseded=False):
        self.text, self.created_at, self.superseded = text, created_at, superseded


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def by_tag(self, tag, include_archived=False):
        return list(self.rows.get(tag, []))


def test_render_pinned_orders_caps_and_renders_subject():
    store = FakeStore({
        "timeline": [Row("2024 年，你第一次聽她唱歌", 2.0), Row("2017 年，畢業展被說是塗鴉", 1.0), Row("2026 年，認識你", 3.0)],
        "stances": [Row("舊的立場", 1.0), Row("新的立場", 2.0), Row("被更正的", 1.5, superseded=True)],
        "refusals": [],
    })
    out = k.render_pinned(store, ["timeline", "stances", "refusals", "standing"], per_tag=2, show=lambda t: t.replace("你", "哥"))
    assert out.startswith("一直記著的：")
    assert "【時間線】" in out and out.index("2017 年") < out.index("2024 年")          # timeline oldest first
    assert "2026 年" not in out                                                          # capped at two
    assert "【立場】" in out and out.index("新的立場") < out.index("舊的立場")             # others newest first
    assert "被更正的" not in out and "【不做的事】" not in out and "【跟人的關係】" not in out
    assert "哥第一次聽她唱歌" in out                                                       # 你 rendered as her term


def test_render_pinned_empty():
    assert k.render_pinned(FakeStore({}), ["timeline"], 8, lambda t: t) == ""
