# The app — 556 Production (Electron + React)

Living doc; last verified 2026-10-19 (0.10.0). The shape decided on 2026-09-30 (notes below) still holds.
What landed since:

- **0.3.0** (2026-10-01): one app owns 556d's lifecycle; office window with 聊天, 名單, 記憶, 設定 (two tiers
  over the config registry); avatar window (Live2D, official sample) toggled from the office window and
  following it; tray icon; the Artemis SPA and pet retired.
- **0.4.0** (2026-10-06): the one conversation per character shown with source badges (Telegram turns
  arrive through the follower); 記憶 shows the long layer with a 近期紀錄 toggle; 名單 shows 收尾中 during a
  graceful stop; 設定 gains the voice connectors, tool extensions (restart applies), your name and reply language;
  two voice modes in the chat window (`../voice/voice.md`).
- **0.5.0** (2026-10-07): 狀態 tab — energy and mood words, feelings right now with their causes, things on her mind,
  recent events and the appraisal per turn, read-only from `psyche.db` (`GET /api/psyche`); Settings → 你 now writes
  `people/你.md`.
- **0.6.0** (2026-10-08): Settings → 主動 (gates, speak override, busyness, what she cares about, personality
  sliders); 狀態 gains what she is doing, her needs, the separation phase, loop close / add-reminder / add-life-event
  commands, the state block she saw, a fuller timeline; chat shows her event-turn messages with a 她主動 badge and
  speaks them per the override.
- **0.7.0** (2026-10-13): 狀態 adds the relationship table, the hurt ledger, feedback buttons on feelings, and the
  characters' conversations (when 主動 → visibility allows); 設定 → 主動 adds inter-agent on/off, turn cap, visibility.
  The roster already holds several characters; each has her own one conversation with you.
- **0.7.3** (2026-10-14): wording made general — every pronoun, role word and workplace term left the windows; the
  character is 「角色」 and the name shows where a name belongs. A page that throws shows its error in place with a retry
  (React would otherwise unmount the whole window; 0.7.2's 狀態 blank was that).
- **0.7.4** (2026-10-14): 設定 in two layers — 全域 (you: name, reply language; 程式: character window on start,
  Telegram mirror, system notes; 語音連線 with the hands-free parameters; backend knobs) and 角色 (the list; a
  character's page: 基本, 記憶, 能力, 主動, 聲音, 頻道, config knobs — opening it puts the character in the chat window,
  since 556d edits the one on stage); 名單 is start / stop / switch only. A voice per character (TTS / STT override
  over the global connectors, `../voice/voice.md`). Narrator cues (the hidden turn behind a proactive message) are
  tagged by 556d and shown only as gray system notes when 程式 says so; a failed turn (model lane down) is a note too,
  never a bubble, and its dangling user row is dropped. 狀態 shows the promise flow (要問誰, 第幾次, 答案).
- **0.7.5** (2026-10-14): your name and reply language reach every character on save; the developer-knob labels
  without 她; 狀態 names other characters by their display name; loop states 忘了 / 重試中; online / offline wording;
  設定 → 角色 → 主動 → 記性 (the forgetting toggle). Backend: the mailbox between characters, forgetting, undelivered
  due items backing off (`../inner-life/inner-life.md`).
- **0.7.6** (2026-10-14): 狀態 — 熟悉度 back, feedback buttons gone, one 時間線 by day (date format and clock in
  設定 → 全域 → 程式), 掛念 in 進行中 / 已結束 with five words and a seven-day fade; online / offline / starting… /
  stopping… wording, no extra light for the model lane; 記性 on the character's 主動 page.
- **0.7.7** (2026-10-14): 時間線 shows the hurt ledger's life (記了一筆 / 又提起了 / 和解了 / 放下了); 記憶 does not list
  held rows (a turn whose hurt is on the ledger). Backend: the ledger ↔ memory rules (`../inner-life/inner-life.md` §9).
- **0.7.8** (2026-10-15): no UI change. Fix (data): a conversation with another character rewrote that character's
  memory store (counterpart pipelines no longer pass a subject word; KeepsakeDB 1.0.1). `vendor/` is two git
  submodules (Hermes at its pinned commit, KeepsakeDB at `v1.0.1`); the repo is plain git.
- **0.7.9** (2026-10-15): no UI change. `docs/prompt/` — the request she answers, verified, and the 0.8.0 design
  (six-part SOUL, thinking dials, clock line, vendor-text filter; the pinned groups proposed there were built in 0.8.7 and
  retired in 0.10.0).
- **0.8.1** (2026-10-16): 設定 → 角色 → **新角色** — the soul skill behind 556d (`../prompt/prompt.md` §2.9). One page per
  character package: 描述 (ten boxes in your own words, the template prompts as grey text), 產生 (the model — the choice
  offered then was gemini or claude on the proxy; since 0.9.0 the page shows the configured 寫靈魂 model instead — 「全部」
  or one phase at a time, the job's log live, the intake's questions), 確認 (the proposed thinking meters and choices
  with the skill's one-line evidence, Big Five and constants under a fold; sliders are your decision), 結果 (the checks,
  the blind read-back, the SOUL, 安裝 → profile created, files copied, seeds loaded → start her on 名單). Packages with a
  hand-written SOUL (the cast) are marked 手寫 and never overwritten. Backend: `/api/characters` and the skill as a 556d
  job (`internal/api/characters.go`, its output in `build/run.log`, hub event `character.job`). 0.8.0 was the skill
  itself (`tools/soul_writer.py`, no UI).
- **0.8.2** (2026-10-16): found by the first character made on the page. The list and the detail carry a stale marker
  (the description or the confirmed numbers changed after the files were generated — the hash differs from
  `soul.lock.json`), the 結果 section warns and names what changed, and 安裝 asks before installing stale files. 「全部」
  runs the intake alone first and stops on a thin description with its questions on the page; 「仍然繼續」 runs from
  step 2 to the end (`--from <phase>` in the skill).
- **0.8.3** (2026-10-16): the page defaulted to gemini — superseded in 0.9.0: the model comes from the connections and
  nothing has a default. Backend: the assembler's list and digit fixes.
- **0.8.4–0.8.5** (2026-10-16): no UI change. Prompt hygiene — the guidance switches written into her `config.yaml`
  before every start, the shim dropping Hermes's vendor paragraphs — and the clock line in the state block
  (`../prompt/prompt.md` §2.7–2.8).
- **0.8.6** (2026-10-19): the avatar window is hidden by default (設定 → 全域 → 程式 → 啟動時顯示角色視窗 off); the avatar
  is parked until the core is done. 能力: the baseline is no tool at all — memory is injected every turn, not called;
  查網路 and later extensions still switch on per character.
- **0.8.8** (2026-10-19): 設定 → 角色 → 主動 gains a **怎麼想** fold with the five thinking sliders and **想不開的程度**;
  restart applies. Backend: the thinking module (`plugins/psyche/thinking.py`) and its one optional 想法 line in the
  state block.
- **0.8.9** (2026-10-19): 狀態 lists **沒說出口** (what she visibly held back, until it is said or fades); the new-character
  page's 確認 gains **跟你有多熟（一開始）** (剛認識 … 很親近; `profile.json` `closeness` → her starting bond with you).
  Backend: the five conversation mechanisms (`../inner-life/inner-life.md` §24).
- **0.8.10** (2026-10-19): 產生 gains the **簡單版** fold (three boxes plus the sliders and choices become the files with
  template sentences, no model; `POST /api/characters/<id>/simple`); 確認 gains **回覆前先想** (the hidden scratch,
  `profile.json` `scratch`; the shim strips it from every reply). Backend: keyword triggers in kokoro, the fidelity probe.
- **0.9.0** (2026-10-19): 設定 → 全域 → **模型連線** — master endpoint with 檢查 (lists the endpoint's models), 對話／記憶／寫靈魂
  follow it or carry their own, the vectors (local llama-server or an embeddings endpoint), the timezone; what is missing is
  listed and a character does not start until it is complete; the new-character page shows the configured model.
- **0.10.1** (2026-10-20): no UI change beyond the new-character page losing the 從範例開始 option (the example package is
  gone; default characters are future work).
- **0.10.0** (2026-10-19): no UI change beyond wording — the 能力 page says there are no tools at baseline, the
  new-character page shows the configured 寫靈魂 model; docs brought current. Backend: the package is the character —
  556d copies SOUL.md, psyche.json and people/*.md from `characters/<id>/` before every start and the 主動 sliders write
  the package's psyche.json too; the SOUL carries 時間線 and 影響過你的人與事, the pinned groups are retired.
- **Coming**: see
  `../inner-life/inner-life.md`.
- **Parked**: packaging (installer, updater, auto-start), pixel-alpha click-through for the avatar,
  emotion → avatar mapping, poke reactions, UI polish.

The hub rule holds: every window talks only to 556d over HTTP + WebSocket, and 556d fans events out
(chat deltas and completions, companion state, speak_audio). Windows never talk to each other.

## Shape decided 2026-09-30 (pre-plan notes, kept as written)

Decided shape — the rewrite plan is written against these:

- **One app: "556 Production"** (TypeScript, Electron shell). Office window = chat + settings, like
  any Windows app. A button shows/hides the **avatar** (the pet window is part of the same app).
  Closing the app shuts the whole backend down (the app owns `556d`'s lifecycle); minimize/hide to
  the tray (bottom-right).
- **Hub, not peers**: every window/channel connects to 556d; 556d broadcasts events to all
  connected services (pet, office window, later Telegram/MCP). No window-to-window links.
  → 556d must publish chat events (deltas, completions, companion state) on its WebSocket, not only
  to the HTTP requester. Fan-out policy (which events to which client) is the next design item.
- **Conversation**: one endless conversation per companion on the backend; context = last X turns
  (Hermes compression, X configurable later). UI shows the current X turns for now (revisit).
- **Approvals/clarify**: not surfaced — handled by the companion's toolset policy.
- **Proactive presence**: no limits for now; needs the push adapter + hub broadcast.
- **Companion = profile** (SOUL + avatar model + voice later + memory store); switcher UI later.

Still undesigned: emotion → avatar mapping (model tool vs classifier), 中文 IME behavior (Enter must
confirm composition, not send), settings scope/storage, visual identity, offline/error states,
UI test harness. Terminology: "companion", not "talent".
