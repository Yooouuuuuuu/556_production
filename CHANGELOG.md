# Changelog

## 0.1.0 — 2026-09-30

Founding release of **556 Production** (556プロ / 心プロダクション — 5-5-6 = こころ).

- **Backbone**: vendored Hermes Agent engine, isolated HERMES_HOME, own shim router (:18767)
  with model lanes and tool-call translation for the Gemini proxy.
- **Memory**: mem0 + embedded Qdrant, bge-m3 embedder on CPU (:18768), extraction on
  gemini-3.8-flash, always-on writes. 1000-round zh-TW endurance test: 19–20/20 recall.
  Design lineage A → C → C2 in docs/MEMORY-DESIGN.md.
- **UI**: web chat (:19270) + thin API adapter (:19260), Live2D avatar with official Hiyori
  model (:19200), Electron desktop pet — transparent, always-on-top, drag-anywhere.
- **Launchers**: `556.cmd` (CLI/TUI) · `avatar.cmd` · `pet.cmd` · `embedder.cmd`.
- **Docs**: STACK, ARCHITECTURE, DECISIONS, ROADMAP, MEMORY-DESIGN.

Known gaps: web chat/pet bypass Hermes (rewrite pending) · no TTS/STT/image-gen yet ·
first companion unnamed · memory Path C not built.
