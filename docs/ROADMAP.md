# Roadmap (plan of record — set by the user, 2026-09-29)

1. ✅ **UI first** — copy the UI from the reference repo (Artemis) and make it run.
   Done: web-chat SPA + Live2D viewer/bridge running against our shim (see STACK.md §UI).
2. 🔨 **Memory** — DECIDED 2026-09-30 (see docs/MEMORY-DESIGN.md): Path A (mem0+Qdrant embedded,
   bge-m3 CPU, gemini-3.8-flash extraction, always-on writes) now → Path C (own Milvus-inspired
   hybrid provider, in-process, English trust labels 0.9/0.5) as target. Implementing A.
3. ⏳ **Media** — connect TTS, STT, and image generation.
4. ⏳ **Last** — language issues + UI rewrite discussion.
5. ⏳ **Learn from Bongo Cat** — study what makes it feel alive as a desktop pet and adopt
   what fits: input-reactive animation (reacts to your real keyboard/mouse activity),
   pixel-alpha click-through (only the character is clickable; desktop clicks pass through
   the transparent area), tray icon + settings menu, auto-start, single-exe packaging.
   (2026-09-30: whole-body dragging already adopted — grab her anywhere, taps still work.)

Standing constraints: production D:\Hermes untouched · Gemini-only via project shim ·
avatar = official free samples (Hiyori) for now.
**System name: 556 Production** (decided 2026-09-30; dir rename happens during the rewrite).
Order update: media/voice slice moved to LAST (GPU/cloud cost); active fronts:
naming ✅(system)/her-name-later → backend+frontend rewrite discussion → Path C build.

## 0.2.0 — backend rewrite ✅ DONE 2026-09-30
Plan of record: docs/PLAN-0.2.0.md. One Go daemon `556d` (supervisor + shim + bridge + UI API)
beside an untouched Hermes; chat via tui_gateway; existing UIs repointed to the real her;
ports → 556xx; Artemis-derived backend pieces retired. Frontend unchanged.

## 0.3.0 — frontend: the "556 Production" app ✅ DONE 2026-10-01
Plan of record: docs/PLAN-0.3.0.md. One Electron+React app (office window: chat + settings; avatar
window toggled) owning 556d's lifecycle; 556d gains the hub event stream, history and settings APIs;
Artemis SPA, old pet, and `vendor/artemis` retired at the end.

## Next (after 0.3.0)
- **0.4.0 packaging** — installer/portable build bundling 556d + hermes venv + models; auto-start,
  updater, input-reactive animation (the Bongo Cat items).
- **Memory engine** (separate repo; name TBD; pipeline-in-DB question first) → `plugins/kokoro`.
- **Her name**. **Companion switcher UI**. **Proactive pushes** (platform adapter). **Voice** last.
