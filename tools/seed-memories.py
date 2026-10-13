"""Load a character's seed memories (characters/<id>/seeds.jsonl) into its KeepsakeDB store.

Run while 556d is up (the embedder at :55602) and the character is NOT running (the store has no owner):
    python tools/seed-memories.py chihiro [--replace]

Memories about you keep the subject word 你 (rendered as your name when injected); memories about the
other characters name them. Existing seeds (same text) are skipped unless --replace.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    e = kok.get("embedder", {})
    emb = OpenAIEmbedder(e.get("base_url", "http://127.0.0.1:55602/v1"), e.get("model", "bge-m3"), api_key=e.get("api_key", ""), dims=e.get("dims"))
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
        ks.add(item["text"], item.get("tags", []), {"seed": True, "source": "設定"})
        n += 1
    ks.close()
    print(f"{args.name}: {n} seed memories added to {db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
