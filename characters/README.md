# characters/ — your cast (ignored by version control except this file)

Each character is a folder `characters/<id>/`. Since 0.8.0 a character is written in two layers (`docs/prompt/prompt.md`
§2.9): **inputs** the person owns, and **outputs** the soul skill generates from them.

Inputs:
- `describe/*.md` — ten short files in your own words (who she is, background, what happened and when, how she talks,
  how she thinks, how she relates, likes, stances, the people around her, other). The HTML comments are the template's
  prompts and are ignored; `templates/character/describe/` is the blank template, `templates/character/example/` a
  filled one (an example description, a disposable test character).
- `profile.json` — the numbers and choices the engine reads: Big Five, the seven constants (self-esteem stability,
  expressiveness, humor coping, clinginess cap, tsundere tendency, assertiveness, chronotype), the five thinking meters,
  the dial 1 and 6 choices, pronoun, schedule, `closeness` (0.8.9) and `scratch` (0.8.10). The skill's thinking phase
  proposes the meters and choices with one line of evidence each (`proposed`); you confirm by filling the null fields
  or run with `--yes`.
- `companion.json` (display name, avatar) and `kokoro.json` (keys merged into the profile's kokoro.json, e.g.
  `address_default`: how she addresses you until Settings → 你 has your name).

Outputs (regenerate explicitly; `soul.lock.json` records which inputs produced them):
- `SOUL.md` — the six-part persona: background, likes and dislikes, 怎麼聽、怎麼想、怎麼回, 怎麼判斷、怎麼決定, 說話的方式
  (with five lines she would say and five she would not), 遇到事情的時候 (with a fallback table), 誰在跟你說話. Inside the
  background, `## 時間線` (absolute dates, oldest first) and `## 影響過你的人與事` — the dated, always-on part of who she
  is; the only place digits are allowed, not counted in the 2,500–4,000 budget (0.10.0).
- `seeds.jsonl` — memories to load with `tools/seed-memories.py`; a row with `at` (YYYY, YYYY-MM or YYYY-MM-DD) is
  stored at that date. Memories about you keep the subject word 你; the others are named.
- `people/*.md` — how she sees you (`你.md`, also carries your name and reply language from Settings) and each other
  character.
- `psyche.json` — the engine's file, built from `profile.json` and the template: `thinking` and `thinking_choices` for
  the thinking module (0.8.8), `relationships.你` from `closeness`. 556d copies it into her profile before every start,
  and the app's 主動 sliders write it here too.
- `build/` — one JSON per phase (intake, structure, thinking, voice, reactions, parts, verify), `check.md`, `verify.md`,
  the raw model replies under `build/raw/`, and `run.log` (the output of the last job 556d ran for this package).

The skill, from the app: 設定 → 角色 → 新角色 (0.8.1) — the same phases as a 556d job, proposals confirmed on the page,
install from the page. From the terminal:
```
python tools/soul_writer.py init <id> --display 名字 [--from-example] [--avatar hiyori/Hiyori.model3.json] [--pronoun 她|他]
python tools/soul_writer.py run <id> --phase all [--yes]        # or one phase at a time: --phase intake|…|verify
python tools/soul_writer.py run <id> --from structure --yes     # from a phase to the end (what 「仍然繼續」 does)
python tools/soul_writer.py run <id> --phase verify             # blind read-back of SOUL.md
python tools/soul_writer.py check <id> ; python tools/soul_writer.py status <id>
```
Every phase stops for review unless `--yes`; a part can be regenerated alone; `assemble` refuses to write a SOUL that
fails the checks (theory or machine words, digits outside 時間線, simplified characters, size 2,500–4,000, missing
sections) unless `--force`. The model is the 寫靈魂 connection of `home/models.json` (設定 → 全域 → 模型連線), or
`--base-url <…/v1> --model <name>` with the key in `X556_API_KEY`; `--timeout` is the per-call limit (900 s — the parts
phase can take minutes); 556d need not be running.

The simple path (0.8.10, `docs/prompt/prompt.md` §2.10): `python tools/soul_writer.py simple <id>` compiles `profile.json`
alone — the sliders, the choices and three boxes under `simple` (`who`, `talk`, `refuses`) — into the same files with
one zh-TW sentence per band, no model; the 產生 step's 簡單版 fold does the same. `closeness` (剛認識 … 很親近) becomes
her starting bond with you (`psyche.json` `relationships.你`); `scratch: true` adds the hidden think-first instruction
(§2.6). The fidelity probe: `python tools/fidelity_probe.py --gold tests/fidelity/<id>.json --soul <SOUL.md> …` scores a
SOUL text blind (recognition in a lineup, 像不像她會說, A/B takes) so two versions of the same character can be compared;
same model rule as the skill (the 寫靈魂 connection, or `--base-url`/`--model`; `--judge` for a different judge).

Install into a profile: `install-character.ps1 -Name <id>` (creates the profile with `new-companion.ps1` when missing,
then copies SOUL.md, companion.json, psyche.json, kokoro keys and people/*.md; restart her afterwards). Seed memories
with the embedder up and the character not running. A hand-written character (SOUL.md and the rest written directly,
no `describe/`) still installs the same way. Keep the word 製作人 and any agency framing out of these files unless that
is the world you want.

## The package is the character

`characters/<id>/` is the truth; `home/profiles/<id>/` is built from it. Before every start 556d copies SOUL.md,
psyche.json and people/*.md from the package into the profile (people/你.md only when the profile has none — the app
maintains it with your name and reply language), the app's 主動 sliders write the package's psyche.json as well, and
556d writes the model, memory and plugin settings from `home/models.json`. So a profile can be deleted and rebuilt, and
an edit made in the package wins at her next start. The dated, always-on part of who she is — `## 時間線`,
`## 影響過你的人與事` — is SOUL text (the skill writes it from the description); the same events are also seeds, for
retrieval.

**Backing a character up** = this package + three files from her profile: `memory/<id>.db` (what she remembers; the
daily snapshots under `backups/` are copies of it), `psyche.db` (how she feels, her loops, the ledger) and `state.db`
(the conversation). Everything else in the profile is rebuilt.
