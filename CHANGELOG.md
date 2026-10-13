# Changelog

## 0.7.0 — 2026-10-13

- **Her inner life, stages 5–6 — relationships, hurt and repair, three characters** (`docs/inner-life/inner-life.md`).
  Every relationship variable is indexed by the person she is dealing with (you, or another character): warmth and
  bond (two speeds), closeness hours with Hall's milestones, disclosure depth, attachment strength growing from zero
  (or from a prior for old acquaintances), the anxiety / avoidance working model, trust as a Beta count of kept and
  broken promises, commitment, perceived responsiveness. The hurt ledger (TRIM) opens only on a relational
  devaluation, slides away by trend forgiveness, is cut by an apology that owns the fault and nearly erased by a
  false-belief correction; its open avoidance gates inverted expression and, after a while, makes her offer the step
  down herself. The expression layer carries the five strategies (直說 / 收斂 / 玩笑 / 反話 with a required tell /
  否認), display rules (what she shows = what she feels × expressiveness × closeness), suppression when you look
  exhausted, assertiveness, and a reply-length hint; the block gains a 對他 line.
- **Inter-agent messaging** (556d `relay.go`): characters talk to each other through 556d. Each pair has a session
  in each character's own `state.db` (key `556:agent:<name>`, opened and stamped like your conversation); a
  character's urge toward another produces an event turn in that session, the psyche plugin hands the message to
  556d, and 556d carries the exchange turn by turn until silence or the turn cap (per character, default 6). Both
  sides appraise, remember and update their relationship with the other as the counterpart; kokoro writes those
  memories with the other's name as the subject and injects the other's person file. `GET /api/relay/log` shows
  their conversations; the 狀態 page lists them when the character's 主動 → visibility allows.
- **Three characters with full backgrounds** under `characters/` (provisional names): 小夜 (sayo, just met),
  千尋 (chihiro) and 悠真 (yuma, the couple; your old acquaintances). Each has a SOUL with background, a
  psyche.json with personality, schedule, small life events and relationship priors per counterpart, person files
  for you and each other, and seed memories (`tools/seed-memories.py`). `install-character.ps1 <id>` makes the
  profile. 真音 stays as the test agent.
- **狀態**: relationship table (closeness words, trust, attachment, hours, disclosure), the hurt ledger, feedback
  buttons on each feeling (太多 / 剛好 / 太少 → ±5 % on that emotion's gain, bounded, replayable), the characters'
  conversations. **設定 → 主動**: inter-agent on/off, turn cap, visibility.
- Engine tests 38 (new: 失約 3 次, 失約後道歉, 誤會後更正, 90 天, 黏人度掃描, 傲嬌度掃描, 三人一個月, feedback).

## 0.6.0 — 2026-10-08

- **Her inner life, stages 3–4 — she speaks first** (`docs/inner-life/inner-life.md`). The psyche plugin now carries
  her time skeleton: the two-process sleep model (bedtime delayed by a late conversation, a message can wake her,
  sleep debt colours the next day), social fatigue, an activity state from a schedule template and a busyness mode
  (work / hobby / none: attention load, interruptibility), small life events and project progress from a seeded rule
  table, the six needs with Bowlby's separation phases (protest → despair → detachment), rumination on idle attention,
  a presence model of your week and a reply-latency model, open loops that come due by cue time. The urge
  λ = W × O × p̂ × D × gates decides when she wants to speak; due loops (reminders you asked for, her 「等我一下」)
  fire on time; one unanswered message → she waits long, two → she waits for you, never a third.
- **Event turns**: the engine posts a narrator-style cue to her own api_server (`X-556-Event`) in her ONE conversation;
  she writes the message in her own words or stays quiet (「（沉默）」). 556d's follower hides the cue, shows her words
  with a 她主動 badge, sends them to Telegram on the app-mirror path, and drops silence and platform errors; kokoro
  skips the observe for these turns; a planned stop no longer waits for an appraisal of them.
- **Settings → 主動**: enabled, no-disturb window, daily cap, usage threshold, minimum gap, speak override (follow /
  always / never), busyness, what she cares about, and her personality sliders (`GET/PUT /api/psyche/settings`); the
  gates apply within a minute, personality and schedule at her next start.
- **狀態 page**: what she is doing, her needs, the separation phase, loops with a close button, add a reminder or a
  life event (commands queued in `psyche.db`, drained by the engine: 556d still never writes her state), the state
  block she saw, a fuller event timeline, output-check counts.
- **Output checks, record only**: literal rules for meta leaks, surveillance phrasing, assistant mode and obvious life
  confabulation on every reply (`transform_llm_output`), into a `checks` table. Farewell mode and usage awareness.
- **Engine semantics**: urges are decided live only and recorded as replayable events, so a replay re-applies them
  and a fast-forward after a stop back-fills nothing (a due reminder fires late, once she runs). Snapshots every
  5 min, after every applied record and block, and at exit (`atexit`, since the gateway's drain never unloads
  plugins). `tools/psychesim.py` (week / day / seeds / replay) and 9 scenario tests (失聯 7 天, 連續熬夜, 半夜傳訊息,
  工作中, 忙碌度 0, 使用量, 提醒準時穿過免打擾, 等我一下, replay with a life); 30 tests in all.
- Verified live on 真音: a reminder two minutes out → event turn → her words in the conversation → Telegram, stop 2 s.

## 0.5.0 — 2026-10-07

- **Docs restructure**: `docs/` holds concept documents only, one folder per part (`structure/`, `memory/`, `app/`,
  `voice/`, `inner-life/`), each a living doc with its D2 graphs beside it (eight graphs, two new: psyche, proactive);
  `DECISIONS.md` and `STACK.md` at the docs root, `README.md` the map; outdated plans, drafts and notes deleted;
  working documents (roadmap, test list) are `docs/*.local.md`, ignored.

- **Her inner life, first milestone — stages 0–2 of `docs/inner-life/inner-life.md`** (2026-10-07): a second plugin
  inside her Hermes process, `plugins/psyche` (opted in with `plugins.enabled: [psyche]`), is the single writer of
  `psyche.db` in her profile: events, appraisals, instances, loops, snapshots, params. A fixed 1-minute tick with seeded
  noise (OU exact solution for core affect, PAD pull–push mood, a circadian energy placeholder) makes replay rebuild the
  same state and turns a stop of any length into the missed ticks run in one go. After each turn, appraisal A (one LLM
  call on the memory lane, fired at the same moment as kokoro's observe, never waited for) reports what happened as
  appraisal vectors and open loops; the deterministic impact model B turns them into emotion instances (prototype
  matching, intensity, half-life, stacking, resolution by apologies and kept promises). Before each reply, `pre_llm_call`
  injects the 【她現在】 state block (≤ 8 lines, words not numbers, names transitions) right after the memory block.
  The turn's memories are stamped (KeepsakeDB 0.3.0 `turn_id` / `source`) and annotated afterwards with valence,
  arousal and instance ids. `people/你.md` replaces `memories/USER.md` (Settings write-through moved, the old file
  carried over once). New 狀態 tab (`GET /api/psyche`, read-only). Graceful stop also waits for the last turn's
  appraisal. 20 engine + golden-case tests; LLM eval set (`tests/psyche_eval.py`), 6-turn scenario: expression gap 0.17
  (0 = reply matches the state), emotion named 1/6 (when asked outright), meta leak 0, assistant mode 0.
- **new-companion.ps1**: links both plugins, installs `psyche.json` and `people/你.md`, opts the psyche plugin in,
  writes templates without a BOM (a BOM in kokoro.json broke the memory provider); the script stays ASCII.
- **製作人 → 你** (2026-10-07): memories are stored with 你 as the subject (her store is migrated on next start)
  and rendered with her term for you — your name from Settings, else 製作人 — when injected or searched, so
  the prompt never confuses 你 with herself and renaming never rewrites the store (KeepsakeDB 0.2.1
  `render_subject`). Settings section 你 / 你的名字 (`your_name`); USER.md header 你; her SOUL keeps 製作人 as
  the role she uses.
- **Baseline toolset = memory only**: `kokoro_search` / `kokoro_forget`. `platform_toolsets` written per
  character for the app route and Telegram; Hermes's built-in memory writer off; kokoro injects USER.md.
  Her prompt loses the 18 default tool schemas.
- **Extensions** (`/api/tools`, 設定 → 她會的事): per-character toggles written into her config.yaml and
  applied by a graceful restart (no hot toggling). First extension: 查網路 (`web`), keyless via Hermes's
  free-tier ring and the `ddgs` package (added to `setup-vendor.ps1`).

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
  exam re-run 20/20 — the Path A correction trap is fixed (see docs/memory/memory.md).
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
