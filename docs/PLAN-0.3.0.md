# 0.3.0 — Frontend: the "556 Production" app (plan of record, 2026-09-30)

0.2.0 made every UI reach the real her through one daemon. 0.3.0 replaces the transitional
Artemis web chat + separate Electron pet with ONE Windows app — chat, settings, and the avatar —
built on the decided shape in `FRONTEND-DESIGN.md`. Backend stays 556d; it grows a hub.

## Decided (inputs)
One app "556 Production": office window (chat + settings) + avatar window toggled by a button/tray
· closing the app closes the whole backend (the app owns `556d`) · minimize → tray · hub: every
client talks only to 556d, which broadcasts to all · endless conversation, last X turns shown ·
no approval/clarify UI (toolset policy) · no proactive limits · terminology "companion" ·
TypeScript under Electron, no Rust/Tauri.

## Stack (settled here)
- **Renderer**: Vite + React + TypeScript + Tailwind (the mainstream stack Hermes Desktop also
  uses — we borrow its *shell pattern*, not its UI, which is far heavier than we need).
  Small state store (zustand). i18n table from day one, **zh-TW default**, en available.
- **Live2D**: `pixi.js` + `pixi-live2d-display-lipsyncpatch` as npm deps in a React component —
  a port of today's `ui/live2d/index.html` (model load, bubble overlay, tap motions, WS events).
  Cubism Core 4 from `vendor/live2d`, models from `assets/live2d`, both served by 556d.
- **Electron main**: spawns `556d.exe` as a child, waits for `:55600` health, single-instance lock,
  Tray (show office / show-hide avatar / quit), two BrowserWindows sharing one renderer bundle
  (`#/office`, `#/avatar`). Quit = kill 556d (its job object takes the rest). Window close → quit;
  minimize → tray.
- Location: new top-level `app/` (`app/electron`, `app/src`). `ui/` is retired at S5.

## 556d hub additions (backend side of this plan)
- **Event stream** on `/ws` for every client (pet, office, later Telegram/MCP bridges):
  `chat.user {text, source}` · `chat.delta {text}` · `chat.complete {text, status, usage}` ·
  `chat.error {message}` · `companion.state {talking}` · existing avatar events unchanged.
  Sends stay HTTP (`POST /api/chat`, header `X-556-Client: office|pet|…`); turns are serialized per
  companion (queue), so several clients can talk at once without racing.
- `GET /api/history?limit=X` — last X turns from `hermes serve`
  (`GET /api/sessions/{sid}/messages`, session token), normalized `{role, text, ts}`.
- `GET/PUT /api/settings` — `memory_language`, `model_lane`, `context_turns` (X), `avatar_model`,
  `show_avatar_on_start`, `embedder_model` (advanced; warns about re-embedding). Writes
  `556d.toml` / `home/config.yaml` / `home/mem0.json`; returns `restart_required`;
  `POST /api/restart-hermes` applies via the supervisor.
- `GET /api/companion` — `{name, profile, avatar_model_url}` (single companion in 0.3.0).
- Fan-out policy v1: everything to everyone (loopback, one user). Refined when Telegram lands.

## Work breakdown (each slice verifiable)
- **S0 556d hub** — WS chat events broadcast, `/api/history`, `/api/settings`, `/api/companion`.
  *Verify: `ws_probe` sees `chat.*` events for a chat sent via curl; history returns last X turns.*
- **S1 app skeleton** — Electron main (spawn/health/kill 556d, single instance, tray, two windows),
  Vite+React renderer with routing, dev script (`npm run dev` starts both).
  *Verify: launching the app starts the backend; quitting leaves zero 556d/hermes/llama processes.*
- **S2 chat window** — history (last X turns), composer with **IME-safe Enter** (ignore when
  `isComposing` / keyCode 229), streaming render from WS, offline/error banner (proxy or hermes down).
  *Verify: 中文 typing never sends mid-composition; memory recall through the app.*
- **S3 avatar window** — Live2D React component, bubble, drag-anywhere (IPC), transparent
  always-on-top, toggle from office button + tray, remembers position.
  *Verify: real-Chrome-equivalent render check (Electron), bubble from a chat sent in the office.*
- **S4 settings** — form bound to `/api/settings`; language/lane/X/avatar/show-on-start; restart
  prompt when required. *Verify: switch memory language → next extraction stored in that language.*
- **S5 retire** — delete `ui/web-chat`, `ui/pet`, `ui/live2d` viewer (diagnostics move to `tools/`),
  `/chat/` route, `avatar.cmd`/`pet.cmd`; **delete `vendor/artemis`** (the Artemis ledger is empty).
  *Verify: only `app/` + 556d serve the UI; `vendor/` = hermes-agent + live2d only.*
- **S6 identity + docs** — minimal visual identity (name mark, dark theme, 繁中 typography),
  STACK/ARCHITECTURE/DECISIONS updates, CHANGELOG 0.3.0, README run instructions → the app.

## Non-goals for 0.3.0
Installer/packaging (0.4.0, with the Bongo Cat items: auto-start, updater, input-reactive
animation) · companion switcher UI (0.3.x; the `/api/companion` shape is ready for it) · voice ·
Telegram/MCP fan-out end state · Path C.

## Risks & mitigations
- Live2D in Electron transparency — already proven by today's pet; keep the same window flags.
- IME handling — explicit test list (注音/拼音 composition + Enter) before S2 is called done.
- `hermes serve` history REST is an internal API — pinned to the vendored commit; isolated in 556d.
- Backend ownership: if the app crashes, 556d's job object still reaps hermes/llama; the app also
  kills 556d on quit → no orphans either way.
- Multiple senders: per-companion turn queue in 556d; the UI shows "she's answering …" state.

## Settle at S0 start
zustand vs plain context · window position persistence store (electron-store) · whether the
avatar window is hidden or destroyed when toggled off (hidden: keeps the model loaded).

## Status
S0 hub ✅ (2026-09-30) · S1 app skeleton ✅ · S2 chat window ✅ · S3 avatar window ✅ · S4 settings ✅ · S5 retire ✅ · S6 identity + docs ✅ — 0.3.0 DONE 2026-10-01 (IME manual check pending) — WS chat events, history, settings write-through, companion, restart verified.
