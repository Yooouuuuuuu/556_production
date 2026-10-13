# Frontend design notes (pre-plan, 2026-09-30)

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
