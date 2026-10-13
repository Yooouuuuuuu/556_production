# characters/ — your cast (ignored by version control except this file)

Each character is a folder `characters/<id>/`: `SOUL.md` (persona and background), `companion.json` (display name,
avatar), `psyche.json` (personality as Big Five percentile ÷ 100, the six constants, schedule, small life events,
relationship priors per counterpart), `kokoro.json` (keys merged into the profile's kokoro.json, e.g. `address_default`:
how she addresses you until Settings → 你 has your name), `people/*.md` (how she sees you and the others; `你.md` is
yours), `seeds.jsonl` (memories to load with `tools/seed-memories.py`).

Install into a profile: `install-character.ps1 -Name <id>` (creates the profile with `new-companion.ps1` when missing,
then copies the files; restart her afterwards). Seed memories with the embedder up and the character not running.
Keep the word 製作人 and any agency framing out of these files unless that is the world you want.
