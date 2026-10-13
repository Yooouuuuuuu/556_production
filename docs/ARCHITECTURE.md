# Architecture — what we took from where (updated 2026-10-01)

The project: a local-first AI companion built ON the Hermes Agent backbone, learning from
momori777/Artemis (and the surveyed field: Open-LLM-VTuber, Soul of Waifu, z-waif, MyAiFriend).

## The core swap

Artemis (our study reference, now deleted from the tree) = OpenClaw Gateway + Headroom proxy + llama-server + media services.
Here, **Hermes replaces OpenClaw AND most of Headroom**: multi-platform gateway (Telegram/Discord/
Slack/WhatsApp/Signal/CLI), per-profile characters (SOUL.md + isolated home), curated memory +
background review, context compression, skills with a real learning loop, cron, subagents.
The user's **shim** (:18766) replaces Artemis's single-model lock-in with routed lanes
(local Qwen / Gemini / Claude fallback chains) — any OpenAI-compatible model plugs in.

## What we keep from Artemis (the seven patterns)

1. Characters as folders of markdown (SOUL/IDENTITY) → Hermes profiles already do this.
2. Memory isolation per character → per-profile HERMES_HOME.
3. Dual-layer memory with recall priority → parked; see memory-notes.md.
4. Compression + memory as one system → Hermes context_compressor + session_search cover it.
5. Scheduled fact distillation (CCR) → candidate feature of the memory decision.
6. **VRAM tiering** → only relevant once local TTS/image-gen share the GPU with Qwen; parked.
7. Thin interchangeable frontends → Hermes gateway platforms.

## What Artemis has that we still need (the embodiment layer — build order)

1. **Character voice**: GPT-SoVITS behind a Hermes skill (HTTP API → audio into the profile's
   `audio_cache/`, delivered as voice notes). Hermes's built-in edge-tts is the placeholder.
2. **Local image gen**: ComfyUI skill (POST workflow JSON to :8188); anime model TBD.
3. **Avatar**: Live2D web page (pixi-live2d-display + Cubism Core 4 — NOT 5, clipping bug),
   official free sample models first.
4. **Channels**: pick per-profile platforms later (no QQ).

## Zones (same discipline as the user's D:\Hermes layout)

- `hermes-agent\` — vendored engine, **never edited** (fixes go upstream or in skills/plugins).
- `home\` — runtime data + config; profiles = characters.
- `docs\` — decisions, stack inventory, research notes.
- Future custom code (skills, TTS/image bridges, avatar frontend) — own folders under root,
  installed into `home\` the same way the Wardrobe's Stylist would (copy, not symlink).

## Where it landed (0.3.0)
One app owns one daemon owns one brain: **556 Production (Electron/React) → 556d (Go: hub, shim,
bridge, supervisor) → hermes serve (Python, vendored)**. Every client talks only to 556d, which
broadcasts to all. Artemis's patterns survive as: per-companion memory isolation (Hermes
profiles), proxy-layer routing (the shim), avatar bridge API (Artemis-compatible control routes),
trust-labeled retrieval (designed into Path C). See STACK.md for the exact inventory.
