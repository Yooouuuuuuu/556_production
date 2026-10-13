# 0.2.0 — Backend rewrite: `556d` (plan of record, 2026-09-30)

0.1.0 proved the pieces. 0.2.0 turns five hand-started processes in two runtimes into one Go
daemon beside an untouched Hermes, and routes every UI to the real her. Frontend stays as-is.

## Decisions locked (see DECISIONS.md for reasoning)

| Topic | Decision |
|---|---|
| Boundary | `vendor/` is untouchable by definition. Hermes is never edited. Anything we edit is not vendor. |
| Languages | **Go** for everything beside Hermes (daemon, shim, bridge, supervisor). **Python** only for what plugs *into* Hermes (memory provider, platform adapter, skills) — by contract, not choice. |
| Shell / UI | UI is **TypeScript** (one codebase; identical under any shell). Shell = **Electron now**; **Wails** optional later (all-Go binary) only if we accept per-OS webview testing. **No Rust / no Tauri.** |
| Multi-OS | Go cross-compiles to all targets from one machine. Electron keeps avatar rendering identical across OSes (bundled Chromium); native webviews (Tauri/Wails) are a WebGL/transparency lottery. |
| Hermes surface | Chat via **`tui_gateway` JSON-RPC over WebSocket** (`hermes serve`): persistent per-session agent, streaming `message.delta`, `session.create(profile=…)` = talent switching. `api_server` optional for third-party clients. Proactive pushes need a **Python platform-adapter plugin** (0.2.x). |
| Artemis | Reference clone stays until the frontend rewrite, then `vendor/artemis/` is deleted. Ledger below. |

## Target repository structure

```
556_production/
├── vendor/                # third-party CODE, never edited
│   ├── hermes-agent/      #   pinned upstream commit; ignored; restored by setup script
│   ├── artemis/           #   study reference (deleted after frontend rewrite)
│   └── live2d/            #   live2dcubismcore.min.js (Core 4, proprietary blob)
├── 556d/                  # OURS — Go daemon
│   ├── cmd/556d/          #   main
│   ├── internal/supervisor/   spawn + watch hermes serve, embedder, future sidecars
│   ├── internal/shim/         model lanes, routing hot-reload, <tool_call> translation
│   ├── internal/bridge/       WebSocket hub: avatar/pet events, bubbles, audio cache
│   ├── internal/hermes/       tui_gateway JSON-RPC client (session/prompt/stream)
│   ├── internal/api/          UI-facing HTTP+WS (OpenAI-compatible + native events), static
│   └── go.mod
├── plugins/               # OURS — Python that plugs INTO Hermes; setup copies into home/plugins/
│   └── (kokoro memory provider, platform adapter — later)
├── assets/                # third-party DATA with licenses (Hiyori model), our future assets
├── ui/                    # web-chat (Artemis SPA, transitional), live2d viewer, pet (Electron)
├── home/ · models/ · bin/ # runtime / weights / downloaded binaries (ignored)
├── docs/ · tests/ · CHANGELOG.md
└── 556.cmd, pet.cmd, avatar.cmd  (thin wrappers around 556d)
```

Deleted in the restructure (dead Artemis leftovers): `ui/live2d/index_atri*.html`, `index_upper.html`,
`fix_atri_all.js`, `switch_model.ps1`. Retired once their Go ports pass parity: `shim/shim.py`,
`ui/live2d/live2d-bridge.mjs`, `ui/webchat_adapter.py`, `ui/start_webchat.py`.

## Target runtime

```
UIs: web-chat SPA (:55600)  ·  Live2D viewer / Electron pet (WS :55600)  ·  TUI (556.cmd)
        │                              │
        ▼                              ▼
556d.exe (Go) :55600 ─ api ─ bridge ─ supervisor ─ shim :55601
        │ JSON-RPC WS                                  │ OpenAI-compatible
        ▼                                              ▼
hermes serve :55610 (Python, vendored; SOUL + memory + tools)   Gemini proxy :18765 (user's)
        │
        └─ memory provider (mem0 now → kokoro/Path C later) ─ embedder :55602 (llama-server, interim)
```

Port family 556xx: `55600` 556d API/WS/static · `55601` shim · `55602` embedder ·
`55610` hermes serve. External and untouched: `18765` Gemini proxy, `18766` production shim.

Chat flow: UI → 556d → `session.create(profile)` / `prompt.submit` → `message.delta` stream → UI;
556d mirrors each completed reply to the bridge as a bubble (today's adapter behavior, moved in).
556d embeds static UI assets (`embed.FS`) so the binary is self-contained.

## Work breakdown (each slice independently verifiable)

- **S0 Restructure** — `vendor/`, `plugins/`, `assets/`; delete cruft; `setup` script restores the
  pinned Hermes commit; docs paths updated. No behavior change. *Verify: everything still runs.*
- **S1 556d skeleton** — Go module, config file (`556d.toml`), logging, **supervisor** (spawn/monitor/
  restart `hermes serve` + embedder; kill children on exit via Windows job object). `go build` →
  one exe. *Verify: `556d.exe` brings the stack up and down.*
- **S2 Shim port** — lanes/backends/routing hot-reload, passthrough, `<tool_call>` translation.
  *Verify: parity — a recorded fixture set of requests/responses replayed against both shims.*
- **S3 Bridge port** — WS hub with the Artemis-compatible HTTP API (`/api/message|motion|expression|
  emotion|speak_audio|status`) so the current viewer/pet work unchanged; static serving; audio cache;
  no SoVITS management (TTS slice later). *Verify: bubble + motion on pet via 556d.*
- **S4 Chat path** — `internal/hermes` JSON-RPC client; 556d exposes (a) OpenAI-compatible
  `/v1/chat/completions` (stream) for the existing SPA, (b) native WS events for the future TS app;
  approval/clarify passthrough; bubble mirroring. *Verify: web chat recalls memory (real her).*
- **S5 Repoint & retire** — SPA → 556d, pet/viewer → 556d, retire the four Python/Node pieces.
  *Verify: only 556d + hermes serve + embedder processes remain.*
- **S6 Ports, wrappers, docs** — 556xx, `.cmd` wrappers → 556d, STACK/ARCHITECTURE/DECISIONS,
  CHANGELOG 0.2.0. *Verify: fresh-machine run guide works.*

Parallel track (own plan): **Path C `kokoro`** in `plugins/`. Deferred to 0.2.x: proactive-push
platform adapter; memory storage language policy (decision pending).

## Non-goals for 0.2.0
Frontend rewrite · TTS/STT/image-gen · her name · Wails/Tauri · Path C (unless parallel).

## Open items to settle at S0 start
Memory storage language (zh-TW / en / mirror) · config format (TOML proposed) · Go module path ·
whether `hermes serve` runs as child of 556d (proposed yes) or as a separate service.

## Risks & mitigations
- `<tool_call>` translation parity → recorded fixtures replayed against the Python shim before retiring it.
- `tui_gateway` is an internal, unversioned protocol → pinned to the vendored commit; isolated in one
  client package; upgrade = re-verify that package only.
- Windows child-process cleanup → job objects; supervisor tested for crash/restart loops.
- Embedded Qdrant is single-process → only `hermes serve` may open the store; cron/one-shot agents
  must not run concurrently against it (revisit with Path C).
- Artemis SPA assumptions (its own persona/system prompt) → 556d ignores client `systemPrompt`
  when routing to Hermes; SOUL owns persona.

## Artemis ledger (drives `vendor/artemis/` deletion)
| Still Artemis-derived | Exit |
|---|---|
| `ui/live2d/live2d-bridge.mjs`, `ui/start_webchat.py` | replaced in 0.2.0 (S3/S5) |
| `ui/web-chat/` SPA, `ui/live2d/index.html` | replaced by the TS frontend rewrite (later) |
When the second row empties, delete `vendor/artemis/`.

## Status — DONE 2026-09-30
S0 restructure ✅ · S1 daemon+supervisor ✅ · S2 shim port (parity-tested) ✅ · S3 bridge port ✅ ·
S4 chat via tui_gateway ✅ · S5 repoint & retire ✅ · S6 ports 556xx + docs ✅.
Carried to 0.2.x: proactive-push platform adapter (Python), approval/clarify UI, memory storage
language decision, `hermes serve` scale/idle behavior review, embedded-Qdrant single-process caveat.
