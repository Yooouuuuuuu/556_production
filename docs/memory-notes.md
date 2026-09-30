# Memory — code-grounded findings & options (PARKED — for a later discussion)

Status: research complete 2026-09-29; **no decision made**. Everything below is verified against
the engine source (`hermes-agent\...`) or the Artemis repo unless flagged.

## A. What stock Hermes does today (engine internals)

**Curated files** (`tools/memory_tool_store.py`, config in `hermes_cli/config_defaults.py` §memory):
- `MEMORY.md` cap **2,200 chars** (~800 tok) + `USER.md` cap **1,375 chars** (~500 tok), per
  HERMES_HOME (= per profile → per character).
- Injected as a **load-time snapshot** into the volatile prompt tier (prefix-cache friendly;
  mid-session writes hit disk, not the live prompt).
- Every **10 user turns** (`memory.nudge_interval`) a nudge schedules the **background review
  fork** (`agent/background_review.py`): a daemon fork replays the turn (warm cache on the main
  model, or a 24-turn digest if routed to a different model) and may write ONLY through the
  `memory` + `skill_manage` tools (whitelist; 16-iteration / 600K-input-token caps).
- **Poisoning guards already exist**: load-time threat sanitization (`[BLOCKED: …]` placeholders
  in the snapshot) and `memory.write_approval: true` → background writes are **staged** for
  `/memory approve` instead of auto-applied (off by default).

**Session recall** (`hermes_state_fts.py` / `tools/session_search_tool.py`):
- FTS5 over **full transcripts** (tool-role rows excluded), three indexes incl. a **CJK-bigram
  tokenizer** → 繁中 keyword search works natively. BM25 + snippets, no LLM in the loop.
  Compacted turns remain searchable.

**Compression** (`agent/context_compressor.py`, config §compression): triggers at **50%** context
ratio (raised to 75% floor for <512K windows), protects first 3 + last 20 messages, summarizes the
middle via the `auxiliary.compression` model, "lean" tail 10K–25K tok, rewrites in place.
Richer than Artemis's SmartCrusher (flat 24-msg/40K-char cap).

## B. Semantic memory Hermes already ships (optional plugins, `memory.provider` — ONE at a time)

- **`mem0`** — the Artemis stack, in-process: mem0ai + **local embedded Qdrant**
  (`~/.hermes/mem0_qdrant`, no server) or pgvector. Default embedder is cloud
  `text-embedding-3-small` → needs a local/zh-capable embedder configured for our use.
  **This makes "Artemis-style memory" a config change, not a build.**
- **Honcho** (plastic-labs) — server-side dialectic user modeling; 5 tools (profile/search/
  reasoning/context/conclude). Cloud or self-hosted.
- Others: hindsight (embedded semantic + entity graph, ~1GB RAM), holographic (deterministic HRR,
  no learned embeddings), byterover/retaindb/supermemory/openviking (external services).
- **The core engine has NO built-in vector store** — FTS5 is the only shipped retrieval.

## C. What Artemis does (the reference we're measuring against)

mem0 over Qdrant; **CCR extraction every ~8 turns**; dual embeddings (BGE-small-zh-v1.5 +
all-MiniLM-L6-v2) on a CPU server; hybrid semantic+keyword search; per-character isolation via
`user_id` payload filter; recall priority **vector > daily notes > SOUL.md**; 30-min cron mirrors
Qdrant → `_mem0_auto.md` markdown; injection happens proxy-side (Headroom) so every frontend
shares it. Why Qdrant: it's mem0's default — light Rust binary, first-class payload filtering.
Nothing Qdrant-exclusive is used.

## D. The Wardrobe (user's schema — one candidate, NOT presumed adopted)

Scope = **procedural learning** (Closet/Wash/Stylist/Outfit/Tailor lifecycle for skills; Fit Notes
preference learning with verify-by-action). It touches episodic memory only through its principles
(supersede-don't-overwrite, review-gated writes) — which Hermes's `write_approval` already
partially implements. Design doc: `D:\Hermes\notes\learning-schema.md`.

## Simulation summary (Hermes stack vs Artemis, per scenario)

| Scenario | Verdict |
|---|---|
| Long-tail recall ("my cat, 3 months ago") | Artemis wins vs STOCK Hermes (bounded file evicts; FTS needs exact keywords). Erased by enabling any semantic provider (B). |
| Head-fact / identity coherence | Hermes wins — disciplined ~1.3K-token always-on injection beats per-turn retrieval noise. |
| Weak-model write fidelity | Both have LLM-in-write-path. User's own tests proved IQ3-Qwen digit corruption. Mitigation neither has by default: route curation through a **strong shim lane** (strong curates, weak chats). |
| Verbatim safety layer | Tie — Artemis daily-note markdown ≈ Hermes full transcripts in state.db. |
| Multi-character isolation | Tie — profiles ≈ `user_id` filters. |
| 繁中 recall | Artemis (zh embeddings) vs Hermes FTS CJK-bigram: embeddings win on paraphrase, FTS on exact terms. A zh-capable embedder closes it. |
| Preference learning | Wardrobe Fit Notes > both (neither has it). |
| Memory-poisoning surface | Hermes wins today (sanitizer + write_approval); Artemis auto-writes extracted facts unreviewed. |

## Options for the later discussion (no recommendation locked)

1. **Stock only** — zero work; weakest long-tail recall.
2. **Enable shipped mem0 plugin** (local Qdrant + local zh embedder, e.g. BGE-small-zh or bge-m3)
   — Artemis-parity for a config change. Open item: whether the plugin passes raw mem0
   `vector_store` config through (mem0ai upstream supports **Milvus** — user's preferred store);
   verify empirically.
3. **Custom `MemoryProvider` on Milvus Lite** — user's ecosystem, clean 4-hook interface
   (`agent/memory_provider.py`: sync_turn / prefetch / on_session_end / on_pre_compress); most
   control, some code.
4. **2 or 3 + `write_approval: true` + Wardrobe supersede/review conventions** — the audited,
   poisoning-guarded variant.

Not recommended: full Artemis transplant (external Qdrant server + custom proxy) — the plugin
makes it redundant. Honcho occupies the same single provider slot as mem0 → choose, or sequence.

## Appendix — name shortlist (undecided)

Greek (fits Hermes): Iris · Hestia · Echo | Japanese (fits the aesthetic): Tsumugi(紡) · Shiori |
Wardrobe-adjacent: Atelier · Loom
