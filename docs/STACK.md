# STACK — what exactly this project is using

Last verified: 2026-10-19 (0.10.0). Ground-truth inventory; update it when reality changes.
Reasoning behind each choice: `DECISIONS.md` and the part docs (`structure/`, `memory/`, `app/`, `voice/`, `inner-life/`).

## One app

**556 Production** (`app/`, Electron + React) is the product. Launching it starts and owns the
whole backend; closing it shuts everything down.

Diagrams: D2 sources next to each part doc (`structure/`, `memory/`, `voice/`, `inner-life/`, `prompt/`).

```
556 Production (Electron)          office window: the roster column, the current character's 聊天 · 狀態 · 記憶 · 角色, the gear (設定) · avatar window (立繪, hidden by default) · tray
  └─ spawns 556d.exe -parent-pid   (Go)  :55600  hub: chat API + events on /ws + avatar bridge + static
        ├─ shim               :55601  OpenAI-compatible, one lane auto/556 → the 對話 connection (bearer key);
        │                             prompt-hygiene filter + scratch strip; 503 until the connections are set
        ├─ llama-server       :<port in models.json>  the embedder, started by 556d only when the vectors are local
        │                             (kind llama: exe + GGUF + port); otherwise an embeddings endpoint elsewhere
        └─ per ACTIVE companion (started from the roster, never automatically) — ONE process:
              └─ hermes gateway run  :dynamic  her brain (HERMES_HOME = home/profiles/<id>): SOUL + kokoro memory
                                               + psyche; inside it the OpenAI-compatible API server (the app's
                                               route) and her channel adapters (Telegram / Discord from her .env)
External: the model endpoints named in home/models.json (any OpenAI-compatible server; this machine's is a local
proxy, openmini — the product assumes nothing about it). No character starts until 設定 → 模型連線 is complete.
```

Ownership chain: on quit the app calls `POST /api/shutdown` and waits; 556d asks every active
companion to finish up (Hermes planned-stop marker → her gateway drains, kokoro lands the in-flight
memory observe, exit 0), kills after a 60 s grace, then exits; the app kills 556d only if it does
not come down in time. 556d watches the app's pid and runs the same shutdown if the app dies; the
Windows job object (kill-on-close) is the backstop for everything else. Roster **stop** is the same
graceful path for one companion and returns when she is gone (「收尾中…」 meanwhile). 556d attaches
instead of spawning if one already serves :55600.

## Layout

| Path | What | Ours? |
|---|---|---|
| `app/` | the app: `electron/` (main, preload, backend lifecycle), `src/` (React: `pages/` Shell, Chat, State, Memory, Settings, Character, NewCharacter, ConnectionsSettings, ProactiveSettings, ToolsSettings, VoiceSettings, DevSettings, Roster, Memory, State, Avatar; `live2d/Live2DStage`, `store` = hub WebSocket state, `api`, `i18n` zh-TW default), `assets/` icons, `scripts/` (dev runner, `cdp_capture.mjs`, `copy-vad.mjs`) | ours |
| `app/public/vad/` | build output: Silero VAD models + audio worklet (from `@ricky0123/vad-web`) and ONNX Runtime wasm (from `onnxruntime-web`), copied by `scripts/copy-vad.mjs`, served by 556d at `/vad/` (ignored) | generated |
| `556d/` | Go daemon: `internal/{api, bridge, companions, config, embedder, hermesapi, memory, models, shim, supervisor, voice}`. In `api/`: `connections.go` (`/api/connections` + probe; `prepareProfile` writes her `config.yaml` / `kokoro.json` / `psyche.json` from `home/models.json` before every start), `package.go` (the package sync: `characters/<id>/` → her profile), `hygiene.go` (the config half of prompt hygiene: guidance switches off, zh-TW platform hints, the old `memory` toolset stripped), `characters.go` (the 新角色 page: packages, the skill and the install as jobs). `shim/hygiene.go` is the shim half: vendor paragraphs and the date paragraph dropped from every system message, the proxy's reply function unwrapped. `models/` loads, merges, masks and probes the connections; `embedder/` runs llama-server when the vectors are local. Config `556d.toml` | ours |
| `vendor/hermes-agent/` | Hermes Agent v0.21.0: git submodule pinned at upstream `7166071f` (fetched shallow); its venv `.venv` (py3.11/uv) is ignored. `setup-vendor.ps1` checks it out and builds the venv | **never edited** |
| `vendor/keepsakedb/` | KeepsakeDB 1.0.1 (ours, upstream Yooouuuuuuu/KeepsakeDB): git submodule pinned at the release tag `v1.0.1`, installed editable into the Hermes venv by `setup-vendor.ps1`. Bumped only on a bug-fix release (`git -C vendor/keepsakedb checkout vX.Y.Z`, commit the pin) | never edited here |
| `vendor/live2d/` | Cubism Core **4** (`live2dcubismcore.min.js`) | never edited |
| `assets/live2d/hiyori/` | official free Hiyori model (Cubism-4-era assets, SDK tag 4-r.7) | third-party data |
| `plugins/` | Python that plugs INTO Hermes, linked into each profile's `plugins/` as junctions: `kokoro/` (memory provider on KeepsakeDB: prefetch, observe, the zh-TW prompt section `kokoro.memory`, keyword triggers) and `psyche/` (the engine: tick, appraisal, impact model, loops, relationships, thinking, the state block; `tests/`, 68) | ours |
| `home/` | runtime, ignored: `models.json` (the model connections, the embedder, the timezone — 設定 → 模型連線, the only place they live), `settings.json` (you + app), `voice.json` (global connectors), `mailbox/<id>.json`, `audio_cache/`, `profiles/<id>/`. Also HERMES_HOME of the shell (`556.cmd`): its `config.yaml` is the CLI's own and is no longer the source of any profile's model block | runtime (ignored) |
| `home/profiles/<id>/` | **a character's HERMES_HOME** (Hermes profile, created by `new-companion.ps1`, rebuilt from `characters/<id>/` and `home/models.json` before every start): `SOUL.md`, `people/*.md` (`你.md` carries your name and reply language as managed lines, written into every profile on save; copied from the package only when missing), `config.yaml` (model → shim, memory → kokoro, plugins [psyche], empty toolsets, hygiene switches — written by 556d), `kokoro.json` (`subject: 你`, `your_name`, `address_default`; `llm` + `embedder` from the connections), `psyche.json` (from the package; `time.timezone_offset_h` from the connections), `companion.json` (display name, avatar, her API key), `voice.json` (her voice override, optional), `.env` (her own bot tokens), `plugins/kokoro` + `plugins/psyche` (junctions), `memory/<id>.db` (KeepsakeDB), `backups/` (its daily snapshots), `psyche.db`, `state.db` (sessions = history) | ours |
| `characters/<id>/` | the character package — the character itself (ignored except `characters/README.md`): authored `describe/01…10.md`, `profile.json`, `companion.json`, `kokoro.json` (keys); generated by the soul skill `SOUL.md`, `seeds.jsonl`, `people/*.md`, `psyche.json`, `soul.lock.json`, `build/` (phase JSON, `check.md`, `verify.md`, `raw/`, `run.log`). Backup = the package + `memory/<id>.db` + `psyche.db` + `state.db` | ours (the user's) |
| `tools/` | `soul_writer.py` (the soul skill: `characters/<id>/describe/` → SOUL, seeds, people, psyche.json; `--base-url`/`--model` or the 寫靈魂 connection, 556d need not run), `fidelity_probe.py` (scores a SOUL text blind against `tests/fidelity/<id>.json`, same model rule), `seed-memories.py` (dated seeds; the embedder from her `kokoro.json`), `psychesim.py`; diagnostics `cdp_shot.mjs` (real-Chrome screenshot), `ws_probe.mjs`, `hub_probe.mjs` (`package.json`: `ws`) | ours |
| `templates/character/` | the blank `describe/` template and `profile.json` (Big Five, the seven constants incl. chronotype, the five thinking meters, the choices, schedule); `example/` is a filled description (a disposable test character). `templates/companion/` stays the profile skeleton `new-companion.ps1` copies (SOUL skeleton, `companion.json`, `kokoro.json`, `psyche.json`, `people/你.md`, `env.example`) — no endpoints in either | ours |
| `tests/` | `test_soul_writer.py`, `test_fidelity_probe.py`, `test_kokoro_triggers.py` (pytest from the Hermes venv); `fidelity/<id>.json` (the gold set for a character); `psyche_eval.py` (LLM eval against a running character); `memory_stress.py` / `memory_probe.py` / `memory_recall_check.py` (the 1000-round zh-TW benchmark and its re-runs); `live/smoke_*.sh` (foreground smoke runs). Go tests under `556d/internal/{api, models, shim, voice}` | ours |
| `models/`, `bin/` | an embedding GGUF (bge-m3 Q8_0 here) and the llama.cpp CPU build — downloads, only when the vectors are local; their paths go into 設定 → 模型連線 (ignored, anchored `/models/`, `/bin/`) | downloaded |
| `556d.toml` | ports and in-repo paths only: `[daemon] port` 55600, `[hermes] home` / `exe`, `[shim] port` 55601 / `timeout_seconds` — no endpoints, no model names, no timezone | ours |
| `556.cmd` | Hermes CLI/TUI on `home/` (`%~dp0`; needs 556d running for the model shim) | ours |
| `.gitattributes`, `.gitignore` | `* -text` (bytes as committed on every machine: CRLF sources and golden files alike); ignored: `home/`, `characters/*/`, `/bin/`, `/models/`, build outputs | ours |

## Build & run
- Daemon: `go -C 556d build -o ..\556d.exe .\cmd\556d` (binary ignored).
- App: `cd app && npm install --ignore-scripts && npm run build && npm start`
  (`npm run dev` = vite + electron with live reload). Electron's postinstall download hangs on
  this network: if `node_modules/electron/dist` is missing, run its `install.js` manually or
  copy a matching `dist` (44.4.5).
- Everything else is spawned by 556d: the shim from `556d.toml` (its port), the embedder and the model backend
  from `home/models.json` (設定 → 模型連線).

## Wire protocols
- **App ↔ 556d (hub)**: HTTP `POST /api/chat` (header `X-556-Client`) to send; WebSocket `/ws`
  for everything that happens — `chat.user/delta/complete/error`, `companion.state`, avatar
  `message/motion/expression/speak_audio`. `GET /api/history?limit=X`, `GET/PUT /api/settings`,
  `GET/PUT /api/connections` + `POST /api/connections/probe` (the model connections, `home/models.json`: PUT applies at
  once to the shim, the embedder and the clock, running characters need a restart; the probe asks an endpoint which
  models it serves), `GET /api/companion`, `GET /api/models`, `POST /api/restart-hermes`, static (`/` = the app
  bundle, `/hiyori/...` models, `/live2dcubismcore.min.js`). OpenAI-compatible
  `/v1/chat/completions` (streaming) for third-party clients.
  The create-character page: `GET/POST /api/characters`, `GET /api/characters/{id}`, `PUT …/describe`, `PUT …/profile`,
  `POST …/run` (the soul skill as a subprocess of the venv's python, one job per package, log in `build/run.log`),
  `POST …/simple` (the simple path: sliders and three boxes → the files, no model), `POST …/install`
  (`install-character.ps1` + `seed-memories.py`; refused while the inputs are stale unless `force`), `GET …/job`; hub
  event `character.job`.
- **556d ↔ her gateway** (`internal/hermesapi`): the gateway's API server platform, enabled per start
  through `API_SERVER_KEY/HOST/PORT` in her environment (key generated once into her `companion.json`,
  port free at start; her `.env` can pin both). One non-stream `POST /v1/chat/completions` per turn with
  `X-Hermes-Session-Id` = **her one conversation** (the Telegram DM session; `POST /api/sessions` +
  a routing stamp when the app speaks first; companions without a channel use key `556:app`), health via
  `/health`. History and the live tail are read from her `state.db` (read-only, `companions.Transcript`),
  each message tagged app / telegram by Hermes's `platform_message_id`. The app is one client of her,
  same level as Telegram; turns serialized per companion in 556d. Client system prompts are not sent
  (SOUL owns persona). Approvals/clarify not surfaced — companion toolset policy avoids them.
- **hermes → models**: through the shim (:55601, `internal/shim`): one lane, `auto/556`, pointed at the 對話
  connection of `home/models.json` with its key as a bearer token; 503 (模型連線未設定) until it is configured. On the
  way in: the prompt-hygiene filter (`shim/hygiene.go`: Hermes's vendor paragraphs and the date paragraph dropped from
  every system message, logged when the set changes) and, only when a character has an extension, the `<tool_call>`
  text-protocol translation under a preamble that names no product. On the way out: the hidden `<think>…</think>`
  scratch stripped and logged before the tool-call parser (0.8.10), a text `<tool_call>` to the proxy's `openmini_reply`
  unwrapped into reply text, a 4-attempt retry on empty replies. The connections' timezone reaches every gateway as
  `HERMES_TIMEZONE`, the daemon's port as `X556_HUB`.

## Memory (kokoro on KeepsakeDB — see memory/memory.md and inner-life/inner-life.md)
**KeepsakeDB 1.0.1** (our memory engine, upstream Yooouuuuuuu/KeepsakeDB, API frozen; a git submodule at `vendor/keepsakedb/` pinned at the release tag, which `setup-vendor.ps1` installs editable, or a local checkout with `-LocalKeepsake` while developing it; Hermes's curated MEMORY.md /
USER.md head is off, the person file `people/你.md` is injected by kokoro): one SQLite file per profile, hybrid recall (dense vectors from the configured embedder + FTS5 BM25 with
CJK bigrams, RRF k=60), trust labels (high ≥ 0.60 / drop < 0.40), archive-with-reason + consent
windows, L2 pipeline on the 記憶 connection (`kokoro.json` `llm`, written by 556d from `home/models.json`) writing
memories in the configured language (zh-TW). Provider: `plugins/kokoro` (prefetch → the memory block, sync_turn →
observe on Hermes's memory worker). **No tools at baseline** (0.8.6): `kokoro_search` / `kokoro_forget` are still
defined (`kokoro.json` `tools: true`) but the `memory` toolset is in no `platform_toolsets` list — 556d strips it before
a start — so she is never offered them unless an extension brings tools back; memory reaches her through the per-turn
block and kokoro's zh-TW prompt section `kokoro.memory` (the memory rule + 關於你 from `people/你.md`, after Hermes's
memory tier). Keyword triggers (0.8.10, `triggers` / `trigger_k`): a roster name, a person file's name or her own name in
the message adds exact BM25 rows under `By name`. No pinned groups: the dated part of who she is (時間線,
影響過你的人與事) is SOUL text; the same events are dated seeds. Logs: history / search_log / pipeline_log in the
store, `logs/keepsake.jsonl` operational (muted in `hermes -z`). Snapshots daily to her `backups/`.
Inspect: `vendor\hermes-agent\.venv\Scripts\keepsake --db home\profiles\<id>\memory\<id>.db stats|list|log`.
**Memory page** (office window tab `記憶`, route `#/memory`): view + delete only. 556d opens the
store read-only with `modernc.org/sqlite` (pure Go) — `GET /api/memory?q=&tag=&archived=1&limit=&layer=long|short`,
`POST /api/memory/delete {ids, reason}` → a row in the store's `commands` table that the owning
Hermes process executes (status `done` with count, or `queued` until she next runs — she "wakes"
on the first chat turn of a session). Never writes the memory tables itself. Every memory a turn writes carries
`meta.turn_id` / `meta.source` (observe); the psyche engine adds `valence` / `arousal` / `instance_ids` later by turn id
(`json_patch` on meta only, never a re-embed).

**Settings & the config registry**: non-technical knobs directly; developer toggle shows every knob from
`GET /api/config` (`internal/api/registry.go`: key, group, type, scope, file+path, effect) and writes them
with `PUT /api/config` into her `config.yaml` / `kokoro.json` / `.env` or the global `556d.toml`; effects tell the UI
what to restart. The model connections are not registry knobs: they are 設定 → 模型連線 (`/api/connections`), and
556d writes them into her files before every start. Secrets are masked and kept when left empty. Since 0.7.4
設定 has two layers: 全域 (`/api/settings` you + app, `/api/voice` connectors, backend knobs) and 角色 (a character's
page; 556d edits the character on stage, so opening the page selects her). `/api/voice?companion=<id>` reads / writes
her `voice.json` override; speak and transcribe use the effective config (`voice.Effective`). A failed turn (model
lane down) is detected in the chat handler: the dangling user row is deactivated (`Transcript.DiscardOrphans`), the
windows get `chat.error {discarded}` and show gray system notes; `POST /api/history/discard` does the same for a cue
the engine could not get answered; unanswered rows older than 15 min are swept when her conversation opens.

**Roster / lifecycle** (office tab 名單, route `#/roster`): `GET /api/companions` (every
`home/profiles/<name>` with a config.yaml: display name from `companion.json`, channels detected from
`.env`, active state, API port), `POST /api/companions/{name}/start|stop` (start runs `prepareProfile` first — the
package sync, her files from the connections, the hygiene switches — and is refused with 模型連線未設定 while something is
missing), `GET/PUT /api/selected`.
`companions.Manager` (Go) owns exactly one `hermes gateway run` per active companion under the
supervisor's job object; stop cancels her context; app close stops all.
Chat, history, memory and the companion part of Settings act on the selected companion; hub events
(`chat.*`, `companion.state`, `message`) carry `companion`, plus `companion.selected` and
`companion.lifecycle`. Verified 2026-10-02 (one-process route): start → gateway ready with API server
in 7 s + Telegram connected → app turn through `/v1/chat/completions` → history by session id →
stop → zero Hermes processes.

**One conversation, two mirrors** (2026-10-02): app and Telegram share one Hermes session (above), so
history is cross-surface by construction and memory stays memory. 556d follows the session (2 s poll)
and shows Telegram turns in the windows with a badge; and after an app turn 556d sends
「你問我：q／我說：a」as plain text to her home channel (`TELEGRAM_HOME_CHANNEL`, else the first allowed
user) through her own bot token — no LLM; Settings toggle `mirror_to_telegram` (default on).

## Inner life (psyche plugin — see inner-life/inner-life.md)
`plugins/psyche` (Python; junction `home/profiles/<name>/plugins/psyche`; opted in with `plugins.enabled: [psyche]` in
her config.yaml — Hermes user plugins are opt-in, a memory provider activates through `memory.provider` instead). Hooks:
`pre_llm_call` → `{"context": <her-state>…【她現在】…}`, which Hermes appends to the user message right after the
`<memory-context>` block; `post_llm_call` → turn event + appraisal queued (own thread, never waited for); `on_unload` →
drain + snapshot. In her profile: `psyche.json` (`character`: Big Five, the seven constants incl. `chronotype`, `rumination`,
`memory_reliability`; `thinking` and `thinking_choices` (0.8.8); `relationships` (per-counterpart priors, `你` from the
package's closeness); `time` incl. `timezone_offset_h`, written by 556d from the connections; impact and expression
knobs, `cares_about`; copied from `characters/<id>/` before every start, the 主動 page writes both copies, the rest
applies at restart) and `psyche.db` (events, appraisals, instances, loops, withheld, snapshots, params, owner heartbeat;
WAL). Appraisal A runs on the `llm` block of kokoro.json (the 記憶 connection), 7–30 s per turn on a flash-class model. 556d reads `psyche.db` read-only for `GET /api/psyche` (狀態 tab) and waits for the last
turn's appraisal before a planned stop. Tests: `plugins/psyche/tests` (pytest from the KeepsakeDB venv) and
`tests/psyche_eval.py` (LLM eval set against a running character; judge = the same lane).
**Proactive (0.6.0)**: the engine's tick decides the urge (urge.py); the decision is a replayable `proactive_fired` event;
the send worker posts a narrator cue (events.py, `【事件】…`) to her own api_server with `X-556-Event` and her session
id; her answer lands as a normal row; the hooks record `sent` / `silent`. 556d: follower → `chat.complete` with
`source: event` + `sendTelegram` (same path as the app mirror); `GET/PUT /api/psyche/settings` (psyche.json, hot keys
`proactive`, `life.busyness_mode`, `cares_about`); `POST /api/psyche/command` → `commands` table (close_loop,
add_loop, life_event). Output checks (checks.py, record only) → `checks` table. Simulator: `tools/psychesim.py`
(week / day / seeds / replay). Engine modules: life.py (sleep, activities, life events), needs.py, tom.py, urge.py,
relation.py (L5 per counterpart, the hurt ledger, the expression strategies), thinking.py (0.8.8: the five thinking meters and the 想法 line). Loops since 0.7.4: a promise opens
only when she agreed (`agreed`); a promise that needs another character (`ask`) is asked once at her free time
(`ask_other` → relay), answered by that conversation's appraisal (`asking` → `answered`), reported back
(`report_back`) when she is up, outside your no-disturb hours and you are around; `proactive.ask_give_up_h` 48.
Undelivered due items back off (5/15/60 min, hourly) and after `undelivered_window_h` (6) are `forgot`;
`character.forgets` (default on) / `memory_reliability` (記性, default 0.8): as an item comes due, P(remember) = 記性
+ 0.3 if important − 0.3 × how much worse than usual her mood is. 556d tags narrator cue rows (`source cue`).
**Multi-agent (0.7.0)**: counterparts by session key (`556:agent:<name>`, source `556`); 556d `relay.go`:
`POST /api/relay/session` (open + stamp), `POST /api/relay {from, to, text}` (one conversation per pair, turn cap from
the initiator's psyche.json `proactive.inter_agent_turn_cap`, hub event `relay.turn`), `GET /api/relay/log` (+
`pending`, `outbox`); her plugins reach 556d at `X556_HUB` (spawn env). Mailbox (0.7.5): a message for a character
who is not running waits in `home/mailbox/<id>.json` (20 per pair, 7-day TTL) and is delivered at her start or the
next sweep, continuing the conversation; late delivery is prefixed with the time it was left. Characters:
`characters/<id>/` is the package (layout table above; `characters/README.md`) — authored `describe/` + `profile.json`,
generated SOUL / seeds / people / psyche.json by the soul skill (名單 → ＋ 新角色, or `tools/soul_writer.py`),
installed by the page or `install-character.ps1`, seeded by `tools/seed-memories.py` (store without an owner, embedder
up), and copied over her profile before every start.

## Third-party inventory (what is not ours, and where it lives)

Three kinds. **Vendored code** sits in `vendor/` and is never edited (see `vendor/README.md`).
**Package dependencies** are declared in a manifest and restored by the package manager; they are
not copied into `vendor/`. **Services** are called over the network under their own terms.

| Kind | Piece | License / terms | Declared in |
|---|---|---|---|
| submodule | Hermes Agent v0.21.0 (`7166071f`) | MIT (Nous Research) | `.gitmodules` → `vendor/hermes-agent/` |
| vendored | Live2D Cubism Core 4 | Live2D proprietary redistributable | `vendor/live2d/` |
| data | Hiyori model (SDK 4-r.7) | Live2D Free Material License | `assets/live2d/hiyori/` |
| npm | react, react-dom, zustand, pixi.js 7 | MIT | `app/package.json` |
| npm | pixi-live2d-display-lipsyncpatch | MIT | `app/package.json` |
| npm | `@ricky0123/vad-web` (bundles the Silero VAD ONNX models — MIT, snakers4/silero-vad — and the audio worklet) | ISC | `app/package.json`; built into `app/public/vad/` |
| npm | onnxruntime-web (wasm runtime for the VAD) | MIT | `app/package.json`; built into `app/public/vad/` |
| npm (dev) | electron 44.4.5, vite 6, tailwindcss 4 (`@tailwindcss/vite`), typescript 5 — build tools, not shipped in the bundle | MIT | `app/package.json` devDependencies |
| Go | modernc.org/sqlite (pure Go), gorilla/websocket, BurntSushi/toml, yaml.v3, x/sys | BSD-3 / BSD-2 / MIT / MIT / BSD-3 | `556d/go.mod` |
| submodule | KeepsakeDB 1.0.1 (ours) → numpy; optional httpx (pipeline LLM client) | MIT | `.gitmodules` → `vendor/keepsakedb/`; installed by `setup-vendor.ps1` |
| Python | `ddgs` (DuckDuckGo search, keyless) for the 查網路 extension | MIT | Hermes venv, `setup-vendor.ps1` |
| downloaded | llama.cpp CPU build; an embedding GGUF (bge-m3 Q8_0 here) — only when the vectors are local, paths set in 設定 → 模型連線 | MIT; MIT (BAAI) | `bin/`, `models/` (ignored) |
| service | Fish Audio (TTS `/v1/tts`, ASR `/v1/asr`) | Fish Audio terms; key in `home/voice.json` (a character may override in her `voice.json`) | 設定 → 語音連線 / 角色 → 聲音 |
| service | the model endpoints in `home/models.json` (any OpenAI-compatible server: 對話, 記憶, 寫靈魂, and embeddings when not local); Telegram Bot API | provider terms; her own bot token | 設定 → 模型連線; her `.env` |

Not used (considered and dropped): sherpa-onnx local STT and the MOSS-TTS server from the earlier
voice agent — 556 uses cloud STT/TTS connectors instead; mem0 + Qdrant (the 0.3.0 Path A, replaced by KeepsakeDB;
the last leftovers — `mem0ai` / `qdrant-client` in `setup-vendor.ps1`, `home/mem0.json`, the `mem0` provider option —
left in 0.9.0).

## Avatar
`Live2DStage` (pixi 7 + pixi-live2d-display-lipsyncpatch `cubism4` ESM; Core 4 fetched from
556d at runtime), fitted bottom-center, idle/tap motions, bubbles + motions from the hub. The
avatar window is transparent/frameless/always-on-top, drag-anywhere (IPC), hides on close.

### Live2D pitfalls (learned the hard way)
1. Cubism Core must be **v4** (SDK 4-r.7); the official URL serves Core 5 → black clipping.
2. Model assets must be **Cubism-4-era** (SDK tag `4-r.7`): the `develop` (SDK5) assets have PNGs
   Chrome's GPU upload rejects and masks that never render. Exact bytes matter → versioned.
3. Headless Chrome on this machine renders no WebGL textures; verify with `tools/cdp_shot.mjs`
   (real Chrome) or `app/scripts/cdp_capture.mjs` (the live app, `--remote-debugging-port=9223`).

## Retired
0.2.0: Python shim, adapter, static server, Node bridge, `embedder.cmd`, ports 18767/19200/
19201/19260/19270/18768. 0.3.0: Artemis web-chat SPA, old Electron pet, viewer page,
`avatar.cmd`/`pet.cmd`, `/chat/`, `vendor/artemis/`. 0.9.0: `shim/routing.json` and its lanes `pro` / `code`, the
endpoint / model / embedder / timezone keys of `556d.toml`, the gemini / claude / opus nicknames, the mem0 / Qdrant
leftovers. 0.10.0: pinned groups (`pinned_tags` / `pinned_per_tag`, `tests/test_kokoro_pinned.py`).
