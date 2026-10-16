"""tools/soul_writer.py — the soul skill (docs/prompt/prompt.md §2.9): a character described in plain words
becomes a six-part SOUL, seed memories with dates, person files and a psyche.json — phase by phase, each
phase stopping for review. The LLM is used only here, at authoring time; what it writes is reviewed, then
the files are written by code. Nothing regenerates on its own: a lock file records which inputs produced
the outputs.

    python tools/soul_writer.py init <id> --display 阿凜 [--from-example] [--avatar hiyori/Hiyori.model3.json]
    python tools/soul_writer.py run <id> --phase all --model gemini|claude|opus|<name> [--yes] [--force]
    python tools/soul_writer.py run <id> --phase intake|structure|thinking|voice|reactions|parts|assemble|verify
    python tools/soul_writer.py check <id>        # the mechanical checks on SOUL.md, no LLM
    python tools/soul_writer.py status <id>

Inputs: characters/<id>/describe/*.md (the person's words; HTML comments are the template's prompts and
are ignored), companion.json, profile.json (numbers and choices — proposed by the thinking phase, confirmed
by the person; --yes accepts proposals into empty fields). Outputs: build/<phase>.json (reviewable),
SOUL.md, seeds.jsonl (with `at`), people/*.md, psyche.json, soul.lock.json. The proxy at :18765 serves the
models directly (no 556d needed); `--base-url` points elsewhere.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CHARS = ROOT / "characters"
TPL = ROOT / "templates" / "character"
PSYCHE_TPL = ROOT / "templates" / "companion" / "psyche.json"
VERSION = "0.8.0"
PROXY = "http://127.0.0.1:18765/v1"
MODELS = {"gemini": "agy/gemini-3.8-flash", "gemini-pro": "agy/gemini-3.1-pro",
          "claude": "agy/claude-sonnet-4-6", "opus": "agy/claude-opus-4-6"}
PHASES = ["intake", "structure", "thinking", "voice", "reactions", "parts", "assemble", "verify"]
LLM_PHASES = {"intake", "structure", "thinking", "voice", "reactions", "parts", "verify"}

DESCRIBE = ["01-她是誰", "02-背景", "03-發生過的事", "04-說話的方式", "05-怎麼想", "06-跟人相處", "07-喜好", "08-立場",
            "09-身邊的人", "10-其他"]

MEDIA = ("inner_dialogic", "inner_condensed", "imagery", "felt", "sound", "unsymbolized")
FIRST_LOOK = ("thing", "people", "scene")
CONTRADICTION = ("hold_both", "pick_one")
CAUSE = ("person", "situation")
METERS = ("rationality", "experientiality", "promotion", "prevention", "maximizing")
CONSTANTS = ("self_esteem_stability", "expressiveness", "humor_coping", "clinginess_cap", "tsundere_tendency",
             "assertiveness", "chronotype")
BIG5 = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")

CHOICE_ZH = {
    "medium": {"inner_dialogic": "腦子裡是句子，會跟自己對話", "inner_condensed": "腦子裡是幾個關鍵字，很省",
               "imagery": "腦子裡是畫面", "felt": "先有感覺，說不出為什麼", "sound": "先聽到聲音和節奏",
               "unsymbolized": "知道自己在想什麼，但沒有字也沒有畫面"},
    "first_look": {"thing": "先看事情本身", "people": "先看跟誰有關、對方是什麼狀態", "scene": "先看現場的氣氛"},
    "contradiction": {"hold_both": "兩邊都留著", "pick_one": "選一邊"},
    "cause": {"person": "先看人", "situation": "先看處境"},
}
METER_ZH = {"rationality": "想好再回的程度", "experientiality": "憑感覺的程度", "promotion": "先看機會的程度",
            "prevention": "先看會不會出錯的程度", "maximizing": "找更好答案找到哪的程度"}

# words the SOUL must not contain: theory, scales, the machine (the fixed guardrail bullets are exempt)
BANNED = ["內在語言", "心智模型", "五大", "人格特質", "外向性", "神經質", "盡責性", "親和性", "開放性", "依附", "焦慮型",
          "迴避型", "調節焦點", "促進焦點", "預防焦點", "反芻", "極大化", "滿足化", "整體型", "分析型", "量表", "分數",
          "參數", "引擎", "狀態區塊", "AI", "人工智慧", "語言模型", "設定檔", "系統提示", "人設"]

GUARDRAILS = [
    "你不是助理：不說「隨時找我」「需要我幫你」這類客服話；不解釋自己是程式、模型或系統；不提狀態、數值、引擎。",
    "你只說真的發生在你生活裡的事（你的作息、工作、今天的小事），不編造沒發生過的經歷。",
    "心情是底色，不是主題：讓它影響語氣和選擇，而不是每句話都在講感覺。",
    "對方用什麼語言就跟著用；知道名字就叫名字。",
]
WHO_LINE = "- 每一回合會附上「現在跟你說話的是誰」的人物檔。對不同的人用不同的距離和稱呼。"

SYSTEM = """你是「556」陪伴角色的設定撰寫者。你會拿到一個人用自己的話寫的角色描述，任務是把它整理成這個角色的設定，給一個會扮演{pr}的語言模型讀。

規則：
1. 只用描述裡有的材料。描述沒提到的事實不要編：可以用描述的語氣和細節把句子寫順，但不要發明新的經歷、家人、地名、作品。缺的東西直接省略那一項，不要寫「未提及」「描述沒提到」之類的註記（只有 intake 那一步才列缺的部分）。描述裡的「我」是作者，也就是跟{pr}說話的那個人（對方）；「你」在描述裡若出現，也多半指那個人。
2. 全部用繁體中文、台灣用法。設定用第二人稱「你」稱呼角色本人（「你是…」「你會…」）；引用{pr}說的話時用{pr}的口吻。
3. 不出現理論名詞、量表、分數、數字（年齡用中文數字；日期不寫進設定，日期另外放）。不提 AI、模型、程式、系統、引擎、設定檔這些字——除非描述裡作者自己就用了那個詞（例如{pr}不喜歡 AI），那就照用，不要換成繞口的說法。
4. 寫行為，不寫形容詞：「有主見」不算，「被放鴿子會記住，雖然嘴上說沒關係」才算。每一句都要能讓人猜到{pr}在新情況下會怎麼做。
5. {pr}不是助理，不寫任何服務用語。
6. 只輸出一個 JSON 物件，不加任何說明文字。"""

P_INTAKE = """下面是角色描述。請列出缺少或太薄、會讓扮演失準的部分，每一項寫一到三個追問（問角色的作者，用中文）。
特別檢查：說話的方式有沒有真的句子；跟人相處有沒有寫到生氣、難過、道歉、和好；立場夠不夠具體；身邊的人有沒有寫到怎麼稱呼。
輸出：{{"enough": true|false, "missing": [{{"part": "哪一部分", "why": "為什麼不夠", "questions": ["追問", "..."]}}]}}

{describe}"""

P_STRUCTURE = """從描述整理出下面幾樣，輸出 JSON：
- "events": 發生過的事，每件 {{"at": "YYYY-MM-DD" 或 "YYYY-MM" 或 "YYYY"——只在描述有寫日期時填，沒有就 null，不要猜年份, "text": "一句話，第三人稱，用{pr}的名字或「{pr}」", "left": "這件事留在{pr}身上的痕跡，寫成設定裡的一句，第二人稱「你」，不帶日期", "tags": ["一到三個英文小寫標籤"]}}
- "seeds": 要載入記憶庫的事實，每條 {{"text": "一句話", "tags": ["..."], "at": "可省略"}}：包含{pr}自己的經歷與生活事實（主詞用{pr}的名字）、{pr}知道的關於跟{pr}說話的人的事（主詞寫「你」）、關於其他人的事（用名字）。十到二十條。
- "stances": {pr}會為之爭的看法，十條左右，一條一句。
- "refusals": {pr}不會答應、不會做的事。
- "tensions": {pr}自己也沒想清楚的矛盾，兩到三條。
- "cares_about": {pr}在乎什麼，五到七條短句（評估{pr}心情時會用到，例：「答應的事有沒有做到」）。
- "vague": 描述裡太空泛、猜不出行為的句子，每條 {{"line": "原句", "why": "為什麼"}}；沒有就空陣列。

{describe}"""

P_THINKING = """依描述判斷{pr}的性格與思考習慣。每一項附一句描述裡的證據；證據不足時給 0.5（或 null）並在 evidence 寫「描述沒提到」。輸出 JSON：
{{
 "big5": {{"openness": 0-1, "conscientiousness": 0-1, "extraversion": 0-1, "agreeableness": 0-1, "neuroticism": 0-1}},   // 0.5 = 一般成人
 "constants": {{"self_esteem_stability": 0-1 (被冷落時多不容易怪到自己), "expressiveness": 0-1 (心裡的事說出來多少), "humor_coping": 0-1 (不開心時用玩笑帶過的傾向), "clinginess_cap": 0-1 (最多能多黏人), "tsundere_tendency": 0-1 (把真心話反過來講的傾向), "assertiveness": 0-1 (不同意時說出來的傾向), "chronotype": -1 到 1 (-1 早鳥, 1 夜貓)}},
 "thinking": {{"rationality": 0-1 (想好再回), "experientiality": 0-1 (憑感覺), "promotion": 0-1 (先看機會), "prevention": 0-1 (先看會不會出錯), "maximizing": 0-1 (找更好的答案找到哪)}},
 "choices": {{"medium_primary": "inner_dialogic|inner_condensed|imagery|felt|sound|unsymbolized", "medium_secondary": 同上或 null, "first_look": "thing|people|scene", "contradiction": "hold_both|pick_one", "cause": "person|situation"}},
 "evidence": {{"每個鍵": "一句證據"}}
}}
選項的意思：inner_dialogic 腦中是句子、會跟自己對話；inner_condensed 腦中是關鍵字；imagery 畫面；felt 先有感覺；sound 先聽到聲音節奏；unsymbolized 知道在想什麼但沒字沒畫面。first_look：thing 先看事情本身；people 先看跟誰有關；scene 先看現場氣氛。contradiction：hold_both 兩邊都留著；pick_one 選一邊。cause：出事時 person 先看人、situation 先看處境。

{describe}"""

P_VOICE = """寫設定裡的「說話的方式」。輸出 JSON：
{{
 "expression": "四到八行：句子長短與節奏、一則訊息多長、怎麼開頭怎麼結尾、標點與表情符號的習慣、不耐煩時的樣子、不想回答時打什麼、被稱讚時的反應。第二人稱「你」。",
 "catchphrases": ["口頭禪與語氣詞，照描述抄"],
 "never_say": ["{pr}絕對不會說的話或字"],
 "lines_yes": ["五句{pr}會這樣說的話，像真的訊息，照描述裡的口吻；描述有真的句子就優先用"],
 "lines_no": ["五句{pr}不會這樣說的話：像別人、太客氣、像客服、太文藝，各一種"]
}}

{describe}"""

P_REACTIONS = """寫設定裡的「遇到事情的時候」。寫的是外面看得到的樣子，不是內心。輸出 JSON：
{{
 "reactions": "六到十行，第二人稱：生氣、難過、吃醋、被虧、被稱讚、要道歉、要和好、對方很累的時候，{pr}各是什麼樣子。",
 "fallback": [{{"when": "情況（寫「你」，不寫「{pr}」）", "she": "你會怎樣"}}]   // 五到八條：被問到你世界以外的事、對方很低落、對方要你做助理的事、對方調情、對方沒禮貌、對方要你答應你不會答應的事、對方很久沒回…
}}

{describe}"""

P_PARTS = """寫設定的前三部分與人物檔。材料：描述、整理出的 events/stances/refusals/tensions、{pr}的思考習慣（已確認，用詞描述）。輸出 JSON：
{{
 "part1": "你是誰與背景：第二人稱，一到三段，把 events 的 left 句子自然放進去，不寫日期、不寫年份。",
 "part2": "喜歡與不喜歡：五到十條，條列，含著迷的事和受不了的事，具體。",
 "thinking": "「怎麼聽、怎麼想、怎麼回」六到八行：想事情時腦中是什麼、先回還是先想（想太久會怎樣）、找機會還是防出錯（哪些事上不一樣）、看不清楚時往哪想、聊完會不會一直想與找答案找到哪、第一眼看什麼、遇到矛盾怎麼辦。照已確認的習慣寫，用{pr}的行為寫，不用理論字。",
 "judging": "「怎麼判斷、怎麼決定」：{pr}看事情的三到五種方式（每種一句，加一個會失準的情況）；五到八條做決定的規則（「遇到…就…」）；在乎的事的順序；不會答應的事；兩三條{pr}自己沒想清楚的矛盾。條列。",
 "people": {{"你": "這一條寫的是跟{pr}說話的那個人（描述裡的「我」），不是{pr}：{pr}怎麼看他、怎麼稱呼他、認識多久、{pr}還沒跟他說過什麼。兩三句；稱{pr}用{pr}的名字或「{pr}」，稱那個人用「你」；不要把{pr}自己的經歷寫成「你」的。", "<其他人的名字>": "同樣兩三句；沒有就省略"}}
}}

## 描述
{describe}

## 整理出的材料
{structure}

## 已確認的習慣（用詞）
{habits}"""

P_VERIFY = """你會讀到一份角色設定。只依設定的內容判斷這個角色的習慣，不要猜作者的意圖。只輸出 JSON：
{{"medium_primary": "inner_dialogic|inner_condensed|imagery|felt|sound|unsymbolized", "first_look": "thing|people|scene", "contradiction": "hold_both|pick_one", "cause": "person|situation",
  "rationality": "low|mid|high", "experientiality": "low|mid|high", "promotion": "low|mid|high", "prevention": "low|mid|high", "maximizing": "low|mid|high",
  "note": "一句話說你是從設定的哪幾句判斷的"}}
選項的意思同前：inner_dialogic 腦中是句子；inner_condensed 關鍵字；imagery 畫面；felt 先有感覺；sound 聲音節奏；unsymbolized 沒字沒畫面。rationality 想好再回；experientiality 憑感覺；promotion 先看機會；prevention 先看會不會出錯；maximizing 找更好答案找到哪。

## 設定
{soul}"""


# ----------------------------------------------------------------------------- files
def cdir(name: str) -> Path:
    return CHARS / name


def read_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8-sig"))


def write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip() + "\n", encoding="utf-8")


_COMMENT = re.compile(r"<!--.*?-->", re.S)


def read_describe(d: Path) -> Dict[str, str]:
    """The person's words per part, template prompts (HTML comments) and the title line stripped."""
    out: Dict[str, str] = {}
    for stem in DESCRIBE:
        p = d / "describe" / f"{stem}.md"
        text = p.read_text(encoding="utf-8-sig") if p.exists() else ""
        text = _COMMENT.sub("", text)
        lines = [ln for ln in text.splitlines() if not ln.startswith("# ")]
        out[stem] = "\n".join(lines).strip()
    return out


def describe_text(parts: Dict[str, str]) -> str:
    chunks = []
    for stem in DESCRIBE:
        body = parts.get(stem, "").strip() or "（未填）"
        chunks.append(f"## {stem[3:]}\n{body}")
    return "\n\n".join(chunks)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else ""


def pronoun(d: Path) -> str:
    prof = read_json(d / "profile.json", {}) or {}
    return str(prof.get("pronoun") or "她")


def display(d: Path) -> str:
    cj = read_json(d / "companion.json", {}) or {}
    return str(cj.get("display_name") or d.name)


# ----------------------------------------------------------------------------- llm
def make_llm(model: str, base_url: str, temperature: float, timeout: float):
    from keepsakedb.llms import OpenAIChat
    name = MODELS.get(model, model)
    return OpenAIChat(base_url, name, api_key="local-proxy-no-key", temperature=temperature, timeout=timeout)


def ask(llm, d: Path, phase: str, system: str, user: str, retries: int = 1) -> Dict[str, Any]:
    """One call, the raw reply kept under build/raw/, JSON extracted; one retry on a malformed reply."""
    from keepsakedb.llms import extract_json
    raw_dir = d / "build" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    last = ""
    for attempt in range(1 + retries):
        t0 = time.perf_counter()
        last = llm.complete(system, user)
        (raw_dir / f"{phase}.txt").write_text(last, encoding="utf-8")
        try:
            data = extract_json(last)
            data["_meta"] = {"model": getattr(llm, "model", "?"), "seconds": round(time.perf_counter() - t0, 1),
                             "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
            return data
        except Exception as e:  # noqa: BLE001
            if attempt >= retries:
                raise SystemExit(f"{phase}: the model did not return JSON ({type(e).__name__}: {e}); raw reply in {raw_dir / (phase + '.txt')}")
            user = user + "\n\n（上一次的回答不是合法的 JSON，請只輸出一個 JSON 物件。）"
    return {}


def _c(x: Any, lo: float = 0.0, hi: float = 1.0) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(min(hi, max(lo, v)), 2)


# ----------------------------------------------------------------------------- phases
def phase_intake(llm, d: Path) -> Dict[str, Any]:
    parts = read_describe(d)
    empty = [stem[3:] for stem in DESCRIBE if not parts.get(stem)]
    data = ask(llm, d, "intake", SYSTEM.format(pr=pronoun(d)), P_INTAKE.format(describe=describe_text(parts)))
    data["empty_files"] = empty
    write_json(d / "build" / "intake.json", data)
    return data


def phase_structure(llm, d: Path) -> Dict[str, Any]:
    pr = pronoun(d)
    data = ask(llm, d, "structure", SYSTEM.format(pr=pr), P_STRUCTURE.format(pr=pr, describe=describe_text(read_describe(d))))
    write_json(d / "build" / "structure.json", data)
    return data


def phase_thinking(llm, d: Path, accept: bool) -> Dict[str, Any]:
    pr = pronoun(d)
    data = ask(llm, d, "thinking", SYSTEM.format(pr=pr), P_THINKING.format(pr=pr, describe=describe_text(read_describe(d))))
    # normalise the proposal
    prop: Dict[str, Any] = {"big5": {}, "constants": {}, "thinking": {}, "choices": {}, "evidence": data.get("evidence") or {},
                            "model": data.get("_meta", {}).get("model"), "at": data.get("_meta", {}).get("at")}
    for k in BIG5:
        prop["big5"][k] = _c((data.get("big5") or {}).get(k))
    for k in CONSTANTS:
        lo = -1.0 if k == "chronotype" else 0.0
        prop["constants"][k] = _c((data.get("constants") or {}).get(k), lo, 1.0)
    for k in METERS:
        prop["thinking"][k] = _c((data.get("thinking") or {}).get(k))
    ch = data.get("choices") or {}
    prop["choices"] = {
        "medium_primary": ch.get("medium_primary") if ch.get("medium_primary") in MEDIA else None,
        "medium_secondary": ch.get("medium_secondary") if ch.get("medium_secondary") in MEDIA else None,
        "first_look": ch.get("first_look") if ch.get("first_look") in FIRST_LOOK else None,
        "contradiction": ch.get("contradiction") if ch.get("contradiction") in CONTRADICTION else None,
        "cause": ch.get("cause") if ch.get("cause") in CAUSE else None,
    }
    write_json(d / "build" / "thinking.json", data)
    prof = read_json(d / "profile.json", {}) or json.loads((TPL / "profile.json").read_text(encoding="utf-8"))
    prof["proposed"] = prop
    if accept:
        accept_proposals(prof)
    write_json(d / "profile.json", prof)
    return data


def accept_proposals(prof: Dict[str, Any]) -> int:
    """Copy proposed values into confirmed fields that are still null. Returns how many were filled."""
    prop = prof.get("proposed") or {}
    n = 0
    for group in ("big5", "constants", "thinking", "choices"):
        cur = prof.setdefault(group, {})
        for k, v in (prop.get(group) or {}).items():
            if cur.get(k) is None and v is not None:
                cur[k] = v
                n += 1
    return n


def phase_voice(llm, d: Path) -> Dict[str, Any]:
    pr = pronoun(d)
    data = ask(llm, d, "voice", SYSTEM.format(pr=pr), P_VOICE.format(pr=pr, describe=describe_text(read_describe(d))))
    write_json(d / "build" / "voice.json", data)
    return data


def phase_reactions(llm, d: Path) -> Dict[str, Any]:
    pr = pronoun(d)
    data = ask(llm, d, "reactions", SYSTEM.format(pr=pr), P_REACTIONS.format(pr=pr, describe=describe_text(read_describe(d))))
    write_json(d / "build" / "reactions.json", data)
    return data


def band(v: Optional[float]) -> str:
    if v is None:
        return "沒說"
    return "偏低" if v < 0.4 else "偏高" if v > 0.6 else "中等"


def habits_text(prof: Dict[str, Any]) -> str:
    th = prof.get("thinking") or {}
    ch = prof.get("choices") or {}
    lines = [f"- {METER_ZH[k]}：{band(th.get(k))}" for k in METERS]
    med = CHOICE_ZH["medium"].get(ch.get("medium_primary") or "", "沒說")
    if ch.get("medium_secondary"):
        med += "；有時候" + CHOICE_ZH["medium"].get(ch["medium_secondary"], "")
    lines.append(f"- 想事情時腦中是什麼：{med}")
    lines.append(f"- 第一眼看什麼：{CHOICE_ZH['first_look'].get(ch.get('first_look') or '', '沒說')}")
    lines.append(f"- 遇到矛盾：{CHOICE_ZH['contradiction'].get(ch.get('contradiction') or '', '沒說')}")
    lines.append(f"- 出事時看原因：{CHOICE_ZH['cause'].get(ch.get('cause') or '', '沒說')}")
    return "\n".join(lines)


def phase_parts(llm, d: Path) -> Dict[str, Any]:
    pr = pronoun(d)
    st = read_json(d / "build" / "structure.json", {}) or {}
    st_text = json.dumps({k: st.get(k) for k in ("events", "stances", "refusals", "tensions")}, ensure_ascii=False, indent=1)
    prof = read_json(d / "profile.json", {}) or {}
    data = ask(llm, d, "parts", SYSTEM.format(pr=pr),
               P_PARTS.format(pr=pr, describe=describe_text(read_describe(d)), structure=st_text, habits=habits_text(prof)))
    write_json(d / "build" / "parts.json", data)
    return data


# ----------------------------------------------------------------------------- assemble (no LLM)
def _bullets(items: Any) -> str:
    return "\n".join(f"- {strip_notes(fix_simplified(str(x).strip()))}" for x in (items or []) if str(x).strip() and not _NOTE_LINE.search(str(x)))


_NOTE = re.compile(r"[（(【\[][^（）()【】\[\]]*(?:未提及|沒提到|未說明|沒有提到|描述未|未提供)[^（）()【】\[\]]*[）)】\]]")
_NOTE_LINE = re.compile(r"(?:未提及|沒提到|未說明|沒有提到|描述未|未提供)")


def strip_notes(text: str) -> str:
    """The model sometimes annotates a gap inline (「（出事時看原因的習慣未提及）」, 「【描述未提及…】」). Those notes belong
    to build/, never to the SOUL: bracketed ones are cut, a line that is only such a note is dropped."""
    text = _NOTE.sub("", text)
    out = []
    for ln in text.split(chr(10)):
        core = ln.strip().lstrip("-・•").strip()
        if core and _NOTE_LINE.search(core) and len(core) <= 40:
            continue
        out.append(ln)
    return chr(10).join(out)


def _para(s: Any) -> str:
    """A section body: a string as is; a list (the model answered with items) as bullets; a string that is
    really a list literal (the model quoted a list) parsed first; simplified characters repaired."""
    if isinstance(s, str) and s.strip().startswith("[") and s.strip().endswith("]"):
        import ast
        try:
            s = ast.literal_eval(s.strip())
        except (ValueError, SyntaxError):
            pass
    if isinstance(s, (list, tuple)):
        return _bullets(s)
    if isinstance(s, dict):
        return "\n".join(f"- {k}：{_para(v)}" for k, v in s.items())
    return strip_notes(fix_simplified(str(s or "").strip())).strip()


# the simplified forms a zh-TW model slips in most often, mapped to the common traditional form in this register
_SIMP = ("觉覺 总總 这這 说說 没沒 么麼 时時 间間 关關 对對 认認 为為 发發 现現 实實 还還 会會 让讓 给給 们們 个個 经經 "
         "过過 应應 该該 种種 问問 题題 来來 后後 里裡 点點 东東 书書 车車 电電 话話 长長 开開 头頭 听聽 见見 学學 习習 "
         "业業 处處 动動 员員 乐樂 从從 两兩 儿兒 几幾 爱愛 边邊 够夠 记記 忆憶 样樣 变變 难難 离離 气氣 确確 线線 练練 "
         "画畫 图圖 买買 卖賣 钱錢 网網 别別 风風 脸臉 坏壞 伤傷 结結 该該 导導 师師 当當 据據 则則 丢丟 卫衛 旧舊 "
         "虽雖 却卻 将將 体體 医醫 药藥 饭飯 饮飲 馆館 场場 园園 楼樓 层層 转轉 轻輕 远遠 进進 运運 连連 选選 适適 "
         "边邊 达達 迟遲 递遞 阳陽 阴陰 际際 随隨 随隨 尽盡 层層 属屬 岁歲 币幣 师師 带帶 帮幫 广廣 应應 庆慶 废廢 "
         "张張 弹彈 归歸 录錄 显顯 晚晚 术術 极極 构構 标標 样樣 树樹 检檢 欢歡 气氣 汉漢 沟溝 湿濕 满滿 灯燈 热熱 "
         "环環 现現 盘盤 眼眼 着著 矿礦 码碼 离離 种種 积積 穿穿 窗窗 竞競 笔筆 签簽 简簡 类類 粮糧 纪紀 约約 级級 "
         "纸紙 纷紛 线線 组組 细細 终終 经經 绍紹 维維 绩績 续續 缘緣 罗羅 翻翻 职職 联聯 聪聰 脑腦 节節 范範 荣榮 "
         "获獲 营營 蓝藍 虑慮 补補 装裝 见見 观觀 规規 视視 觉覺 誉譽 讲講 许許 论論 设設 访訪 评評 识識 试試 诗詩 "
         "语語 误誤 说說 请請 读讀 调調 谁誰 谈談 谢謝 赶趕 轮輪 边邊 过過 这這 远遠 连連 迹跡 适適 选選 遗遺 邮郵 "
         "铁鐵 银銀 错錯 锁鎖 长長 门門 闭閉 问問 闲閒 间間 阅閱 队隊 阶階 际際 险險 难難 预預 频頻 题題 颜顏 饱飽 "
         "马馬 驾駕 验驗 骑騎 鱼魚 鸟鳥 鸡雞 黄黃 齐齊 龙龍")
_SIMP_MAP = {pair[0]: pair[1] for pair in _SIMP.split() if len(pair) == 2 and pair[0] != pair[1]}


def fix_simplified(text: str) -> str:
    return "".join(_SIMP_MAP.get(c, c) for c in text)


def build_soul(d: Path) -> str:
    name = display(d)
    parts = read_json(d / "build" / "parts.json", {}) or {}
    voice = read_json(d / "build" / "voice.json", {}) or {}
    react = read_json(d / "build" / "reactions.json", {}) or {}
    out = [f"# {name}", "", _para(parts.get("part1")), "", "## 喜歡與不喜歡", _para(parts.get("part2")), "",
           "## 怎麼聽、怎麼想、怎麼回", _para(parts.get("thinking")), "",
           "## 怎麼判斷、怎麼決定", _para(parts.get("judging")), "",
           "## 說話的方式", _para(voice.get("expression"))]
    if voice.get("catchphrases"):
        out.append("- 口頭禪、語氣詞：" + "、".join(str(x) for x in voice["catchphrases"]))
    if voice.get("never_say"):
        out.append("- 絕對不會說：" + "、".join(str(x) for x in voice["never_say"]))
    out += [_bullets(GUARDRAILS), ""]
    if voice.get("lines_yes"):
        out += ["你會這樣說：", _bullets(voice["lines_yes"]), ""]
    if voice.get("lines_no"):
        out += ["你不會這樣說：", _bullets(voice["lines_no"]), ""]
    out += ["## 遇到事情的時候", _para(react.get("reactions"))]
    fb = react.get("fallback") or []
    if fb:
        out += ["", "| 情況 | 你會 |", "| --- | --- |"]
        out += [f"| {str(x.get('when', '')).strip()} | {str(x.get('she', '')).strip()} |" for x in fb if isinstance(x, dict)]
    out += ["", "## 誰在跟你說話", WHO_LINE]
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _date_zh(at: str) -> str:
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", str(at or "").strip())
    if not m:
        return ""
    y, mo, da = m.group(1), m.group(2), m.group(3)
    s = f"{y} 年"
    if mo:
        s += f" {int(mo)} 月"
    if da:
        s += f" {int(da)} 日"
    return s


def build_seeds(d: Path) -> List[Dict[str, Any]]:
    st = read_json(d / "build" / "structure.json", {}) or {}
    rows: List[Dict[str, Any]] = []
    seen = set()

    def add(text: str, tags: Any, at: Any = None) -> None:
        text = str(text or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        text = fix_simplified(text)
        row: Dict[str, Any] = {"text": text, "tags": [str(t).strip().lower() for t in (tags or []) if str(t).strip()][:3] or ["history"]}
        at_s = str(at or "").strip()
        if re.match(r"^\d{4}(-\d{1,2}){0,2}$", at_s):
            row["at"] = at_s
        rows.append(row)

    for e in st.get("events") or []:
        if not isinstance(e, dict):
            continue
        at = e.get("at")
        text = str(e.get("text") or "").strip()
        zh = _date_zh(at)
        add((zh + "，" + text) if zh and text and not text.startswith(zh) else text, e.get("tags") or ["history"], at)
    for s in st.get("seeds") or []:
        if isinstance(s, dict):
            add(s.get("text"), s.get("tags"), s.get("at"))
    return rows


def build_people(d: Path) -> Dict[str, str]:
    parts = read_json(d / "build" / "parts.json", {}) or {}
    people = parts.get("people") or {}
    out: Dict[str, str] = {}
    for who, text in people.items():
        who = str(who).strip()
        if not who:
            continue
        body = _para(text)
        if who == "你":
            out["你"] = "# 你\n- 名字：（尚未設定）\n- 回覆語言：跟著對方（對方用什麼語言就用什麼語言回覆）\n- " + body
        else:
            out[who] = f"# {who}\n- {body}"
    return out


def build_psyche(d: Path) -> Dict[str, Any]:
    base = json.loads(PSYCHE_TPL.read_text(encoding="utf-8-sig"))
    prof = read_json(d / "profile.json", {}) or {}
    st = read_json(d / "build" / "structure.json", {}) or {}
    ch = base.setdefault("character", {})
    big5 = ch.setdefault("big5", {})
    for k in BIG5:
        v = (prof.get("big5") or {}).get(k)
        if v is not None:
            big5[k] = v
    for k in CONSTANTS:
        v = (prof.get("constants") or {}).get(k)
        if v is not None:
            ch[k] = v
    ch["pronoun"] = prof.get("pronoun") or "她"
    ch["big5_scale"] = "percentile ÷ 100 (0.50 = average adult)"
    if st.get("cares_about"):
        base["cares_about"] = [str(x).strip() for x in st["cares_about"] if str(x).strip()][:8]
    base["thinking"] = {k: (prof.get("thinking") or {}).get(k) for k in METERS}
    base["thinking_choices"] = {k: (prof.get("choices") or {}).get(k) for k in ("medium_primary", "medium_secondary", "first_look", "contradiction", "cause")}
    if isinstance(prof.get("schedule"), dict):
        base.setdefault("life", {})["schedule"] = prof["schedule"]
    return base


def checks(soul: str, allowed: str = "") -> List[str]:
    """Mechanical checks on the generated text (the fixed guardrail bullets are exempt; a banned word the author
    used in the description — `allowed` — is hers to use)."""
    body = soul
    for g in GUARDRAILS:
        body = body.replace(g, "")
    body = body.replace(WHO_LINE, "")
    found: List[str] = []
    for w in BANNED:
        n = body.count(w)
        if n and w in allowed:
            continue
        if n:
            found.append(f"含理論字或機器字「{w}」×{n}")
    # list numbering ("1. …", "2、…") is fine; digits inside sentences are not (ages, dates, scales)
    body_no_lists = re.sub(r"(?m)^\s*\d+[.、)]\s*", "", body)
    digits = re.findall(r"\d+", body_no_lists)
    if digits:
        found.append(f"含阿拉伯數字 {len(digits)} 處（{', '.join(digits[:6])}…）：年齡用中文數字，日期不進設定")
    drift = len(re.findall(r"(?:^|[，。；：\s])(?:她|他)(?:會|偏向|習慣|不會|常常|覺得|知道|說|先|只|也|很|就)", body, re.M))
    if drift >= 4:
        found.append(f"注意：第三人稱「她／他」當主詞 {drift} 處——設定應以「你」稱呼角色本人（模型的筆誤，可重跑該段）")
    n = len(soul)
    if n < 2500:
        found.append(f"太短：{n} 字（目標 2,500–4,000）")
    elif n > 4000:
        found.append(f"太長：{n} 字（目標 2,500–4,000）")
    simp = [c for c in "觉这说没么时间关对认为发现实还会让给们个经过应该种问题" if c in body]
    if simp:
        found.append(f"含簡體字：{''.join(simp)}")
    for h in ("## 喜歡與不喜歡", "## 怎麼聽、怎麼想、怎麼回", "## 怎麼判斷、怎麼決定", "## 說話的方式", "## 遇到事情的時候", "## 誰在跟你說話"):
        if h not in soul:
            found.append(f"缺少段落 {h}")
    return found


def lock_data(d: Path, model: Optional[str]) -> Dict[str, Any]:
    inputs = {f"describe/{s}.md": sha(d / "describe" / f"{s}.md") for s in DESCRIBE}
    inputs["companion.json"] = sha(d / "companion.json")
    inputs["profile.json"] = sha(d / "profile.json")
    return {"version": VERSION, "model": model, "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "inputs": inputs,
            "outputs": {f: sha(d / f) for f in ("SOUL.md", "seeds.jsonl", "psyche.json")}}


def stale_inputs(d: Path) -> List[str]:
    """Inputs that changed since the lock was written (so SOUL.md / psyche.json no longer match them)."""
    lock = read_json(d / "soul.lock.json")
    if not lock:
        return []
    cur = lock_data(d, lock.get("model"))["inputs"]
    return [k for k, v in (lock.get("inputs") or {}).items() if cur.get(k) != v]


def phase_assemble(d: Path, force: bool, model: Optional[str] = None) -> List[str]:
    for f in ("parts.json", "voice.json", "reactions.json", "structure.json"):
        if not (d / "build" / f).exists():
            raise SystemExit(f"assemble: build/{f} missing — run the earlier phases first")
    if (d / "SOUL.md").exists() and not (d / "soul.lock.json").exists() and not force:
        print("assemble: SOUL.md here is hand-written (no soul.lock.json) — the cast stays untouched; --force to replace it with the generated one")
        return ["手寫的 SOUL.md 不覆蓋（沒有 soul.lock.json）；要用產生的取代請 --force"]
    soul = build_soul(d)
    found = checks(soul, describe_text(read_describe(d)))
    write_text(d / "build" / "check.md", "# 檢查\n" + ("\n".join(f"- {x}" for x in found) if found else "- 通過"))
    blocking = [x for x in found if not x.startswith("注意：")]
    if blocking and not force:
        print("assemble: the SOUL did not pass the checks (build/check.md); fix the inputs and rerun, or --force to write anyway")
        for x in found:
            print("  -", x)
        return found
    for x in found:
        print("  -", x)
    write_text(d / "SOUL.md", soul)
    seeds = build_seeds(d)
    (d / "seeds.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in seeds), encoding="utf-8")
    for who, text in build_people(d).items():
        write_text(d / "people" / f"{who}.md", text)
    write_json(d / "psyche.json", build_psyche(d))
    if not (d / "kokoro.json").exists():
        write_json(d / "kokoro.json", {"address_default": "你"})
    write_json(d / "soul.lock.json", lock_data(d, model))
    print(f"assemble: SOUL.md {len(soul)} chars, {len(seeds)} seeds, people: {', '.join(build_people(d).keys()) or '-'}")
    return found


def phase_verify(llm, d: Path) -> Dict[str, Any]:
    soul_p = d / "SOUL.md"
    if not soul_p.exists():
        raise SystemExit("verify: SOUL.md missing — run assemble first")
    soul = soul_p.read_text(encoding="utf-8")
    data = ask(llm, d, "verify", "你是審稿人。只輸出 JSON。", P_VERIFY.format(soul=soul))
    prof = read_json(d / "profile.json", {}) or {}
    th, ch = prof.get("thinking") or {}, prof.get("choices") or {}
    rows: List[str] = []
    hits = total = 0
    for k in ("medium_primary", "first_look", "contradiction", "cause"):
        want = ch.get(k)
        got = data.get(k)
        if want is None:
            continue
        total += 1
        ok = want == got
        hits += ok
        rows.append(f"| {k} | {want} | {got} | {'✓' if ok else '✗'} |")
    bands = {"low": "偏低", "mid": "中等", "high": "偏高"}
    for k in METERS:
        want = th.get(k)
        if want is None:
            continue
        total += 1
        got = bands.get(str(data.get(k)), str(data.get(k)))
        ok = band(want) == got
        hits += ok
        rows.append(f"| {k} | {band(want)} | {got} | {'✓' if ok else '✗'} |")
    report = ["# 盲讀回推（只給設定，不給描述）", f"模型：{data.get('_meta', {}).get('model')}", "",
              "| 項目 | 設定值 | 讀回 | |", "| --- | --- | --- | --- |", *rows, "",
              f"一致：{hits}/{total}", f"依據：{data.get('note', '')}", "", "## 機械檢查", *(f"- {x}" for x in (checks(soul, describe_text(read_describe(d))) or ["通過"]))]
    write_text(d / "build" / "verify.md", "\n".join(report))
    write_json(d / "build" / "verify.json", {**data, "matches": hits, "total": total})
    print(f"verify: {hits}/{total} consistent; report in build/verify.md")
    return data


# ----------------------------------------------------------------------------- cli
def cmd_init(args: argparse.Namespace) -> int:
    d = cdir(args.name)
    if not re.match(r"^[a-z0-9_-]+$", args.name):
        raise SystemExit("id must be lowercase letters, digits, _ or -")
    if d.exists() and any(d.iterdir()):
        raise SystemExit(f"{d} already exists and is not empty")
    (d / "describe").mkdir(parents=True, exist_ok=True)
    src = TPL / "example" / "describe" if args.from_example else TPL / "describe"
    for p in src.glob("*.md"):
        shutil.copy(p, d / "describe" / p.name)
    write_json(d / "companion.json", {"display_name": args.display, "avatar_model": args.avatar})
    write_json(d / "kokoro.json", {"address_default": "你"})
    prof = json.loads((TPL / "profile.json").read_text(encoding="utf-8"))
    prof["pronoun"] = args.pronoun
    write_json(d / "profile.json", prof)
    print(f"init: {d} — fill describe/*.md (or keep the example), then: soul_writer.py run {args.name} --phase all --model claude --yes")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    d = cdir(args.name)
    if not (d / "describe").exists():
        raise SystemExit(f"no describe/ under {d} — run init first")
    phases = PHASES if args.phase == "all" else [args.phase]
    if getattr(args, "from_phase", None):
        phases = PHASES[PHASES.index(args.from_phase):]
    llm = None
    if any(p in LLM_PHASES for p in phases):
        llm = make_llm(args.model, args.base_url, args.temperature, args.timeout)
    model_name = getattr(llm, "model", None)
    for ph in phases:
        print(f"== {ph} ==")
        if ph == "intake":
            data = phase_intake(llm, d)
            if data.get("empty_files"):
                print("  empty:", ", ".join(data["empty_files"]))
            for m in data.get("missing") or []:
                print(f"  - {m.get('part')}: {m.get('why')}")
                for q in m.get("questions") or []:
                    print(f"      ? {q}")
            if (args.phase == "all" or getattr(args, "from_phase", None)) and not data.get("enough", True) and not args.yes:
                print("intake: the description is thin; answer the questions in describe/ or rerun with --yes to continue anyway")
                return 2
        elif ph == "structure":
            data = phase_structure(llm, d)
            print(f"  events {len(data.get('events') or [])}, seeds {len(data.get('seeds') or [])}, stances {len(data.get('stances') or [])}, vague {len(data.get('vague') or [])}")
            for v in data.get("vague") or []:
                print(f"  vague: {v.get('line')} — {v.get('why')}")
        elif ph == "thinking":
            data = phase_thinking(llm, d, accept=args.yes)
            prof = read_json(d / "profile.json", {}) or {}
            print("  proposed:", json.dumps(prof.get("proposed", {}).get("thinking"), ensure_ascii=False), json.dumps(prof.get("proposed", {}).get("choices"), ensure_ascii=False))
            if not args.yes:
                print("  review profile.json (proposed → confirm by filling the null fields, or rerun with --yes)")
                if args.phase == "all" or getattr(args, "from_phase", None):
                    return 2
        elif ph == "voice":
            data = phase_voice(llm, d)
            print("  lines:", " / ".join(str(x) for x in (data.get("lines_yes") or [])[:3]))
        elif ph == "reactions":
            data = phase_reactions(llm, d)
            print(f"  fallback rows {len(data.get('fallback') or [])}")
        elif ph == "parts":
            prof = read_json(d / "profile.json", {}) or {}
            if any(v is None for v in (prof.get("thinking") or {}).values()) and not args.yes:
                print("  profile.json still has null meters; confirm them or use --yes")
            phase_parts(llm, d)
        elif ph == "assemble":
            found = phase_assemble(d, force=args.force, model=model_name)
            if found and not args.force:
                return 3
        elif ph == "verify":
            phase_verify(llm, d)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    d = cdir(args.name)
    p = d / "SOUL.md"
    if not p.exists():
        raise SystemExit("no SOUL.md")
    found = checks(p.read_text(encoding="utf-8"), describe_text(read_describe(d)))
    print("\n".join(f"- {x}" for x in found) if found else "通過")
    return 1 if found else 0


def cmd_status(args: argparse.Namespace) -> int:
    d = cdir(args.name)
    parts = read_describe(d)
    print("describe:", ", ".join(f"{s[3:]}{'✓' if parts.get(s) else '—'}" for s in DESCRIBE))
    print("build:", ", ".join(p for p in PHASES if (d / "build" / f"{p}.json").exists() or (p == "assemble" and (d / "SOUL.md").exists())) or "-")
    lock = read_json(d / "soul.lock.json")
    if lock:
        stale = stale_inputs(d)
        print(f"lock: {lock.get('at')} model={lock.get('model')} " + (f"STALE inputs: {', '.join(stale)}" if stale else "inputs unchanged"))
    else:
        print("lock: none (not assembled)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init")
    a.add_argument("name")
    a.add_argument("--display", required=True)
    a.add_argument("--avatar", default="hiyori/Hiyori.model3.json")
    a.add_argument("--pronoun", default="她")
    a.add_argument("--from-example", action="store_true")
    a.set_defaults(fn=cmd_init)
    r = sub.add_parser("run")
    r.add_argument("name")
    r.add_argument("--phase", default="all", choices=["all", *PHASES])
    r.add_argument("--from", dest="from_phase", default=None, choices=PHASES, help="run from this phase to the end (overrides --phase)")
    r.add_argument("--model", default="gemini", help="gemini | gemini-pro | claude | opus | a model name on the proxy")
    r.add_argument("--base-url", default=PROXY)
    r.add_argument("--temperature", type=float, default=0.4)
    r.add_argument("--timeout", type=float, default=900, help="per call; claude through the proxy can take several minutes on the parts phase")
    r.add_argument("--yes", action="store_true", help="accept proposals into empty profile fields; continue past a thin intake")
    r.add_argument("--force", action="store_true", help="write SOUL.md even when the checks fail")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check")
    c.add_argument("name")
    c.set_defaults(fn=cmd_check)
    s = sub.add_parser("status")
    s.add_argument("name")
    s.set_defaults(fn=cmd_status)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
