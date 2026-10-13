# Direct engine check: run the exam probes through KeepsakeDB's recall path (no chat model).
# A probe passes if the injected block (context) or the top-5 hybrid hits contain the expected answer.
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from memory_stress import PROBES  # noqa: E402
from keepsakedb import Keepsake  # noqa: E402
from keepsakedb.embedders import OpenAIEmbedder  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else r"D:\dev\556_production\home\memory\default.db"
ALIASES = {"三月五": ["三月五", "3月5", "3 月 5"], "七月十四": ["七月十四", "7月14", "7 月 14"], "十天": ["十天", "10天", "10 天"]}

def norm(s): return re.sub(r"\s+", "", s).lower()
def hit(texts, expected):
    blob = norm(" ".join(texts))
    for k in expected:
        for a in ALIASES.get(k, [k]):
            if norm(a) in blob: return True
    return False

ks = Keepsake(DB, embedder=OpenAIEmbedder("http://127.0.0.1:55602/v1", "bge-m3"), log_searches=False, log_pipeline=False, log_retention_days=None)
print(f"store: {ks.count()} memories, {ks.stats()['superseded']} superseded")
ok_ctx = ok_top5 = 0
for q, expected in PROBES:
    hits = ks.search(q, k=5)
    block = ks.context(q, k=5)
    injected = [l[2:] for l in block.splitlines() if l.startswith("- ")]
    c = hit(injected, expected); t = hit([h.text for h in hits], expected)
    ok_ctx += c; ok_top5 += t
    rank = next((i + 1 for i, h in enumerate(hits) if hit([h.text], expected)), None)
    print(f"  [{'O' if c else ('o' if t else 'X')}] {q}  (rank {rank}, injected {len(injected)})" + ("" if c else f"  -> {[h.text[:28] for h in hits]}"))
print(f"\n=== injected-block recall {ok_ctx}/{len(PROBES)} | top-5 recall {ok_top5}/{len(PROBES)} ===")
ks.close()
