# Docs — what is here

Everything in `docs/` is a concept document: what each part is and why it is built that way. Nothing
here is a to-do list. One folder per part; each holds one living doc that is always current (edited in
place, with a "last verified" date) and its D2 graphs beside it (sources only; render with d2 for a
picture). A part gets a second file only when its design is replaced wholesale, kept as
`<part>-v1.md` with a "superseded by" line; small edits never make a new file. History is in jj.

| Part | Doc | Graphs | What it covers |
| --- | --- | --- | --- |
| `structure/` | `structure.md` | `structure`, `turn-flow`, `hermes`, `lifecycle` | one process per character, 556d as the hub, one turn (1 + 2), inside her Hermes process, lifecycle, zones, origins |
| `memory/` | `memory.md` | `memory-layers` | history is not memory; long and short layers; the kokoro pipeline on KeepsakeDB; subject 你; the test record |
| `app/` | `app.md` | — | the Electron app: windows, pages, the hub rule, what landed per version |
| `voice/` | `voice.md` | `voice` | press-to-record and conversation mode, connectors (Fish Audio), what is next |
| `inner-life/` | `inner-life.md` | `psyche`, `proactive` | her inner life: engine as a plugin, layers L0–L6, appraisal A and impact model B, memory and open loops, expression, proactive, multi-agent, guardrails, roadmap by stage, parameter glossary |

At the docs root:

- `DECISIONS.md` — one chronological decision log, each entry tagged with its part. Versions live here:
  a redesign is a new entry that says what it replaces.
- `STACK.md` — exact inventory of what runs (versions, ports, files, third parties).
- `CHANGELOG.md` is at the repo root, per version.

`characters/` (repo root) holds your cast — SOUL, psyche.json, kokoro keys, person files, seed memories — installed
into a profile with `install-character.ps1`. It is ignored by git except `characters/README.md` (the layout).

Working documents are local and ignored (`docs/*.local.md`): `ROADMAP.local.md` (what is next and in
which version) and `TEST-LIST.local.md` (manual test history). Outdated plans and drafts are deleted,
not kept.
