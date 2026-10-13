# Memory design — PLAN OF RECORD (decided 2026-09-30)

Research trail: `memory-notes.md`. This doc is the decided design.

## The five-tier stack (who writes what; conflicts resolve top-down)

| Tier | What | Written by |
|---|---|---|
| Spirit card — `SOUL.md` (+ ST card import later) | identity, voice, habits | **human only** (frozen core) |
| Lorebook (later, ST-style keyword triggers) | world-setting, canon | human; deterministic injection |
| Curated head — `MEMORY.md`/`USER.md` | top learned facts, always injected | her (background review) |
| **DB tier — this doc** | long-tail facts, retrieved per turn | extraction pipeline |
| FTS5 sessions | verbatim archive | automatic |

Wardrobe = skills/procedures — a parallel track, NOT conversational memory.

## Path A — IMPLEMENTED & VERIFIED 2026-09-30 ✅

End-to-end proof: explicit `mem0_add` ✓ · Qdrant store at `home\mem0_qdrant` ✓ · fresh-session
semantic recall via pure paraphrase ("pet"→cat 0.65, "live"→Hsinchu 0.46) ✓ · **implicit always-on
extraction from casual 繁中 chat** (「下個月要去東京玩一週」 auto-became "Planning a 1-week trip to
Tokyo next month; wants to practice Japanese") ✓ · sane ranking (travel query: trip 0.60 > move
0.42 > cat 0.39) ✓. Note: mem0 stores facts in English regardless of chat language (bge-m3 is
cross-lingual so recall works; memory language belongs to the roadmap's "language issues" step).

## Path A design: mem0 + embedded Qdrant

- `memory.provider: "mem0"` in the 556_production profile; config in `home\mem0.json` (per-profile).
- **Embedder**: bge-m3 GGUF on **CPU** via a `llama-server --embedding` sidecar (OpenAI-compatible
  :18768). No Ollama (separate app ≠ single-exe goal); GPU kept free for the media slice.
- **Extraction LLM**: `agyapi/gemini-3.8-flash` DIRECT to the proxy :18765 (no tools needed for
  extraction, so no shim translation required). Chosen by test 2026-09-30: matched 3.1-pro's
  accuracy at 4× the speed (3.1-pro: 19.5s, over-captured short-term events). Ceiling option if
  quality ever disappoints: claude-sonnet-4-6 (best habit-capture in test, tokens scarce).
- **Vector store**: Qdrant embedded at `home\mem0_qdrant\` (per-profile isolation; NOT the global
  `~/.hermes` default).
- **Write mode: always-on** (`memory.write_approval: false`). Post-moderation instead of gating:
  `hermes memory` to inspect, conversational correction (supersede/UPDATE), and later a daily
  "what I learned about you today" digest cron. write_approval stays available as a debug mode.
- Keyword leg in the interim: existing FTS5 session search (CJK-capable).

## 1000-round zh-TW endurance test (2026-09-30, tests/memory_stress.py)

Fresh session every round (hardest condition). Exam after 100 rounds: **20/20** incl. all 5
correction traps. Exam after 1000 (with ~400 varied restatements as dedup pressure): **19/20**.
Store growth 41 → 50 entries; identical-fact restatements deduped ~perfectly (「不吃香菜」×15+
stayed one entry); latency stable, no degradation, no crashes across 1000 sessions.

**Failure modes found → Path C write-pipeline requirements:**
1. **Temporal conflict loss (the 19/20 miss)**: after the half→full marathon correction, later
   restatements of the STALE fact were stored as fresh confirmations; repetition buried the
   correction and final recall regressed to "half". C must do conflict detection on write
   (new fact contradicts stored → resolve explicitly, favoring corrections over repetitions).
2. **Assistant-advice leakage** (3 entries): extraction stored the assistant's own suggestions
   as user facts. C's extraction prompt must store user-facts only.
3. **Cross-language duplicate** (Japan trip stored once in zh, once in en): dedup must compare
   across languages (bge-m3 similarity check on write).
4. Episodic small talk gets stored but auto-DATED (bad day, traffic) — arguably companion-good;
   consider a decay/archival policy rather than blocking.

## Path C (TARGET): own hybrid engine, learned from Milvus (Apache-2.0, open source)

Custom Hermes `MemoryProvider` (4 hooks: sync_turn / prefetch / on_session_end / on_pre_compress):
- **Dense leg**: bge-m3 via **in-process llama-cpp-python** (no sidecar; single-exe friendly).
  Numpy brute-force cosine — at companion scale (≤100k facts) this equals a FLAT index.
- **Sparse leg**: SQLite FTS5 **BM25** (same algorithm Milvus Standalone advertises).
- **Fusion**: RRF (Milvus's default hybrid ranker, ~10 lines).
- **Trust labels (English)**, tiered on dense cosine, injected as a "Long-term memory" block:
  - score > **0.9** → `[high]` (must reflect)
  - 0.5–0.9 → plain (weave in naturally)
  - < **0.5** → dropped
  - Thresholds are CONFIG KNOBS with score logging; calibrating the trust line on real bge-m3
    score distributions is an explicit future task (Artemis used 0.7/0.5/0.3 on weaker embedders).
  - **First real data (2026-09-30, Path A tests)**: correct paraphrase recalls scored 0.46–0.65;
    an irrelevant hit scored 0.39. The originally proposed 0.9/0.5 would have dropped a correct
    fact (0.46) and labeled nothing high → initial knob values set to **high ≥ 0.60, drop < 0.40**;
    the calibration job stays open as more scores accumulate.
- Write path: our extraction prompts borrowing mem0's ADD/UPDATE/DELETE pattern + supersede-history.
- Migration A→C: read facts out of Qdrant, re-embed, done (minutes at our scale).
- Outgrow point (~1M vectors): graduate to real Milvus Standalone with the same conceptual model.

## Future after C: "C2" — tag-organized memory (noted 2026-09-30, user design; NOT now)

Read path unchanged. Write path becomes one LLM pass returning
`{remember?: bool, tag, merge_target?, op}`:
1. Worth remembering? (also enforces user-facts-only → fixes advice leakage)
2. Assign to an existing tag group (sports/travel/work/…) or create a new group.
3. Within the group, check merge with existing memories — conflict-aware merge
   (recency + explicit-correction outranks repetition) → fixes the temporal-conflict
   failure (the marathon 19/20 miss); merging restatements also bounds store growth.

Group mechanics enable topic-level operations. **Archive design (FINAL shape, user design
2026-09-30): archive = a TAG, not a place.**

- Archiving adds an `archived` tag alongside topic tags (marathon → [sports, archived]) and
  records a **group-level reason** ("user finds it painful" / "former company, sore subject").
  One store; memories stay embedded and searchable; purge = delete-by-tag.
- **Retrieval branches, not filters**: archived hits above threshold inject as META-INFO ONLY —
  `[archived: sports/marathon — reason — contents withheld; offer to discuss]` — never content.
  This powers her human-like consent line, the canonical UX:
  「我有記著喔——你的事無論大小我都記得。但那段對你來說不太好受，真的想聊嗎？」
  (or: "if I'm not mistaken that's about your former company — want to go deeper?")
  She never initiates archived topics; asking consent when the USER touches one is the design.
- **Consent opens a temp window: y turns (knob, e.g. 100), capped at session end** — the group
  behaves as active inside the window, then quietly re-archives. No recover ceremony for casual
  access; permanent recovery = natural language (「那個可以聊了」→ remove `archived` tag, log).
- Decayed episodic memories use the same tag with reason="decay"; touch-to-revive applies.
- Delete unchanged: user-commanded purge (one confirmation, hard delete by tag) — never
  automatic for suppressed groups; retention policy surfaces old untouched archived groups as
  purge CANDIDATES in the weekly digest for human veto (the actual infinite-growth bound).

## Rejected / parked

- **Milvus Lite**: no sparse/BM25/hybrid (Standalone-only), native Windows unsupported (py3.10-only
  CI). Weakest expression of the Milvus preference.
- **Milvus Standalone now**: Docker service — conflicts with the single-exe end goal; revisit only
  at C's outgrow point.
- **Ollama**: separate app install; same single-exe conflict.
- **Honcho / other providers**: one provider slot; mem0 (A) then ours (C).

## Constraints adopted (from the single-exe end goal)

Prefer in-process/embeddable components; no separate app installs (no Ollama, no Docker).
Realistic final packaging = one installer/launcher with bundled sidecars (roadmap item 5).

## Artemis features consciously inherited / dropped

- Inherited: trust-label injection (improved thresholds), per-character isolation, score-filtered
  top-5 retrieval, CPU embedding server pattern (interim only).
- Improved on: single bge-m3 replaces their dual small embedders; query-rewrite hook
  (`auxiliary.memory_query_rewrite`) + post-moderation visibility — they have neither.
- Dropped: proxy-side injection (provider prefetch covers it), 30-min markdown mirror (candidate
  digest-cron feature later).

## Language & embedder — user-changeable (decided 2026-09-30)

- `memory.language` per companion (default **zh-TW**; en selectable): the extraction prompt writes
  facts in this language. Never "mirror the input" — mixed-language stores defeat dedup.
- `memory.embedder` per install: default **bge-m3** (100+ languages incl. zh/ja/fr/en). **Anyone
  running a companion in another language must pair it with an embedder that covers that language**
  — the language knob and the embedder knob travel together. Changing the embedder means
  re-embedding the store (minutes at companion scale; the migration path A→C is the same tool).
- Standalone engine plan: see DECISIONS (2026-09-30 after 0.2.0) — separate Python library,
  layered so the DB core stays lightweight; 556 keeps `kokoro` as the provider name.
