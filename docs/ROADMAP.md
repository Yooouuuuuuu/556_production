# Roadmap (plan of record — set by the user, 2026-09-29)

1. ✅ **UI first** — copy the UI from the reference repo (Artemis) and make it run.
   Done: web-chat SPA + Live2D viewer/bridge running against our shim (see STACK.md §UI).
2. ✅ **Memory** — Path A (mem0+Qdrant) shipped 2026-09-30; the engine became **KeepsakeDB**
   (2026-10-01, benchmarked ahead of Milvus Lite) and the `kokoro` provider went live 2026-10-02
   (hybrid recall, trust labels, archive + consent, zh-TW pipeline). Endurance test: see
   docs/MEMORY-DESIGN.md. Memory page (view + delete) shipped 2026-10-02. Left: a clean
   1000-round run under a stable backend; thresholds recalibrated from logged scores if needed.
3. 🟡 **Media** — TTS + STT ✅ 0.4.0 (Fish Audio connector, press-to-record and conversation mode); image generation ⏳.
4. ⏳ **Last** — language issues + UI rewrite discussion.
5. ⏳ **Bongo Cat lessons** (reworded 2026-10-01 — a study list, not requirements). Adopted:
   whole-body dragging (0.1.0), tray icon + settings (0.3.0), single app owning the backend (0.3.0).
   Still a real need: **pixel-alpha click-through** (only the character is clickable; desktop
   clicks pass through the transparent area) — polish for 0.4.0. Nice to have: auto-start.
   Optional, not planned: input-reactive animation.

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

## 0.4.0 — her own process, one conversation, memory, Telegram, voice ✅ DONE 2026-10-06
Everything under CHANGELOG 0.4.0: 真音 as the first character; one `hermes gateway run` per character
(its API server is the app's route, its adapters are her channels); one session shared by the app and
Telegram with both mirrors; kokoro on KeepsakeDB 0.2.0 with the long and short layers; graceful stop;
two voice modes on Fish Audio; two-tier Settings over the config registry. Packaging and click-through
moved to Next.

## Next (after 0.4.0) — order to be set by the user
Open: Discord adapter · MCP bindings per character · proactive pushes (platform adapter) · image
generation · prompt-layer design · 0.4.x/0.5.0 packaging (installer, updater, auto-start) and pixel
click-through · approval/clarify in the UI · language + UI rewrite discussion · clean 1000-round memory
run + threshold recalibration · facts about her (self-facts) · STT Traditional-Chinese conversion ·
her toolset trim (~25k-token prompt).

### History of the previous list (after 0.3.0, order set 2026-10-02)
1. Finish the memory check (clean 1000-round run) → KeepsakeDB goes public (private GitHub) once good.
2. ✅ **The first character: 真音（まね, Mane）** — fresh persona, the agency's manager, sample Live2D stays
   (`kokoro` stays the memory plugin's name). After the memory run: SOUL draft, settings name, `memory/mane.db`.
3. **Channel bindings, Telegram and Discord first** — her own accounts, bound strictly to her
   (Hermes gateway adapters, one per character, under the 556d supervisor; MCP tool servers
   follow the same per-character binding rule). **Text only**; voice over channels is future work.
   ✅ Roster/lifecycle shipped 2026-10-02. ✅ **Telegram live 2026-10-02** (真音's own bot, DM allowlist,
   first reply through the model lane, memory pipeline ran). Discord postponed by the user.
Then the rest, in no committed order:
- ✅ **Producer's name in Settings** (2026-10-02): `producer_name` → written through to the bound
  profile's `memories/USER.md` (one managed line) and `kokoro.json` (`producer_name`); memories keep the
  fixed subject 「製作人」 (DECISIONS). Memory language / embedder now write through to `kokoro.json` too.
- **Voice** (future feature): **connectors shipped 2026-10-02** — `home/voice.json`, OpenAI-compatible
  TTS/STT clients, Settings → 語音連線 with a TTS→STT round-trip test. Shortlist (Oct 2026 prices): STT Groq
  Whisper turbo $0.04/h · AssemblyAI $0.0025/min · OpenAI mini-transcribe $0.003/min · Deepgram Nova-3
  $0.0043/min; TTS Fish Audio $15/1M chars (best zh/ja) · Azure Neural $15/1M (native zh-TW voices) ·
  Google Chirp 3 HD $30/1M (1M free) · OpenAI mini-tts ≈ $0.015/min · MiniMax $60–100/1M. Not now.
- **Reply language** ✅ (2026-10-02): Settings → her reply language (default follow / en / zh-CN / zh-TW / ja),
  written to her USER.md with the Producer's name. Prompt-layer deep dive later (DECISIONS).
- **0.4.0 packaging** — installer/portable build bundling 556d + hermes venv + models; pixel
  click-through; auto-start (nice to have); updater.
- **Memory engine → KeepsakeDB** (`D:\dev\KeepsakeDB`, created 2026-10-01; SQLite hybrid store,
  benchmarked ahead of Milvus Lite 3.x). Next: the Hermes provider `plugins/kokoro` on top of it,
  migrate Path A's Qdrant facts, re-run the 1000-round test.
- **Companion lifecycle** (decided 2026-10-02, see DECISIONS): roster with manual start/stop per
  companion, several active at once, stop-all on app close; MCP/channel bindings belong to exactly one
  character (strict); avatar follows the chat window; one Hermes process + one memory store per active companion. Supersedes the
  "companion switcher" idea. **Her name**. **Proactive pushes** (platform adapter). **Voice** last.
