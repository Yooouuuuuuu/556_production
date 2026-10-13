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

## Decided (2026-09-30, after 0.2.0) — memory language, engine repo, frontend shape
- **Memory language is a per-companion setting** (user-changeable; default zh-TW). "Mirror the
  input language" rejected (mixed stores defeat dedup — the zh/en Japan-trip duplicate).
  **Catch, documented in README + MEMORY-DESIGN**: the embedding model is user-changeable too, and a
  companion in another language (ja/fr/…) must be paired with an embedder that covers it.
- **Standalone memory engine**: own repo, pure Python library consumed by 556 via a thin Hermes
  MemoryProvider in `plugins/`. Name deferred (may take a `DB` suffix; "kokoro" collides with the
  Kokoro TTS model, so it stays 556-internal). Open before writing: whether the memory *pipeline*
  (extract/tag/merge/archive) lives inside the library or in 556 — proposal: layered library
  (storage+retrieval core; pipeline as an optional module) so the DB alone stays lightweight.
- **Conversation model**: backend keeps ONE endless conversation per companion; only the last X
  turns are in context (Hermes compression knobs; X user-settable later). Frontend shows the
  current X turns for now — revisit.
- **Hub architecture**: every UI/channel (office window, pet, Telegram, MCP…) connects to the
  backend; the backend fans events out to all connected services. Windows never talk to each
  other directly. Fan-out policy (what goes where) to be designed; end state: ask on Telegram,
  the pet answers on the desktop.
- **Approvals/clarify**: solved by toolset policy, not UI — the companion's toolset excludes
  approval-gated tools and the `clarify` tool. No prompt UI planned.
- **Proactive presence**: no limits/etiquette rules for now.
- **App model**: ONE Windows app, "556 Production" — office window with chat + settings, a button
  to show/hide the avatar (pet window belongs to the same app). Closing the app closes the whole
  backend (the app owns 556d's lifecycle); minimize/hide to the tray (bottom-right).
- Terminology: "companion" (not "talent") in docs and UI.

## Done (2026-10-01, 0.3.0 S5) — Artemis exit
- The Artemis ledger emptied (SPA and viewer replaced by the app) → `vendor/artemis/` deleted.
  What we learned from it lives in `docs/ARCHITECTURE.md`, `STACK.md` pitfalls and this log.
- Retired: `ui/` (web-chat SPA, Electron pet, viewer), `avatar.cmd`, `pet.cmd`, the `/chat/`
  route and the SPA-compat endpoints. Diagnostics moved to `tools/`.
