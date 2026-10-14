# Changelog

## 0.7.6 — 2026-10-14

- **狀態 round.** 熟悉度 shows again (the snapshot now carries the closeness words; the page reads the snapshot). The
  three feedback buttons on feelings are gone. 最近發生 and 每回合的評估 became one 時間線: one line per round (the turn,
  what the appraisal saw, how many feelings it bore) plus everything else that happened, newest first, grouped by
  今天 / 昨天 / date; 設定 → 全域 → 程式 chooses the date format (年/月/日 · ISO · 日/月/年 · 月/日/年) and 24 h / 12 h.
- **掛念 in two groups.** 進行中 (等待, 等待（到了）, 等待（等你回）, 進行中（去問了 / 問到了）) and 已結束 (完成, 沒成, 忘了),
  finished items shown for seven days after the day they finished, then hidden (the database keeps them). A reminder,
  her promise or a report counts as done the moment she says it (a report with nothing found is 沒成); a thing you
  mentioned is done when it comes to something and 沒成 if seven days pass. Saying the same thing again refreshes the
  one loop instead of opening another (the appraisal reports `loops.refresh`; the engine merges near-duplicates).
- 名單 and the header say online / offline / starting… / stopping…. No extra light for the model lane: a character's
  status is hers; a failed turn shows in the chat.
- 設定 → 角色 → 主動 → 記性: on by default for every character, reliability 0.8. The roll as an item comes due:
  P(remember) = 記性 + 0.3 for an important item − 0.3 × how much worse than usual her mood is (small things slip one
  time in five, important ones never; on a really bad day half the small things).
- Docs and graphs brought up to 0.7.5 (settings in two layers, a voice per character, cues and failed turns, the two
  kinds of promise, the mailbox, forgetting).

## 0.7.5 — 2026-10-14

- **Mailbox between characters** (556d `relay.go`): a message for a character who is not running waits in
  `home/mailbox/<id>.json` and is delivered when she starts (or at the next sweep), continuing the conversation where
  it stopped; late delivery is prefixed with the time it was left; 7-day TTL, 20 per pair. `GET /api/relay/log` lists
  `pending` and `outbox`. Asking another character is now "ask once, wait up to `proactive.ask_give_up_h` (48 h)".
- **Forgetting.** `character.forgets` (off by default) lets a character forget a scheduled thing as it comes due:
  base rate `character.forget_rate` or 0.3 × (1 − conscientiousness), lower for important items, higher when tired or
  low, higher the longer it waited; decided with the seeded rng. A due item the platform could not deliver backs off
  (5/15/60 min, then hourly) and after `proactive.undelivered_window_h` (6 h) is 忘了 too. Forgotten items leave her
  state block, stay visible to the appraisal (she owns it when you bring it up) and show as 忘了 on 狀態.
- 設定 → 全域 → 你: your name and reply language are written into every character's profile on save (people/你.md,
  kokoro.json), not only the one on stage; each character applies them at its next start. Memory language and
  embedder stay the selected character's own.
- The developer-knob labels (556d's config registry) no longer say 她; the unnamed line in a person file reads
  「稱呼對方「哥」」 instead of 「她叫你」, which was wrong for a character whose pronoun is 他.
- 狀態 names the other characters by their display name (要問誰, 關係, 委屈帳) even before any conversation with them exists (the roster's names, not profile ids).

## 0.7.4 — 2026-10-14

- **A failed turn leaves nothing behind.** When the model lane is down (or the agent errors), Hermes stores your
  message and no answer, and the platform's error text came back as her bubble, was spoken to the avatar, and the
  dangling user row re-entered her context on the next successful turn. Now 556d detects the failure
  (`finish_reason: error`, `hermes.error`, or a platform-error text), deactivates that user row (`active = 0`, the
  same flag Hermes uses to rewind), turns your undelivered message and the error into gray system notes (hidden
  unless 設定 → 全域 → 程式 shows system notes, like the narrator cues), and neither mirrors nor speaks it. A cue the platform could not answer is dropped the same way (the engine calls
  `POST /api/history/discard`), and when her conversation opens at start, unanswered rows older than 15 minutes
  (a Telegram turn during the outage, an old cue) are swept.
- **Two kinds of promise** (`docs/inner-life/inner-life.md` §13, §16). A loop opens only when she agreed in her
  reply (the appraisal reports `agreed`; declining is her SOUL's business). A promise that concerns only her and you
  is forced through at its time, as before. A promise that needs another character (「幫你問子睿」: the appraisal fills
  `ask`) is carried to that character at her free time (`ask_other`, through the relay), the answer is taken from that
  conversation's appraisal (loop state `asking` → `answered`), and the result comes back to you (`report_back`) only
  when she is up, outside your no-disturb hours and when your presence model says you are around; no answer → retry at
  the next free slot, give up after `proactive.ask_retry_max`. 狀態 shows each step (要問誰, 第幾次, 答案); her state
  block says 已去問… / 問到了…. Knobs: `promise_requires_agreement`, `ask_retry_max`, `ask_timeout_h`,
  `report_only_when_awake`. Four new engine tests.
- **Narrator cues are never your words.** The hidden turn behind a proactive message (the 【事件】 cue the
  psyche engine posts) used to surface as one of your bubbles whenever the chat reloaded its history (and stayed
  there when the model failed to answer). 556d now tags such rows (`source: cue`; her answer `event`; silence or a
  platform error in that place `cue`) in history and in the live follower alike; the app hides them by default
  and 設定 → 全域 → 程式 has a switch to show them, styled as a dim centered 旁白 note. The follower also attaches
  correctly when a cue landed before it did (her answer was filed as an app turn and hidden).
- The engine records `send_failed` when the platform answers a cue with an error instead of her words (every
  model backend down): Hermes stores the cue but calls no hook, so nothing was recorded and 狀態 stayed at 想開口.
- **設定 has two tabs**: 全域 (you, the app, the global voice connectors, the backend knobs) and 角色, a list of
  the characters; a character's page opens from that list, not from 名單 any more (名單 is only start / stop /
  switch).
- **A voice per character.** Each character's page has a 聲音 section: TTS and STT blocks that say 「跟全域一樣」
  by default, or override the global connector for that character (only the differing fields are needed, e.g.
  another Fish Audio reference_id). Stored in `home/profiles/<id>/voice.json`; 556d speaks and transcribes with the
  effective config of the character on stage (`/api/voice/speak`, `/api/voice/transcribe`) or of `?companion=`.
  Hands-free parameters stay global (they are about your microphone).

## 0.7.3 — 2026-10-14

- **The app speaks generally**: no pronoun for the character (她), no role word for you (製作人), no agency
  framing (事務所, 上班, 成員) anywhere in the windows; the character's name shows where a name belongs.
- **Settings in two layers.** 設定 holds what is yours and the app's: your name and reply language, the
  character window on start, the Telegram mirror, the voice connectors, and the backend developer knobs.
  Everything that belongs to one character moved to that character's page under 名單 (click the name or 設定
  on its row): name and Live2D model, memory language and context window, abilities, 主動, the channel
  accounts (Telegram / Discord, no longer hidden behind the developer toggle), and the model / memory-engine
  knobs behind the toggle. Opening a character's page puts it in the chat window, because 556d edits the
  character on stage. No backend change.

## 0.7.2 — 2026-10-14

- Fix: opening 狀態 for a character who had never talked to another character blanked the whole window (it
  looked like a hang). `GET /api/relay/log` answered `conversations: null` (a Go nil slice), the page read its
  length, and React unmounts everything on an uncaught render error. 556d now always returns lists, the pages
  guard the arrays they index (relay log, history, memory tags), and a page that throws shows the error in place
  with a retry button; the header and the other tabs keep working.

## 0.7.1 — 2026-10-13

- **Your cast lives outside version control**: `characters/<id>/` (SOUL, psyche.json, person files, seed memories,
  kokoro keys) is ignored; only `characters/README.md` (the layout) is versioned. The characters designed in this
  cycle are the user's own: a main conversation partner and a couple close to you, with no agency framing and no
  role word (製作人) in their files; kokoro's injected profile header no longer calls you the producer who runs the
  agency. Each character's `kokoro.json` sets how she addresses you until Settings → 你 has
  your name; `install-character.ps1` merges those keys; the person file's unnamed line follows the term.
- Fix: the shim's gemini-flash backend pointed at `agyapi/gemini-3.7-flash`, which Google retired (the proxy returned
  404 as an instant empty reply); now `agyapi/gemini-3.8-flash`. The shim logs the backend's body on an empty reply.
- Fix: in a conversation between characters the listener mistook the speaker for the producer. The relayed message now
  carries the speaker's name, the state block's first line says who she is talking to, kokoro's per-turn note says the
  same, and the SOUL template calls the producer a role instead of "whoever is talking to you".
- Fix: the app's own messages showed the client name ("office") as a badge; badges now mark only channels and her
  event turns.
- Live scripts under `tests/live/` refuse to start while the app or a daemon is running (the daemon owns :55600 and
  the app attaches to whatever listens there). Test artifacts under `tests/` are ignored.

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
- **Three characters with full backgrounds** under `characters/` (placeholders, later replaced by the user's own
  cast): one just met, two old acquaintances who are a couple. Each has a SOUL with background, a
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
