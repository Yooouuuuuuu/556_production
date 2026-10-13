# STACK — what exactly this project is using

Last verified: 2026-10-01 (0.3.0). Ground-truth inventory; update it when reality changes.
Reasoning behind each choice: `DECISIONS.md`, `MEMORY-DESIGN.md`, `FRONTEND-DESIGN.md`,
`PLAN-0.2.0.md`, `PLAN-0.3.0.md`.

## One app

**556 Production** (`app/`, Electron + React) is the product. Launching it starts and owns the
whole backend; closing it shuts everything down.

```
556 Production (Electron)          office window: chat + settings · avatar window (toggle) · tray
  └─ spawns 556d.exe -parent-pid   (Go)  :55600  hub: chat API + events on /ws + avatar bridge + static
        ├─ shim               :55601  OpenAI-compatible model router (lanes → Gemini proxy)
        ├─ hermes serve       :55610  the brain (Python, vendored) — SOUL + memory + tools
        └─ llama-server       :55602  bge-m3 embedder on CPU (memory Path A)
External, untouched: Gemini proxy :18765 (user's), production shim :18766 (user's D:\Hermes).
```

Ownership chain: the app kills 556d on quit; 556d watches the app's pid and exits if the app
dies; 556d's Windows job object (kill-on-close) reaps hermes/llama. Verified for graceful quit
and force-kill. 556d attaches instead of spawning if one already serves :55600.

## Layout

| Path | What | Ours? |
|---|---|---|
| `app/` | the app: `electron/` (main, preload, backend lifecycle), `src/` (React: Office/Chat/Settings/Avatar, `live2d/Live2DStage`, `store` = hub WebSocket state, `api`, `i18n` zh-TW default), `assets/` icons, `scripts/` (dev runner, `cdp_capture.mjs`) | ours |
| `556d/` | Go daemon: `internal/{config,supervisor,shim,bridge,hermes,api}`; config `556d.toml` | ours |
| `vendor/hermes-agent/` | Hermes Agent v0.21.0, upstream `7166071f`; venv `.venv` (py3.11/uv). Ignored; `setup-vendor.ps1` restores it | **never edited** |
| `vendor/live2d/` | Cubism Core **4** (`live2dcubismcore.min.js`) | never edited |
| `assets/live2d/hiyori/` | official free Hiyori model (Cubism-4-era assets, SDK tag 4-r.7) | third-party data |
| `plugins/` | Python that plugs INTO Hermes (kokoro memory provider, platform adapter — planned) | ours |
| `home/` | HERMES_HOME: `config.yaml` (model → shim :55601 lane `auto/556`, `memory.provider: mem0`), `mem0.json`, `settings.json` (app settings), `mem0_qdrant/`, `audio_cache/`, sessions | runtime (ignored) |
| `shim/routing.json` | lanes → backends (hot-reload): `556`→gemini-flash, `pro`→gemini, `code`→claude | ours |
| `tools/` | diagnostics: `cdp_shot.mjs` (real-Chrome screenshot), `ws_probe.mjs`, `hub_probe.mjs` | ours |
| `models/`, `bin/` | bge-m3 Q8_0 GGUF; llama.cpp CPU build (ignored, downloaded) | downloaded |
| `tests/memory_stress.py` | 1000-round zh-TW memory benchmark harness | ours |
| `556.cmd` | Hermes CLI/TUI on this home (needs 556d running for the model shim) | ours |

## Build & run
- Daemon: `go -C 556d build -o ..\556d.exe .\cmd\556d` (binary ignored).
- App: `cd app && npm install --ignore-scripts && npm run build && npm start`
  (`npm run dev` = vite + electron with live reload). Electron's postinstall download hangs on
  this network: if `node_modules/electron/dist` is missing, run its `install.js` manually or
  copy a matching `dist` (44.4.5).
- Everything else is spawned by 556d from `556d.toml`.

## Wire protocols
- **App ↔ 556d (hub)**: HTTP `POST /api/chat` (header `X-556-Client`) to send; WebSocket `/ws`
  for everything that happens — `chat.user/delta/complete/error`, `companion.state`, avatar
  `message/motion/expression/speak_audio`. `GET /api/history?limit=X`, `GET/PUT /api/settings`,
  `GET /api/companion`, `GET /api/models`, `POST /api/restart-hermes`, static (`/` = the app
  bundle, `/hiyori/...` models, `/live2dcubismcore.min.js`). OpenAI-compatible
  `/v1/chat/completions` (streaming) for third-party clients.
- **556d ↔ hermes serve**: JSON-RPC over WebSocket (`/api/ws?token=`), `session.create` /
  `prompt.submit`, `message.delta` stream; history via REST `/api/sessions/{id}/messages`.
  One persistent session per companion; client system prompts ignored (SOUL owns persona);
  turns serialized. Approvals/clarify not surfaced — companion toolset policy avoids them.
- **hermes → models**: through the shim (:55601): `<tool_call>` text translation for the Gemini
  proxy, lane fallback chains, 4-attempt retry for emulated backends.

## Memory (Path A live — see MEMORY-DESIGN.md)
Curated `MEMORY.md`/`USER.md` head + FTS5 sessions + **mem0 + embedded Qdrant** (per-profile,
user_id `556-user`), extraction on `agyapi/gemini-3.8-flash`, embeddings from the bge-m3 sidecar.
1000-round test: 19–20/20 recall. Settings: memory language (stored; effective with the kokoro
engine — mem0 has no prompt hook), embedder (re-embed on change). Path C / C2 are the designed
successors.

## Avatar
`Live2DStage` (pixi 7 + pixi-live2d-display-lipsyncpatch `cubism4` ESM; Core 4 fetched from
556d at runtime), fitted bottom-center, idle/tap motions, bubbles + motions from the hub. The
avatar window is transparent/frameless/always-on-top, drag-anywhere (IPC), hides on close.

### Live2D pitfalls (learned the hard way)
1. Cubism Core must be **v4** (SDK 4-r.7); the official URL serves Core 5 → black clipping.
2. Model assets must be **Cubism-4-era** (SDK tag `4-r.7`): the `develop` (SDK5) assets have PNGs
   Chrome's GPU upload rejects and masks that never render. Exact bytes matter → versioned.
3. Headless Chrome on this machine renders no WebGL textures; verify with `tools/cdp_shot.mjs`
   (real Chrome) or `app/scripts/cdp_capture.mjs` (the live app, `--remote-debugging-port=9223`).

## Retired
0.2.0: Python shim, adapter, static server, Node bridge, `embedder.cmd`, ports 18767/19200/
19201/19260/19270/18768. 0.3.0: Artemis web-chat SPA, old Electron pet, viewer page,
`avatar.cmd`/`pet.cmd`, `/chat/`, `vendor/artemis/`.
