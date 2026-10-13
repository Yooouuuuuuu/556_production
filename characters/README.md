# characters/ — the 0.7.0 cast (provisional names)

Three characters with full backgrounds, as versioned files; a profile is made with `new-companion.ps1` and
these files are copied in with `install-character.ps1 -Name <id>`. Names are placeholders you can change:
the id is the folder, the display name lives in `companion.json` and the SOUL.

| id | display | who |
| --- | --- | --- |
| `sayo` | 小夜 | 24, singer-songwriter just signed; you have only just met (attachment from 0) |
| `chihiro` | 千尋 | 27, vocalist; dating yuma for three years; your old acquaintance from a live house |
| `yuma` | 悠真 | 29, arranger / producer; chihiro's boyfriend; your acquaintance of three years |

Each folder: `SOUL.md` (persona and background), `companion.json`, `psyche.json` (personality, constants,
schedule, small life events, relationship priors per counterpart), `people/*.md` (how they see you and each
other), `seeds.jsonl` (shared memories to load into the character's KeepsakeDB store with `seed-memories.py`).
