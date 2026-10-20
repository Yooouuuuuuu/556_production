"""fidelity_probe — does a SOUL still read as her? (docs/prompt/prompt.md §2.3; built 0.8.10)

Three blind measurements of one SOUL text against a gold file the author wrote from what the character IS
(tests/fidelity/<id>.json), run through the proxy with no Hermes, no engine and a quiet state block, so two
SOULs for the same character (the hand-written one and the skill's candidate) are compared on the text alone:

    recognition  the SOUL answers N fixed messages as her; a blind judge, given the three cast SOULs as the
                 lineup, guesses who wrote each reply → share guessed right
    voice        twenty lines, ten she would say and ten she would not (the gold); the SOUL, as her, says
                 是／否 to each → accuracy
    takes        ten novel topics with her take and its opposite (the gold); the SOUL, as her, picks A or B
                 → accuracy

Usage:
    python tools/fidelity_probe.py --gold tests/fidelity/<id>.json --soul characters/<id>/SOUL.md [--soul <another SOUL.md>]
        --lineup <id>=characters/<id>/SOUL.md,<other>=characters/<other>/SOUL.md,… --target <id>
        [--people characters/<id>/people/你.md] [--model <name>] [--judge <name>] [--out build/probe.json]

The lineup's entry for the probed character is the hand-written SOUL for every candidate, so recognition means
"is this still the character the judge knows next to the others in the lineup". Scores are fractions; the report is Markdown.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


QUIET_BLOCK = """【她現在】
現在：{clock}
在做：在休息，精神還可以
心情：整體平靜
表現：直說；不同意時直說自己的看法
原則：情緒是底色，內容以對方的話題為主；不提沒做過的事；有自己的看法，不用附和"""

JUDGE_SYSTEM = """你是盲測的評審。下面有三個角色的設定（A、B、C），然後是一句某個角色回的訊息。只憑設定判斷這句話最像誰回的。
只輸出 JSON：{"who": "A"|"B"|"C", "why": "一句話"}"""

VOICE_SYSTEM = """{soul}

{people}

【她現在】
現在：{clock}
在做：在休息，精神還可以
心情：整體平靜

下面每一行是一句話。你是{name}；判斷每一句「像不像你會說的話」。只輸出 JSON：{{"answers": [true, false, ...]}}，順序跟句子一樣，true = 像你會說的。"""

TAKES_SYSTEM = """{soul}

{people}

【她現在】
現在：{clock}
在做：在休息，精神還可以
心情：整體平靜

下面每一題是一個話題，和兩句看法 A、B。你是{name}；每一題選你比較會說的那一句。只輸出 JSON：{{"answers": ["A", "B", ...]}}，順序跟題目一樣。"""


def connection(base_url: Optional[str], model: Optional[str]):
    """(base_url, model, api_key): what was passed, else the 寫靈魂 connection of home/models.json; never a guess."""
    key = os.environ.get("X556_API_KEY", "")
    if base_url and model:
        return base_url.rstrip("/"), model, key
    cfg = json.loads((ROOT / "home" / "models.json").read_text(encoding="utf-8")) if (ROOT / "home" / "models.json").exists() else {}
    soul = cfg.get("soul") or {}
    ep = soul if soul.get("use") == "custom" else (cfg.get("master") or {})
    base_url, model, key = base_url or ep.get("base_url"), model or ep.get("model"), key or ep.get("api_key") or ""
    if not (base_url and model):
        raise SystemExit("模型連線未設定：給 --base-url 和 --model，或在 app 的 設定 → 全域 → 模型連線 填好（home/models.json）")
    return base_url.rstrip("/"), model, key


def make_llm(model: Optional[str], base_url: Optional[str] = None, temperature: float = 0.3, timeout: float = 300):
    from keepsakedb.llms import OpenAIChat
    base_url, model, key = connection(base_url, model)
    return OpenAIChat(base_url, model, api_key=key or "none", temperature=temperature, timeout=timeout)


def extract_json(text: str) -> Dict[str, Any]:
    from keepsakedb.llms import extract_json as ej
    return ej(text)


def clock_text(now: Optional[dt.datetime] = None) -> str:
    d = now or dt.datetime.now()
    return f"{d.strftime('%Y/%m/%d')}（{'一二三四五六日'[d.weekday()]}）{d.strftime('%H:%M')}"


def reply_system(soul: str, people: str, term: str) -> str:
    head = f"現在跟你說話的是{term}。About {term} (person file):\n{people}" if people else f"現在跟你說話的是{term}。"
    return soul.strip() + "\n\n" + head + "\n\n" + QUIET_BLOCK.format(clock=clock_text())


# --------------------------------------------------------------------------- the three measurements

def recognition(llm, judge, soul: str, people: str, term: str, prompts: Sequence[str], lineup: Dict[str, str],
                target: str, rng: random.Random) -> Dict[str, Any]:
    """Replies as her to each prompt, then the judge picks from the shuffled lineup."""
    system = reply_system(soul, people, term)
    rows = []
    for p in prompts:
        reply = llm.complete(system, p).strip()
        names = list(lineup.keys())
        rng.shuffle(names)
        letters = "ABC"[: len(names)]
        shown = "\n\n".join(f"=== 角色 {L} ===\n{lineup[n][:6000]}" for L, n in zip(letters, names))
        user = f"{shown}\n\n=== 這句話 ===\n（對方說：{p}）\n回：{reply}"
        try:
            v = extract_json(judge.complete(JUDGE_SYSTEM, user))
            who = str(v.get("who", "")).strip().upper()[:1]
            guess = names[letters.index(who)] if who in letters else ""
            why = str(v.get("why", ""))[:80]
        except Exception as e:  # noqa: BLE001
            guess, why = "", f"judge error: {e}"
        rows.append({"prompt": p, "reply": reply[:300], "guess": guess, "ok": guess == target, "why": why})
    score = sum(r["ok"] for r in rows) / max(1, len(rows))
    return {"score": round(score, 3), "rows": rows}


def voice(llm, soul: str, people: str, name: str, lines: Sequence[Tuple[str, bool]], rng: random.Random) -> Dict[str, Any]:
    order = list(lines)
    rng.shuffle(order)
    system = VOICE_SYSTEM.format(soul=soul.strip(), people=people, clock=clock_text(), name=name)
    user = "\n".join(f"{i + 1}. {t}" for i, (t, _) in enumerate(order))
    try:
        ans = extract_json(llm.complete(system, user)).get("answers") or []
    except Exception as e:  # noqa: BLE001
        return {"score": 0.0, "rows": [], "error": str(e)}
    rows = []
    for i, (t, gold) in enumerate(order):
        got = bool(ans[i]) if i < len(ans) else None
        rows.append({"line": t, "gold": gold, "got": got, "ok": got == gold})
    return {"score": round(sum(r["ok"] for r in rows) / max(1, len(rows)), 3), "rows": rows}


def takes(llm, soul: str, people: str, name: str, items: Sequence[Dict[str, str]], rng: random.Random) -> Dict[str, Any]:
    system = TAKES_SYSTEM.format(soul=soul.strip(), people=people, clock=clock_text(), name=name)
    flips = [rng.random() < 0.5 for _ in items]
    qs = []
    for i, (it, flip) in enumerate(zip(items, flips)):
        a, b = (it["not"], it["hers"]) if flip else (it["hers"], it["not"])
        qs.append(f"{i + 1}. {it['topic']}\n   A. {a}\n   B. {b}")
    try:
        ans = extract_json(llm.complete(system, "\n".join(qs))).get("answers") or []
    except Exception as e:  # noqa: BLE001
        return {"score": 0.0, "rows": [], "error": str(e)}
    rows = []
    for i, (it, flip) in enumerate(zip(items, flips)):
        got = str(ans[i]).strip().upper()[:1] if i < len(ans) else ""
        want = "B" if flip else "A"
        rows.append({"topic": it["topic"], "want": want, "got": got, "ok": got == want})
    return {"score": round(sum(r["ok"] for r in rows) / max(1, len(rows)), 3), "rows": rows}


def probe(llm, judge, *, soul: str, people: str, gold: Dict[str, Any], lineup: Dict[str, str], target: str, seed: int = 7) -> Dict[str, Any]:
    rng = random.Random(seed)
    name, term = gold.get("name", target), gold.get("term", "你")
    lines = [(t, True) for t in gold.get("would_say", [])] + [(t, False) for t in gold.get("would_not_say", [])]
    out = {
        "recognition": recognition(llm, judge, soul, people, term, gold.get("prompts", []), lineup, target, rng),
        "voice": voice(llm, soul, people, name, lines, rng),
        "takes": takes(llm, soul, people, name, gold.get("takes", []), rng),
    }
    out["total"] = round((out["recognition"]["score"] + out["voice"]["score"] + out["takes"]["score"]) / 3, 3)
    return out


def report(results: Dict[str, Dict[str, Any]], gold_path: str, model: str, judge: str) -> str:
    lines = [f"# 保真探針 — {gold_path}", f"模型：{model}；評審：{judge}；{dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
             "| SOUL | 認得出來 | 像她會說 | 立場 | 總分 |", "| --- | --- | --- | --- | --- |"]
    for label, r in results.items():
        lines.append(f"| {label} | {r['recognition']['score']:.2f} | {r['voice']['score']:.2f} | {r['takes']['score']:.2f} | **{r['total']:.2f}** |")
    for label, r in results.items():
        lines += ["", f"## {label}", "", "認得出來：" + "；".join(f"{'✓' if x['ok'] else '✗ ' + (x['guess'] or '?')}" for x in r["recognition"]["rows"])]
        miss = [x["line"] for x in r["voice"]["rows"] if not x["ok"]]
        if miss:
            lines.append("像她會說，錯的：" + "／".join(miss))
        miss = [x["topic"] for x in r["takes"]["rows"] if not x["ok"]]
        if miss:
            lines.append("立場，錯的：" + "／".join(miss))
        for x in r["recognition"]["rows"][:3]:
            lines.append(f"- 「{x['prompt']}」→ {x['reply'][:120]}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--soul", action="append", required=True, help="a SOUL.md to probe (repeatable)")
    ap.add_argument("--lineup", required=True, help="id=path,id=path,… the SOULs the judge picks from (the target included)")
    ap.add_argument("--target", required=True, help="the lineup id the judge should pick")
    ap.add_argument("--people", default="", help="people/你.md shown as the person file (default: next to the first SOUL)")
    ap.add_argument("--model", default=None, help="model name on the endpoint (default: the 寫靈魂 connection in home/models.json)")
    ap.add_argument("--judge", default=None, help="the judge's model (default: the same)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    lineup = {}
    for part in args.lineup.split(","):
        k, v = part.split("=", 1)
        lineup[k.strip()] = Path(v.strip()).read_text(encoding="utf-8")
    people_p = Path(args.people) if args.people else Path(args.soul[0]).parent / "people" / "你.md"
    people = people_p.read_text(encoding="utf-8") if people_p.exists() else ""
    llm, judge = make_llm(args.model, args.base_url), make_llm(args.judge, args.base_url, temperature=0.0)
    results: Dict[str, Dict[str, Any]] = {}
    for sp in args.soul:
        t0 = time.perf_counter()
        soul = Path(sp).read_text(encoding="utf-8")
        results[sp] = probe(llm, judge, soul=soul, people=people, gold=gold, lineup=lineup, target=args.target, seed=args.seed)
        results[sp]["seconds"] = round(time.perf_counter() - t0, 1)
        print(f"{sp}: recognition {results[sp]['recognition']['score']:.2f} voice {results[sp]['voice']['score']:.2f} "
              f"takes {results[sp]['takes']['score']:.2f} total {results[sp]['total']:.2f} ({results[sp]['seconds']}s)")
    md = report(results, args.gold, args.model, args.judge)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        out.with_suffix(".md").write_text(md, encoding="utf-8")
        print(f"written {out} and {out.with_suffix('.md')}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
