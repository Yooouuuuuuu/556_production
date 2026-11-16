"""Not every message gets a reply (docs/inner-life/when-to-reply.md).

One rule for every character, carried by the state block (回不回 line); how easily she lets a closer go is
derived from her big5 and the moment (busy, tired, mood, wanting to talk, closeness), never set per character.
Her answer may be text, silence (the whole reply is NO_REPLY — Hermes's gateway already drops it), or one
reaction ([REACT 🤣] — turned into NO_REPLY here and a reaction on your message by the plugin).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

NO_REPLY = "NO_REPLY"
# Hermes gateway/response_filters.py LIVE_GATEWAY_SILENT_MARKERS: an exact whole reply is dropped, not sent
SILENT_MARKERS = frozenset({"[SILENT]", "SILENT", "NO_REPLY", "NO REPLY"})

# Telegram's fixed reaction set (Bot API ReactionTypeEmoji); anything else is mapped or becomes silence
TELEGRAM_REACTIONS = frozenset(
    "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 "
    "👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 🤷‍♀ 😡".split())
NEAREST = {"😂": "🤣", "😆": "😁", "😄": "😁", "😃": "😁", "😀": "😁", "😅": "😁", "🙂": "😁", "😊": "🥰", "☺": "🥰",
           "🥹": "🥰", "💕": "❤", "💖": "❤", "💗": "❤", "💓": "❤", "😚": "😘", "😙": "😘", "😥": "😢", "😞": "😢",
           "😔": "😢", "🥲": "😢", "😮": "😱", "😲": "😱", "😠": "😡", "🙄": "🤨", "😑": "😐", "😶": "😐", "💪": "👏",
           "✌": "👌", "🆗": "👌", "👋": "🤗", "🎊": "🎉", "🥳": "🎉", "😪": "😴", "🤭": "🙈", "😳": "🙈"}

_REACT = re.compile(r"\[\s*REACT\s*:?\s*([^\]]{1,16})\]", re.IGNORECASE)
_SILENT_ANY = re.compile(r"\[SILENT\]|\bNO[_ ]REPLY\b", re.IGNORECASE)


def _canon(s: str) -> str:
    return " ".join(s.strip().strip("「」\"'`*.。!！").upper().split())


def is_silent(text: Optional[str]) -> bool:
    """The whole reply is a silence marker (the same set the gateway drops)."""
    t = (text or "").strip()
    return 0 < len(t) <= 64 and _canon(t) in SILENT_MARKERS


def reaction_emoji(raw: str) -> Optional[str]:
    """One emoji Telegram accepts: as given, with skin tone / variation selector removed, or the nearest one."""
    e = "".join(ch for ch in raw.strip() if ch not in "️︎" and not (0x1F3FB <= ord(ch) <= 0x1F3FF)).strip()
    if not e:
        return None
    if e in TELEGRAM_REACTIONS:
        return e
    if e in NEAREST:
        return NEAREST[e]
    first = e[0]
    if first in TELEGRAM_REACTIONS:
        return first
    return NEAREST.get(first)


def parse(text: Optional[str]) -> Tuple[str, Optional[str], str]:
    """(kind, emoji, text): kind 'silent' | 'react' | 'text'. A reaction that Telegram cannot show is silence.
    A marker mixed with words is dropped and the words are sent."""
    t = (text or "").strip()
    if is_silent(t):
        return "silent", None, ""
    m = _REACT.fullmatch(t)
    if m:
        e = reaction_emoji(m.group(1))
        return ("react", e, "") if e else ("silent", None, "")
    if _REACT.search(t) or _SILENT_ANY.search(t):
        rest = _SILENT_ANY.sub("", _REACT.sub("", t)).strip()
        return ("text", None, rest) if rest else ("silent", None, "")
    return "text", None, t


def tendency(*, extraversion: float, agreeableness: float, busy: bool, said_wait: bool, low_energy: bool,
             pleasure: float, want_talk: float, bond: float, worn_out: bool) -> float:
    """< 0 lets closers go, > 0 picks them up. Same formula for everyone; the numbers are hers."""
    s = 0.6 * (extraversion - 0.5) + 0.3 * (agreeableness - 0.5) + 0.2 * (bond - 0.5)
    s += 0.4 * max(0.0, want_talk - 0.3)
    s += 0.2 * pleasure
    if busy:
        s -= 0.5
    if said_wait:
        s -= 0.3
    if low_energy:
        s -= 0.3
    if worn_out:
        s -= 0.3
    return s


def line(*, pr: str, term: str, lean: float, silent_streak: int) -> str:
    """The 回不回 line of the state block."""
    you = "妳" if pr == "她" else "你"
    rule = (f"不是每則都要回。{term}只是在收尾（好啦、晚安、謝謝、單一個表情或貼圖），沒問{you}什麼、沒帶情緒也沒帶新的事時，"
            f"可以不回（整則只寫 {NO_REPLY}），或只按個表情（整則只寫 [REACT 表情]，例如 [REACT 🤣]）；"
            f"有問題、有情緒、有新消息、或{you}答應過要回的，一定要用文字回")
    if silent_streak >= 2:
        hint = "已經兩則沒用文字回了，這則有內容就回"
    elif lean <= -0.3:
        hint = "現在收尾的訊息多半不回，頂多按個表情"
    elif lean >= 0.3:
        hint = "現在想聊，收尾也可能接一句"
    else:
        hint = ""
    return "回不回：" + rule + (f"；{hint}" if hint else "")


def recent_answer(assistant_text: str, kind: str, emoji: Optional[str]) -> str:
    """What the recent-turns ring and appraisal see for a turn she did not answer in words."""
    if kind == "react":
        return f"（沒回字，按了 {emoji}）"
    if kind == "silent":
        return "（沒回）"
    return assistant_text


def silent_streak(recent: list) -> int:
    n = 0
    for _u, a in reversed(recent or []):
        if isinstance(a, str) and a.startswith("（沒回"):
            n += 1
        else:
            break
    return n

