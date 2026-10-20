"""Load a character's seed memories (characters/<id>/seeds.jsonl) into its KeepsakeDB store.

Run while 556d is up (the embedder at :55602) and the character is NOT running (the store has no owner):
    python tools/seed-memories.py <id> [--replace]

Memories about you keep the subject word 你 (rendered as your name when injected); memories about the
other characters name them. A seed with `at` (YYYY[-MM[-DD]]) is stored at that date. Existing seeds (same text) are
skipped unless --replace.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ts(at) -> float | None:
    """'2024', '2024-03' or '2024-03-09' -> a timestamp at local noon of that day (month/day default to 1)."""
    import datetime as dt
    import re
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", str(at or "").strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        return dt.datetime(y, mo, d, 12, 0).timestamp()
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    src = ROOT / "characters" / args.name / "seeds.jsonl"
    profile = ROOT / "home" / "profiles" / args.name
    if not src.exists() or not profile.exists():
        print("missing character files or profile:", src, profile)
        return 1
    kok = json.loads((profile / "kokoro.json").read_text(encoding="utf-8-sig"))
    from keepsakedb import Keepsake
    from keepsakedb.embedders import OpenAIEmbedder
    e = kok.get("embedder") or {}
    if not (e.get("base_url") and e.get("model")):
        print("模型連線未設定：kokoro.json 沒有 embedder（在 app 的 設定 → 全域 → 模型連線 填好，啟動角色一次讓 556d 寫入，再來）")
        return 1
    emb = OpenAIEmbedder(e["base_url"], e["model"], api_key=e.get("api_key", ""), dims=e.get("dims"))
    db = profile / str(kok.get("db", "memory/{profile}.db")).format(profile=args.name)
    db.parent.mkdir(parents=True, exist_ok=True)
    ks = Keepsake(str(db), embedder=emb, tokenizer=kok.get("tokenizer", "bigram"), dims=e.get("dims"), owner=False)
    try:
        ks._set_meta_default("subject", kok.get("subject", "你"))  # the store's fixed subject word, as kokoro would set it
    except Exception:
        pass
    existing = {r[0] for r in ks.conn.execute("SELECT text FROM memories").fetchall()}
    n = 0
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item["text"] in existing and not args.replace:
            continue
        ts = _ts(item.get("at"))  # a dated seed (YYYY, YYYY-MM or YYYY-MM-DD) is stored at that time, not at seeding time
        meta = {"seed": True, "source": "設定"}
        if item.get("at"):
            meta["at"] = str(item["at"])
        ks.add(item["text"], item.get("tags", []), meta, ts=ts)
        n += 1
    ks.close()
    print(f"{args.name}: {n} seed memories added to {db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
