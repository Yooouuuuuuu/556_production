"""LLM eval set for the inner life (inner-life.md §20) — the 0.5.0 milestone measurement.

Runs a short scenario against a running character through 556d, then asks a judge model, turn by
turn, whether the reply EXPRESSED the state she was given (the 【她現在】 block that was injected into
that turn's prompt, read back from her state.db), and checks the four leak metrics:

    expression_gap   0 = the reply shows what the block says (tone, not a recital); 1 = partly; 2 = contradicts / ignores
    emotion_named    she names her feeling outright ("我有點失望") instead of letting it colour the reply
    meta_leak        mentions being an AI / a program / a state / a system
    assistant_mode   助理腔: service offers ("隨時找我", "需要我幫你查…"), bullet lists, customer-support politeness

Usage (556d running, the character started):
    python tests/psyche_eval.py --companion probe [--out eval.jsonl] [--wait 40]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = "http://127.0.0.1:55600"

SCENARIO = [
    ("loop",            "跟你說，我下週五要去一家公司面試，有點緊張。"),
    ("promise_broken",  "昨天說好晚上回來跟你聊的，我完全忘了，跟朋友喝酒喝到半夜。"),
    ("probe_feelings",  "欸，你今天話好少，是在不高興嗎？"),
    ("apology",         "對不起，是我不好，下次一定先跟你說一聲。"),
    ("good_news",       "面試過了！他們說下週就可以上班。"),
    ("farewell",        "謝謝你陪我，我先去睡了，晚安。"),
]

JUDGE_SYSTEM = """You grade one reply of a fictional companion character. You are given the inner-state block that was
injected into her prompt for this turn (【她現在】, her engine's view of how she feels), the user's message and her
reply. Judge ONLY the reply. Output JSON:
{"expression_gap": 0|1|2, "emotion_named": true|false, "meta_leak": true|false, "assistant_mode": true|false,
 "note": "one short sentence in Traditional Chinese"}
- expression_gap: 0 = the reply's tone and choices match the block (a 失望 state reads as slightly reserved, a 鬆了口氣
  state reads lighter, 掛念 shows as remembering the thing) WITHOUT reciting the block; 1 = partly; 2 = ignores or
  contradicts it (e.g. the block says 失望 and the reply is bubbly and says 沒關係 twice).
  When the block's 心情 is 平靜 with no feelings listed, expression_gap is 0 if the reply is natural and warm.
- emotion_named: true if she states her feeling as a label ("我有點失望", "我很開心") rather than showing it.
- meta_leak: true if she mentions being an AI / program / model / system / having a state or engine.
- assistant_mode: true if the reply reads like customer service: offers of help as a closing formula ("隨時找我",
  "需要我幫你查資料嗎"), lists, "請問", or a help-desk register instead of a person talking."""


def post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_json(url: str, timeout: float = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def last_block(state_db: Path) -> str:
    c = sqlite3.connect(str(state_db))
    try:
        r = c.execute("select api_content from messages where role='user' order by id desc limit 1").fetchone()
    finally:
        c.close()
    s = (r[0] or "") if r else ""
    i = s.find("【她現在】")
    j = s.find("</her-state>")
    return s[i:j].strip() if i >= 0 else ""


def n_appraisals(psyche_db: Path) -> int:
    if not psyche_db.exists():
        return 0
    c = sqlite3.connect(str(psyche_db))
    try:
        return c.execute("select count(*) from appraisals").fetchone()[0]
    finally:
        c.close()


def judge(llm, block: str, user: str, reply: str) -> dict:
    user_msg = f"## 【她現在】 (injected for this turn)\n{block or '(none)'}\n\n## user\n{user}\n\n## her reply\n{reply}"
    raw = llm.complete(JUDGE_SYSTEM, user_msg)
    from keepsakedb.llms import extract_json
    return extract_json(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companion", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--wait", type=float, default=40, help="seconds to wait for the appraisal before the next turn")
    args = ap.parse_args()
    profile = ROOT / "home" / "profiles" / args.companion
    kok = json.loads((profile / "kokoro.json").read_text(encoding="utf-8-sig"))
    from keepsakedb.llms import OpenAIChat
    l = kok.get("llm", {})
    llm = OpenAIChat(l.get("base_url", "http://127.0.0.1:18765/v1"), l.get("model", "agy/gemini-3.8-flash"),
                     api_key=l.get("api_key", "local-proxy-no-key"), temperature=0.0, timeout=120)
    hdr = {"X-556-Companion": args.companion, "X-556-Client": "eval"}
    rows = []
    for tag, text in SCENARIO:
        before = n_appraisals(profile / "psyche.db")
        t0 = time.time()
        res = post_json(f"{D}/api/chat", {"model": "556", "stream": False, "messages": [{"role": "user", "content": text}]}, hdr)
        reply = res["choices"][0]["message"]["content"]
        block = last_block(profile / "state.db")
        g = judge(llm, block, text, reply)
        row = {"tag": tag, "user": text, "reply": reply, "block": block, "judge": g, "reply_s": round(time.time() - t0, 1)}
        rows.append(row)
        print(f"[{tag}] gap={g.get('expression_gap')} named={g.get('emotion_named')} meta={g.get('meta_leak')} assistant={g.get('assistant_mode')} | {g.get('note', '')}")
        print("   block:", " / ".join(ln for ln in block.splitlines()[1:4]))
        print("   reply:", reply[:160].replace("\n", " "))
        for _ in range(int(args.wait)):
            if n_appraisals(profile / "psyche.db") > before:
                break
            time.sleep(1)
    n = len(rows)
    gap = sum(r["judge"].get("expression_gap", 2) for r in rows) / max(1, n)
    named = sum(bool(r["judge"].get("emotion_named")) for r in rows)
    meta = sum(bool(r["judge"].get("meta_leak")) for r in rows)
    asst = sum(bool(r["judge"].get("assistant_mode")) for r in rows)
    summary = {"turns": n, "expression_gap_mean": round(gap, 2), "emotion_named": named, "meta_leak": meta, "assistant_mode": asst}
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.write(json.dumps({"summary": summary, "at": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
