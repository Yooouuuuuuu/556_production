# Decisions log

## Decided
- 2026-09-29 — Workspace: everything under `D:\dev\556_production` (placeholder name).
- 2026-09-29 — Backbone: Hermes Agent (own copy, fresh venv, isolated HERMES_HOME) replaces
  Artemis's OpenClaw role. Production D:\Hermes stays untouched.
- 2026-09-29 — Model access: via the existing shim (:18766) lanes; testing lane `auto/probe`.
- 2026-09-29 — Gemini-only for now (proxy :18765 behind the shim). The shim is mandatory for
  tool calling (proxy strips `tools`; direct mode = chat-only with silent tool hallucination).
  Full loop verified: chat, tools, memory write, cross-session recall.
- 2026-09-29 — Project runs its OWN shim copy (:18767, `shim\`) instead of touching the
  production shim; chat model = `agyapi/gemini-3.7-flash` via lane `auto/556_production`
  (tool calling verified on flash). `auto/pro` kept for heavier jobs.
- 2026-09-29 — Live2D: official free sample models first; polish/custom later.

## Decided (2026-09-30, continued)
- **System name: 556 Production** (556プロ / 心プロダクション). Goroawase こ(5)こ(5)ろ(6) =
  心 kokoro — an idol-agency-style name (765PRO lineage: the number encodes a word): a good
  place where hearts and minds are created. The system is the AGENCY; companions are the talent;
  the user is the Producer. AI/tech stays subtext, like 765 = Namco.
- Physical rename 556_production/ → 556 happens DURING the rewrite (renaming now breaks the venv's
  absolute paths + all launchers; the rewrite touches those anyway).
- Candidate flourish for later: Path C memory engine module named `kokoro` — her heart literally
  being the memory engine. Port family 556xx available if the rewrite renumbers services.

## Parked (explicitly deferred by user)
- **Her name** (first companion) — decided AFTER the system; agency-first like the reference.
- **MCP / channel list** — later; QQ excluded.
- **Whether the Wardrobe schema is adopted** — it's one candidate, not presumed.

## Open questions
- Which profile becomes the first companion character here (fresh SOUL vs port of Bith's)?
- TTS voice source/reference audio for GPT-SoVITS (when we get there).
- GPU budget: does local image-gen/TTS coexist with WSL Qwen (→ revisit Artemis VRAM tiering)?

## Decided (2026-09-30, 0.2.0 discussion) — see docs/PLAN-0.2.0.md
- **Frontend stays as-is** for 0.2.0; 0.2.0 = backend rewrite.
- **`vendor/` is untouchable by definition**; if we edit it, it is not vendor. Hermes never edited.
- **Go** for the beside-Hermes layer (daemon `556d`: supervisor, shim, bridge, UI API): single
  static binary, cross-compiles to every OS, best fit for HTTP/WS + process supervision.
  **Python only inside Hermes** (memory provider, platform adapter, skills) — by contract.
- **No Rust, no Tauri.** Tauri is a window shell, not a TypeScript alternative; with Go fixed its
  Rust side is dead weight, and its small-binary benefit is what Wails gives in Go-land.
- **UI = TypeScript, one codebase**, identical under any shell. **Shell = Electron now** (bundled
  Chromium → avatar renders identically on every OS); **Wails later only if** we accept testing the
  avatar on three native webviews (WebView2 / WKWebView / WebKitGTK).
- **Hermes surface for chat = `tui_gateway` JSON-RPC over WS** (what Hermes Desktop uses):
  persistent agent, streaming, `profile` = talent switching. `api_server` optional. Proactive
  pushes need a Python platform-adapter plugin (0.2.x); cron agents run without memory provider.
- **Artemis exit**: reference clone kept until the frontend rewrite empties the ledger, then deleted.
