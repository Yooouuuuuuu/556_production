"""psyche.events — the event turn (inner-life.md §16, §0): how she speaks first.

The engine composes the facts of the occasion and posts them to HER OWN api_server as a user turn in
her one conversation, tagged X-556-Event. She writes the message in her own words, or stays quiet with
「（沉默）」. 556d's follower shows her words with a 主動 badge and sends them to Telegram on the same
path as the app mirror; kokoro skips the observe for these turns; the psyche hooks record 'sent' or
'silent' instead of appraising.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

EVENT_MARK = "【事件】"
SILENCE = "（沉默）"

REASONS = {
    "reminder": "{term}之前請她在這個時間提醒他：{what}",
    "return_promise": "她之前跟{term}說「等我一下」，現在忙完了，回來找他",
    "care": "{term}說過的事到了：{what}，她想關心一下",
    "share": "她今天有件事想告訴{term}：{what}",
    "longing": "有一陣子沒跟{term}說到話了，她想找他",
    "olive_branch": "之前的事她還有點在意，但想主動給個台階",
}
# an event-turn "reply" that is really a platform error (e.g. the model invented a tool): not her words
ERRORISH = ("Model generated invalid tool call", "does not exist. Available tools", "Tool '", "[error", "Error:")


def compose(kind: str, *, term: str, what: str, now_text: str, extra: str = "", pronoun: str = "她") -> str:
    """A narrator's cue, not an instruction to "send a message" — worded that way, Gemini invents a reply tool."""
    reason = REASONS.get(kind, "{what}").format(term=term, what=what).replace("她", pronoun)
    lines = [f"{EVENT_MARK}（旁白，不是{term}說的話）現在是 {now_text}。{reason}。"]
    if extra:
        lines.append(extra)
    lines.append(f"{pronoun}會開口對{term}說什麼？請直接以{pronoun}的口吻寫出那一兩句話，當作這一回合的回覆；這裡沒有任何工具可用，也不需要。"
                 f"不要提到這段旁白，不要說自己被提醒或被設定；如果依{pronoun}現在的狀態判斷此刻不該打擾，只回「{SILENCE}」。")
    return "\n".join(lines)


def is_event_turn(user_text: str) -> bool:
    return bool(user_text) and user_text.lstrip().startswith(EVENT_MARK)


def is_silence(reply: str) -> bool:
    """Her event-turn answer that is not a message: silence, or a system error the platform returned."""
    r = (reply or "").strip().strip("「」\"'")
    if not r or r == SILENCE.strip("（）") or r == SILENCE or r.startswith(SILENCE) or r in ("沉默", "(沉默)"):
        return True
    return any(r.startswith(e) or e in r for e in ERRORISH)


def api_base() -> Tuple[str, str]:
    host = os.environ.get("API_SERVER_HOST", "127.0.0.1")
    port = os.environ.get("API_SERVER_PORT", "")
    key = os.environ.get("API_SERVER_KEY", "")
    return (f"http://{host}:{port}" if port else ""), key


def live_session_id(state_db: Path) -> Optional[str]:
    """Her one conversation: the newest session that has not ended (556d opens it at her start)."""
    try:
        c = sqlite3.connect(str(state_db), timeout=5)
        try:
            r = c.execute("SELECT id FROM sessions WHERE ended_at IS NULL ORDER BY COALESCE(last_activity_at, started_at) DESC, rowid DESC LIMIT 1").fetchone()
        finally:
            c.close()
        return str(r[0]) if r else None
    except Exception:
        return None


def counterpart_session(hub: str, companion: str, counterpart: str, timeout: float = 20.0) -> Optional[str]:
    """Her conversation with another character lives in her own state.db (key 556:agent:<name>); 556d opens
    and stamps it, like it opens her conversation with you."""
    if not hub:
        return None
    req = urllib.request.Request(hub.rstrip("/") + "/api/relay/session", data=json.dumps({"companion": companion, "counterpart": counterpart}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (json.loads(r.read().decode()) or {}).get("session_id") or None
    except Exception:  # noqa: BLE001
        return None


def relay(hub: str, sender: str, to: str, text: str, timeout: float = 20.0) -> Optional[str]:
    """Hand a message she wrote for another character to 556d, which carries the conversation on."""
    if not hub:
        return "no hub"
    req = urllib.request.Request(hub.rstrip("/") + "/api/relay", data=json.dumps({"from": sender, "to": to, "text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        return None
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def send(base: str, key: str, session_id: str, text: str, timeout: float = 180.0) -> Tuple[str, Optional[str]]:
    """POST the event turn through her API; returns (reply text, error). The hooks do the bookkeeping."""
    body = {"model": "556", "stream": False, "messages": [{"role": "user", "content": text}]}
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                          "X-Hermes-Session-Id": session_id, "X-556-Event": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        return (data.get("choices") or [{}])[0].get("message", {}).get("content") or "", None
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}"
