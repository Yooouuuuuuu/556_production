# Docs — what is here

Everything in `docs/` is a concept document: what each part is and why it is built that way. Nothing
here is a to-do list. One folder per part; each holds one living doc that is always current (edited in
place, with a "last verified" date) and its D2 graphs beside it (sources only; render with d2 for a
picture). A part gets a second file only when its design is replaced wholesale, kept as
`<part>-v1.md` with a "superseded by" line; small edits never make a new file. History is in git.

| Part | Doc | Graphs | What it covers |
| --- | --- | --- | --- |
| `structure/` | `structure.md` | `structure`, `turn-flow`, `hermes`, `lifecycle` | one process per character, 556d as the hub, one turn (1 + 2), inside her Hermes process, lifecycle, zones, origins |
| `memory/` | `memory.md` | `memory-layers` | history is not memory; long and short layers; the kokoro pipeline on KeepsakeDB; subject 你; the test record |
| `app/` | `app.md` | — | the Electron app: windows, pages, the hub rule, what landed per version |
| `voice/` | `voice.md` | `voice` | press-to-record and conversation mode, connectors (Fish Audio), what is next |
| `inner-life/` | `inner-life.md` | `psyche`, `proactive` | her inner life: engine as a plugin, layers L0–L6, appraisal A and impact model B, memory and open loops, expression, proactive, multi-agent, guardrails, roadmap by stage, parameter glossary |
| `prompt/` | `prompt.md`, `around-the-soul.md` | `prompt`, `character-files` | what she reads before she speaks: one request verified block by block (the SOUL, Hermes's vendor text around it, kokoro's block, the shim's tools, history replay and its cost, the last message's three pieces); the design, built 0.8.0–0.10.0 — three homes by cost, the six-part SOUL with 時間線 and 影響過你的人與事 inside it, the clock, the thinking dials, the hidden scratch, the vendor-text filter, no tools at baseline, the authoring path (the character package and the soul skill, with the slider-only simple path); `around-the-soul.md` is the block-by-block decision brief for the vendor and shim text (keep / off / replace / drop, with the tool-usage data); `character-files` shows what the author writes, what the skill makes, what 556d copies before a start, and where each file lands in one request |

At the docs root:

- `DECISIONS.md` — one decision log, newest entries first within each cluster, each entry tagged with its part. Versions live here:
  a redesign is a new entry that says what it replaces.
- `STACK.md` — exact inventory of what runs (versions, ports, files, third parties).
- `CHANGELOG.md` is at the repo root, per version.

`characters/` (repo root) holds your cast as packages, one folder per character: `describe/*.md` and `profile.json` are
yours, `SOUL.md`, `seeds.jsonl`, `people/`, `psyche.json`, `soul.lock.json` and `build/` are what the soul skill makes
from them. A package is installed from 名單 → ＋ 新角色 or with `install-character.ps1`, and the package is the
character: 556d copies it over her profile before every start, so backing her up = the package + `memory/<id>.db`,
`psyche.db` and `state.db` from the profile. Ignored by git except `characters/README.md` (the layout).

Working documents are local and ignored (`docs/*.local.md`): `ROADMAP.local.md` (what is next and in
which version) and `TEST-LIST.local.md` (manual test history). Outdated plans and drafts are deleted,
not kept.
