# 556 Production

556プロ — the agency where hearts are made (5-5-6 = こころ). A local-first companion system:
Hermes Agent as the brain, a Go daemon (`556d`) beside it, and one Windows app — chat, settings,
and a Live2D companion on your desktop.

## Run
1. `setup-vendor.ps1` once (checks out the `vendor/` submodules — Hermes at its pinned commit, KeepsakeDB at its
   release — and builds the venv); build the daemon (`go -C 556d build -o ..\556d.exe .\cmd\556d`). The first launch
   asks for 設定 → 模型連線 — an OpenAI-compatible endpoint and model for 對話／記憶／寫靈魂, the embedder (the
   vectors), the timezone — and nothing runs until it is set: there are no defaults. If the vectors are local,
   `bin/llama` and an embedding GGUF are downloads (see `docs/STACK.md`) whose paths go into that page.
2. `cd app && npm install --ignore-scripts && npm run build` (see STACK.md for the Electron
   binary note), then `npm start` — the app starts and owns the whole backend.
3. Terminal alternative: `556.cmd` (Hermes CLI/TUI; needs the app or `556d.exe` running).
4. Characters: 名單 → ＋ 新角色 in the app (describe her, run the soul skill, install), or
   `install-character.ps1 -Name <id>` for a package under `characters/` (your own cast, ignored by version control —
   the package is the character, `characters/README.md`), then `tools/seed-memories.py <id>` with 556d up and the
   character not running; `new-companion.ps1` makes a blank profile.

## Memory language and embedding model
Each companion stores memories in a chosen language (default Traditional Chinese; changeable in
Settings). The embedder is yours to choose in 設定 → 模型連線 — a local llama-server with a GGUF (`bge-m3`
covers zh/ja/en/fr and 100+ more) or any OpenAI-compatible embeddings endpoint — but **if you run a companion in a
language your embedder doesn't cover, change the embedder as well**; the two settings travel together (see
`docs/memory/memory.md`). Changing the embedder re-embeds the store.

## Docs
`docs/README.md` is the map: one folder per part (`structure/`, `memory/`, `app/`, `voice/`, `inner-life/`, `prompt/`), each a
living concept doc with its graphs; `docs/DECISIONS.md` and `docs/STACK.md` at the docs root; working documents
(roadmap, test list) are `docs/*.local.md`, ignored. `CHANGELOG.md` is per version.
Version control is git; `vendor/` holds the two submodules and is never edited.

## License
MIT (`LICENSE`) for 556 Production's own code. Third-party pieces keep their terms — the Live2D Cubism Core and the
Hiyori sample are Live2D's, not open source; see `THIRD-PARTY.md`.
