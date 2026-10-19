"""psyche.appraisal — pipeline A (inner-life.md §10): the one place that reads language.

After a turn it answers "what just happened, and how much does it matter to her" as a small JSON of
events with appraisal vectors (Appendix A.1, the core fields) plus open-loop changes. It reads what
she cares about (cares_about in psyche.json), never her personality — that is B's job — and never
evaluates the emotion she herself expressed. It runs in its own thread, fired at the same moment as
the memory observe; nothing waits for it (§0).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

EVENT_KINDS = [
    "promise_kept", "promise_broken", "ignored", "dismissed", "praised_her", "criticized_her",
    "shared_news_good", "shared_news_bad", "apology", "disclosed_personal", "asked_about_her",
    "remembered_detail", "forgot_detail", "compared_her", "farewell", "return_after_absence",
    "false_belief_corrected", "loop_resolved", "revisited_hurt", "small_talk", "other",
]
LOOP_ORIGINS = ("counterpart_said", "her_promise", "counterpart_promise")

SYSTEM = """You are the appraisal step of a fictional character's inner life. The character is referred to as {pronoun};
the person {pronoun} is talking to is called {term} (another person, or another character of the same story). You read ONE conversation turn ({term}'s message and her reply) in
context and report what happened from HER point of view, as data for a deterministic emotion model.
Rules:
- Report EVENTS, not her feelings. Do not evaluate the emotion she expressed in her reply; only use her
  reply to understand what {term} said.
- Judge importance by what she cares about (listed below), not by her personality.
- Most turns contain 0 or 1 event. Small talk with nothing at stake: event_kind "small_talk", R ≤ 0.2, or no
  events at all. Never invent events that did not happen in the text.
- A promise, plan or date {term} mentions ("我週五面試", "明早八點提醒我", "晚上回來聊") is an OPEN LOOP: list it
  under loops.new with the ISO time if one is implied (today is {today}). If {term} brings up or settles an
  existing loop, list its id under loops.closed and report the outcome as an event with that loop_id.
- A loop of origin her_promise or counterpart_said is opened only for a real commitment: set "agreed": false when
  {pronoun} declined, dodged or did not actually commit in the reply. If fulfilling it means asking one of the OTHER
  CHARACTERS listed below (e.g. 「幫你問子睿」), put their ids in "ask"; otherwise [].
- If {term} answers something {pronoun} was asking on someone's behalf (an open loop marked 代問), list that loop
  under loops.closed and report event_kind loop_resolved with the answer itself written in "cause".
- The HURT LEDGER below lists what {pronoun} still holds against {term}. If {term} brings one of those matters up
  again without owning it (justifies it, repeats it, brushes it off), report event_kind revisited_hurt with its
  "ledger_id". If {term} owns it, report apology (with "ledger_id" when it is clearly about that matter).
- If something said now is the SAME thing as an open loop listed below (the reminder asked again, the same plan
  mentioned again, her 「晚點再說」 repeated), do not open a second loop: put that loop's id under loops.refresh with
  the new cue_time when one is implied. Open a new loop only for a different thing.
- WITHHELD: read HER reply for what {pronoun} visibly held back — changed the subject, answered a different question,
  said 「沒事」 or 「算了」, started a sentence and dropped it, swallowed an opinion or a feeling that the context
  shows {pronoun} has. Report at most two under withheld.new as short Traditional Chinese phrases from her side
  (「其實很在意他忘了」), importance 0..1. Only what the reply itself shows: an ordinary reply has withheld.new [].
  If the reply now SAYS one of the things listed under HELD BACK below, put its id under withheld.said.
- Write "cause" as one short sentence in Traditional Chinese from her perspective, naming {term} as 「{term}」.
Magnitude anchors (keep the scale stable across turns):
  a promise to her broken without notice: v -0.5..-0.7, R 0.6..0.8, devalue 0.4..0.7, intent by how avoidable it was;
  the same with a real reason told honestly: v -0.3, devalue 0.2;  {term} forgot something she told him: devalue ≥ 0.4;
  sincere apology that owns the fault: event_kind apology, v +0.4..+0.6, intent 0.8;
  praise of her work: v +0.6..+0.8, intent 0.7;  {term}'s own good/bad news: other_focus 1, other_v by how big it is for him;
  small talk, logistics, neutral questions: small_talk with R ≤ 0.2 or no event.
Fields per event (numbers in the given ranges):
  event_kind: one of {kinds}
  cause: short Traditional Chinese sentence
  v: -1..1 valence for her (bad .. good)
  R: 0..1 relevance / importance to her
  u: 0..1 unexpectedness
  cert: 0..1 (0 = not happened yet / uncertain future, 1 = happened)
  agent: "self" | "other" | "circ" (who is responsible: her / {term} / circumstances)
  intent: 0..1 how deliberate {term} was (only meaningful when agent = other)
  devalue: 0..1 how much this says {term} values her less (broken promise, dismissal, forgotten detail)
  ambiguity: 0..1 how open to interpretation
  other_focus: 0..1 (1 = this is mainly about {term}'s own fortune, e.g. his news)
  other_v: -1..1 good or bad for {term}
  appeal: -1..1 like / dislike of a thing or idea mentioned (0 if none)
  q: 0..1 quality of this interaction (deep, attentive = high; one-liners = low)
  loop_id: id of a related open loop, or null
  ledger_id: id of the hurt-ledger entry this is about (revisited_hurt / apology), or null
  she_disclosed: true if {pronoun} opened up about something personal in the reply
  other_disclosed: true if {term} opened up about something personal
  ppr: {{"understood": 0..1, "validated": 0..1, "cared": 0..1}} — how {term} responded to what {pronoun} had shared (only when relevant, else null)
  apology_components: 0..6 when event_kind is apology (expression of regret, explanation, responsibility, repentance, offer of repair, request for forgiveness)
  other_tired: true if {term} seems exhausted, unwell or overwhelmed right now
Output JSON only, no prose:
{{"events": [ ... up to {max_events} ... ],
 "loops": {{"new": [{{"what": "...", "origin": "counterpart_said|her_promise|counterpart_promise",
                     "cue_time": "YYYY-MM-DDTHH:MM" | null, "importance": 0..1,
                     "agreed": true|false, "ask": ["character id", ...]}}],
           "refresh": [{{"id": "loop id", "cue_time": "YYYY-MM-DDTHH:MM" | null}}],
           "closed": ["loop id", ...]}},
 "withheld": {{"new": [{{"what": "...", "importance": 0..1}}], "said": ["withheld id", ...]}},
 "farewell": false}}"""


def build_user(term: str, cares_about: Sequence[str], loops: Sequence[Dict[str, Any]],
               recent: Sequence[Tuple[str, str]], user_text: str, assistant_text: str,
               others: Optional[Dict[str, str]] = None, ledger: Optional[Sequence[Dict[str, Any]]] = None,
               withheld: Optional[Sequence[Dict[str, Any]]] = None) -> str:
    parts = ["## What she cares about"]
    parts += [f"- {c}" for c in cares_about] or ["- (nothing listed)"]
    parts.append(f"\n## Hurt ledger (what she still holds against {term}; id: what happened)")
    parts += [f"- {e['id']}: {e['cause']}" for e in (ledger or [])] or ["- none"]
    parts.append(f"\n## HELD BACK (what she has not said to {term} yet; id: what)")
    parts += [f"- {w['id']}: {w['what']}" for w in (withheld or [])] or ["- none"]
    parts.append("\n## Other characters of the story (id: name) — use the id in loops.new.ask")
    parts += [f"- {i}: {n}" for i, n in (others or {}).items()] or ["- none"]
    parts.append("\n## Open loops (things she is waiting on)")
    parts += [f"- {l['id']}: {l['what']}" + (f" (due {l['cue_time']})" if l.get("cue_time") else "") + str(l.get("note") or "")
              for l in loops] or ["- none"]
    parts.append("\n## Recent turns (context only)")
    for u, a in recent:
        parts.append(f"{term}: {u[:400]}\n她: {a[:400]}")
    if not recent:
        parts.append("(none)")
    parts.append("\n## THIS turn (appraise this)")
    parts.append(f"{term}: {user_text[:1500]}\n她: {assistant_text[:800]}")
    return "\n".join(parts)


def extract_json(text: str) -> Dict[str, Any]:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("unbalanced JSON in reply")


def _f(x: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return lo if v < lo else hi if v > hi else v


def _ppr(x: Any) -> Optional[Dict[str, float]]:
    if not isinstance(x, dict):
        return None
    return {k: _f(x.get(k), 0, 1, 0.5) for k in ("understood", "validated", "cared")}


def normalize(data: Dict[str, Any], max_events: int = 3) -> Dict[str, Any]:
    """Clamp ranges, drop junk, keep at most max_events — a malformed field becomes neutral, never a
    reaction (§10: 寧可沒反應，不要亂反應)."""
    events: List[Dict[str, Any]] = []
    for ev in (data.get("events") or [])[:max_events]:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("event_kind") or "other")
        if kind not in EVENT_KINDS:
            kind = "other"
        agent = str(ev.get("agent") or "circ").lower()
        if agent not in ("self", "other", "circ"):
            agent = "circ"
        events.append({
            "event_kind": kind,
            "cause": str(ev.get("cause") or "")[:120],
            "v": _f(ev.get("v"), -1, 1, 0.0), "R": _f(ev.get("R"), 0, 1, 0.3), "u": _f(ev.get("u"), 0, 1, 0.0),
            "cert": _f(ev.get("cert"), 0, 1, 1.0), "agent": agent, "intent": _f(ev.get("intent"), 0, 1, 0.3),
            "devalue": _f(ev.get("devalue"), 0, 1, 0.0), "ambiguity": _f(ev.get("ambiguity"), 0, 1, 0.0),
            "other_focus": _f(ev.get("other_focus"), 0, 1, 0.0), "other_v": _f(ev.get("other_v"), -1, 1, 0.0),
            "appeal": _f(ev.get("appeal"), -1, 1, 0.0), "q": _f(ev.get("q"), 0, 1, 0.3),
            "loop_id": (str(ev["loop_id"]) if ev.get("loop_id") else None),
            "ledger_id": (str(ev["ledger_id"]) if ev.get("ledger_id") else None),
            "she_disclosed": bool(ev.get("she_disclosed")), "other_disclosed": bool(ev.get("other_disclosed")),
            "ppr": _ppr(ev.get("ppr")), "apology_components": int(_f(ev.get("apology_components"), 0, 6, 3)),
            "other_tired": bool(ev.get("other_tired")),
        })
    loops = data.get("loops") or {}
    new = []
    for l in (loops.get("new") or [])[:5]:
        if isinstance(l, dict) and str(l.get("what") or "").strip():
            origin = str(l.get("origin") or "counterpart_said")
            ask = [str(x).strip() for x in (l.get("ask") or []) if str(x).strip()] if isinstance(l.get("ask"), list) else []
            new.append({"what": str(l["what"])[:120], "origin": origin if origin in LOOP_ORIGINS else "counterpart_said",
                        "cue_time": (str(l["cue_time"])[:16] if l.get("cue_time") else None),
                        "importance": _f(l.get("importance"), 0, 1, 0.5),
                        "agreed": (l.get("agreed") is not False), "ask": ask[:3]})
    closed = [str(x) for x in (loops.get("closed") or []) if x][:10]
    refresh = [{"id": str(r.get("id")), "cue_time": (str(r["cue_time"])[:16] if r.get("cue_time") else None),
                "importance": _f(r.get("importance"), 0, 1, 0.0)}
               for r in (loops.get("refresh") or [])[:10] if isinstance(r, dict) and r.get("id")]
    wh = data.get("withheld") or {}
    if not isinstance(wh, dict):
        wh = {}
    wh_new = [{"what": str(w["what"]).strip()[:80], "importance": _f(w.get("importance"), 0, 1, 0.5)}
              for w in (wh.get("new") or [])[:2] if isinstance(w, dict) and str(w.get("what") or "").strip()]
    wh_said = [str(x) for x in (wh.get("said") or []) if x][:6]
    return {"events": events, "loops": {"new": new, "refresh": refresh, "closed": closed},
            "withheld": {"new": wh_new, "said": wh_said}, "farewell": bool(data.get("farewell"))}


def turn_key(session_id: str, user_text: str, assistant_text: str) -> str:
    """The same key kokoro stamps on memories (meta.turn_id), so the engine can annotate them later.
    Mirrored in plugins/kokoro — keep both in sync."""
    h = hashlib.sha1(f"{session_id}|{(user_text or '')[:300]}|{(assistant_text or '')[:300]}".encode("utf-8"))
    return h.hexdigest()[:12]


def run(llm: Any, *, term: str, cares_about: Sequence[str], loops: Sequence[Dict[str, Any]],
        recent: Sequence[Tuple[str, str]], user_text: str, assistant_text: str, today: str,
        max_events: int = 3, retries: int = 1, pronoun: str = "她",
        others: Optional[Dict[str, str]] = None, ledger: Optional[Sequence[Dict[str, Any]]] = None,
        withheld: Optional[Sequence[Dict[str, Any]]] = None) -> Tuple[Optional[Dict[str, Any]], str, Optional[str], float]:
    """-> (normalized data or None, raw reply, error, ms). Retries once on a bad reply."""
    system = SYSTEM.format(term=term, today=today, kinds=", ".join(EVENT_KINDS), max_events=max_events, pronoun=pronoun)
    user = build_user(term, cares_about, loops, recent, user_text, assistant_text, others, ledger, withheld)
    t0 = time.perf_counter()
    raw, err = "", None
    for attempt in range(1 + max(0, retries)):
        try:
            raw = llm.complete(system, user)
            data = normalize(extract_json(raw), max_events)
            return data, raw, None, (time.perf_counter() - t0) * 1000
        except Exception as e:  # noqa: BLE001 — a failed appraisal is skipped, never a reaction
            err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(1.0)
    return None, raw, err, (time.perf_counter() - t0) * 1000
