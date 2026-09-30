# STACK — what exactly this project is using

Last verified: 2026-09-29. This is the ground-truth inventory; update it when reality changes.

## Engine
- **Hermes Agent v0.21.0 (2026.8.31)** by Nous Research, MIT license.
- Source **copied** from `D:\Hermes\hermes-agent` at upstream commit **`7166071f`** (2026-09-06,
  "fix(auxiliary): ResourceExhausted spellings…"). Excluded from the copy: `.venv`, `.git`,
  `__pycache__`, `node_modules`, `index-cache`, `.pytest_cache`, `hermes_agent.egg-info`.
- To update the engine later: re-copy from `D:\Hermes\hermes-agent` (after updating it) or
  `git clone https://github.com/NousResearch/hermes-agent` fresh — this copy has no git history.

## Python environment
- Fresh venv at `hermes-agent\.venv` — **Python 3.11.16** (uv-managed), created with **uv 0.12.10**,
  editable install (`uv pip install -e .`, core extras only).
- The old install's venv was deliberately NOT copied: its `hermes.exe` launcher and `pyvenv.cfg`
  hardcode `D:\Hermes\...` paths — a copied venv silently runs the old install.

## Data home (isolation)
- `HERMES_HOME = D:\dev\556_production\home` — own `config.yaml`, `state.db`, `memories/`, `skills/`,
  `SOUL.md`. The production home (`D:\Hermes\home`) and its three live bots
  (taskdesk / Bith / newsdesk) are untouched; verified zero file changes during setup.
- Launcher: `556_production.cmd` (sets HERMES_HOME, runs this venv's hermes).

## Model backend (verified working 2026-09-29)
- **Project-own shim** `http://127.0.0.1:18767/v1` (`shim\shim.py` — copied from the production
  shim, port changed, `gemini-flash` backend added). Lane **`auto/556_production`** → Gemini proxy
  :18765, model **`agyapi/gemini-3.7-flash`**. Extra lanes: `auto/pro` (gemini-3.1-pro),
  `auto/code` (claude-sonnet). Routing hot-reloads from `shim\routing.json`.
- The shim is REQUIRED for tool calling: the Gemini proxy strips the `tools` param; the shim
  translates tools ↔ Nous `<tool_call>` text format. Direct-to-proxy (:18765) works for chat
  but tools fail SILENTLY (model hallucinates results — demonstrated).
- The production shim (D:\Hermes\shim, :18766) is NOT used by this project and stays untouched
  (permission classifier also enforces this). Start ours with:
  `Start-Process D:\dev\556_production\hermes-agent\.venv\Scripts\python.exe D:\dev\556_production\shim\shim.py`
- End-to-end verified: chat ✓ · tool calls on 3.7-flash (real file read) ✓ · memory write ✓ ·
  cross-session memory recall ✓.

## UI (running as of 2026-09-29 — copied from the Artemis reference repo)
- **Web chat** `http://127.0.0.1:19270` — Artemis's SPA (`ui\web-chat\`, unmodified), served by
  `ui\start_webchat.py`. Its backend API is our **adapter** `ui\webchat_adapter.py` on **:19260**
  (stand-in for Artemis's 2,484-line shiki_daemon): implements /api/gateway-config, /api/chat
  (→ shim :18767, non-streaming), /api/status; everything else returns benign empties and the
  SPA falls back gracefully (built-in character list, etc.).
- **Live2D avatar** `http://127.0.0.1:19200/index.html` — Artemis's viewer + bridge
  (`ui\live2d\`, node live2d-bridge.mjs, HTTP :19200 + WS :19201), pixi 7.4.3 +
  pixi-live2d-display-lipsyncpatch 0.5.0-ls-8 dist as `plid-v5-bundle.js`. Model = official
  free **Hiyori** (`ui\live2d\hiyori\`; Free Material License) + **Cubism Core 4** (SDK 4-r.7).
  Bridge API (expression/motion/message/speak) works; GPT-SoVITS hooks dormant until TTS slice.
- **Live2D pitfalls discovered the hard way (2026-09-29)** — rules for future model imports:
  1. `plid-v5-bundle.js` is a build artifact NOT in the Artemis repo — we serve the
     lipsyncpatch package's dist `cubism4.min.js` under that name.
  2. **Cubism Core must be v4** (SDK 4-r.7); the official URL now serves Core 5 → black
     clipping shapes (as Artemis's README warns).
  3. **Model assets must be Cubism-4-era**: assets from Live2D's `develop` (SDK5) branch
     failed twice — recompressed PNGs that Chrome's GPU `texImage2D` rejects with
     GL_INVALID_VALUE (black textures; fixable by re-encoding), and masked meshes that never
     render (face/eyes/skirt invisible; NOT fixable by pixi/plid downgrades). Assets from the
     `4-r.7` git tag work perfectly. Diagnostic tool kept: `ui\live2d\cdp_shot.mjs`
     (real-Chrome screenshots via CDP; headless Chrome renders no WebGL textures here).
- Start all three: adapter + webchat via venv python, bridge via node (see DECISIONS/commits).
- CAVEAT: web-chat currently talks straight to the shim (raw model + its own local prompt/
  character system) — it does NOT go through Hermes agent memory/tools yet. That integration
  is the "UI rewrite" discussion, deliberately last on the roadmap.
- Terminal TUI (`556_production.cmd`) remains the full-agent interface (tools + memory).

## Memory (Path A LIVE since 2026-09-30 — see MEMORY-DESIGN.md)
- Stock tiers: curated `MEMORY.md`/`USER.md` head + FTS5 session search + compression (unchanged).
- **Long-tail tier: mem0 provider** (`memory.provider: mem0`, config `home\mem0.json`):
  extraction LLM = `agyapi/gemini-3.8-flash` direct to proxy :18765 · embedder = **bge-m3 Q8_0
  GGUF on CPU** via llama-server sidecar **:18768** (`embedder.cmd`; binary `bin\llama\`, model
  `models\bge-m3-Q8_0.gguf`) · store = embedded Qdrant at `home\mem0_qdrant` (per-profile).
  Always-on writes (post-moderation). Verified end-to-end incl. implicit 繁中 extraction and
  cross-language paraphrase recall.
- Target: Path C custom hybrid provider (see MEMORY-DESIGN.md); mem0 tier migrates into it.

## Not (yet) used
- No gateway/bot startup (CLI only). No TTS / ASR / image generation / avatar yet.
- Live2D: will use **official free sample models** (Hiyori etc.) when we get there.
- MCP list: TBD (later discussion). QQ: excluded.
- Project name: TBD ("556_production" is a placeholder directory name).

## Related
- `D:\dev\companion-lab` — earlier learning repo distilling Artemis's architecture (docs there:
  ARCHITECTURE.md, COMPARISON.md).
- Artemis (study reference): https://github.com/momori777/Artemis
- `D:\Hermes` — production Hermes install + the user's notes (`notes/architecture.md`,
  `notes/learning-schema.md`, `wardrobe/`). Read-only reference from this project.
