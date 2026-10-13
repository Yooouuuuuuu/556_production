# Exam only: re-run the recall probes of memory_stress.py against the CURRENT store
# (fresh session per probe), for when the chat backend failed during a run's exam phase.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_stress import PROBES, ask, log  # noqa: E402


def main() -> int:
    hits = 0
    results = []
    for i, (q, expected) in enumerate(PROBES, 1):
        reply, secs = ask(q + "（請根據你對我的記憶回答，一句話就好）")
        norm = reply.lower().replace(" ", "").replace("　", "")
        ok = any(k.lower().replace(" ", "") in norm for k in expected)
        hits += ok
        results.append((ok, q, expected, reply[:150]))
        log({"phase": "probe-rerun", "round": i, "q": q, "expected": expected,
             "reply": reply[:400], "hit": ok, "secs": round(secs, 1)})
        print(f"  [{'O' if ok else 'X'}] {q} ({secs:.0f}s)", flush=True)
    print(f"\n=== RESULT: {hits}/{len(PROBES)} probes passed ===", flush=True)
    for ok, q, exp, rep in results:
        if not ok:
            print(f"  MISS: {q} (expected {exp}) -> {rep}", flush=True)
    return 0 if hits == len(PROBES) else 1


if __name__ == "__main__":
    sys.exit(main())
