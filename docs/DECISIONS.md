# Decisions log

## Decided
- 2026-09-29 — Workspace: everything under `D:\dev\556_production` (placeholder name).
- 2026-09-29 — Backbone: Hermes Agent (own copy, fresh venv, isolated HERMES_HOME) replaces
  Artemis's OpenClaw role. Production D:\Hermes stays untouched.
- 2026-09-29 — Model access: via the existing shim (:18766) lanes; testing lane `auto/probe`.
- 2026-09-29 — Gemini-only for now (proxy :18765 behind the shim). The shim is mandatory for
  tool calling (proxy strips `tools`; direct mode = chat-only with silent tool hallucination).
  Full loop verified: chat, tools, memory write, cross-session recall.
- 2026-09-29 — Project runs its OWN shim copy (:18767, `shim\`) instead of touching the
  production shim; chat model = `agyapi/gemini-3.7-flash` via lane `auto/556_production`
  (tool calling verified on flash). `auto/pro` kept for heavier jobs.
- 2026-09-29 — Live2D: official free sample models first; polish/custom later.

## Decided (2026-09-30, continued)
- **System name: 556 Production** (556プロ / 心プロダクション). Goroawase こ(5)こ(5)ろ(6) =
  心 kokoro — an idol-agency-style name (765PRO lineage: the number encodes a word): a good
  place where hearts and minds are created. The system is the AGENCY; companions are the talent;
  the user is the Producer. AI/tech stays subtext, like 765 = Namco.
- Physical rename 556_production/ → 556 happens DURING the rewrite (renaming now breaks the venv's
  absolute paths + all launchers; the rewrite touches those anyway).
- Candidate flourish for later: Path C memory engine module named `kokoro` — her heart literally
  being the memory engine. Port family 556xx available if the rewrite renumbers services.

## Decided (2026-10-02) — companion lifecycle is a manual, per-companion action
- The app can hold **many companions**; the user picks which ones to **start** (manually) and each
  stays up until the user **stops that one** or closes the app (closing the app stops all).
  Several can be active at the same time; nothing auto-starts.
- **MCP bindings are strictly per character.** Every MCP server / channel binding belongs to
  exactly one companion and is configured on her; a call arriving through her binding goes to
  her and nobody else. No shared pool, no content-based routing across companions. If she is
  not active, that binding has no one behind it (the call fails / is not served).
  Concretely for channels: a Telegram binding is **the character's own Telegram account**
  (her bot token, her identity), never a shared "556 Production" account. 556 is the agency
  that runs her; the account, the contacts and the conversations are hers. One character may
  hold several bindings (Telegram, Discord, an MCP server); one binding never serves two.
- Consequences for the backend: one Hermes process per active companion (its own profile,
  HERMES_HOME, session) under the 556d supervisor, with per-companion ports; the embedder
  sidecar is shared. Each companion owns its own memory store file (`home/memory/<profile>.db`,
  one owner process each, so no writer conflicts); the memory page and the memory API become
  per-companion (`/api/memory?companion=`), replacing today's single `daemon.profile`.
- UI: the office window gets a roster with start/stop per companion and an "active" state.
  **The avatar does not change: it follows the companion the chat window is currently on.**
  With bindings strictly per character there is no fan-out policy to design: a channel's
  messages belong to its character; the hub only has to address the right active process.
- **Stopping is graceful** (2026-10-02 evening, found by the smoke test: a stop 3 s after a reply
  hard-killed her before the ~6 s memory observe landed → turn lost). Stop / app quit / app death
  all write Hermes's planned-stop marker so her gateway drains and kokoro waits for its observe;
  kill only after 60 s; and the stop first waits (≤ 30 s) for the pipeline to observe the newest turn, since
  Hermes queues that observe a few seconds after the reply. A stop therefore takes ~10 s and shows 收尾中.

## Decided (2026-10-02) — one route per character: her gateway is her only Hermes
- The first live Telegram test exposed the two-process shape (`hermes serve` for the app + `hermes
  gateway run` for Telegram): two owners of her memory, 📬 "no home channel" notices, and Telegram
  knowing nothing of what was just said in the app. **Fixed the same day: one `hermes gateway run`
  per active character.** Its API server platform (`API_SERVER_KEY/HOST/PORT`, key kept in her
  `companion.json`) is the app's route; its adapters are the channels'. The app UI and the
  channel/MCP bindings are peers at the same level, all calling her. 556d never runs Hermes for her
  any other way.
- **One conversation per character** (corrected the same night — the first cut kept one session per
  surface and faked continuity through memory; the user rejected both). Her Telegram DM session IS the
  conversation. The app continues it by id (`X-Hermes-Session-Id`); the gateway rebuilds context from
  `state.db` every turn, so Telegram and the app see one history. When the app speaks first, 556d creates
  the session through her API and stamps the Telegram routing identity (`sessions.source` +
  `session_key`) on the row, so her first Telegram message lands in it. History survives restarts
  (SQLite); auto-reset is off; compression summarizes, never deletes. 556d never proxies Telegram.
- **History is not memory.** Last-X-turns is the agent's session store; KeepsakeDB keeps only what the
  pipeline judges worth keeping. The recent-exchange layer was removed (KeepsakeDB 0.1.3).
- **Every surface shows in the app.** 556d follows the conversation (2 s poll of her session store) and
  broadcasts channel turns to the windows with a source badge; app turns are mirrored into Telegram.
- **(c) Telegram mirror**: after an app turn, 556d sends「你問我：q／我說：a」as plain text to her
  home channel through her own bot token — no LLM call, so the Telegram thread catches up with the
  app. Settings toggle (default on); `TELEGRAM_HOME_CHANNEL` is a registry knob.

## Decided (2026-10-03) — voice: two modes in the chat, Fish Audio first
- **Mode 1, press-to-record**: the default text chat gains a 🎙 button; press to record, press again to
  stop; the transcript lands in the composer and the Producer sends it like typed text. No TTS.
- **Mode 2, conversation mode (免手持)**: the mic stays open, Silero VAD runs in the browser, the
  endpointing from the earlier `voice_agent_vad.py` is kept (threshold 0.5, cut after 500 ms, pre-roll
  0.4 s, grace 0.9 s so pauses merge into one turn, min 0.35 s, max 30 s). Strict 1:1 pipeline: one
  transcription, one chat turn, one synthesis, one playback; cuts made while she answers queue FIFO.
  The text box is locked meanwhile. Voice turns carry an ephemeral spoken-style hint (short, no markdown)
  and replies are sanitized before TTS; they are ordinary turns otherwise (same session, memory, mirror).
- **Playback**: the avatar window plays and lip-syncs (it always exists, hidden unless shown); the office
  plays only when no window claims playback. Echo guard pauses the mic while she speaks (default on).
- **Connectors**: `fish-audio` next to `openai-compatible` (TTS `/v1/tts` with `reference_id`, ASR
  `/v1/asr`); keys stay in `home/voice.json`, entered in Settings, never in chat. Hands-free parameters
  live in the same file and in Settings. Telegram turns are not spoken by the app.

## Decided (2026-10-03) — two memory layers, one file; history stays history
- **Short layer** (KeepsakeDB 0.2.0): the same observe call that writes tagged long-term facts may
  also return one dated line — the episode of the turn when it could matter later (what the Producer
  asked for or did, a plan, a mood with its cause). No tags; surface stamped in meta; ring of 1000
  (`short_cap`), oldest dropped. Greetings, small talk and trivia return null. Purpose: a second chance
  when a long fact was missed or mis-written.
- **Read path**: one embedding, then every layer searched at once — the bigger layer (in-memory count)
  starts first on its own read-only connection, the smaller follows on the calling thread, only the
  final join waits. Hybrid (dense + BM25, RRF), top 5 each. Injected as `Facts (long-term)` and
  `Notes (recent, dated)` in one `Memory` block.
- **Priority told to her**: the conversation itself is ground truth; otherwise the newest entry wins
  whatever its layer; a fact beats a note only on a tie. The pipeline supersedes a stale fact afterwards.
- **One file, two layers** (a `layer` column), not two databases: one owner, one backup rotation, one
  memory page (long by default, toggle for the short layer).
- **At most one session, opened by the manual start**: 556d opens her conversation when she is started
  from the roster (create + Telegram routing stamp if none is live); a message never opens one. Hermes's
  slash commands (`/new`, `/reset`, `/model` …) are admin-only on her Telegram with a placeholder admin,
  so the Producer cannot fork the conversation from the phone; everything is set from the app.

## Decided (2026-10-02) — the Producer's name vs the memory subject
- Stored memories never contain the Producer's name as subject. The subject is a **fixed role
  marker per store**: 「製作人」 for zh-TW stores ("the Producer" for en), recorded in the store's
  meta like the tokenizer; other people are stored by their own names / relations. Reason: a name
  can be added after many rounds or changed later; a role marker never splits the corpus, never
  needs a migration or a re-embed. (Changing the marker itself is a deliberate migration:
  one text replace + re-embed.)
- The name lives in the prompt layer: Settings `producer_name` → written through to
  `home/USER.md` (Hermes injects it every turn) → she addresses him by name while the memory
  block says 製作人. The L2 pipeline prompt is told the current name so first-person mentions by
  name (e.g. his English name) still resolve to 製作人 and a different person with that name
  stays separate.
- Search is unaffected either way (a constant subject token has no discriminating power; probes
  are first-person and matched neither word, recall was 20/20).
- Test stores so far say 「使用者」 (harness default); the real store starts with 「製作人」.

## Decided (2026-10-02) — the prompt layer: Producer settings that shape her system prompt
- Two Settings now write into the selected companion's `memories/USER.md` as managed lines that
  Hermes injects every turn: the **Producer's name** (「名字：…」) and **her reply language**
  (「回覆語言：…」; default = follow the Producer; options en / zh-CN / zh-TW / ja). Both take effect
  after restarting her. Memory storage language and the fixed memory subject are separate knobs
  (kokoro.json) and are NOT affected by the reply language.
- These are the first entries of a **prompt layer** (settings-driven text around the hand-written
  SOUL). The user wants to go deeper here later: a generated block (name, reply language, channel
  etiquette, time/locale, relationship stage…) assembled per turn instead of managed lines in a
  file. Design pass to come; for now the managed-lines approach keeps SOUL.md human-owned.

## Decided (2026-10-02) — voice: connectors first, feature later
- STT / TTS are cloud services (GPU stays free); the app gets **connectors** now, the feature later.
  `home/voice.json` (agency-level keys, 0600) holds a TTS and an STT provider; the only kind
  implemented is **OpenAI-compatible** (`/audio/speech`, `/audio/transcriptions`), which covers
  OpenAI, Groq (STT), Fish Audio, Azure OpenAI and local proxies; vendor-specific APIs (ElevenLabs,
  MiniMax, Azure Speech) are later adapters behind the same `Speak` / `Transcribe` calls.
- Settings → 語音連線: configure, save, and **test** (TTS the phrase, then STT the audio — the round
  trip proves both). Per-companion voice choice (her voice id) lives in `companion.json` later.

## Decided (2026-10-02) — Settings principle: nothing is fixed in a config file
- Settings has two tiers. **Non-technical knobs are shown directly** (製作人: name, her reply
  language; 她: name, Live2D, show on start; 記憶: storage language, context turns X; 語音連線).
  **Everything else is behind a "developer options" toggle with a warning**, rendered from
  556d's **config registry** (`/api/config`): every knob declared once with its file, path, type,
  scope (agency / selected companion), and the effect of changing it (restart her / restart the
  app / re-embed / reindex / migrate subject). Groups: her model (config.yaml), her memory engine
  (kokoro.json), her channel bindings (.env, tokens masked), the agency backend (556d.toml, shim
  routing). Writes go into the files in place (YAML keeps comments).
- Consequence in the engine: the two "constants" became changeable — KeepsakeDB now reindexes at
  open when the configured tokenizer differs from the store's, and migrates every memory when the
  subject word changes (rewrite + re-embed, logged in history). The configured value always wins.

## Parked (explicitly deferred by user)
- ~~**Her name** (first companion) — decided AFTER the system; agency-first like the reference.~~
  **2026-10-02: first character = a fresh persona** (not a port of Bith), 556's first talent, framed
  as the agency's **manager** (經紀人／マネージャー) — the one who answers the phone, which is exactly the
  channel-binding job that comes next. The sample Live2D model (Hiyori) stays for now. First job with
  her: channel connections (Telegram, Discord) in **pure text**; voice over channels is future work.
  Name: "Kokoro" was considered and dropped the same day because the memory provider plugin is
  `kokoro` (her heart) and the user wants that name to stay. **Her name: 真音（まね, Mane）** —
  decided 2026-10-02: マネ is what idols call their manager, hidden in a real name meaning "true
  sound"; reads naturally in 繁中 (真音). Her name lands in: `SOUL.md` (fresh draft), settings
  `companion_name`, `home/memory/mane.db`, the account handles (e.g. `@mane_556_bot`).
- **MCP / channel list** — later; QQ excluded.
- **Whether the Wardrobe schema is adopted** — it's one candidate, not presumed.

## Open questions
- Which profile becomes the first companion character here (fresh SOUL vs port of Bith's)?
- TTS voice source/reference audio for GPT-SoVITS (when we get there).
- GPU budget: does local image-gen/TTS coexist with WSL Qwen (→ revisit Artemis VRAM tiering)?

## Decided (2026-09-30, 0.2.0 discussion) — see docs/PLAN-0.2.0.md
- **Frontend stays as-is** for 0.2.0; 0.2.0 = backend rewrite.
- **`vendor/` is untouchable by definition**; if we edit it, it is not vendor. Hermes never edited.
- **Go** for the beside-Hermes layer (daemon `556d`: supervisor, shim, bridge, UI API): single
  static binary, cross-compiles to every OS, best fit for HTTP/WS + process supervision.
  **Python only inside Hermes** (memory provider, platform adapter, skills) — by contract.
- **No Rust, no Tauri.** Tauri is a window shell, not a TypeScript alternative; with Go fixed its
  Rust side is dead weight, and its small-binary benefit is what Wails gives in Go-land.
- **UI = TypeScript, one codebase**, identical under any shell. **Shell = Electron now** (bundled
  Chromium → avatar renders identically on every OS); **Wails later only if** we accept testing the
  avatar on three native webviews (WebView2 / WKWebView / WebKitGTK).
- **Hermes surface for chat = `tui_gateway` JSON-RPC over WS** (what Hermes Desktop uses):
  persistent agent, streaming, `profile` = talent switching. `api_server` optional. Proactive
  pushes need a Python platform-adapter plugin (0.2.x); cron agents run without memory provider.
- **Artemis exit**: reference clone kept until the frontend rewrite empties the ledger, then deleted.

## Decided (2026-09-30, after 0.2.0) — memory language, engine repo, frontend shape
- **Memory language is a per-companion setting** (user-changeable; default zh-TW). "Mirror the
  input language" rejected (mixed stores defeat dedup — the zh/en Japan-trip duplicate).
  **Catch, documented in README + MEMORY-DESIGN**: the embedding model is user-changeable too, and a
  companion in another language (ja/fr/…) must be paired with an embedder that covers it.
- **Standalone memory engine**: own repo, pure Python library consumed by 556 via a thin Hermes
  MemoryProvider in `plugins/`. Name deferred (may take a `DB` suffix; "kokoro" collides with the
  Kokoro TTS model, so it stays 556-internal). Open before writing: whether the memory *pipeline*
  (extract/tag/merge/archive) lives inside the library or in 556 — proposal: layered library
  (storage+retrieval core; pipeline as an optional module) so the DB alone stays lightweight.
  **Decided 2026-10-01: KeepsakeDB** (`D:\dev\KeepsakeDB`), layered B — L1 store (SQLite: FTS5
  BM25 + dense, RRF), L2 pipeline pluggable/unpluggable, L3 integration for any agent; recommended
  all three together. SQLite is a trial, judged by the benchmark against Milvus Lite 3.x.
- **Conversation model**: backend keeps ONE endless conversation per companion; only the last X
  turns are in context (Hermes compression knobs; X user-settable later). Frontend shows the
  current X turns for now — revisit.
- **Hub architecture**: every UI/channel (office window, pet, Telegram, MCP…) connects to the
  backend; the backend fans events out to all connected services. Windows never talk to each
  other directly. Fan-out policy (what goes where) to be designed; end state: ask on Telegram,
  the pet answers on the desktop.
- **Approvals/clarify**: solved by toolset policy, not UI — the companion's toolset excludes
  approval-gated tools and the `clarify` tool. No prompt UI planned.
- **Proactive presence**: no limits/etiquette rules for now.
- **App model**: ONE Windows app, "556 Production" — office window with chat + settings, a button
  to show/hide the avatar (pet window belongs to the same app). Closing the app closes the whole
  backend (the app owns 556d's lifecycle); minimize/hide to the tray (bottom-right).
- Terminology: "companion" (not "talent") in docs and UI.

## Done (2026-10-01, 0.3.0 S5) — Artemis exit
- The Artemis ledger emptied (SPA and viewer replaced by the app) → `vendor/artemis/` deleted.
  What we learned from it lives in `docs/ARCHITECTURE.md`, `STACK.md` pitfalls and this log.
- Retired: `ui/` (web-chat SPA, Electron pet, viewer), `avatar.cmd`, `pet.cmd`, the `/chat/`
  route and the SPA-compat endpoints. Diagnostics moved to `tools/`.
