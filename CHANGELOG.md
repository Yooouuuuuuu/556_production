# Changelog

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
