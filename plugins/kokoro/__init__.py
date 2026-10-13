"""kokoro — 556 Production's memory provider for Hermes, on KeepsakeDB (her heart).

L3 glue only: Hermes hooks -> KeepsakeDB. prefetch() -> the Long-term memory block for the
turn (hybrid recall, trust labels, archived topics as meta-info); sync_turn() -> the L2 pipeline
observes the completed turn (runs on Hermes's serialized memory worker, so it is synchronous
here); on_session_end() closes consent windows. Config: $HERMES_HOME/kokoro.json.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt

logger = logging.getLogger(__name__)

_CONFIG_NAME = "kokoro.json"
_GLYPH = "💗"


def _turn_key(session_id: str, user_text: str, assistant_text: str) -> str:
    """Stamped on this turn's memories (meta.turn_id). Mirrors plugins/psyche/appraisal.turn_key, which the
    psyche engine computes from the same post_llm_call texts, so emotion is aligned with memory later."""
    import hashlib
    h = hashlib.sha1(f"{session_id}|{(user_text or '')[:300]}|{(assistant_text or '')[:300]}".encode("utf-8"))
    return h.hexdigest()[:12]


def _read_config(hermes_home: Path) -> Dict[str, Any]:
    p = hermes_home / _CONFIG_NAME
    if not p.exists():
        return {}
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


class KokoroMemoryProvider(MemoryProvider):
    def __init__(self) -> None:
        self._cfg: Dict[str, Any] = {}
        self._home: Optional[Path] = None
        self._store = None
        self._pipeline = None
        self._pipelines: Dict[str, Any] = {}      # per other character (subject = their name)
        self._cp_cache: Dict[str, str] = {}       # session id -> counterpart id
        self._agent_context = "primary"
        self._last_count = 0
        self._turn_lock = threading.Lock()   # in-flight observe; shutdown waits for it

    @property
    def name(self) -> str:
        return "kokoro"

    # -- availability --------------------------------------------------------
    def is_available(self) -> bool:
        try:
            from hermes_constants import get_hermes_home
            import keepsakedb  # noqa: F401
            return (get_hermes_home() / _CONFIG_NAME).exists()
        except Exception:
            return False

    def unavailable_reason(self) -> str:
        try:
            import keepsakedb  # noqa: F401
        except Exception:
            return "keepsakedb is not installed in the Hermes venv (uv pip install -e D:/dev/KeepsakeDB)"
        return f"{_CONFIG_NAME} missing in HERMES_HOME"

    # -- lifecycle -----------------------------------------------------------
    def initialize(self, session_id: str, **kwargs) -> None:
        from keepsakedb import Keepsake, configure_logging
        from keepsakedb.embedders import OpenAIEmbedder
        from keepsakedb.llms import OpenAIChat
        from keepsakedb.pipeline import Pipeline, PipelineConfig

        self._home = Path(kwargs["hermes_home"])
        self._cfg = cfg = _read_config(self._home)
        self._agent_context = kwargs.get("agent_context", "primary")
        profile = kwargs.get("agent_identity") or "default"
        db = self._home / cfg.get("db", "memory/{profile}.db").format(profile=profile)
        db.parent.mkdir(parents=True, exist_ok=True)
        if cfg.get("log"):
            log_path = self._home / cfg["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if not any(getattr(h, "baseFilename", None) == str(log_path)
                       for h in logging.getLogger("keepsakedb").handlers):
                configure_logging(str(log_path))

        e = cfg.get("embedder", {})
        embedder = OpenAIEmbedder(e.get("base_url", "http://127.0.0.1:55602/v1"), e.get("model", "bge-m3"),
                                  api_key=e.get("api_key", ""), batch_size=int(e.get("batch_size", 32)),
                                  timeout=float(e.get("timeout", 60)), dims=e.get("dims"))
        owner = self._agent_context == "primary"
        backup_dir = str(self._home / cfg["backup_dir"]) if cfg.get("backup_dir") else None
        self._store = Keepsake(
            str(db), embedder=embedder, tokenizer=cfg.get("tokenizer", "bigram"),
            dims=e.get("dims"), rrf_k=float(cfg.get("rrf_k", 60)), high=float(cfg.get("high", 0.60)),
            drop=float(cfg.get("drop", 0.40)), oversample=int(cfg.get("oversample", 3)), owner=owner,
            backup_dir=backup_dir, snapshot_text_only=bool(cfg.get("snapshot_text_only", False)),
            log_searches=bool(cfg.get("log_searches", True)), log_pipeline=bool(cfg.get("log_pipeline", True)),
            log_retention_days=cfg.get("log_retention_days", 90), slow_ms=float(cfg.get("slow_ms", 50)),
            reindex_on_mismatch=True,  # you may change the tokenizer in Settings; the store follows
        )
        if owner:
            self._store.start_owner_loop(float(cfg.get("owner_poll_s", 1.0)))
        l = cfg.get("llm", {})
        llm = OpenAIChat(l.get("base_url", "http://127.0.0.1:18765/v1"), l.get("model", "agy/gemini-3.8-flash"),
                         api_key=l.get("api_key", "local-proxy-no-key"), temperature=float(l.get("temperature", 0.0)),
                         timeout=float(l.get("timeout", 60)), json_mode=bool(l.get("json_mode", False)))
        # which surface this agent serves — stamped on short-layer notes (meta only, never the text)
        platform = str(kwargs.get("platform") or "cli")
        surfaces = {"api_server": "事務所", "telegram": "Telegram", "discord": "Discord", "cli": "終端機"}
        surfaces.update(cfg.get("surface_names", {}) or {})
        self._pipeline = Pipeline(self._store, llm, PipelineConfig(
            language=cfg.get("language", "zh-TW"), max_candidates=int(cfg.get("max_candidates", 8)),
            consent_turns=int(cfg.get("consent_turns", 100)), context_k=int(cfg.get("context_k", 5)),
            subject=cfg.get("subject") or None,            # fixed subject word in stored memories (你)
            user_name=self._your_name(cfg) or None,          # prompt-layer only; written through from Settings
            render_subject=self._address_term(cfg),         # how she refers to you when memories are injected
            retries=int(cfg.get("llm_retries", 1)),
            short_layer=bool(cfg.get("short_layer", True)), short_k=int(cfg.get("short_k", 5)),
            short_cap=int(cfg.get("short_cap", 1000)), surface=surfaces.get(platform, platform),
        ))
        logger.info("kokoro: %s (%d memories, owner=%s, language=%s)", db, self._store.count(), owner,
                    self._pipeline.cfg.language)

    def system_prompt_block(self) -> str:
        return self._memory_block_text() + self._your_profile_block()

    @staticmethod
    def _your_name(cfg: Dict[str, Any]) -> str:
        return str(cfg.get("your_name") or cfg.get("producer_name") or "").strip()

    def _address_term(self, cfg: Dict[str, Any]) -> str:
        """What she calls you: your name from Settings, else the role term (default 製作人)."""
        return self._your_name(cfg) or str(cfg.get("address_default") or "製作人").strip()

    def _render(self, text: str) -> str:
        """Stored memories say 你; in anything she reads, 你 becomes her term for you."""
        subj = self._pipeline.subject if self._pipeline else None
        term = self._address_term(self._cfg)
        return text.replace(subj, term) if subj and term and term != subj else text

    def _your_profile_block(self) -> str:
        """people/你.md (formerly memories/USER.md) — your profile the app maintains (name, reply language). Hermes's
        built-in memory writer is off in 556 (one memory system), so kokoro carries the profile."""
        if not self._home:
            return ""
        try:
            text = ""
            for rel in (("people", "你.md"), ("memories", "USER.md")):
                p = self._home.joinpath(*rel)
                if p.exists():
                    text = p.read_text(encoding="utf-8").strip()
                    break
        except Exception:
            return ""
        term = self._address_term(self._cfg)
        return f"\n\nAbout {term} — the person you are talking to (profile maintained in the app):\n" + text[:2000] if text else ""

    # -- counterparts (0.7.0): her session with you, or a session 556d keyed 556:agent:<name> ---------
    def _counterpart_of(self, session_id: str) -> str:
        if not session_id or not self._home:
            return "你"
        if session_id in self._cp_cache:
            return self._cp_cache[session_id]
        cp = "你"
        try:
            import sqlite3
            c = sqlite3.connect(f"file:{(self._home / 'state.db').as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                r = c.execute("SELECT session_key FROM sessions WHERE id = ?", (session_id,)).fetchone()
            finally:
                c.close()
            key = str(r[0] or "") if r else ""
            if key.startswith("556:agent:"):
                cp = key[len("556:agent:"):] or "你"
        except Exception:
            pass
        self._cp_cache[session_id] = cp
        return cp

    def _display_name(self, profile: str) -> str:
        try:
            cj = json.loads((self._home.parent / profile / "companion.json").read_text(encoding="utf-8-sig"))
            return str(cj.get("display_name") or profile)
        except Exception:
            return profile

    def _pipeline_for(self, counterpart: str):
        """Memories about another character are written with that character's name as the subject; the
        store is shared (one file per character), only the pipeline's subject word differs."""
        if counterpart == "你" or self._pipeline is None:
            return self._pipeline
        pl = self._pipelines.get(counterpart)
        if pl is None:
            from keepsakedb.pipeline import Pipeline, PipelineConfig
            base = self._pipeline.cfg
            name = self._display_name(counterpart)
            pl = Pipeline(self._store, self._pipeline.llm, PipelineConfig(
                language=base.language, max_candidates=base.max_candidates, consent_turns=base.consent_turns, context_k=base.context_k,
                subject=name, user_name=None, render_subject=None, retries=base.retries, short_layer=base.short_layer,
                short_k=base.short_k, short_cap=base.short_cap, surface=f"跟{name}的對話"))
            pl.subject = name  # the store's meta subject is 你; this pipeline speaks about the other character
            self._pipelines[counterpart] = pl
        return pl

    def _person_block(self, counterpart: str) -> str:
        if not self._home or counterpart == "你":
            return ""
        try:
            p = self._home / "people" / f"{counterpart}.md"
            text = p.read_text(encoding="utf-8").strip() if p.exists() else ""
        except Exception:
            return ""
        return f"\n\nAbout {self._display_name(counterpart)} — the character you are talking to now (her person file):\n" + text[:2000] if text else ""

    def _memory_block_text(self) -> str:
        return (self._cfg.get("system_prompt_block") or
                "Memory about the user is injected per turn as a 'Memory' block: 'Facts (long-term)' with "
                "trust labels ([high] = certain, plain = likely) and 'Notes (recent, dated)' — one line per "
                "past turn that seemed worth keeping. Priority when they disagree: the conversation itself is "
                "ground truth; otherwise the NEWEST entry wins, whatever its kind; a fact beats a note only "
                "on a tie. '[archived: …]' lines are topics the user asked not to bring up — never recite "
                "them, offer to talk about them only if the user touches the topic. Use kokoro_search for "
                "anything not in the block.")

    # -- per turn ------------------------------------------------------------
    def prefetch(self, query: str, *, session_id: str = "") -> str:
        self._last_count = 0
        if self._store is None or is_trivial_prompt(query):
            return ""
        cp = self._counterpart_of(session_id)
        pl = self._pipeline_for(cp)
        k = pl.cfg.context_k
        try:
            block = pl.context_for(query, k) + self._person_block(cp)
        except Exception as exc:  # embedder down: lexical recall still works
            logger.warning("kokoro prefetch fell back to BM25: %s", exc)
            try:
                block = self._store.context(query, k, mode="bm25")
            except Exception as exc2:
                logger.warning("kokoro prefetch failed: %s", exc2)
                return ""
        self._last_count = sum(1 for line in block.splitlines() if line.startswith("- "))
        return block

    def recall_status(self) -> Optional[RecallStatus]:
        return RecallStatus("Kokoro", self._last_count, glyph=_GLYPH) if self._last_count else None

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "", **kwargs) -> None:
        """Runs on Hermes's serialized memory worker, so the observe is synchronous here."""
        if self._pipeline is None or self._agent_context != "primary":
            return
        if (user_content or "").lstrip().startswith("【事件】"):
            return  # her own event turn (psyche speaks first): nothing you said, nothing to remember about you
        cp = self._counterpart_of(session_id)
        pl = self._pipeline_for(cp)
        with self._turn_lock:
            res = pl.observe(user_content, assistant_content,
                             turn_id=_turn_key(session_id, user_content, assistant_content),
                             source=(pl.subject if cp == "你" else self._display_name(cp)) or None)
        if res.error:
            logger.warning("kokoro observe error: %s", res.error)
        elif res.applied:
            logger.info("kokoro observe: %s", "; ".join(f"{o['op']}" + (f" #{o.get('id')}" if o.get("id") else "")
                                                        for o in res.applied))

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if self._pipeline is not None:
            self._pipeline.end_session()

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        return ""  # every turn was already observed; nothing to extract from the compressed span

    # -- tools ---------------------------------------------------------------
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        if not self._cfg.get("tools", True):
            return []
        return [
            {"name": "kokoro_search",
             "description": ("Search the user's long-term memories (hybrid: meaning + exact words). Use it "
                             "when a question may depend on something the user told you before that is "
                             "not in the injected memory block; vary the wording for multi-part questions."),
             "parameters": {"type": "object", "properties": {
                 "query": {"type": "string", "description": "What to look for."},
                 "k": {"type": "integer", "description": "Max results (default 5, max 20)."},
                 "layer": {"type": "string", "enum": ["long", "short"],
                           "description": "long = facts, short = dated notes of past turns; omit for both."}},
                 "required": ["query"]}},
            {"name": "kokoro_forget",
             "description": ("Permanently delete a memory by id (from kokoro_search) when the user explicitly "
                             "asks you to forget it. For 'please don't bring that up' do NOT delete — the "
                             "memory pipeline archives such topics automatically."),
             "parameters": {"type": "object", "properties": {
                 "id": {"type": "integer", "description": "Memory id."},
                 "reason": {"type": "string", "description": "The user's words, briefly."}},
                 "required": ["id"]}},
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if self._store is None:
            return json.dumps({"error": "memory not initialized"})
        try:
            if tool_name == "kokoro_search":
                k = max(1, min(int(args.get("k", 5) or 5), 20))
                layer = args.get("layer") if args.get("layer") in ("long", "short") else None
                hits = self._store.search(str(args.get("query", "")), k=k, archived="meta", layer=layer)
                return json.dumps({"results": [
                    {"id": m.id, "text": self._render(m.text), "tags": m.tags, "label": m.label, "layer": m.layer,
                     "archived_reason": m.archive_reason if m.archived else None,
                     "dense": None if m.dense is None else round(m.dense, 3),
                     "bm25": None if m.bm25 is None else round(m.bm25, 2)} for m in hits]}, ensure_ascii=False)
            if tool_name == "kokoro_forget":
                n = self._store.delete([int(args["id"])], reason=str(args.get("reason", "user asked via tool")))
                return json.dumps({"deleted": n})
        except Exception as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps({"error": f"unknown tool {tool_name}"})

    # -- shutdown ------------------------------------------------------------
    def shutdown(self) -> None:
        if self._store is None:
            return
        # an observe may still be running on the memory worker: wait for it so the write lands
        got = self._turn_lock.acquire(timeout=float(self._cfg.get("shutdown_wait_s", 90)))
        try:
            self._store.close()
        finally:
            if got:
                self._turn_lock.release()
        self._store = None
        self._pipeline = None

    def backup_paths(self) -> List[str]:
        return []  # everything lives under HERMES_HOME (memory/, backups/, logs/)


def register(ctx) -> None:
    ctx.register_memory_provider(KokoroMemoryProvider())
