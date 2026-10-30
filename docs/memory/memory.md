# Memory — history is not memory

Living doc. **Last verified 2026-10-19 (0.10.0)** against `plugins/kokoro/__init__.py`, `tools/seed-memories.py`,
`templates/companion/kokoro.json`, `556d/internal/api/connections.go` / `hygiene.go`, `556d/internal/memory/memory.go`,
`vendor/keepsakedb` 1.0.1 and `tests/test_kokoro_triggers.py`. Graph: `memory-layers.d2` (commentary in the last
section). Decision trail: `../DECISIONS.md`.

**Read this first — what changed since the plan of record (2026-09-30):**

- The engine is **KeepsakeDB 1.0.1**, the git submodule `vendor/keepsakedb` (its own repo is `D:\dev\KeepsakeDB`;
  `setup-vendor.ps1` installs it into the Hermes venv), behind the Hermes provider `plugins/kokoro`, linked into every
  profile as `home/profiles/<id>/plugins/kokoro` (a junction made by `new-companion.ps1`) with its config
  `home/profiles/<id>/kokoro.json`. Path A (mem0 + Qdrant) is history (its leftovers left the repo in 0.9.0);
  Path C became KeepsakeDB (2026-10-01/02).
- The "curated head" tier is off: Hermes's own MEMORY.md / USER.md writer is disabled (`memory.memory_enabled: false`,
  `memory.user_profile_enabled: false`, pinned into her `config.yaml` by 556d before every start). The person file
  (`people/你.md`, formerly `memories/USER.md`) and the memory rule are kokoro's zh-TW system-prompt section
  `kokoro.memory` (position `after_memory`, since 0.8.4) — once per session, not the per-turn block, not tied to a
  toolset.
- **Two layers** since 2026-10-03: long (tagged facts, trust labels, supersede/archive) and short (dated
  notes), one file, one observe call, searched concurrently. A recent-exchange layer was tried and removed:
  the last X turns are history, in Hermes's session store, shared by every surface.
- Memories about you are **stored with the subject word 你** and rendered as her term for you (`your_name`, else the
  character's own default term, `address_default` in her kokoro.json) when injected or shown (2026-10-07;
  `PipelineConfig.render_subject`, KeepsakeDB 1.0.1). The word is the store's (`meta.subject`): only the main pipeline
  may rename it (`migrate_subject=True`, from Settings); a conversation with another character runs a counterpart
  pipeline on the same store that passes `subject=None` and sets `pl.subject = <her name>`, so those memories name
  that character (KeepsakeDB 1.0.1; incident `../DECISIONS.md` 2026-10-14). There is no "self" subject: what she
  herself holds to is SOUL text, not a memory row.
- Since 0.7.7 a memory can be **held** (`meta.hold`): kept and embedded, still a dedupe candidate for the observe, but never
  injected and never hinted at — the psyche engine holds a turn's memories while a hurt from that turn is on its ledger,
  and releases them when the entry closes (forgiven by time: tagged `舊帳` with the date and rendered with a
  「（舊帳 …）」 prefix; repaired: plain). KeepsakeDB 1.0.1 `hold` / `patch` commands (the psyche engine queues them in
  the store's `commands` table, so kokoro stays the one writer), `Memory.held`, `meta.prefix`.
- Since 0.7.0 the store is shared across her counterparts: memories about another character are written with that
  character's name as the subject (one kokoro pipeline per counterpart, same file, surface 跟<name>的對話), and the
  other's person file (`people/<id>.md`) is injected in those conversations behind the line 現在跟你說話的是<name>.
- Her *state* (how she is now) is not memory either: it lives in `psyche.db`
  (`../inner-life/inner-life.md`). Since 0.5.0 every memory a turn writes carries `meta.turn_id` and
  `meta.source`, and the engine annotates `valence`, `arousal`, `instance_ids` afterwards (`Keepsake.annotate_turn`).
- Since 0.9.0 nothing in memory has a hidden default: kokoro.json's `llm` (the 記憶 connection) and `embedder` (the
  vectors) blocks are written by 556d from `home/models.json` (設定 → 全域 → 模型連線) before every start
  (`writeKokoroConnections`); kokoro raises 模型連線未設定 instead of guessing an endpoint, and `tools/seed-memories.py`
  reads the embedder from kokoro.json or stops.
- Since 0.8.6 **no tools at baseline**: 556d empties the `memory` toolset from every `platform_toolsets` list before a
  start, so `kokoro_search` / `kokoro_forget` (still defined behind kokoro.json `tools`) are never offered; memory is
  injected, not a tool. Since 0.8.10 the per-turn block ends with **`By name`** rows: keyword triggers, names only.
- The 0.8.7 **pinned groups are retired** (reserved tags `timeline` / `influences` / `stances` / `refusals` /
  `standing` rendered as 一直記著的 — gone, with `render_pinned`, `pinned_tags`, `pinned_per_tag`). The dated, always-on
  part of who she is is SOUL text (`## 時間線`, `## 影響過你的人與事`, written by the soul skill); the store keeps what
  she knows; the same events are dated seeds for retrieval. See "The dated part of who she is" below.

The rest of this doc is the design as decided, with its test record.

## The five-tier stack (who writes what)

| Tier | What | Written by |
|---|---|---|
| Spirit card — `SOUL.md` (+ ST card import later) | identity, voice, habits — and since 2026-10-19 the dated part of who she is: `## 時間線`, `## 影響過你的人與事` | **human**, or the soul skill from the description (code, not a model); never grows through conversation |
| Lorebook — keyword triggers (built 0.8.10: kokoro `_with_triggers`, names only — the roster, the person files, your name; places later) | the people she knows by name | deterministic: a name in the message → one exact BM25 lookup per matched name, up to `trigger_k` rows under `By name`, minus what similarity already brought |
| Curated head — `MEMORY.md`/`USER.md` | **off** — Hermes's writer is disabled (`memory_enabled` / `user_profile_enabled` false); the one curated file is `people/你.md`, carried by kokoro's prompt section | the app (Settings writes its managed lines), your hand |
| **DB tier — this doc** | long facts + short dated notes, retrieved per turn; seeds | the observe pipeline (one LLM pass per turn), `tools/seed-memories.py` |
| FTS5 sessions | verbatim archive — the history, `state.db` | automatic |

When tiers disagree there is no top-down rule: **the conversation itself is ground truth; otherwise the newest entry
wins, whatever the layer; a fact beats a note only on a tie** (kokoro's memory rule, `_memory_block_text`; the pipeline
then supersedes the stale fact).

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

## Path K — kokoro on KeepsakeDB — IMPLEMENTED 2026-10-02 (Path C realized as its own repo)

The target engine exists: **KeepsakeDB** (then 0.1.x at `D:\dev\KeepsakeDB`; today 1.0.1 as the submodule
`vendor/keepsakedb`) and the Hermes provider **`plugins/kokoro`** (linked into `home/profiles/<id>/plugins/kokoro`;
`memory.provider: kokoro`; config `home/profiles/<id>/kokoro.json`). What runs per turn (as of 0.10.0):

- **prefetch** → `Pipeline.context_for(user_text)`: hybrid recall (the vectors' dense leg + FTS5 BM25 with
  CJK bigrams, RRF k=60, over-fetch ×3), trust labels (`[high]` ≥ 0.60, dropped < 0.40 unless BM25
  matched), archived topics as meta-info only unless a consent window is open; superseded and held facts
  never surface. Then the person block when another character is talking, then the `By name` rows.
  Embedder down → BM25-only fallback (`store.context`). Skipped on trivial prompts. Recall indicator 💗 Kokoro.
- **sync_turn** (on Hermes's serialized memory worker) → `Pipeline.observe`: one JSON pass by the 記憶 connection
  (kokoro.json `llm`) over the turn + the 8 most similar long memories (`max_candidates`) + the tag groups →
  add / update / supersede / archive / unarchive / consent / noop, plus an optional dated `note` for the short layer;
  memories written in **zh-TW**, tags as English slugs; stamped `meta.turn_id` / `meta.source`. Her own 【事件】 turns
  are not observed. Shutdown waits for an in-flight observe so one-shot runs never lose a write.
- **tools**: none offered at baseline (0.8.6). `kokoro_search` / `kokoro_forget` (hard delete on explicit request only)
  are still defined behind kokoro.json `tools` (true), but 556d empties the `memory` toolset from `platform_toolsets`
  before every start, so she carries no tools unless an extension (查網路) is switched on for her.
- **store**: `home/profiles/<id>/memory/<id>.db` — memories (a `layer` column), history, search_log, pipeline_log,
  command queue; owner heartbeat + `data_version` reload; a snapshot on the first write of each day and before risky
  operations into `home/profiles/<id>/backups/` (`backup_dir`; Anki-style rotation 7 daily / 4 weekly / 12 monthly);
  the engine log at `home/profiles/<id>/logs/keepsake.jsonl` (`log`).
- **inspect**: `vendor\hermes-agent\.venv\Scripts\keepsake --db home\profiles\<id>\memory\<id>.db stats|list|log|plog|search Q --explain`
  (the `keepsake` CLI of the vendored package).
- 556d gained `-no-hermes` (shim + embedder + API only) so CLI harnesses can run without a second
  Hermes process owning the store.

Smoke (2026-10-02): a self-introduction (a name, then 「…我最喜歡吃麻辣鍋」) → two memories: the name and how to address him
(identity) and `最喜歡吃麻辣鍋。` (food); next fresh session 「我最愛吃的食物是什麼？」→ 「你最愛吃的食物是
麻辣鍋。」 with the memory injected at cosine 0.62 `[high]`. Turn cost ≈ 24 s one-shot (model via shim +
≈ 7 s observe + startup); recall itself ≈ 2 ms + one embedding call.

**Endurance test (tests/memory_stress.py, fresh session every round) — 100 rounds, 2026-10-02:
19/20** (Path A: 20/20). 18.2 s per round mean, no timeouts; 33 active memories + 3 superseded,
12 tag groups, ~45 restatements deduped to zero duplicates; 119 pipeline runs (33 add,
3 supersede, 0 skipped, 1 LLM error), observe ≈ 7.4 s. The miss: the model returned empty
content on the probe (proxy hiccup, not recall). Found and fixed before the 1000-round run: the
Path A temporal-conflict trap reproduced — after 半馬→全馬 was superseded correctly, a
reminder-style restatement 「再跟你說一次喔…報了半馬」 was treated as a new correction and superseded
it back (the first restatement 「我有提過嗎？…」 was correctly noop). Prompt rule added: a
reminder/repeat never overrides a recorded correction. Calibration data (580 context rows):
injected `[high]` hits are restatement-level matches (dense 0.60–0.93, p50 0.83); ordinary
correct recalls sit at 0.44–0.55 (p50 0.48); 0.38–0.40 hits survived only via BM25. Thresholds
0.60 / 0.40 kept. Logs: `tests/stress_log_kokoro_100.jsonl`, store snapshot `home/backups_run100/`.
**1000-round run (2026-10-02 02:50–06:58, 14.6 s/round)**: rounds 1–483 ran for real; at 04:56 the
user's Gemini proxy (:18765) started returning empty responses and stayed down, so rounds 484–1000
and the exam got "HTTP 502: all backends failed" replies (exam 0/20 = backend, not recall). What the
483 real rounds prove: all 30 facts stored (33 active memories), every correction resolved the right
way (sister → 台南, Japan 10 days, firmware, Mochi 3/5, **半馬 → 全馬 held through ~200 reminder-style
restatements** — the Path A trap is fixed), zero duplicates, 483 pipeline runs (33 add, 2 supersede,
0 skipped), observe ≈ 6.3 s; a 556d restart mid-run (tool time cap) cost one 52 s round and nothing
else. Calibration on 4 776 injected rows: `[high]` 0.61–0.95 (p50 0.87), plain 0.46–0.55 (p50 0.50),
15 hits rescued by BM25 below 0.40. **Exam re-run at 07:10 when the backend returned
(`tests/memory_probe.py`, fresh session per probe, store as left by the 483 real rounds): 20/20**,
including the marathon probe (全馬) that Path A missed at 1000 rounds. A full 1000-round re-run
under a stable backend remains the clean number. Logs: `tests/stress_log.jsonl`.

**Clean 1000-round run (2026-10-02 10:21–15:19, fresh store, 19 s/round)**: rounds 1–932 real; the
Gemini lane hit its limit at round 933 (second outage of the day) and the harness was stopped
(`--start=N` added for resumes). Store at 932: 32 memories, 2 superseded, **932 pipeline runs for
932 rounds (no lost observe)**, marathon correction held (全馬 active, 半馬 superseded) through ~400
restatements, zero duplicates. **Direct engine exam** (`tests/memory_recall_check.py`: the 20 probes
through KeepsakeDB's own recall, no chat model): **18/20 in the injected block, 18/20 in top-5**.
The two misses are explained: (1) 「我去日本要去多久？」 — the trip's only mention got an **empty
LLM reply in the L2 observe** (the run's single pipeline error), so the fact was never stored →
KeepsakeDB pipeline now retries once on an empty / non-JSON reply (0.1.x); (2) 「我現在住在哪個城市？」
— inferential (新竹 is only implied by F12 / 新竹馬拉松 / 十八尖山); the chat model answered it in both
model-based exams. Verdict: the memory check is closed — engine recall is at the ceiling of what was
stored, writes are lossless, corrections hold; the remaining variance is the backend. Snapshots:
`home/backups_run932/`; logs `tests/stress_run_kokoro_1000b.log`, `tests/stress_log.jsonl`.

### Two layers (2026-10-03, KeepsakeDB 0.2.0)
`memories.layer`: **long** = tagged facts with trust labels, supersede/archive (unchanged); **short** =
dated notes, one per turn worth recalling, no tags, surface in meta, ring-capped (`short_cap` 1000).
Written by the same observe call (`ops` + `note`). Read by `search_layers`: one embedding, layers
searched concurrently (bigger first, each on its own read connection), hybrid top 5 each, injected as
`Facts (long-term)` / `Notes (recent, dated)`. kokoro's prompt section carries the priority rule: the
conversation is ground truth, then newest wins across layers, fact beats note on a tie. Knobs:
`short_layer`, `short_k`, `short_cap` (kokoro.json, dev registry). The memory page shows long by
default, short behind a toggle (看近期紀錄). Unchanged in KeepsakeDB 1.0.1.

### History is not memory (2026-10-02)
A 'recent-exchange layer' that recorded every turn in the store (for cross-surface continuity) lived
for a few hours and was removed: it put trivia into 記憶 and confused two different things. The
last X turns are conversation history — verbatim, in Hermes's session store (`state.db`, survives
restarts, compressed never deleted), shared by every surface because the app continues the same
session. Memory is what the pipeline decides to keep. KeepsakeDB 0.1.3.

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

- **Milvus Lite**: CORRECTED 2026-10-01 — the 2.4.x note above was outdated. Milvus Lite 3.x is a
  pure-Python rewrite with BM25 + sparse index + hybrid_search (RRF/weighted) and a Windows wheel.
  It still falls short for a memory store: BM25 statistics are segment-local (flush every 10k
  rows; an acknowledged TODO in its source), scoring is a Python loop rebuilt per query, one
  process per data dir. Full analysis + benchmark vs our SQLite engine: KeepsakeDB
  (`D:\dev\KeepsakeDB\docs\RESEARCH-milvus.md`, `BENCHMARK.md`).
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

- `language` per companion (kokoro.json, template **zh-TW**; en selectable): the extraction prompt writes
  facts in this language. Never "mirror the input" — mixed-language stores defeat dedup.
- The embedder is the **vectors** connection of 設定 → 全域 → 模型連線 (0.9.0): 556d's own llama-server with a model
  file, or any OpenAI-compatible embeddings endpoint, with its name and dimensions; no default — 556d writes it into
  every profile's kokoro.json `embedder` before a start, and nothing starts until it is set (this machine: local
  bge-m3, 100+ languages incl. zh/ja/fr/en). **Anyone running a companion in another language must pair it with an
  embedder that covers that language** — the language knob and the embedder knob travel together. Changing the
  embedder means re-embedding the store (`reembed`; minutes at companion scale).
- Standalone engine: **KeepsakeDB** (own repo `D:\dev\KeepsakeDB`, created 2026-10-01; vendored here as the submodule
  `vendor/keepsakedb`, 1.0.1, API frozen 2026-10-14) — layered L1 store / L2 pipeline (unpluggable) / L3 integration;
  556 keeps `kokoro` as the Hermes provider name.

## The dated part of who she is — SOUL text, not pinned memory (2026-10-19, `../prompt/prompt.md` §2.4)

The 0.8.7 pinned groups — reserved tags (`timeline`, `influences`, `stances`, `refusals`, `standing`) rendered once per
session under 一直記著的 — are retired (`render_pinned`, `pinned_tags`, `pinned_per_tag` and their test are gone). Once
it was settled that this content does not grow through conversation, "fixed and in every request" means SOUL:

- Her timeline with absolute dates and the people and things that shaped her are `## 時間線` (oldest first) and
  `## 影響過你的人與事` in `SOUL.md`, written by the soul skill from the description (code, not a model) or by hand;
  stances and refusals live in `## 怎麼判斷、怎麼決定`, the people in `## 誰在跟你說話`; where she stands with someone
  *now* is the engine's 對他 line. Before every start 556d copies SOUL.md, psyche.json and people/*.md from
  `characters/<id>/` into the profile (people/你.md only when missing) — the package is the character.
- The store keeps what she knows. The same events reach it as **seeds** (`characters/<id>/seeds.jsonl` →
  `tools/seed-memories.py <id> [--replace]`, run while 556d is up and the character is not): `meta.seed: true`,
  `meta.source: 設定`, tags as given (the skill still tags events `timeline` and influences `influences` — ordinary
  tags now, for retrieval); a seed's `at` (`YYYY`, `YYYY-MM` or `YYYY-MM-DD`) becomes `created_at` (local noon of
  that day) and is kept in `meta.at`, so a 2019 event sorts (and shows on the 記憶 page) as 2019. Same text = skipped unless
  `--replace`. The tool reads the embedder from kokoro.json and stops if 556d has not written it yet.
- Nothing in the pipeline knows a reserved tag; a row the observe LLM tags `timeline` is a fact about you and stays in
  the retrieved tier.

## What she reads, and the knobs (0.10.0)

**System prompt, once per session** — kokoro's section `kokoro.memory` (`register_system_prompt_section`, position
`after_memory`, at most 4 000 chars, frozen into the session like every section, until the next restart: since 0.11.0 556d drops the session's stored
prompt before every start and the first turn rebuilds it): the zh-TW memory rule (how to read
the block: `[high]` is certain, plain is probably right, notes are dated, `[archived: …]` is never spoken — only asked
about when the other side touches it, `By name` is why a person came up, a name in memory belongs to that person and never to whoever is talking now —
who that is comes only from 關於你, and with no name there she uses none (0.12.2), what is not in memory is unknown — no
guessing), then 關於<her term for you>：`people/你.md` (first 2 000 chars; `memories/USER.md` as the legacy
fallback). The provider's own `system_prompt_block()` returns "" so nothing is injected twice. The SOUL (Hermes's
identity slot) comes before it, with its 時間線.

**The last user message, every turn** — Hermes wraps kokoro's prefetch in `<memory-context>` ("[System note: … recalled
memory context, NOT new user input …]"); inside, in this order:

- `Memory:` → `Facts (long-term):` up to `context_k` long rows, `[high]` or plain, `(tags: …)`, a `meta.prefix` such
  as 「（舊帳 2026/10/13）」 in front; `[archived: <topic> — <reason> — contents withheld; offer to discuss]` for an
  archived hit outside a consent window; superseded, held and below-`drop` rows out;
- `Notes (recent, dated):` up to `short_k` short rows as `[MM/DD <surface>] text`;
- when the session is another character's (`556:agent:<id>`): 現在跟你說話的是<name>，不是<your term>。About <name>
  (person file): + `people/<id>.md`;
- `By name:` — for each trigger name found in the message (the roster's display names, the `people/*.md` stems, your
  name; never 你, two characters or more) one exact BM25 lookup (`phrase=True`, `k = trigger_k`), archived / superseded
  / held rows out, rows already in the block out, at most `2 × trigger_k` lines in all; the block is `Memory:` +
  `By name:` alone when similarity brought nothing.

Then psyche's `<her-state>` with 【她現在】. The block is absent on trivial prompts; 你 is rendered as her term
throughout. Tests: `tests/test_kokoro_triggers.py`.

**Knobs** (`home/profiles/<id>/kokoro.json`; defaults = `templates/companion/kokoro.json`, else the code):

| Key | Default | Meaning |
|---|---|---|
| `llm` | written by 556d | the 記憶 connection: `base_url`, `model`, `api_key`, `timeout` (60, kept if you changed it); the observe LLM |
| `embedder` | written by 556d | the vectors: `base_url`, `model`, `api_key`, `dims`; one embedding per prefetch and per write |
| `db` | `memory/{profile}.db` | the store, under the profile |
| `backup_dir` | `backups` | snapshots (daily on first write, before risky ops; 7/4/12 rotation) |
| `log` | `logs/keepsake.jsonl` | the engine log; `log_searches` / `log_pipeline` true, `log_retention_days` 90 |
| `subject` | `你` | the stored subject word for memories about you; the store's record wins (`meta.subject`) |
| `your_name` | `""` | your name (Settings writes it through); her term for you when set |
| `address_default` | the template's role term | her term for you while `your_name` is empty |
| `context_k` | 5 | long rows per turn |
| `short_layer` / `short_k` / `short_cap` | true / 5 / 1000 | the short layer on, notes per turn, ring size |
| `triggers` / `trigger_k` | true / 3 (code; not in the template) | the `By name` lookups and rows per name |
| `tools` | true | defines `kokoro_search` / `kokoro_forget` — not offered while `platform_toolsets` is empty |
| `system_prompt_block` | unset (the code's zh-TW rule) | replaces the memory-rule text of the section |
| `high` / `drop` / `rrf_k` / `oversample` | 0.6 / 0.4 / 60 / 3 | trust line, drop line, RRF constant, over-fetch |
| `language` / `max_candidates` / `consent_turns` / `tokenizer` | zh-TW / 8 / 100 / bigram | memory language, observe candidates, consent window, FTS tokenizer |

**Where the files are** (all under `home/profiles/<id>/`): the store `memory/<id>.db`, snapshots `backups/`, the
log `logs/keepsake.jsonl`, the config `kokoro.json` (`llm` + `embedder` rewritten before every start, the rest is
hers), the person files `people/*.md`, the history `state.db`, the state `psyche.db`; the plugin itself is the junction
`plugins/kokoro` → the repo's `plugins/kokoro`. `tools/seed-memories.py` writes the store with `owner=False` while
she is stopped; 556d reads it read-only and sends deletes through the `commands` table (`internal/memory`).

## History vs memory vs state — `memory-layers.d2`

- Three stores feed her prompt: history (the verbatim session), memory (long facts + short dated notes),
  and state (`psyche.db`, how she is now, derived from events).
- Still one observe call per turn; it may return two strings (`ops` for long, `note` for short). Still one
  embedding per prefetch, then both layers searched at once: the bigger layer starts first on its own read
  connection, the smaller follows immediately, nothing waits but the final join; hybrid (dense + BM25,
  RRF), top `context_k` / `short_k` each, a few ms per search — plus one exact BM25 lookup per name found in
  the message (`By name`, 0.8.10).
- Priority when they disagree: history first; then the newest entry regardless of layer; long breaks
  ties; the pipeline supersedes the stale long fact afterwards. The state block names transitions
  explicitly so the history's tone inertia does not win.
- One file with a layer column (one owner, one backup), not two database files. 記憶 shows the long layer;
  a toggle shows the short layer. 556d reads the store read-only and deletes through the command queue; the
  psyche engine's holds and patches travel the same queue.
