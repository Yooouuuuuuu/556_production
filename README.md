# 556 Production

556プロ — the agency where hearts are made (5-5-6 = こころ). A local-first companion system:
Hermes Agent as the brain, a Go daemon (`556d`) beside it, and one Windows app — chat, settings,
and a Live2D companion on your desktop.

## Run
1. `setup-vendor.ps1` once (restores the pinned Hermes engine + venv); download `bin/llama` and
   `models/bge-m3-Q8_0.gguf` as described in `docs/STACK.md`; build the daemon
   (`go -C 556d build -o ..\556d.exe .\cmd\556d`).
2. `cd app && npm install --ignore-scripts && npm run build` (see STACK.md for the Electron
   binary note), then `npm start` — the app starts and owns the whole backend.
3. Terminal alternative: `556.cmd` (Hermes CLI/TUI; needs the app or `556d.exe` running).

## Memory language and embedding model
Each companion stores memories in a chosen language (default Traditional Chinese; changeable in
Settings). The embedding model is changeable too — the default `bge-m3` covers zh/ja/en/fr and
100+ more, but **if you run a companion in a language your embedder doesn't cover, change the
embedder as well**; the two settings travel together (see `docs/memory/memory.md`). Changing the
embedder re-embeds the store.

## Docs
`docs/README.md` is the map: one folder per part (`structure/`, `memory/`, `app/`, `voice/`, `inner-life/`), each a
living concept doc with its graphs; `docs/DECISIONS.md` and `docs/STACK.md` at the docs root; working documents
(roadmap, test list) are `docs/*.local.md`, ignored. `CHANGELOG.md` is per version.
Version control is jj; `vendor/` is never edited.
