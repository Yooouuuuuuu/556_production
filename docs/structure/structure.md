# Structure — one process per character, 556d around her

Living doc; last verified 2026-10-19 (0.10.0). Graphs in this folder are D2 sources: solid = what runs
today (0.10.0), dashed pink = later work (Discord, MCP). Discord and MCP stay dashed. Why things are this way: `../DECISIONS.md`.

## 1. The shape — `structure.d2`

- Her `hermes gateway run` is her only Hermes process. Its API server is the app's route; its adapters are
  her channels (her own accounts). 556d is the hub around her, never a chat participant: it starts and
  stops her, shows her conversation, mirrors app turns into Telegram, and reads her stores read-only (and
  opens her one session at start).
- Shared across characters: the model shim (one lane, `auto/556`, pointed at the 對話 connection), the embedder
  (started by 556d when the vectors are local), 556d. Nothing has a default: the connections — `home/models.json`,
  設定 → 全域 → 模型連線 (0.9.0) — must be complete before any character starts, and 556d writes her `config.yaml` /
  `kokoro.json` / `psyche.json` from them before every start. Per character: process, API port and key,
  `state.db` (history), `memory/<name>.db` (memory), `psyche.db` (state, 0.5.0), SOUL / config / `.env`.
- Inside her process, two plugins of ours: **kokoro** (memory) and **psyche** (the engine: 1-minute tick,
  appraisal queue, impact model, state block, event turns; single writer of `psyche.db`). 556d only reads
  `psyche.db` (狀態 page) and writes `psyche.json` from Settings, applied by a restart like tool extensions.
- Tools: none at baseline (0.8.6; memory is injected every turn, not a tool — 556d strips the old `memory` toolset
  from every `platform_toolsets` list before a start, so her prompt carries no tools preamble); extensions per
  character in 設定 → 角色 → 能力, written to `platform_toolsets`, applied by a restart. No hot toggling.

## 2. One turn — `turn-flow.d2`

- Exactly one session per character. 556d opens it when you start her from the roster (never a message,
  from any surface); the app continues her Telegram DM session by id, so both surfaces see each other's
  turns and the gateway rebuilds the context from `state.db` every turn. 556d never proxies Telegram.
  `/new` and the other gateway slash commands are admin-only on her Telegram.
- **1 + 2**: one LLM call you wait for (the reply). After the reply, two background calls fire at the same
  moment: kokoro's observe (memory) and psyche's appraisal A (what happened, how much it matters). Neither
  is waited for; the appraisal shapes the *next* turn through the state block. Prefetch (memory search,
  state block) reads what has landed and never waits, voice or text.
- Two mirrors: app → Telegram as plain text; Telegram → app through the follower, with a badge.
- Section D of the graph is the event turn (built 0.6.0): the engine posts a narrator cue to her own API with
  `X-556-Event`; her words land as a normal row in her one conversation, the follower shows them in the
  app, 556d sends them to Telegram on the same path as the app mirror, and the 主動 override decides
  whether they are spoken.
- A stop right after a reply (section C) waits for the memory pipeline, then (0.5.0) the appraisal queue
  and a snapshot, before the planned-stop marker.
- Characters talk to each other through 556d (0.7.0): each pair has a session in each character's own `state.db`
  (key `556:agent:<name>`), opened and stamped by 556d like your conversation. A character's urge toward another
  produces an event turn in that session; the psyche plugin posts the message to `/api/relay`; 556d delivers it as
  a user turn on the other side and carries the exchange on until silence or the turn cap. Both sides remember and
  appraise the other as the counterpart. Never plugin to plugin: 556d knows the ports and keys and owns the pacing.

## 3. Inside her process — `hermes.d2`

- Green = ours: SOUL, `people/你.md` (replacing `memories/USER.md`, 0.5.0), `config.yaml`, `.env`,
  `kokoro.json`, `psyche.json`, the two plugin junctions, the three stores. Grey = Hermes vendor code,
  never edited; fixes go in plugins, 556d or upstream.
- Per turn: history rebuilt from `state.db` → toolsets for this platform from `platform_toolsets` (none at baseline) →
  AIAgent with the system prompt (SOUL, with 時間線 and 影響過你的人與事 inside it; kokoro's zh-TW section — the memory
  rule + 關於你 from `people/你.md`) and the last message (the question; the memory block — top facts and notes by
  similarity, `By name` rows for names in the message; 【她現在】 — the clock first, then state lines and one optional
  想法 line) → the model through the shim → rows appended → the memory worker fans out to kokoro (observe) and psyche
  (appraisal).
- Before every start 556d prepares her folder (`api/connections.go` `prepareProfile`, `api/package.go`,
  `api/hygiene.go`): the package `characters/<id>/` is copied over (SOUL.md, psyche.json, people/*.md; 你.md only when
  missing), `config.yaml` is pinned (model → the shim, memory → kokoro, plugins [psyche], empty toolsets), `kokoro.json`
  gets the 記憶 and embedder endpoints and `psyche.json` the zone from `home/models.json`, and the hygiene switches go in
  (vendor guidance off, zh-TW platform hints). A profile is rebuildable from nothing; an edit in the package wins at
  her next start.
- The shim (`shim/hygiene.go`, `shim/textproto.go`; 0.8.4–0.8.10) is the other half of prompt hygiene: it drops
  Hermes's vendor paragraphs and the date paragraph from every system message on every platform (a resumed session
  keeps the prompt pieces it was born with, so the config switches alone would never reach the cast's endless
  sessions), unwraps the proxy's reply function, and strips the hidden `<think>…</think>` scratch from the reply before
  the tool-call parser and before Hermes sees the text.
- The clock: the first line under 【她現在】 is 現在：YYYY/MM/DD（weekday）HH:MM from the engine's own zone
  (`time.timezone_offset_h`, written from the connections; `HERMES_TIMEZONE` agrees); the eight-line cap counts state
  lines only.
- The exact bytes of one request — the system prompt block by block (what Hermes and the shim put around
  the SOUL), the history replay and its cost, the last message's three pieces — are in `../prompt/prompt.md`
  §1; the design that reshapes them is §2 there.
- The psyche tick runs on a background thread inside the process, so the engine runs exactly when she
  runs. No Hermes cron: reminders are open loops the tick fires. Output checks use the
  `transform_llm_output` plugin hook and record only at first.

## 4. Lifecycle — `lifecycle.d2`

- Nothing auto-starts. Roster start spawns her with the API key/host/port in her env, waits for
  `/health`, then opens her one conversation if none is live (Telegram routing stamped so a DM joins it).
- Roster stop, app quit and app death take the same path: wait for the memory pipeline to catch up with
  the last turn (and, 0.5.0, the appraisal queue), planned-stop marker, drain, exit 0; kill only after
  60 s. No "Gateway shutting down" ping to Telegram.
- Her time is continuous: at start the engine loads the last snapshot and fast-forwards the offline hours
  (sleep, activities, projects, life events, due loops); no proactive messages are back-filled — a reminder
  that came due while she was stopped fires at her first live tick. While she is stopped nothing ticks: she is not living and cannot speak first.

## 5. Zones

- `vendor/hermes-agent/` — the engine, a git submodule pinned in `.gitmodules`, never edited; `vendor/keepsakedb/` — the memory engine, a submodule at its release tag.
- `home/` — runtime data and config, ignored by VCS: `models.json` (the model connections, the embedder, the timezone —
  the only place they live), `settings.json`, `voice.json`, `mailbox/`, and `home/profiles/<id>/` — a character's
  runtime folder, rebuilt from her package and the connections before every start.
- `characters/<id>/` — the character package, the character itself (ignored except `characters/README.md`): authored
  `describe/01…10.md` and `profile.json`; generated `SOUL.md`, `seeds.jsonl`, `people/*.md`, `psyche.json`,
  `soul.lock.json`, `build/`. Backup = the package + `memory/<id>.db` + `psyche.db` + `state.db` from the profile;
  everything else is rebuilt. `templates/character/` is the blank template (and 阿凜 as `example/`),
  `templates/companion/` the profile skeleton `new-companion.ps1` copies.
- `556d/` (Go daemon), `app/` (Electron + React), `plugins/` (Python, inside Hermes by contract: kokoro, psyche),
  `tools/` (the soul skill, the fidelity probe, seeds, the simulator, diagnostics), `tests/` (pytest for the skill, the
  probe and kokoro's triggers; the psyche suite under `plugins/psyche/tests`; Go tests in `556d/internal`), `docs/`
  (concepts only).
- Production `D:\Hermes` is a different install and is never touched.

## 6. Origins — what we took from where

Built on the Hermes Agent backbone, learning from momori777/Artemis (and the surveyed field:
Open-LLM-VTuber, Soul of Waifu, z-waif, MyAiFriend). Artemis was OpenClaw Gateway + Headroom proxy +
llama-server + media services; here **Hermes replaces OpenClaw and most of Headroom** (multi-platform
gateway, per-profile characters with SOUL.md and an isolated home, context compression, skills, plugins),
and the model **shim** replaces single-model lock-in with routed lanes (any OpenAI-compatible model).

Artemis patterns and where they landed:

| Pattern | Here |
| --- | --- |
| Characters as folders of markdown | the character package `characters/<id>/` — authored as `describe/*.md` in the person's words, generated by the soul skill, copied into her Hermes profile before every start |
| Memory isolation per character | one KeepsakeDB file per character, one process per character |
| Dual-layer memory with recall priority | long + short layers, priority rule (`../memory/memory.md`) |
| Compression + memory as one system | Hermes compression keeps history; memory is the pipeline's choice |
| Scheduled fact distillation | one observe call per turn instead of a cron |
| VRAM tiering | parked (local TTS / image gen not in use; voice is Fish Audio) |
| Thin interchangeable frontends | her gateway platforms (API server for the app, Telegram) |
| Avatar bridge | Live2D in the app's avatar window, driven by 556d's events |
| Trust-labelled retrieval | kokoro's `[high]` / plain labels |

Milestones: 0.2.0 the Go daemon beside an untouched Hermes (2026-09-30); 0.3.0 the one app that owns the
backend and the Artemis exit (2026-10-01); 0.4.0 one process per character, one conversation shared by
app and Telegram, two memory layers, graceful stop, two voice modes (2026-10-06); 0.5.0 tools, 你, and the
inner life's first milestone (2026-10-07, `../inner-life/inner-life.md`); 0.6.0 she speaks first (2026-10-08); 0.7.0
relationships, the hurt ledger, characters talking to each other (2026-10-13); 0.7.x 設定 in two layers, the mailbox,
forgetting, the submodules (2026-10-14/15); 0.8.0 the soul skill (2026-10-16); 0.8.1 the 新角色 page (2026-10-16);
0.8.4 prompt hygiene and the clock (2026-10-16); 0.8.6 no tools at baseline (2026-10-19); 0.8.8 the thinking module;
0.8.9 the five conversation mechanisms; 0.8.10 the hidden scratch, keyword triggers, the simple path, the fidelity
probe; 0.9.0 the model connections in the app, no hidden defaults (2026-10-19); 0.10.0 the package is the character,
the dated part of who she is in the SOUL (2026-10-19).
