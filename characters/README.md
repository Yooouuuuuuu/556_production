# characters/ — your cast (ignored by version control except this file)

Each character is a folder `characters/<id>/`. Since 0.8.0 a character is written in two layers (`docs/prompt/prompt.md`
§2.9): **inputs** the person owns, and **outputs** the soul skill generates from them.

Inputs:
- `describe/*.md` — ten short files in your own words (who she is, background, what happened and when, how she talks,
  how she thinks, how she relates, likes, stances, the people around her, other). The HTML comments are the template's
  prompts and are ignored; `templates/character/describe/` is the blank template, `templates/character/example/` a
  filled one (阿凜, a disposable test character).
- `profile.json` — the numbers and choices the engine reads: Big Five, the six constants, the five thinking meters, the
  dial 1 and 6 choices, pronoun, schedule. The skill's thinking phase proposes them with one line of evidence each
  (`proposed`); you confirm by filling the null fields or run with `--yes`.
- `companion.json` (display name, avatar) and `kokoro.json` (keys merged into the profile's kokoro.json, e.g.
  `address_default`: how she addresses you until Settings → 你 has your name).

Outputs (regenerate explicitly; `soul.lock.json` records which inputs produced them):
- `SOUL.md` — the six-part persona: background, likes and dislikes, 怎麼聽、怎麼想、怎麼回, 怎麼判斷、怎麼決定, 說話的方式
  (with five lines she would say and five she would not), 遇到事情的時候 (with a fallback table), 誰在跟你說話.
- `seeds.jsonl` — memories to load with `tools/seed-memories.py`; a row with `at` (YYYY, YYYY-MM or YYYY-MM-DD) is
  stored at that date. Memories about you keep the subject word 你; the others are named.
- `people/*.md` — how she sees you (`你.md`, also carries your name and reply language from Settings) and each other
  character.
- `psyche.json` — the engine's file, built from `profile.json` and the template; `thinking` and `thinking_choices` are
  recorded there for the coming thinking module.
- `build/` — one JSON per phase (intake, structure, thinking, voice, reactions, parts, verify), `check.md`, `verify.md`,
  and the raw model replies under `build/raw/`.

The skill, from the app: 設定 → 角色 → 新角色 (0.8.1) — the same phases as a 556d job, proposals confirmed on the page,
install from the page. From the terminal:
```
python tools/soul_writer.py init <id> --display 名字 [--from-example]
python tools/soul_writer.py run <id> --phase all --model gemini|claude [--yes]   # or one phase at a time
python tools/soul_writer.py run <id> --phase verify --model claude               # blind read-back of SOUL.md
python tools/soul_writer.py check <id> ; python tools/soul_writer.py status <id>
```
Every phase stops for review unless `--yes`; a part can be regenerated alone; `assemble` refuses to write a SOUL that
fails the checks (theory or machine words, digits, simplified characters, size 2,500–4,000, missing sections) unless
`--force`. The models are served by the proxy at :18765; 556d need not be running.

The simple path (0.8.10, `docs/prompt/prompt.md` §2.10): `python tools/soul_writer.py simple <id>` compiles `profile.json`
alone — the sliders, the choices and three boxes under `simple` (`who`, `talk`, `refuses`) — into the same files with
one zh-TW sentence per band, no model; the 產生 step's 簡單版 fold does the same. `closeness` (剛認識 … 很親近) becomes
her starting bond with you (`psyche.json` `relationships.你`); `scratch: true` adds the hidden think-first instruction
(§2.6). The fidelity probe: `python tools/fidelity_probe.py --gold tests/fidelity/<id>.json --soul <SOUL.md> …` scores a
SOUL text blind (recognition in a lineup, 像不像她會說, A/B takes) so two versions of the same character can be compared.

Install into a profile: `install-character.ps1 -Name <id>` (creates the profile with `new-companion.ps1` when missing,
then copies SOUL.md, companion.json, psyche.json, kokoro keys and people/*.md; restart her afterwards). Seed memories
with the embedder up and the character not running. A hand-written character (SOUL.md and the rest written directly,
no `describe/`) still installs the same way. Keep the word 製作人 and any agency framing out of these files unless that
is the world you want.
