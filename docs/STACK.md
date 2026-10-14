# STACK — what exactly this project is using

Last verified: 2026-10-01 (0.3.0). Ground-truth inventory; update it when reality changes.
Reasoning behind each choice: `DECISIONS.md` and the part docs (`structure/`, `memory/`, `app/`, `voice/`, `inner-life/`).

## One app

**556 Production** (`app/`, Electron + React) is the product. Launching it starts and owns the
whole backend; closing it shuts everything down.

Diagrams: D2 sources next to each part doc (`structure/`, `memory/`, `voice/`, `inner-life/`).

```
556 Production (Electron)          office window: chat + settings · avatar window (toggle) · tray
  └─ spawns 556d.exe -parent-pid   (Go)  :55600  hub: chat API + events on /ws + avatar bridge + static
        ├─ shim               :55601  OpenAI-compatible model router (lanes → Gemini proxy)
        ├─ llama-server       :55602  bge-m3 embedder on CPU (KeepsakeDB dense leg), shared
        └─ per ACTIVE companion (started from the roster, never automatically) — ONE process:
              └─ hermes gateway run  :dynamic  her brain (HERMES_HOME = home/profiles/<name>): SOUL + kokoro memory
                                               + tools; inside it the OpenAI-compatible API server (the app's
                                               route) and her channel adapters (Telegram / Discord from her .env)
External, untouched: Gemini proxy :18765 (user's), production shim :18766 (user's D:\Hermes).
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
| `app/` | the app: `electron/` (main, preload, backend lifecycle), `src/` (React: Office/Chat/Settings/Avatar, `live2d/Live2DStage`, `store` = hub WebSocket state, `api`, `i18n` zh-TW default), `assets/` icons, `scripts/` (dev runner, `cdp_capture.mjs`) | ours |
| `app/public/vad/` | build output: Silero VAD models + audio worklet (from `@ricky0123/vad-web`) and ONNX Runtime wasm (from `onnxruntime-web`), copied by `scripts/copy-vad.mjs`, served by 556d at `/vad/` (ignored) | generated |
| `556d/` | Go daemon: `internal/{config,supervisor,shim,bridge,hermes,api}`; config `556d.toml` | ours |
| `vendor/hermes-agent/` | Hermes Agent v0.21.0: git submodule pinned at upstream `7166071f` (fetched shallow); its venv `.venv` (py3.11/uv) is ignored. `setup-vendor.ps1` checks it out and builds the venv | **never edited** |
| `vendor/keepsakedb/` | KeepsakeDB 1.0.1 (ours, upstream Yooouuuuuuu/KeepsakeDB): git submodule pinned at the release tag `v1.0.1`, installed editable into the Hermes venv by `setup-vendor.ps1`. Bumped only on a bug-fix release (`git -C vendor/keepsakedb checkout vX.Y.Z`, commit the pin) | never edited here |
| `vendor/live2d/` | Cubism Core **4** (`live2dcubismcore.min.js`) | never edited |
| `assets/live2d/hiyori/` | official free Hiyori model (Cubism-4-era assets, SDK tag 4-r.7) | third-party data |
| `plugins/` | Python that plugs INTO Hermes: `kokoro/` memory provider on KeepsakeDB (live; linked into `home/plugins/`), platform adapter — planned | ours |
| `home/` | HERMES_HOME of the shared shell (profile `default`): `config.yaml` (model → shim :55601 lane `auto/556`, `memory.provider: kokoro`), `kokoro.json`, `settings.json`, `plugins/kokoro` (junction), `memory/default.db` (the test stores), legacy `mem0.json` + `mem0_qdrant/` (Path A fallback), sessions | runtime (ignored) |
| `home/profiles/<id>/` | **a character's HERMES_HOME** (Hermes profile, created by `new-companion.ps1`; `mane` is the disposable test character): `SOUL.md`, `people/*.md` (`你.md` carries your name and reply language as managed lines, written into every profile on save), `config.yaml`, `kokoro.json` (`subject: 你`, `your_name`, `address_default`), `voice.json` (her voice override, optional), `psyche.json`, `.env` (her own bot tokens), `plugins/kokoro` + `plugins/psyche` (junctions), `memory/<id>.db` (KeepsakeDB), `state.db` (sessions = history), `psyche.db` | ours |
| `shim/routing.json` | lanes → backends (hot-reload): `556`→gemini-flash, `pro`→gemini, `code`→claude | ours |
| `tools/` | diagnostics: `cdp_shot.mjs` (real-Chrome screenshot), `ws_probe.mjs`, `hub_probe.mjs` | ours |
| `models/`, `bin/` | bge-m3 Q8_0 GGUF; llama.cpp CPU build (ignored, downloaded) | downloaded |
| `tests/memory_stress.py` | 1000-round zh-TW memory benchmark harness | ours |
| `556.cmd` | Hermes CLI/TUI on this home (needs 556d running for the model shim) | ours |

## Build & run
- Daemon: `go -C 556d build -o ..\556d.exe .\cmd\556d` (binary ignored).
- App: `cd app && npm install --ignore-scripts && npm run build && npm start`
  (`npm run dev` = vite + electron with live reload). Electron's postinstall download hangs on
  this network: if `node_modules/electron/dist` is missing, run its `install.js` manually or
  copy a matching `dist` (44.4.5).
- Everything else is spawned by 556d from `556d.toml`.

## Wire protocols
- **App ↔ 556d (hub)**: HTTP `POST /api/chat` (header `X-556-Client`) to send; WebSocket `/ws`
  for everything that happens — `chat.user/delta/complete/error`, `companion.state`, avatar
  `message/motion/expression/speak_audio`. `GET /api/history?limit=X`, `GET/PUT /api/settings`,
  `GET /api/companion`, `GET /api/models`, `POST /api/restart-hermes`, static (`/` = the app
  bundle, `/hiyori/...` models, `/live2dcubismcore.min.js`). OpenAI-compatible
  `/v1/chat/completions` (streaming) for third-party clients.
- **556d ↔ her gateway** (`internal/hermesapi`): the gateway's API server platform, enabled per start
  through `API_SERVER_KEY/HOST/PORT` in her environment (key generated once into her `companion.json`,
  port free at start; her `.env` can pin both). One non-stream `POST /v1/chat/completions` per turn with
  `X-Hermes-Session-Id` = **her one conversation** (the Telegram DM session; `POST /api/sessions` +
  a routing stamp when the app speaks first; companions without a channel use key `556:app`), health via
  `/health`. History and the live tail are read from her `state.db` (read-only, `companions.Transcript`),
  each message tagged app / telegram by Hermes's `platform_message_id`. The app is one client of her,
  same level as Telegram; turns serialized per companion in 556d. Client system prompts are not sent
  (SOUL owns persona). Approvals/clarify not surfaced — companion toolset policy avoids them.
- **hermes → models**: through the shim (:55601): `<tool_call>` text translation for the Gemini
  proxy, lane fallback chains, 4-attempt retry for emulated backends.

## Memory (kokoro on KeepsakeDB — see memory/memory.md and inner-life/inner-life.md)
**KeepsakeDB 1.0.1** (our memory engine, upstream Yooouuuuuuu/KeepsakeDB, API frozen; a git submodule at `vendor/keepsakedb/` pinned at the release tag, which `setup-vendor.ps1` installs editable, or a local checkout with `-LocalKeepsake` while developing it; Hermes's curated MEMORY.md /
USER.md head is off, the person file `people/你.md` is injected by kokoro): one SQLite file per profile, hybrid recall (bge-m3 dense + FTS5 BM25 with
CJK bigrams, RRF k=60), trust labels (high ≥ 0.60 / drop < 0.40), archive-with-reason + consent
windows, L2 pipeline on `agy/gemini-3.8-flash` writing memories in the configured language
(zh-TW). Provider: `plugins/kokoro` (prefetch → block, sync_turn → observe on Hermes's memory
worker, tools `kokoro_search` / `kokoro_forget`). Logs: history / search_log / pipeline_log in the
store, `logs/keepsake.jsonl` operational (muted in `hermes -z`). Snapshots daily to `home/backups/`.
Inspect: `D:\dev\KeepsakeDB\.venv\Scripts\keepsake --db home\memory\default.db stats|list|log`.
Path A (mem0 + Qdrant) stays on disk as the fallback (`memory.provider: mem0`).
**Memory page** (office window tab `記憶`, route `#/memory`): view + delete only. 556d opens the
store read-only with `modernc.org/sqlite` (pure Go) — `GET /api/memory?q=&tag=&archived=1&limit=`,
`POST /api/memory/delete {ids, reason}` → a row in the store's `commands` table that the owning
Hermes process executes (status `done` with count, or `queued` until she next runs — she "wakes"
on the first chat turn of a session). Never writes the memory tables itself. Every memory a turn writes carries
`meta.turn_id` / `meta.source` (observe); the psyche engine adds `valence` / `arousal` / `instance_ids` later by turn id
(`json_patch` on meta only, never a re-embed).

**Settings & the config registry**: non-technical knobs directly; developer toggle shows every knob from
`GET /api/config` (`internal/api/registry.go`: key, group, type, scope, file+path, effect) and writes them
with `PUT /api/config` into her `config.yaml` / `kokoro.json` / `.env` or the global `556d.toml` /
`shim/routing.json`; effects tell the UI what to restart. Secrets are masked and kept when left empty. Since 0.7.4
設定 has two layers: 全域 (`/api/settings` you + app, `/api/voice` connectors, backend knobs) and 角色 (a character's
page; 556d edits the character on stage, so opening the page selects her). `/api/voice?companion=<id>` reads / writes
her `voice.json` override; speak and transcribe use the effective config (`voice.Effective`). A failed turn (model
lane down) is detected in the chat handler: the dangling user row is deactivated (`Transcript.DiscardOrphans`), the
windows get `chat.error {discarded}` and show gray system notes; `POST /api/history/discard` does the same for a cue
the engine could not get answered; unanswered rows older than 15 min are swept when her conversation opens.

**Roster / lifecycle** (office tab 名單, route `#/roster`): `GET /api/companions` (every
`home/profiles/<name>` with a config.yaml: display name from `companion.json`, channels detected from
`.env`, active state, API port), `POST /api/companions/{name}/start|stop`, `GET/PUT /api/selected`.
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
drain + snapshot. In her profile: `psyche.json` (Big Five, six constants, time constants, impact knobs, `cares_about`;
written with defaults on first start; Settings edits apply at restart) and `psyche.db` (events, appraisals, instances,
loops, snapshots, params, owner heartbeat; WAL). Appraisal A runs on the `llm` block of kokoro.json (the memory lane),
7–30 s per turn on Gemini flash. 556d reads `psyche.db` read-only for `GET /api/psyche` (狀態 tab) and waits for the last
turn's appraisal before a planned stop. Tests: `plugins/psyche/tests` (pytest from the KeepsakeDB venv) and
`tests/psyche_eval.py` (LLM eval set against a running character; judge = the same lane).
**Proactive (0.6.0)**: the engine's tick decides the urge (urge.py); the decision is a replayable `proactive_fired` event;
the send worker posts a narrator cue (events.py, `【事件】…`) to her own api_server with `X-556-Event` and her session
id; her answer lands as a normal row; the hooks record `sent` / `silent`. 556d: follower → `chat.complete` with
`source: event` + `sendTelegram` (same path as the app mirror); `GET/PUT /api/psyche/settings` (psyche.json, hot keys
`proactive`, `life.busyness_mode`, `cares_about`); `POST /api/psyche/command` → `commands` table (close_loop,
add_loop, life_event). Output checks (checks.py, record only) → `checks` table. Simulator: `tools/psychesim.py`
(week / day / seeds / replay). Engine modules: life.py (sleep, activities, life events), needs.py, tom.py, urge.py,
relation.py (L5 per counterpart, the hurt ledger, the expression strategies). Loops since 0.7.4: a promise opens
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
`characters/<id>/` (SOUL, companion.json, psyche.json, kokoro.json keys, people/, seeds.jsonl) — the user's own,
ignored by git except `characters/README.md`; `install-character.ps1`, `tools/seed-memories.py` (store without an
owner, embedder up).

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
| Go | modernc.org/sqlite (pure Go), gorilla/websocket, BurntSushi/toml, yaml.v3, x/sys | BSD-3 / BSD-2 / MIT / MIT / BSD-3 | `556d/go.mod` |
| submodule | KeepsakeDB 1.0.1 (ours) → numpy; optional httpx (pipeline LLM client) | MIT | `.gitmodules` → `vendor/keepsakedb/`; installed by `setup-vendor.ps1` |
| Python | `ddgs` (DuckDuckGo search, keyless) for the 查網路 extension | MIT | Hermes venv, `setup-vendor.ps1` |
| downloaded | llama.cpp CPU build; bge-m3 Q8_0 GGUF | MIT; MIT (BAAI) | `bin/`, `models/` (ignored) |
| service | Fish Audio (TTS `/v1/tts`, ASR `/v1/asr`) | Fish Audio terms; key in `home/voice.json` (a character may override in her `voice.json`) | 設定 → 全域 → 語音連線 / 角色 → 聲音 |
| service | Gemini / Claude through the user's proxy (:18765); Telegram Bot API | provider terms; her own bot token | shim lanes; her `.env` |

Not used (considered and dropped): sherpa-onnx local STT and the MOSS-TTS server from the earlier
voice agent — 556 uses cloud STT/TTS connectors instead; mem0 + Qdrant (replaced by KeepsakeDB).

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
`avatar.cmd`/`pet.cmd`, `/chat/`, `vendor/artemis/`.
