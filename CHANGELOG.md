# Changelog

## 0.4.0 — 2026-10-06

Her own process, one conversation, her memory, her Telegram, her voice. 真音 is the first character.
Memory engine switch: **kokoro on KeepsakeDB** replaces mem0 + Qdrant.

- **`plugins/kokoro`** — Hermes memory provider on KeepsakeDB (`D:\dev\KeepsakeDB`, installed into the
  Hermes venv): hybrid recall (bge-m3 dense + FTS5 BM25 with CJK bigrams, RRF), trust labels,
  archived topics as meta-info with consent windows, L2 pipeline on gemini-3.8-flash writing
  memories in the configured language (zh-TW); tools `kokoro_search` / `kokoro_forget`.
  Config `home/kokoro.json`; store `home/memory/<profile>.db`; daily snapshots `home/backups/`.
- **Memory page** in the office window (view + delete only): 556d reads the store file directly
  (pure-Go SQLite, read-only) — `GET /api/memory` (substring, tag and archived filters, stats,
  tags), `POST /api/memory/delete` through the engine's command queue (done in < 1 s while she
  runs, queued otherwise). Route `#/memory`.
- **Roster and lifecycle** (DECISIONS 2026-10-02): companions are Hermes profiles under
  `home/profiles/<name>`; nothing auto-starts. The office window's 名單 tab starts/stops each one
  (several active at once, app close stops all) and picks which one the chat window — and the
  avatar — is on. Per active companion 556d runs **one process**: her `hermes gateway run`, whose
  API server is the app's route and whose adapters (from her `.env` tokens) are her channels, so
  channel bindings are strictly hers. API: `GET /api/companions`, `POST /api/companions/{name}/start|stop`,
  `GET/PUT /api/selected`; chat/history/memory/settings act on the selected companion
  (`?companion=` / `X-556-Companion` override); hub events carry `companion`.
- **First character: 真音 (Mane)** — profile `home/profiles/mane` (fresh SOUL, kokoro.json with the
  fixed memory subject 製作人, companion.json), the app opens on her (`556d.toml daemon.profile`).
- **Settings: Producer's name** → written through to the selected profile's `memories/USER.md`
  and `kokoro.json`; memory language / embedder write through to `kokoro.json`.
- **Settings, two tiers**: non-technical knobs directly; a developer toggle (with warning) renders every
  other knob from the config registry (`/api/config`) and writes it into the right file; nothing stays
  fixed in a config file. Changing the memory subject or tokenizer now migrates / reindexes the store.
- **Telegram, live**: 真音 answers DMs on her own bot account (token + allowlist in her profile's
  `.env`); memory pipeline runs on channel turns too.
- **One route per character** (DECISIONS 2026-10-02): `hermes serve` removed; 556d talks to her gateway's
  OpenAI-compatible API server (`internal/hermesapi`: one non-stream chat request per turn,
  `X-Hermes-Session-Id` continuity, `/health` → `hermes_connected`).
  `internal/hermes` (JSON-RPC client) deleted; `556d.toml [hermes] port/token` gone.
- **Voice modes**: 🎙 press-to-record into the composer (STT), and 對話模式 — a hands-free loop with Silero VAD
  in the browser (`@ricky0123/vad-web`), the tuned endpointing from the earlier voice agent, one STT → one chat
  turn (spoken-style hint) → one TTS → one playback through the avatar window (lip-sync) with FIFO queueing and
  an echo guard. New connector kind `fish-audio`; `/api/voice/transcribe`, `/api/voice/speak`; hands-free
  parameters in `home/voice.json` + Settings. VAD assets ship in `app/public/vad` (built, ignored).
- **Two memory layers** (KeepsakeDB 0.2.0): the observe call may also return a dated `note` for the short
  layer (ring of 1000, no tags, surface in meta); prefetch embeds once and searches both layers at once
  (bigger first, own read connections), hybrid top 5 each, injected as Facts / Notes with the priority rule
  in her system prompt. Memory page: long by default, toggle for 近期紀錄; knobs `kokoro.short_*`.
- **Her one session is opened by the start**, not by a message: `openConversation` runs after the gateway is
  healthy (create + Telegram routing stamp). `/new` and other gateway slash commands are admin-only on her
  Telegram (placeholder admin id), so nothing can fork the conversation from the phone.
- **One conversation per character**: the app continues her Telegram DM session by id, so Telegram and the
  app share one history (Hermes rebuilds context from `state.db` each turn). When the app speaks first,
  556d opens the session via `POST /api/sessions` and stamps the Telegram routing identity so her first
  Telegram message joins it. History and the live tail come from her session store (`companions.Transcript`);
  Telegram turns appear in the app with a badge. (A short-lived 'recent-exchange layer' in memory was
  removed the same night — history is not memory.)
- **Telegram mirror**: after each app turn 556d posts「你問我：q／我說：a」(plain text, no LLM) to her
  home channel via her bot token; Settings toggle `mirror_to_telegram` (default on); registry knob
  `telegram.home_channel` (`TELEGRAM_HOME_CHANNEL`, also kills the 📬 no-home-channel notice).
- **Graceful stop**: roster stop, app quit (`POST /api/shutdown`, the app waits) and app death all ask
  her gateway to finish up through Hermes's planned-stop marker (target = her `gateway.pid`); kill only
  after 60 s. A stop also waits (≤ 30 s) until the memory pipeline has observed the newest turn — Hermes
  queues the observe a few seconds after the reply, and a stop in that window used to lose it. Roster shows 收尾中.
  Her Telegram no longer gets Hermes's「Gateway shutting down」ping on each stop
  (`platforms.telegram.gateway_restart_notification: false`; dev knob `telegram.restart_notice`).
- **Settings**: her reply language (default follow / en / zh-CN / zh-TW / ja → USER.md); voice connectors
  (OpenAI-compatible TTS/STT in `home/voice.json`, round-trip test). `new-companion.ps1` + `templates/companion/`.
- **556d `-no-hermes`** — now the default behaviour (kept as a no-op flag); 556d no longer spawns a
  Hermes at startup.
- Endurance: 100 rounds 19/20; 1000-round run (483 real rounds before a backend outage) with the
  exam re-run 20/20 — the Path A correction trap is fixed (see docs/MEMORY-DESIGN.md).
- Settings: the memory-language note is now true (kokoro honors it). mem0 config stays as fallback.

## 0.3.0 — 2026-10-01

The app. One Windows program, **556 Production**, replaces the transitional Artemis web chat and
the separate Electron pet.

- **App** (`app/`, Electron + React + TypeScript, zh-TW default): office window with chat and
  settings; avatar window (transparent, always-on-top, drag-anywhere) toggled by button or tray;
  minimize → tray; closing the app closes the whole backend.
- **Backend ownership**: the app spawns `556d -parent-pid`; 556d exits when the app dies; its
  job object reaps hermes/llama. Verified for graceful quit and force-kill.
- **556d hub**: chat events for every connected client on `/ws` (`chat.user/delta/complete/error`,
  `companion.state`), `/api/history`, `/api/settings` with write-through to Hermes config,
  `/api/companion`, `/api/restart-hermes` (client reconnects, session recreated).
- **Chat window**: last X turns, hub-driven rendering (a message from any client appears
  everywhere), streaming, IME-safe Enter. **Settings**: her name, Live2D model, show-on-start,
  model lane, context turns, memory language, embedder (re-embed warning), restart button.
- **Avatar**: Live2D stage in React (pixi + cubism4 ESM, Core 4 from 556d), hub bubbles/motions.
- Retired: `ui/` (SPA, old pet, viewer), `avatar.cmd`/`pet.cmd`, `/chat/`, **`vendor/artemis`**
  (the Artemis ledger is empty). Diagnostics moved to `tools/`. App icon added.

Known gaps: no installer/packaging (0.4.0); companion switcher UI not built; approval/clarify
not surfaced (toolset policy); no proactive pushes; memory language effective only with the
kokoro engine; IME behavior still needs a human check; first companion unnamed.


## 0.2.0 — 2026-09-30

Backend rewrite: five hand-started processes in two runtimes became one Go daemon.

- **`556d`** (Go): supervisor (Windows job object, backoff, health probes) spawning `hermes serve`
  and the bge-m3 embedder; **shim** port (:55601) with Python-golden parity tests; **avatar bridge**
  (:55600, `/ws`, Artemis-compatible API, audio cache); **chat API** — OpenAI-compatible
  `/v1/chat/completions` (streaming) backed by a persistent `hermes serve` session over JSON-RPC.
- **Web chat and pet now reach the real her** (SOUL + memory + tools); replies bubble on the avatar.
  Web chat is served by 556d at `/chat/`.
- Repo layout: `vendor/` (untouchable: hermes-agent, artemis, Cubism core), `plugins/`, `assets/`;
  Artemis leftovers removed; `setup-vendor.ps1` restores the pinned engine.
- Ports → 556xx family. Retired: Python shim, adapter, static server, Node bridge, `embedder.cmd`.
- Decisions recorded: Go beside Hermes / Python inside; TypeScript UI under Electron (no Rust/Tauri);
  `tui_gateway` as the Hermes surface; memory-language policy still open.

Known gaps: approval/clarify prompts not surfaced in the UI; no proactive pushes; frontend still
the transitional Artemis SPA; no TTS/STT/image-gen; first companion unnamed; Path C not built.

## 0.1.0 — 2026-09-30

Founding release of **556 Production** (556プロ / 心プロダクション — 5-5-6 = こころ).

- **Backbone**: vendored Hermes Agent engine, isolated HERMES_HOME, own shim router with model
  lanes and tool-call translation for the Gemini proxy.
- **Memory**: mem0 + embedded Qdrant, bge-m3 embedder on CPU, extraction on gemini-3.8-flash,
  always-on writes. 1000-round zh-TW endurance test: 19–20/20 recall. Design lineage A → C → C2.
- **UI**: web chat + thin API adapter, Live2D avatar with official Hiyori model, Electron desktop
  pet — transparent, always-on-top, drag-anywhere.
- **Docs**: STACK, ARCHITECTURE, DECISIONS, ROADMAP, MEMORY-DESIGN.
