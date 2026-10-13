# The app — 556 Production (Electron + React)

Living doc; last verified 2026-10-06 (0.4.0). The shape decided on 2026-09-30 (notes below) still holds.
What landed since:

- **0.3.0** (2026-10-01): one app owns 556d's lifecycle; office window with 聊天, 名單, 記憶, 設定 (two tiers
  over the config registry); avatar window (Live2D, official sample) toggled from the office window and
  following it; tray icon; the Artemis SPA and pet retired.
- **0.4.0** (2026-10-06): the one conversation per character shown with source badges (Telegram turns
  arrive through the follower); 記憶 shows the long layer with a 近期紀錄 toggle; 名單 shows 收尾中 during a
  graceful stop; 設定 → 語音連線, 她會的事 (tool extensions, restart applies), 你 (your name, reply language);
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
- **Unreleased** (2026-10-14): wording made general (no 她 / 製作人 / agency words in the windows); settings in two
  layers — 設定 is yours and the app's (name, reply language, character window on start, Telegram mirror, voice
  connectors, backend knobs), while a character's own settings (name, model, memory, abilities, 主動, channel
  accounts, config knobs) open from its row on 名單 and put it in the chat window first.
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
