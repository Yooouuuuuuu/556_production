"""tools/soul_writer.py — the soul skill (docs/prompt/prompt.md §2.9): a character described in plain words
becomes a six-part SOUL, seed memories with dates, person files and a psyche.json — phase by phase, each
phase stopping for review. The LLM is used only here, at authoring time; what it writes is reviewed, then
the files are written by code. Nothing regenerates on its own: a lock file records which inputs produced
the outputs.

    python tools/soul_writer.py init <id> --display <名字> [--avatar hiyori/Hiyori.model3.json]
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
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
CHARS = ROOT / "characters"
TPL = ROOT / "templates" / "character"
PSYCHE_TPL = ROOT / "templates" / "companion" / "psyche.json"
VERSION = "0.8.0"
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

# the hidden scratch (prompt.md §2.6; 0.8.10, after its four checks): one instruction compiled from the dial 1 and 6
# choices, in the 怎麼聽、怎麼想、怎麼回 section, only when profile.json `scratch` is true. The shim strips the block
# and logs it; nothing downstream ever sees it.
SCRATCH_HEAD = "回覆之前，先在 <think> 和 </think> 之間用兩三行寫下你腦子裡先出現的東西，再寫要說的話。那幾行是你自己的，對方看不到；回覆裡不要提到它，也不要解釋你想過什麼。"
SCRATCH_MEDIUM = {
    "inner_dialogic": "那幾行是句子，像在跟自己講話，可以自己反駁自己。",
    "inner_condensed": "那幾行是幾個關鍵字，不成句。",
    "imagery": "那幾行是一個畫面：人在哪、光從哪來、誰的表情。",
    "felt": "那幾行先寫感覺，不寫理由；理由想到再補。",
    "sound": "那幾行先寫對方聽起來的語氣和節奏，再寫你聽到了什麼。",
    "unsymbolized": "那幾行只寫結論，不解釋怎麼來的。",
}
SCRATCH_FIRST = {"thing": "第一行先寫他問的到底是什麼。", "people": "第一行先寫他現在是什麼狀態。", "scene": "第一行先寫現場是什麼氣氛。"}
SCRATCH_CONTRA = {"hold_both": "兩邊都有道理的時候，兩邊都留著，不急著選。", "pick_one": "兩邊都有道理的時候，選一邊，寫一句為什麼。"}


def scratch_line(prof: Dict[str, Any]) -> str:
    """The compiled scratch instruction, or "" when the profile does not ask for it."""
    if not prof or not prof.get("scratch"):
        return ""
    ch = prof.get("choices") or {}
    bits = [SCRATCH_HEAD]
    for table, key in ((SCRATCH_MEDIUM, "medium_primary"), (SCRATCH_FIRST, "first_look"), (SCRATCH_CONTRA, "contradiction")):
        v = ch.get(key)
        if v and v in table:
            bits.append(table[v])
    return "".join(bits)


# the simple path (prompt.md §2.10): one sentence per band per meter, one line per choice, written once here in zh-TW
BAND_TEXT = {
    "rationality": {"low": "你先回再想，回完才會覺得剛才講太快。", "mid": "你看情況，小事先回，大事會停一下。", "high": "你想好才回，寧可慢一點也不要講錯。"},
    "experientiality": {"low": "你不太信直覺，會找理由說服自己。", "mid": "直覺跟理由各半，對不上的時候會再看一次。", "high": "你憑感覺，先知道對不對，理由之後才想得出來。"},
    "promotion": {"low": "你不太會去想「還可以怎樣」，有就好。", "mid": "有機會你會看一下，但不會追。", "high": "你預設在找機會，先看能變成什麼。"},
    "prevention": {"low": "你不太擔心出錯，錯了再說。", "mid": "重要的事你會先想會不會出錯。", "high": "你預設在防出錯，先看哪裡會壞。"},
    "maximizing": {"low": "差不多就好，你不會一直找更好的。", "mid": "你會多看一兩個選擇，然後就決定。", "high": "你會一直找更好的答案，決定了還會再想。"},
}
CHOICE_TEXT = {
    "medium_primary": {"inner_dialogic": "想事情的時候你腦子裡是句子，會跟自己來回講。", "inner_condensed": "想事情的時候你腦子裡是幾個關鍵字，不成句。",
                       "imagery": "想事情的時候你腦子裡是畫面。", "felt": "想事情的時候你先有一種感覺，字是之後才來的。",
                       "sound": "想事情的時候你先聽到語氣和節奏。", "unsymbolized": "你知道自己在想什麼，但沒有字也沒有畫面。"},
    "first_look": {"thing": "你第一眼看事情本身。", "people": "你第一眼看這件事跟誰有關、對方什麼狀態。", "scene": "你第一眼看現場是什麼氣氛。"},
    "contradiction": {"hold_both": "遇到矛盾你兩邊都留著。", "pick_one": "遇到矛盾你會選一邊。"},
    "cause": {"person": "出事的時候你先看人。", "situation": "出事的時候你先看處境。"},
}
REACT_TEXT = {
    "expressiveness": {"low": "心裡的事你不太說出來，看得出來的人才看得出來。", "high": "心裡有什麼臉上就有什麼。"},
    "humor_coping": {"high": "不開心的事你用玩笑帶過。"},
    "tsundere_tendency": {"high": "真心話你常常反過來講，但會留破綻。"},
    "assertiveness": {"low": "不同意的時候你先收著，不附和也不爭。", "high": "不同意的時候你直說。"},
}


def simple_band(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "mid"
    return "low" if x < 0.4 else "high" if x > 0.6 else "mid"


def build_simple(d: Path) -> str:
    """The simple path's SOUL: the three boxes verbatim in the six-part order, the band sentences, no model."""
    prof = read_json(d / "profile.json", {}) or {}
    sp = prof.get("simple") or {}
    name = display(d)
    who = str(sp.get("who") or "").strip() or f"你是{name}。"
    talk = str(sp.get("talk") or "").strip()
    refuses = [x.strip() for x in str(sp.get("refuses") or "").splitlines() if x.strip()]
    th = {k: (prof.get("thinking") or {}).get(k) for k in METERS}
    ch = prof.get("choices") or {}
    think = [BAND_TEXT[k][simple_band(th.get(k))] for k in METERS]
    for key, table in CHOICE_TEXT.items():
        v = ch.get(key)
        if v and v in table:
            think.append(table[v])
    sc = scratch_line(prof)
    if sc:
        think.append(sc)
    const = prof.get("constants") or {}
    react = []
    for key, table in REACT_TEXT.items():
        b = simple_band(const.get(key))
        if b in table:
            react.append(table[b])
    out = [f"# {name}", "", who, "", "## 喜歡與不喜歡", "（還沒寫）", "",
           "## 怎麼聽、怎麼想、怎麼回", _bullets(think), "",
           "## 怎麼判斷、怎麼決定", _bullets(refuses) if refuses else "（還沒寫）", "",
           "## 說話的方式", talk or "用口語，像在傳訊息：通常一到三句。", _bullets(GUARDRAILS), "",
           "## 遇到事情的時候", _bullets(react) if react else "（還沒寫）", "",
           "## 誰在跟你說話", WHO_LINE]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def phase_simple(d: Path, force: bool = False) -> List[str]:
    """Write the simple path's files. The size check does not apply (flatter text is the stated cost); the other
    checks are recorded. A hand-written SOUL (no lock) is never overwritten without --force."""
    if (d / "SOUL.md").exists() and not (d / "soul.lock.json").exists() and not force:
        print("simple: SOUL.md here is hand-written (no soul.lock.json) — --force to replace it")
        return ["手寫的 SOUL.md 不覆蓋（沒有 soul.lock.json）；要取代請 --force"]
    soul = build_simple(d)
    found = [x for x in checks(soul, "") if not x.startswith(("太短：", "太長："))]   # flatter and shorter is the stated cost
    write_text(d / "build" / "check.md", "# 檢查（簡單版）\n" + ("\n".join(f"- {x}" for x in found) if found else "- 通過"))
    write_text(d / "SOUL.md", soul)
    lines = [ln.strip(" -•\t") for ln in shared_past(d).splitlines() if ln.strip(" -•\t")]
    if lines:   # no model here: each line of 關係 → 一起經歷過的事 is one memory as written (0.12.0)
        (d / "seeds.jsonl").write_text("".join(json.dumps({"text": fix_simplified(ln), "tags": ["shared"]}, ensure_ascii=False) + "\n" for ln in lines), encoding="utf-8")
    elif not (d / "seeds.jsonl").exists():
        (d / "seeds.jsonl").write_text("", encoding="utf-8")
    if not (d / "people" / "你.md").exists():
        write_text(d / "people" / "你.md", "# 你\n- 名字：（尚未設定）\n- 回覆語言：跟著對方（對方用什麼語言就用什麼語言回覆）\n")
    write_json(d / "psyche.json", build_psyche(d))
    if not (d / "kokoro.json").exists():
        write_json(d / "kokoro.json", {"address_default": "你"})
    write_json(d / "soul.lock.json", lock_data(d, "simple"))
    print(f"simple: SOUL.md {len(soul)} chars (no model)")
    return found

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
- "influences": 影響過{pr}的人與事（老師、某個人說過的話、一本書、一首歌），每條 {{"text": "一句話，寫明留下了什麼", "tags": ["..."]}}；描述沒有就空陣列。
- "stances": {pr}會為之爭的看法，十條左右，一條一句。
- "refusals": {pr}不會答應、不會做的事。
- "tensions": {pr}自己也沒想清楚的矛盾，兩到三條。
- "cares_about": {pr}在乎什麼，五到七條短句（評估{pr}心情時會用到，例：「答應的事有沒有做到」）。
- "life": {pr}的日子，描述有寫到的才填，沒寫的欄位用 null：{{"wake": 起床時間（小時，例 7.5）, "bedtime": 睡覺時間（小時，例 23.5；凌晨一點寫 1）, "busy": [[開始, 結束], ...] 忙的時段（上班、上課；小時）, "busyness_mode": "work"（上班上課）|"hobby"（做自己的事）|"none"（不忙）, "project": {{"title": "{pr}手上在做的一件事", "stage": "到哪個階段"}}, "small_events": [{{"text": "會發生在{pr}日子裡的一件小事，一句", "v": -1 到 1 好壞}}] 三到六條}}；描述完全沒寫就 null。
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


P_SHARED = """下面是作者寫的、{name}（{pr}）跟「跟{pr}說話的人」一起經歷過的事。把它整理成要載入記憶庫的記憶條目，一件事一條。只輸出 JSON：
{{"seeds": [{{"text": "一句話", "tags": ["shared", "另一個英文小寫標籤"], "at": "YYYY-MM-DD 或 YYYY-MM 或 YYYY——只在作者有寫日期時填，沒有就省略，不要猜"}}]}}
規則：跟{pr}說話的人寫「你」；{pr}自己寫「{name}」（不要用別的稱呼）；只寫作者寫了的事，不補細節、不加感想、不推論；一條一件；作者寫幾件就幾條。

## 一起經歷過的事
{shared}"""

P_SHARED_CHECK = """你會讀到一份角色設定（{name}，{pr}），和幾條「{name}跟對方一起經歷過的事」的記憶。只找兩者對不上的地方：年齡、時間、地點、人物、跟設定裡寫的經歷互相矛盾的。沒有就空陣列。只輸出 JSON：
{{"conflicts": ["一句話說哪一條記憶跟設定的哪一句對不上"]}}

## 設定
{soul}

## 記憶
{seeds}"""


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
def make_llm(model: Optional[str], base_url: Optional[str], temperature: float, timeout: float):
    from keepsakedb.llms import OpenAIChat
    base_url, model, key = connection(base_url, model)
    return OpenAIChat(base_url, model, api_key=key or "none", temperature=temperature, timeout=timeout)


# ----------------------------------------------------------------------------- connection
def connection(base_url: Optional[str], model: Optional[str]) -> Tuple[str, str, str]:
    """(base_url, model, api_key): what was passed, else the 寫靈魂 connection of home/models.json (設定 →
    模型連線). Nothing is guessed: with neither, this is an error."""
    key = os.environ.get("X556_API_KEY", "")
    if base_url and model:
        return base_url.rstrip("/"), model, key
    p = ROOT / "home" / "models.json"
    cfg = read_json(p, {}) or {}
    soul = cfg.get("soul") or {}
    ep = soul if soul.get("use") == "custom" else (cfg.get("master") or {})
    base_url = base_url or ep.get("base_url")
    model = model or ep.get("model")
    key = key or ep.get("api_key") or ""
    if not (base_url and model):
        raise SystemExit("模型連線未設定：給 --base-url 和 --model，或在 app 的 設定 → 模型連線 填好（home/models.json）")
    return base_url.rstrip("/"), model, key


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
    data.pop("closeness", None)       # 0.12.0: how close you start is the author's bar (profile.json), never proposed
    data.pop("closeness_why", None)
    data["shared_seeds"] = shared_seeds(llm, d)
    write_json(d / "build" / "structure.json", data)
    return data


def shared_past(d: Path) -> str:
    """profile.json `shared_past`: what the author wrote under 關係 → 一起經歷過的事 (0.12.0). It becomes memory rows
    like anything she will remember from real talk — never SOUL text, never the people file."""
    prof = read_json(d / "profile.json", {}) or {}
    return str(prof.get("shared_past") or "").strip()


def shared_seeds(llm, d: Path) -> List[Dict[str, Any]]:
    """The author's shared past as memory rows: the model only splits and phrases (subject rules, dates only when
    written), it adds nothing; [] when the box is empty."""
    text = shared_past(d)
    if not text:
        return []
    pr = pronoun(d)
    res = ask(llm, d, "shared", SYSTEM.format(pr=pr), P_SHARED.format(pr=pr, name=display(d), shared=text))
    out: List[Dict[str, Any]] = []
    for s in res.get("seeds") or []:
        if not isinstance(s, dict) or not str(s.get("text") or "").strip():
            continue
        tags = [str(t).strip().lower() for t in (s.get("tags") or []) if str(t).strip() and str(t).strip().lower() != "shared"]
        row: Dict[str, Any] = {"text": str(s["text"]).strip(), "tags": ["shared", *tags][:3]}
        if str(s.get("at") or "").strip():
            row["at"] = str(s["at"]).strip()
        out.append(row)
    return out


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
_LEADNUM = re.compile(r"^\s*\d+\s*[.、)]\s*")


def _bullets(items: Any) -> str:
    """Items become bullets; a short item ending in a colon is a sub-heading the model put in the list and stays a
    plain line."""
    out = []
    for x in (items or []):
        raw = str(x).strip()
        if not raw or _NOTE_LINE.search(raw):
            continue
        txt = strip_notes(fix_simplified(_LEADNUM.sub("", raw)))
        out.append(txt if (txt.endswith("：") or txt.endswith(":")) and len(txt) <= 16 else f"- {txt}")
    return "\n".join(out)


def _bullets_old(items: Any) -> str:
    return "\n".join(f"- {strip_notes(fix_simplified(_LEADNUM.sub('', str(x).strip())))}" for x in (items or []) if str(x).strip() and not _NOTE_LINE.search(str(x)))


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
    prof = read_json(d / "profile.json", {}) or {}
    st = read_json(d / "build" / "structure.json", {}) or {}
    sc = scratch_line(prof)
    out = [f"# {name}", "", _para(parts.get("part1")), "", *timeline_sections(st), "## 喜歡與不喜歡", _para(parts.get("part2")), "",
           "## 怎麼聽、怎麼想、怎麼回", _para(parts.get("thinking")) + (("\n- " + sc) if sc else ""), "",
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
        tags = [str(t).strip().lower() for t in (e.get("tags") or []) if str(t).strip()]
        if "timeline" not in tags:  # a dated event: a seed for retrieval; the SOUL's 時間線 carries it too
            tags = ["timeline", *tags]
        add((zh + "，" + text) if zh and text and not text.startswith(zh) else text, tags, at)
    for inf in st.get("influences") or []:
        if isinstance(inf, dict):
            tags = [str(t).strip().lower() for t in (inf.get("tags") or []) if str(t).strip()]
            add(inf.get("text"), ["influences", *[t for t in tags if t != "influences"]])
    for s in st.get("seeds") or []:
        if isinstance(s, dict):
            add(s.get("text"), s.get("tags"), s.get("at"))
    for s in st.get("shared_seeds") or []:   # 關係 → 一起經歷過的事 (0.12.0): memory with its own tag, never SOUL text
        if isinstance(s, dict):
            add(s.get("text"), ["shared", *[t for t in (s.get("tags") or []) if str(t).strip().lower() != "shared"]], s.get("at"))
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


# how close she and the user are when she starts (the structure phase reads it from the description; profile.json
# `closeness` overrides): bond and quality hours, the bands of relation.closeness_words — and the disclosure depth the
# bond gives (1 喜好 / 2 看法 / 3 感受 / 4 脆弱處), which the 表現 line caps on since 0.8.9
CLOSENESS = {
    "剛認識": {"bond": 0.05, "hours": 2.0},
    "還不算熟": {"bond": 0.2, "hours": 30.0},
    "朋友": {"bond": 0.4, "hours": 70.0},
    "很熟": {"bond": 0.6, "hours": 150.0},
    "很親近": {"bond": 0.8, "hours": 250.0},
}


def _overlay(tpl: Dict[str, Any], cur: Dict[str, Any]) -> Dict[str, Any]:
    """The template with the package's current values on top: what was set outside the skill (the 主動 sliders,
    anything hand-edited) stays, and a key the template gained since still appears."""
    for k, v in cur.items():
        if isinstance(v, dict) and isinstance(tpl.get(k), dict):
            tpl[k] = _overlay(tpl[k], v)
        else:
            tpl[k] = v
    return tpl


def life_from_structure(st_life: Any) -> Optional[Dict[str, Any]]:
    """The structure phase's draft of her day (wake, bedtime, busy, busyness_mode, project, small_events) in the engine's
    shape (psyche.json `life`, docs/inner-life §14); None when the description gave nothing."""
    if not isinstance(st_life, dict):
        return None
    out: Dict[str, Any] = {}
    sched: Dict[str, Any] = {}
    for key in ("wake", "bedtime"):
        v = st_life.get(key)
        if isinstance(v, (int, float)) and 0 <= float(v) < 24:
            sched[key] = float(v)
    busy = st_life.get("busy")
    if isinstance(busy, list):
        blocks = [[float(b[0]), float(b[1])] for b in busy if isinstance(b, (list, tuple)) and len(b) == 2
                  and all(isinstance(x, (int, float)) for x in b)]
        if blocks:
            sched["work"] = blocks
    if sched:
        out["schedule"] = sched
    if st_life.get("busyness_mode") in ("work", "hobby", "none"):
        out["busyness_mode"] = st_life["busyness_mode"]
    pj = st_life.get("project")
    if isinstance(pj, dict) and str(pj.get("title") or "").strip():
        out["projects"] = [{"title": str(pj["title"]).strip(), "stage": str(pj.get("stage") or "進行中").strip(), "difficulty": 0.5, "progress": 0.0}]
    evs = []
    for e in st_life.get("small_events") or []:
        if isinstance(e, dict) and str(e.get("text") or "").strip():
            try:
                v = max(-1.0, min(1.0, float(e.get("v") or 0.0)))
            except (TypeError, ValueError):
                v = 0.0
            evs.append({"text": str(e["text"]).strip(), "v": v, "R": 0.3, "p": 0.1, "kind": "life", "share": True})
    if evs:
        out["small_events"] = evs
    return out or None


def build_psyche(d: Path) -> Dict[str, Any]:
    # Not a rebuild from the template (before 0.10.3 it was, and every assemble wiped the 主動 sliders): the package's
    # psyche.json is the base, the skill overwrites only the keys it derives from profile.json and the structure phase.
    base = _overlay(json.loads(PSYCHE_TPL.read_text(encoding="utf-8-sig")), read_json(d / "psyche.json", {}) or {})
    if isinstance(base.get("time"), dict):
        base["time"].pop("timezone_offset_h", None)   # this machine's zone lives in the profile copy only (556d writes it)
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
    # her day (0.11.0): profile.json `life` (the page: a sample, the draft, or your own) wins; else the structure phase's
    # draft; else the package keeps what it has (the template's neutral schedule, nothing in hand, no small events)
    life = prof.get("life") if isinstance(prof.get("life"), dict) else life_from_structure(st.get("life"))
    if life:
        base["life"] = _overlay(base.get("life") or {}, life)
    band = str(prof.get("closeness") or "").strip()   # 0.12.0: the author's bar; the skill no longer proposes one
    if band in CLOSENESS:
        base.setdefault("relationships", {})["你"] = dict(CLOSENESS[band])
    return base


def timeline_sections(st: Dict[str, Any]) -> List[str]:
    """## 時間線 and ## 影響過你的人與事 from the structure phase: the dated, always-on part of who you are, inside the
    SOUL (DECISIONS 2026-10-19 — the pinned tags of 0.8.7 are retired). Code, not a model; absent when the description
    gives nothing. Dated events first, oldest first; undated after."""
    out: List[str] = []
    events = [e for e in (st.get("events") or []) if isinstance(e, dict) and str(e.get("text") or "").strip()]
    dated = sorted([e for e in events if _date_zh(e.get("at"))], key=lambda e: str(e.get("at")))
    lines = []
    for e in dated + [e for e in events if not _date_zh(e.get("at"))]:
        zh, text = _date_zh(e.get("at")), str(e.get("text")).strip()
        lines.append((zh + "，" + text) if zh and not text.startswith(zh) else text)
    if lines:
        out += ["## 時間線", _bullets(lines), ""]
    infl = [str(i.get("text") or "").strip() for i in (st.get("influences") or []) if isinstance(i, dict) and str(i.get("text") or "").strip()]
    if infl:
        out += ["## 影響過你的人與事", _bullets(infl), ""]
    return out


DATED_SECTIONS = ("## 時間線", "## 影響過你的人與事")


def _without_sections(text: str, heads) -> str:
    """The text minus the named sections (a heading line to the next '## ' heading)."""
    lines, out, skip = text.split("\n"), [], False
    for ln in lines:
        if ln.startswith("## "):
            skip = ln.strip() in heads
        if not skip:
            out.append(ln)
    return "\n".join(out)


def checks(soul: str, allowed: str = "") -> List[str]:
    """Mechanical checks on the generated text (the fixed guardrail bullets are exempt; a banned word the author
    used in the description — `allowed` — is hers to use)."""
    body = soul
    for g in GUARDRAILS:
        body = body.replace(g, "")
    body = body.replace(SCRATCH_HEAD, "")   # the scratch instruction names its tag on purpose
    body = body.replace(WHO_LINE, "")
    core = _without_sections(body, DATED_SECTIONS)   # the dated sections carry years on purpose and are not prose
    found: List[str] = []
    for w in BANNED:
        n = body.count(w)
        if n and w in allowed:
            continue
        if n:
            found.append(f"含理論字或機器字「{w}」×{n}")
    # list numbering ("1. …", "2、…") is fine; digits inside sentences are not (ages, dates, scales)
    body_no_lists = re.sub(r"(?m)^\s*(?:[-・•]\s*)?\d+\s*[.、)]\s*", "", core)
    digits = re.findall(r"\d+", body_no_lists)
    if digits:
        found.append(f"含阿拉伯數字 {len(digits)} 處（{', '.join(digits[:6])}…）：年齡用中文數字，日期不進設定")
    drift = len(re.findall(r"(?:^|[，。；：\s])(?:她|他)(?:會|偏向|習慣|不會|常常|覺得|知道|說|先|只|也|很|就)", body, re.M))
    if drift >= 4:
        found.append(f"注意：第三人稱「她／他」當主詞 {drift} 處——設定應以「你」稱呼角色本人（模型的筆誤，可重跑該段）")
    n = len(_without_sections(soul, DATED_SECTIONS))   # prose budget; the dated sections are data and not counted
    if n < 2500:
        found.append(f"太短：{n} 字（目標 2,500–4,000，不計時間線）")
    elif n > 4000:
        found.append(f"太長：{n} 字（目標 2,500–4,000，不計時間線）")
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
    st = read_json(d / "build" / "structure.json", {}) or {}
    shared = [s for s in st.get("shared_seeds") or [] if isinstance(s, dict) and str(s.get("text") or "").strip()]
    conflicts: List[str] = []
    if shared:   # 0.12.0: the author's shared past is memory, so it is checked against the SOUL instead of written into it
        chk = ask(llm, d, "shared_check", "你是審稿人。只輸出 JSON。",
                  P_SHARED_CHECK.format(pr=pronoun(d), name=display(d), soul=soul, seeds="\n".join(f"- {s['text']}" for s in shared)))
        conflicts = [str(x).strip() for x in chk.get("conflicts") or [] if str(x).strip()]
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
    if shared:
        report += ["", f"## 共同經歷（{len(shared)} 條記憶）對設定"] + ([f"- {x}" for x in conflicts] or ["- 沒有對不上的地方"])
    write_text(d / "build" / "verify.md", "\n".join(report))
    write_json(d / "build" / "verify.json", {**data, "matches": hits, "total": total, "shared_conflicts": conflicts})
    print(f"verify: {hits}/{total} consistent; report in build/verify.md" + (f"; shared past: {len(conflicts)} conflict(s)" if shared else ""))
    return data


# ----------------------------------------------------------------------------- cli
def cmd_init(args: argparse.Namespace) -> int:
    d = cdir(args.name)
    if not re.match(r"^[a-z0-9_-]+$", args.name):
        raise SystemExit("id must be lowercase letters, digits, _ or -")
    if d.exists() and any(d.iterdir()):
        raise SystemExit(f"{d} already exists and is not empty")
    (d / "describe").mkdir(parents=True, exist_ok=True)
    src = TPL / "describe"
    for p in src.glob("*.md"):
        shutil.copy(p, d / "describe" / p.name)
    write_json(d / "companion.json", {"display_name": args.display, "avatar_model": args.avatar})
    write_json(d / "kokoro.json", {"address_default": "你"})
    prof = json.loads((TPL / "profile.json").read_text(encoding="utf-8"))
    prof["pronoun"] = args.pronoun
    write_json(d / "profile.json", prof)
    print(f"init: {d} — fill describe/*.md, then: soul_writer.py run {args.name} --phase all --yes")
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
    a.set_defaults(fn=cmd_init)
    r = sub.add_parser("run")
    r.add_argument("name")
    r.add_argument("--phase", default="all", choices=["all", *PHASES])
    r.add_argument("--from", dest="from_phase", default=None, choices=PHASES, help="run from this phase to the end (overrides --phase)")
    r.add_argument("--model", default=None, help="model name on the endpoint (default: the 寫靈魂 connection in home/models.json)")
    r.add_argument("--base-url", default=None, help="OpenAI-compatible /v1 endpoint (default: the same connection)")
    r.add_argument("--temperature", type=float, default=0.4)
    r.add_argument("--timeout", type=float, default=900, help="per call; a slow endpoint can take minutes on the parts phase")
    r.add_argument("--yes", action="store_true", help="accept proposals into empty profile fields; continue past a thin intake")
    r.add_argument("--force", action="store_true", help="write SOUL.md even when the checks fail")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check")
    c.add_argument("name")
    c.set_defaults(fn=cmd_check)
    sp = sub.add_parser("simple", help="the simple path: sliders, choices and three boxes from profile.json, no model")
    sp.add_argument("name")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=lambda a: (phase_simple(cdir(a.name), a.force) and 0) or 0)
    s = sub.add_parser("status")
    s.add_argument("name")
    s.set_defaults(fn=cmd_status)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
