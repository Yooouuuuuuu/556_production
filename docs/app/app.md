# The app — 556 Production (Electron + React)

Living doc; last verified 2026-10-14 (0.7.5). The shape decided on 2026-09-30 (notes below) still holds.
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
- **0.8.1** (2026-10-16): 設定 → 角色 → **新角色** — the soul skill behind 556d (`../prompt/prompt.md` §2.9). One page per
  character package: 描述 (ten boxes in your own words, the template prompts as grey text), 產生 (model gemini / claude,
  「全部」 or one phase at a time, the job's log live, the intake's questions), 確認 (the proposed thinking meters and
  choices with the skill's one-line evidence, Big Five and constants under a fold; sliders are your decision), 結果
  (the checks, the blind read-back, the SOUL, 安裝 → profile created, files copied, seeds loaded → start her on 名單).
  Packages with a hand-written SOUL (the cast) are marked and never overwritten. Backend: `/api/characters` and the
  skill as a 556d job (`internal/api/characters.go`). 0.8.0 was the skill itself (`tools/soul_writer.py`, no UI).
- **0.8.6** (2026-10-19): the avatar window is hidden by default (設定 → 全域 → 啟動時顯示角色 off); the avatar is parked
  until the core is done. 能力: the baseline is no tool at all — memory is injected every turn, not called; 查網路
  and later extensions still switch on per character.
- **0.7.9** (2026-10-15): no UI change. `docs/prompt/` — the request she answers, verified, and the 0.8.0 design
  (six-part SOUL, thinking dials, pinned groups, clock line, vendor-text filter).
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
