# STACK — what exactly this project is using

Last verified: 2026-09-30 (0.2.0). Ground-truth inventory; update it when reality changes.
History of how each piece was chosen: `DECISIONS.md`, `MEMORY-DESIGN.md`, `PLAN-0.2.0.md`.

## One command

`556d.exe` (from the repo root) is the whole backend. It starts and supervises everything else.

```
556d.exe (Go)  :55600  UI API + avatar bridge + static (viewer at /, web chat at /chat/)
  ├─ shim      :55601  OpenAI-compatible model router (lanes → Gemini proxy), tool-call translation
  ├─ spawns hermes serve  :55610  the brain (Python, vendored) — SOUL + memory + tools
  └─ spawns llama-server  :55602  bge-m3 embedder on CPU (memory Path A)
External, untouched: Gemini proxy :18765 (user's), production shim :18766 (user's D:\Hermes).
```

Children live in a Windows job object (kill-on-close) and restart with backoff; readiness is
health-probed. Config: `556d.toml` (paths relative to repo root). Build:
`go -C 556d build -o ..\556d.exe .\cmd\556d`. Binary is gitignored.

## Layout

| Path | What | Ours? |
|---|---|---|
| `vendor/hermes-agent/` | Hermes Agent v0.21.0, upstream `7166071f`; venv `.venv` (py3.11/uv). Ignored; `setup-vendor.ps1` restores it | **never edited** |
| `vendor/artemis/` | momori777/Artemis study reference (ignored) — deleted after the frontend rewrite | never edited |
| `vendor/live2d/` | Cubism Core **4** (`live2dcubismcore.min.js`) | never edited |
| `556d/` | the Go daemon (`cmd/556d`, `internal/{config,supervisor,shim,bridge,hermes,api}`) | ours |
| `plugins/` | Python that plugs INTO Hermes (kokoro memory provider, platform adapter — planned) | ours |
| `assets/live2d/hiyori/` | official free Hiyori model (Cubism-4-era assets from SDK tag 4-r.7) | third-party data |
| `ui/web-chat/` | Artemis SPA (transitional, served at `/chat/`; repointed to :55600) | borrowed → replaced by the TS frontend |
| `ui/live2d/` | viewer `index.html` (+ bubble renderer, `/ws` connect), `plid-v5-bundle.js`, npm deps for pixi; diagnostics `cdp_shot.mjs`, `ws_probe.mjs`, `test_hiyori.html` | borrowed/ours |
| `ui/pet/` | Electron desktop pet (transparent, always-on-top, drag-anywhere) → loads `/index.html?embed=1` from :55600 | ours |
| `home/` | HERMES_HOME: `config.yaml` (model → shim :55601 lane `auto/556`, `memory.provider: mem0`), `mem0.json`, `mem0_qdrant/`, `audio_cache/`, sessions | runtime (ignored) |
| `shim/routing.json` | lanes → backends (hot-reload): `556`→gemini-flash, `pro`→gemini, `code`→claude | ours |
| `models/`, `bin/` | bge-m3 Q8_0 GGUF; llama.cpp CPU build | downloaded (ignored) |
| `tests/memory_stress.py` | 1000-round zh-TW memory benchmark harness | ours |

Launchers: `556.cmd` (Hermes CLI/TUI on this home — needs 556d running for the model shim),
`avatar.cmd` (app-mode window), `pet.cmd` (desktop pet).

## The chat path (0.2.0)

UI → `556d /v1/chat/completions` or `/api/chat` → JSON-RPC over WebSocket to `hermes serve`
(`session.create` / `prompt.submit`, `message.delta` stream) → Hermes agent with SOUL, memory
provider, tools → model calls through the shim (:55601) → Gemini proxy. Completed replies are
mirrored to every avatar viewer as a bubble. One persistent Hermes session per daemon lifetime;
client-sent system prompts are ignored (SOUL owns persona). Not yet: approval/clarify prompts in the
UI, proactive pushes (needs a Python platform-adapter plugin), talent switching UI.

## Memory (Path A live — see MEMORY-DESIGN.md)

Curated `MEMORY.md`/`USER.md` head + FTS5 sessions + **mem0 + embedded Qdrant** (per-profile,
user_id `556-user`), extraction on `agyapi/gemini-3.8-flash` direct to the proxy, embeddings from
the bge-m3 sidecar (:55602). 1000-round test: 19–20/20 recall. Path C (own hybrid engine) and C2
(tags/archive) are the designed successors. Memory storage language: decision still open.

## Avatar

Live2D viewer served by 556d; WebSocket at `/ws` (same origin; legacy `:19201` fallback in the
page). Control API is Artemis-compatible: `/api/message|motion|expression|emotion|speak|
speak_audio|reset|status|models`. Audio cache `home/audio_cache` (max 50 files / 30 min).

### Live2D pitfalls (learned the hard way)
1. `plid-v5-bundle.js` is a build artifact absent from the Artemis repo — we ship the
   pixi-live2d-display-lipsyncpatch dist `cubism4.min.js` under that name.
2. Cubism Core must be **v4** (SDK 4-r.7); the official URL now serves Core 5 → black clipping.
3. Model assets must be **Cubism-4-era** (SDK tag `4-r.7`): the `develop` (SDK5) assets have
   PNGs Chrome's GPU upload rejects and masks that never render. Exact bytes matter → versioned.
4. Headless Chrome on this machine renders no WebGL textures; verify with `cdp_shot.mjs`
   against a real Chrome (`--remote-debugging-port`).

## Retired in 0.2.0
Python shim (`shim/shim.py`), `ui/webchat_adapter.py`, `ui/start_webchat.py`, Node bridge
(`ui/live2d/live2d-bridge.mjs`), `embedder.cmd`, ports 18767/19200/19201/19260/19270/18768.
