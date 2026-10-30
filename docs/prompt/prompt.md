# The prompt — what she reads before she speaks

Last verified 2026-10-19 (0.10.0) against Hermes `7166071f` (`agent/system_prompt.py`, `agent/memory_manager.py`),
`556d/internal/api/hygiene.go`, `connections.go`, `package.go`, `characters.go`, `556d/internal/shim/shim.go`,
`hygiene.go`, `textproto.go` and `testdata/`, `556d/internal/models/models.go`, `556d/internal/companions/manager.go`,
`plugins/kokoro/__init__.py`, `plugins/psyche/__init__.py`, `engine.py` (`state_block`), `thinking.py`, `config.py`,
`tools/soul_writer.py`, `tools/fidelity_probe.py`, `tests/fidelity/*.json`, `new-companion.ps1`,
`install-character.ps1`, `characters/*/SOUL.md`; `CHANGELOG.md` 0.8.0–0.9.0 and Unreleased; `../DECISIONS.md`
2026-10-16 and 2026-10-19. Graphs: `prompt.d2` (one request top to bottom, who writes each piece, how many copies it
costs) and `character-files.d2` (her files: what the author writes, what the skill makes, what 556d copies before a
start, where each lands in one request).

This folder owns everything the model reads in one request and the design that reshaped it: the SOUL and
its parts, what Hermes and the shim put around the SOUL, the history, the last message with its blocks,
the clock, the thinking dials. The SOUL is its first and largest subject, but the
folder is named for the whole: the vendor filter, the clock line, the wrapper language and the request
order are not the SOUL, and nobody would look for them under "soul". §1 is what runs today (0.10.0),
verified; §2 is the design as decided on 2026-10-14 / 15 and 2026-10-16, each section headed with what of it is
built; §3 is the order it was built in, with what remains. Decisions are logged in
`../DECISIONS.md` (2026-10-14 through 2026-10-19, tag `[prompt]`).

## 1. One request today

One request = the system prompt, then the history, then one last user message. Her process (one Hermes
per character, `../structure/structure.md` §3) builds it the same way for the app, Telegram, voice, a
【事件】 cue and a relay turn from another character. Per platform only the platform hint differs (§1.2,
block 9: one zh-TW line each for `api_server`, `telegram` and `discord`). She carries **no tools at baseline**
(option C, 0.8.6): 556d writes an empty `platform_toolsets` list per platform and removes the old `memory` entry
before every start, so the two kokoro tools, the tools preamble and the three tool-only guidance blocks are
absent; an extension (查網路 = `web`) brings the tools scaffold back for that character only.

| Piece | Copies per request | Written by | Changes when |
| --- | --- | --- | --- |
| system prompt (§1.2) | 1, cached prefix | the author or the soul skill (SOUL), kokoro (zh-TW section), Hermes (the platform line; the rest of its text is dropped by the shim), the shim (tools preamble, only when an extension adds tools) | her restart; a context compression (Hermes rebuilds the volatile tier; the shim drops the date paragraph either way) |
| history (§1.3) | every row in the window, 20+ | as sent at the time, blocks included | every turn (one more row) |
| last user message (§1.4) | 1 | you / 556d (text), kokoro (memory, By name), psyche (clock, state, 想法) | every turn |

As found on 2026-10-15, the base prompt measured about 2.5k tokens on 0.5.0 (`TEST-LIST`, "minimal = 2 tools"). That
figure had been read as the cost of the two tools; it was the cost of the whole vendor scaffold, most of which was
not hers. That scaffold no longer reaches the model (block by block below).

### 1.2 The system prompt, block by block

`build_system_prompt_parts` assembles three cache tiers, stable → context → volatile, from the same inputs
on every request, so the bytes are identical until her restart or a compression. The shim
(`556d/internal/shim/hygiene.go`) then filters every system message before the request leaves, on every
platform; the filter is deterministic, so the prefix the provider caches stays byte-stable per session. For a
character at baseline (platform `api_server`, model `auto/556`, no tools, Hermes's own memory store off) Hermes
writes the blocks below in this order, and this is what each one is today:

| # | Block | Today (0.10.0) | Mechanism |
| --- | --- | --- | --- |
| 1 | **SOUL.md** | her identity, first. The cast's hand-written SOULs (the main character's: 2,871 bytes, 1,029 characters, four sections 你的背景, 你的性格, 誰在跟你說話, 說話的方式 — unchanged since 10-15); a skill-written SOUL carries the six parts with `## 時間線` and `## 影響過你的人與事` inside (§2.4). 556d copies it from `characters/<id>/` before every start | the author or `tools/soul_writer.py`; `556d/internal/api/package.go` |
| 2 | Help guidance | dropped by the shim (paragraph prefix `You run on Hermes Agent (by Nous Research).`) | shim |
| 3 | Finishing the job | off (`agent.task_completion_guidance: false`); Hermes adds it only with tools anyway; the shim drops it by prefix as well (`# Finishing the job`) | config + shim |
| 4 | Parallel tool calls | off (`agent.parallel_tool_call_guidance: false`); tools only; prefix `# Parallel tool calls` | config + shim |
| 5 | Mid-turn user steering | tools only; dropped by prefix `## Mid-turn user steering` | shim |
| 6 | Environment hints | dropped by prefix (`Host: `, `Shell: on this Windows host`, `You are running inside WSL`) | shim |
| 7 | Environment probe | off (`agent.environment_probe: false`); prefix `Python toolchain:` | config + shim |
| 8 | Active profile line | dropped by prefix `Active Hermes profile: ` | shim |
| 9 | Platform hint | replaced by one zh-TW line per platform — `api_server`: 你在聊天視窗裡說話：純文字，不用 markdown（沒有星號、條列、標題、程式碼框）。像在傳訊息，簡短自然。 — `telegram` / `discord`: 你在 Telegram（Discord）上說話：純文字就好，不用 markdown，不用標題或表格。像在傳訊息，簡短自然。 | `platform_hints.<platform>.replace` in `config.yaml`, written by `556d/internal/api/hygiene.go` before every start |
| 10 | Voice system message | context tier, voice turns only: the hands-free 說話風格 text as the request's `system_message`, injected for that call and never cached (as documented on 10-15; the 556d side was not re-verified on 10-19) | 設定 → 語音 |
| 11 | kokoro's section | volatile tier, after the memory tier, zh-TW. The memory rule: 記憶：每一回合會附上一段「Memory」。「Facts (long-term)」是你記得的事（標 [high] 的很確定，沒標的很可能對）；「Notes (recent, dated)」是近期的紀錄，一行一件、帶日期。對不上的時候：對話本身最準；其次是最新的一條，不分種類；事實和紀錄平手時事實優先。「[archived: …]」是對方不想被提起的話題——絕不說出內容，只有對方自己碰到時才問一句要不要聊。「By name」是因為對方提到了某個名字而翻出來的那個人的事。記憶裡沒有的事就是不知道，不編、不猜。 — then 關於<her term for you>（每一回合另有一行說現在是誰在跟你說話）： + `people/你.md` (first 2,000 chars). A plugin prompt section (`kokoro.memory`, position `after_memory`, frozen per session; re-read at the first turn after a restart since 0.11.0, §2.8 item 4), tied to no toolset. KeepsakeDB's block titles stay English on purpose: they are the library's, explained here in zh-TW. Nothing dated lives here any more — the 0.8.7 pinned groups were folded into the SOUL (§2.4) | `plugins/kokoro/__init__.py` `prompt_section`; `kokoro.json` `system_prompt_block` overrides the rule text |
| 12 | Date paragraph | dropped whole by the shim since 0.8.5 — `Conversation started:`, `Today's date`, `Timezone: `, `Session ID: ` and the `Model:` / `Provider:` / `Platform:` trailer (its weekday was wrong on the first live check). The clock is per turn, in the state block (§1.4, §2.7) | shim |
| 13 | Tools preamble, by the shim | absent at baseline (no tools, nothing appended). When an extension adds tools, the shim appends its own reworded preamble to the system message — "Tools are available in this conversation. Their signatures are listed within <tools> </tools> XML tags. Use a tool only when the request needs it; otherwise just answer in natural language. …" — followed by the schemas; it names no product and does not call her a function calling model. A text `<tool_call>` to the proxy's own reply function (`openmini_reply`, `…:openmini_reply`) is unwrapped into reply text, never forwarded | `556d/internal/shim/textproto.go` (`toolsPrompt`); the request and reply shapes are pinned by the golden files in `556d/internal/shim/testdata/` — the Go shim is the only shim |

So at baseline she reads three things in the system prompt: her SOUL, one zh-TW platform line, kokoro's zh-TW
section. The shim logs what it dropped whenever the set changes (`[shim] system prompt: dropped N vendor
paragraph(s): help,steer,host,…`), logs the tool names it is offered whenever that set changes, and warns once if a
Hermes prompt arrives without the help paragraph (the vendor text changed shape — the first thing to look at after
a Hermes bump). `X556_SHIM_DUMP=<file>` writes her system message as received, before the filter, for the next
audit. The config half (blocks 3, 4, 7, 9 and the empty toolsets) reaches new sessions only — a resumed session
keeps the prompt pieces and the tool list it was born with (found on the test character, 0.8.5) — so the shim half is what
protects the cast's endless sessions.

Not in her prompt, verified on 2026-10-15 and unchanged at the pinned Hermes commit: the coding posture and
workspace snapshot (`api_server` is not an interactive coding platform); the skills index (no skills tools);
tool-use enforcement, Google and execution guidance (gated on the model name, and `auto/556` matches none of
their lists — keep the lane name opaque); the Alibaba identity; Hermes's built-in memory and USER.md blocks
(`memory.memory_enabled` and `memory.user_profile_enabled` are written false before every start); project context
files (no AGENTS.md or `.hermes.md` in her cwd or home); the Bot Mode protocol.

**Time.** She has a clock (0.8.4): the first line under the state block's title, 現在：2026/10/19（一）22:40, from
the engine's own zone — `psyche.json` `time.timezone_offset_h`, which 556d writes from the connections' timezone
(`home/models.json`, 設定 → 全域 → 模型連線) before every start; the same zone goes to every gateway as
`HERMES_TIMEZONE`. Nothing has a default: a character does not start until the zone is set. Hermes's own date
paragraph is dropped whole (block 12). Her session is still endless (one session per character, never rotated),
and she now knows the date, the weekday and the hour on every turn; a proactive cue's 現在是…, the MM/DD stamp on
short notes and the 在做 line come from the same clock.

**As found on 2026-10-15 (history, for the record).** Before 0.8.4 the same prompt carried, after her SOUL and in
English: help guidance naming her as a Nous Research product with a docs URL (466 chars), finishing-the-job and
parallel-tool-call guidance (769, 618), the mid-turn steering note (724), the Windows host, your home path, her
cwd and a Windows-shell paragraph (~1,600), the Python toolchain probe (~90), the profile-paths line (~350), the
`api_server` / `telegram` hints with their MEDIA paragraphs (712 / 617), kokoro's memory rule in English (~800)
under an "About …" header that mentioned the app, the start date with the Model / Provider / Platform trailer
(~200), and the shim's preamble opening with "You are a function calling AI model" (1,086 + two schemas) — about
5,500 chars of vendor text plus 1,700 of tools text around 2,871 bytes of SOUL, where the SOUL says
不解釋自己是程式、模型或系統 and the output checks (說破, 助理腔) flag exactly these leaks on the way out. Blocks 3,
4, 7 and 9 had a switch; 2, 5, 6, 8 and 12 had none, and vendor is never edited — hence the shim filter. The
block-by-block decision (keep, switch off, replace or drop, with what she loses in each case and what the two
tools had actually done) is `around-the-soul.md`; what was built from it is 0.8.4–0.8.6 (`CHANGELOG.md`).

### 1.3 History

Every row in the window is replayed exactly as it was sent. Hermes keeps two columns per message:
`content`, the typed text the app shows, and `api_content`, the bytes the model actually received; replay
substitutes `api_content`. So each past user row still carries the memory block and the state block that
were glued onto it that turn — today including the clock line, the 想法 line and the By name rows. Measured on
2026-10-15 in the main character's live session (not re-measured on 10-19), last 40 user rows: 29 carried `<memory-context>`, 31
carried `<her-state>`; the newest was 1,147 chars, of which 9 were typed, 685 memory, 422 state. With
`compression.protect_last_n: 20` a request carries at least twenty such rows, so **a line injected per
turn is paid twenty-plus times per request; a line in the system prompt once, and cached.** That is the
cost rule everything in §2 follows. Assistant rows are stored as replied: the shim strips her hidden scratch
before Hermes sees the text (0.8.10, §2.6), and Hermes strips closed `<think>…</think>` pairs before storage as a
second net (`strip_think_blocks`), so no stored reply contains one.

### 1.4 The last user message

Three pieces glued with blank lines, in this order (content → memory → plugin context, confirmed in the
stored bytes on 10-15; the hook order is unchanged):

1. **The text.** What you typed; or the narrator cue (`【事件】…`, `psyche/events.py`), which is why a failed
   cue turn is discarded (`../app/app.md` 0.7.4); or another character's message, late ones prefixed
   「（M/D HH:MM 留的話）」 (`../inner-life/inner-life.md`, the multi-agent section).
2. **`<memory-context>`** — wrapper by Hermes's memory manager, text by kokoro. "[System note: The following
   is recalled memory context, NOT new user input. …]" (Hermes's, in English, kept as is — decided 2026-10-19),
   then "Facts (long-term):" top 5 with trust labels and tags, "Notes (recent, dated):" top 5, "[archived: … —
   contents withheld; offer to discuss]" for consented topics; 你 rendered as her term for you. When another
   character is talking: "現在跟你說話的是<name>，不是<your term>。About <name> (person file):" + `people/<name>.md`.
   Then, since 0.8.10, **`By name:`** — tier 3 (§2.2): when the message contains a roster character's name, a
   person file's name or your name, kokoro runs an exact BM25 lookup for it (`trigger_k` rows per name, default
   3; at most 2 × `trigger_k` lines in all; archived, superseded and held rows skipped; minus what similarity
   already brought); `triggers: false` in `kokoro.json` turns it off. The whole block is absent on trivial prompts
   (`is_trivial_prompt`). `../memory/memory.md`.
3. **`<her-state>`** — psyche's `pre_llm_call`. The note, zh-TW since 0.8.4: [旁白：下面的【她現在】是她此刻的狀態，
   不是對方說的話。讓它影響語氣和選擇（照「表現」那一行）；不要引用它，不要提到它或任何數字。] — then 【她現在】, then the
   clock line 現在：2026/10/19（一）22:40, then the state lines in this order: 在做, 心情, 心裡, 表現, 想法, 對他 /
   對<name>, 掛念, 轉變, 原則 — of which 心裡, 想法, 對他, 掛念 and 轉變 appear only when there is something to say.
   The title and the clock are extra; `max_lines` (8, `psyche.json` `expression`) counts the state lines, and on
   overflow the engine drops 轉變 first, then 心裡, then 想法, then 掛念; 原則 always stays (fixed in the work after
   0.9.0: the old slice counted the title, so a full block lost 轉變 and 原則). Words, never numbers
   (`../inner-life/inner-life.md`: the expression layer section; the thinking module section for 想法; the five
   mechanisms section for the depth cap in 表現 and 有件事還沒跟他說 under 掛念).

Then she writes. The raw reply reaches the shim first: the hidden scratch (`<think>…</think>`, §2.6) is stripped
and logged, the `<tool_call>` parser runs on the visible text, a call to the proxy's own reply function is
unwrapped into text; then Hermes's `transform_llm_output` (output checks, record only), and the reply lands in
the app, Telegram or the voice path.

### 1.5 What the docs said before this folder

`DECISIONS` 2026-10-02 named a "prompt layer" of settings-driven text around the SOUL and promised a design
pass; 2026-10-06 cut Hermes's 20 default tools to two; `STACK` says client system prompts are not sent;
`inner-life` §2 names the shim as a possible injection point. None inventoried the vendor text around the
SOUL, so no fix was ever routed. This doc is that design pass; the 2026-10-02 entry now points here.

## 2. The design (decided 2026-10-14 / 15 and 2026-10-16; what is built is marked per section)

### 2.1 Rules

- The engine is the single writer of feelings. The LLM reads state, never writes it.
- Numbers never reach the model: `psyche.json` holds numbers, the state block renders words, the SOUL is words.
- Per-turn injection is paid 20+ times per request; the state block stays at eight lines of state (plus the clock line).
- The SOUL is human-owned. Nothing in the pipeline rewrites it without a person approving; trait growth, if
  it ever comes, goes through a correction path with approval.
- All character text is zh-TW with 台灣 particles, and nothing she reads names a product, a machine, a model
  or the app.
- Vendor is never edited: changes land in `config.yaml` switches, the plugins, 556d and the shim.
- Parameter discipline: every new constant ships with a simulator scenario and a visible consequence (a
  rendered line or a changed strategy). If nothing observable changes, it is not added.

### 2.2 Three homes by cost (built: tier 1 0.8.4 and the SOUL sections after 0.9.0; tier 2 0.8.4 / 0.8.8; tier 3 0.8.10, names only)

| Home | Copies | What goes there | Today (0.10.0) |
| --- | --- | --- | --- |
| tier 1 — system prompt | 1, cached; rebuilt at her restart or a compression | the SOUL — with its 時間線 and 影響過你的人與事, the dated, always-on part of who she is (§2.4); kokoro's section: the memory rule in zh-TW and 關於你 | built. No date line any more: the start date went with Hermes's date paragraph (0.8.5), the clock is tier 2. Budget: SOUL 2,500–4,000 chars of prose, the two dated sections not counted |
| tier 2 — per turn, tiny | 1 per turn, ×20+ in history | the state block with the **clock line** (§2.7) and the optional 想法 line (§2.5) | built; eight lines of state, the title and the clock extra (§1.4) |
| tier 3 — per turn, only when it hits | 0 or 1 per turn | similarity recall top 5 + 5 as before, plus **keyword triggers** | built 0.8.10 for names only — the roster, the person files, your name (`By name`, §1.4); places are not triggers until a store has enough named places to need them (DECISIONS 2026-10-19). The lorebook row in `memory.md` is this and nothing more |

The decision rule, SOUL vs memory: **does it have to shape every reply, even when nobody brings it up?**
Yes → SOUL (a disposition). No, topic-bound, dated, or could become untrue → memory. Memory can retrieve
a fact by topic but never a habit of speaking. The awkward middle — always present but slowly changing
(current stances, where she stands with each person) — is SOUL text as well — stances in 怎麼判斷、怎麼決定, where she stands with each person is the engine's 對他 line — not a self file and not memory rows.
"Too heavy for the SOUL" stops being a reason to push things into memory; the only question is whether a
line must act on every turn.

### 2.3 The six-part SOUL (the skill writes it since 0.8.0; the fidelity probe built 0.8.10)

| Part | Holds | Home |
| --- | --- | --- |
| 1 | background as prose; formative events as the traits they left behind; the dated events themselves in `## 時間線`, the people and things in `## 影響過你的人與事` (§2.4) | SOUL.md |
| 2 | likes, dislikes, interests, pet peeves | SOUL.md |
| 3 | thinking and deciding: 3–5 ways she judges things, 5–8 decision rules, values in order, what she refuses (the promise mechanism reads this: a loop opens only if she agreed, and whether she agrees is the SOUL's business), 2–3 unresolved tensions, and the section 我怎麼聽、怎麼想、怎麼回 (§2.5; written as `## 怎麼聽、怎麼想、怎麼回` and `## 怎麼判斷、怎麼決定`) | SOUL.md |
| 4 | speaking habit: expression DNA per character — sentence length and rhythm, 口頭禪 and particles (欸 啦 吼), punctuation and emoji, one long message or three short, how she opens and closes, what short-and-annoyed looks like on her, what she types when she does not want to answer; words she never uses | SOUL.md |
| 5 | situational reactions: what angry, sad, jealous, teased, flattered and making-up look like on her; a fallback table (outside her written world, he is down, he asks for assistant work, he flirts, he is rude — the engine decides the strategy, the SOUL says what it looks like on her); five sample lines 她會這樣說 and five 不會這樣說 | SOUL.md |
| 6 | shared history per person = seeds and person files, dated | the store (`seeds.jsonl` with an `at` field, stored at that date by `tools/seed-memories.py`) and `people/<name>.md` |

As found on 2026-10-15 and still true on 10-19 (the cast is untouched, the three 說話的方式 sections hash the same):
all three hand-written SOULs share a word-for-word identical 說話的方式 block; what separates the second character from the third is a few
adjectives. Ten stances per character (opinions she would argue about, some you disagree with) so a reader
can predict her take on a new topic. Vagueness audit: 有主見 is not operational, 被放鴿子會記住，雖然嘴上說沒關係
is. Validation — **built 0.8.10 as `tools/fidelity_probe.py`** with the gold `tests/fidelity/<id>.json` (written for the main character): eight
prompts the SOUL answers as her and a blind judge picks her out of the three-SOUL lineup (recognition), ten lines
she would say and ten she would not, answered 是／否 (voice), ten novel topics with her take and its opposite,
answered A / B (takes); on the text alone, a quiet state block and no engine, through the 寫靈魂 connection
(`--base-url` / `--model`, else `home/models.json`, key in `X556_API_KEY`); the scoring is tested in
`tests/test_fidelity_probe.py`. One SOUL change at a time, keep it only if the score holds. First run 2026-10-19:
the main character's hand-written SOUL and her skill-made candidate both scored 0.96 — a tie at the ceiling, so the gold must get harder
(§3 item 6).

### 2.4 The dated part of who she is lives in the SOUL (pinned groups retired, 2026-10-19)

What must frame every reply and never changes by itself — her timeline with absolute dates, the people and things
that shaped her, her stances and refusals, who the people around her are — is SOUL text: `## 時間線` (one dated
line per event, oldest first) and `## 影響過你的人與事` written by the skill from the description (code, not a
model; absent when the description gives none), stances and refusals in `## 怎麼判斷、怎麼決定`, the people in
`## 誰在跟你說話` and the person files. The same events and influences also go to the store as dated seeds, for
retrieval when a topic touches them. Dates may appear only in 時間線 (the digit check and the 2,500–4,000 prose
budget leave it out). Where she stands with each person *now* is the engine's 對他 line, not text.

The 0.8.7 mechanism — five reserved tags (`timeline`, `influences`, `stances`, `refusals`, `standing`) whose store
rows kokoro rendered into its prompt section as 一直記著的 — is gone: it was the 10-14 "always-on but slowly
changing" slot, and once the user decided this content does not grow through conversation, a tagged memory row was
only a SOUL line with extra rules (who may tag, what the observe LLM reuses). The store keeps "what she knows";
the package keeps "who she is". And the package is the character: before every start 556d copies SOUL.md,
psyche.json and people/*.md from `characters/<id>/` into her profile (people/你.md only when the profile has
none, Settings maintains it), the app's 主動 sliders write the package's psyche.json too, so a profile can be
rebuilt from nothing and a backup is the package plus `memory/<id>.db`, `psyche.db` and `state.db`.

### 2.5 The thinking dials (built 0.8.8: `plugins/psyche/thinking.py` — five meters with Big Five defaults, the 想法 line, reading care, rumination as a knob; the choices are recorded, not read)

Six stable, replicated dimensions of how people think (the 2026-10-14 brief; references to be verified
before they enter `inner-life.md` Appendix D). Meters, never booleans; two of them are two independent
scores. Thinking control is a separate module: it reads energy, fatigue, arousal, pleasure, attachment anxiety,
the hurt gate for this counterpart, bond and whether a hurt is open, and never writes any of it; its meters never
change an emotion's intensity or half-life.

| Dial | zh-TW | Home | Numbers in `psyche.json` `thinking` | Engine reads it | Today (0.10.0) |
| --- | --- | --- | --- | --- | --- |
| 1 medium of thought | 思考媒介 | SOUL text; the choice recorded | none (`thinking_choices.medium_primary`, `medium_secondary`) | no — `thinking.choices()` exists and nothing calls it | the skill writes the text from the description (§2.9), the simple path one sentence per choice (§2.10); the label also drives the scratch instruction (§2.6) |
| 2 deliberation | 深思預算 | SOUL + meters | `rationality` (default: conscientiousness), `experientiality` (0.5) | the 想法 rules "stakes" and "no energy"; `rationality` inside reading care | built as the line; the length hint and the Telegram delay still use energy, fatigue and arousal, not the meters; split messages do not exist |
| 3 orientation | 調節焦點 | SOUL + meters | `promotion` (default: extraversion), `prevention` (default: neuroticism) | the 想法 rules "mood flips the framing" only | the design's expression strategy weights are **not built** — nothing in `relation.py` or `engine.py` reads these two; the impact gains stay `0.7 + 0.6E` / `0.7 + 0.6N` |
| 4 interpretation | 解讀偏向 | SOUL prose + one rendered line | none | the first 想法 rule, from the emotion side (attachment anxiety with an open hurt or a low mood) | built: 今天特別容易往壞處想 |
| 5 aftermath | 事後處理 | SOUL + one meter | `maximizing` (0.5) | the last 想法 rule | built as the clarifying question; "caps dial 2's budget" is **not built**. Rumination is `character.rumination` (blank = neuroticism), an emotion-side knob with its 主動 slider 想不開的程度 |
| 6 context weighting | 情境權重 | SOUL text; the choices recorded | none (`thinking_choices.first_look`, `contradiction`, `cause`) | no | text by the skill or the simple path; `first_look` and `contradiction` drive the scratch instruction |

Every number has a Big Five default so a blank block still works. **Words only, in two layers:** trait text
written once into 怎麼聽、怎麼想、怎麼回 (by the author, the skill or the simple path), and a state line 想法：
rendered by the engine after 表現 only when this turn differs from her trait (a meter read against the moment
crosses a threshold; below it the line is absent and the SOUL sentence stands). The moment is what is known
before her reply, because prefetch never waits for the appraisal: energy, fatigue, arousal, the mood's pleasure,
attachment anxiety, the hurt gate for this counterpart, bond, and whether a hurt is open on the ledger. Dial 4's
line comes from the emotion side. One block, two writers; the separation is in the engine, not the layout.

The 2026-10-14 examples (design: a trait sentence in the SOUL against the line that would differ from it; the sentences are generic examples, not a real character's):

| Meter | Trait text in the SOUL (example) | 想法 line, only when it differs |
| --- | --- | --- |
| rationality | 我通常先回再想，講完才發現不對 | 想法：這件事不小，她會想一下再回 |
| experientiality | 沒把握的時候我憑感覺，不太會先問 | 想法：今天沒力氣猜，直接問他 |
| promotion | 做事我先看能變成什麼 | 想法：這題她先看會不會出錯 |
| prevention | 我先看會不會出錯，再想要不要做 | 想法：心情好，先看能變成什麼 |
| maximizing | 差不多就好，我不會一直找更好的答案 | 想法：她會問清楚再答，不想隨便 |
| dial 4 (no meter) | 看不清楚的時候我會往「他沒那麼在意我」想 | 想法：今天特別容易往壞處想 |

What `thinking.py` renders today — the first rule that fires, at most one line (tired = energy < 0.35 or fatigue >
0.6; stakes = the hurt gate ≥ 0.15; care = 0.5 + 0.3·rationality − 0.3·bond − 0.3·fatigue + 0.3·stakes):

| Rule | Fires when | Line |
| --- | --- | --- |
| dial 4, interpretation | anxiety ≥ 0.6 and (an open hurt or pleasure < −0.3) | 想法：今天特別容易往壞處想 |
| stakes | stakes and rationality ≤ 0.45 | 想法：這件事不小，會想一下再回 |
| no energy | tired and rationality ≥ 0.6 | 想法：今天沒力氣想，會先回再想 |
| no energy | tired and experientiality ≥ 0.6 and anxiety < 0.6 | 想法：今天沒力氣猜，直接問對方 |
| dial 3, mood lifts the framing | prevention ≥ 0.6 and pleasure > 0.4 | 想法：心情好，先看能變成什麼 |
| dial 3, mood drops it | promotion ≥ 0.6 and (pleasure < −0.3 or anxiety ≥ 0.6) | 想法：這題先看會不會出錯 |
| reading care, low | care < 0.25 (closer and tired = less careful) | 想法：懶得猜對方的意思，直接當對方懂 |
| reading care, high | care > 0.85 | 想法：會多想一下對方是什麼意思 |
| dial 5, the maximizer | maximizing ≥ 0.6 and energy ≥ 0.5 and arousal ≥ 0.6 | 想法：會問清楚再答，不想隨便 |

**Dials 1 and 6 are recorded choices**, because prose-only gets forgotten and the instruments are profiles,
not axes. The rule that makes it safe holds: **the label never reaches the model.** `profile.json` holds the
choice, `psyche.json` `thinking_choices` records it, nothing at runtime reads it; the text that enters the SOUL is
written by the skill from the description (§2.9) or, on the simple path, one sentence per option from `CHOICE_TEXT`
in `tools/soul_writer.py` (§2.10) — a named theory becomes a performance, the output checks flag theory words, and
the dial 6 terms carry cultural baggage the behaviour does not.

Dial 1, 思考媒介: a primary and up to one secondary (the design's option descriptions; the simple path's
one-sentence versions are in §2.10).

| Choice | What the text makes her do |
| --- | --- |
| 內在語言，對話式 | hesitates in sentences, rehearses what she would say to someone, quotes her own inner back-and-forth: 「我剛才還在跟自己吵要不要說」 |
| 內在語言，壓縮式 | thinks in fragments and keywords, replies short and sure, rarely narrates the thinking |
| 畫面 | explains by scenes and comparisons, remembers places and faces first: 「我腦中就是那個畫面」 |
| 感覺與身體 | knows before she can say why, reports the feeling first and the reason later: 「就是有一種怪怪的感覺」 |
| 聲音與節奏 | notices tone and rhythm before words, describes moods as sounds |
| 無聲的想法 | knows what she thinks without words or pictures; answers plainly and struggles to explain how she got there |

Dial 6, 情境權重: three separate choices, matching the instrument's factors.

| Factor | Choices | What the text makes her do |
| --- | --- | --- |
| 第一眼看什麼 | 事情本身 / 誰跟誰 / 現場的氣氛 | the order she answers in: the literal ask first, the person's state first, or the situation first |
| 遇到矛盾 | 兩邊都留著 / 選一邊 | 「兩邊都有道理」 and holds both, versus picks one and says so |
| 事情的原因 | 先看人 / 先看處境 | blames the person or the circumstances when something goes wrong |

An example of one agreed set (invented, not a real character): condensed inner speech with felt sense as the
secondary; both deliberation scores moderate; promotion a little above prevention; a mild maximizer; the ask first
(事情本身); picks a side when two things contradict; blames the circumstances.

**Authoring and validation.** As designed: the author answers the instruments as the character — REI, RFQ and
the Maximization short form for the meters, the IRQ and the Analysis–Holism scale for the choices — and the model
answers the same instruments blind, as the character, with the full stack at a quiet state, and the answers must
land on the authored scores and choices. What exists at 0.10.0: the skill's thinking phase proposes every meter
and choice with one line of evidence from the description and the person confirms (§2.9), and its verify phase is
a blind read-back — the model reads only the finished SOUL and names the dials, compared to the confirmed values.
**The blind questionnaire is not built**: there is no such test in `tests/`, and the instruments have no zh-TW
versions in the repo. The fidelity probe (§2.3) is the measurement that exists.

### 2.6 Dials 1 and 6 as a process: the hidden scratch (built 0.8.10, opt-in per character: `profile.json` `scratch`; the four checks answered below)

A transformer has no state between tokens except the tokens: every token is produced by attending over the
whole context, and its only thinking is the text it has already written. Attention is not flat — the start
and the end of the context pull hardest, the middle least — so the SOUL at the top and the state block at
the bottom already sit in the two strong positions. Only two levers change the computation: what is in the
context, and the order of the tokens she generates; everything else changes wording. If she writes nothing
before the answer there is no medium and no order at all.

So dials 1 and 6 become a process, not a style, through a short hidden scratch — two or three lines inside
`<think>…</think>` before the visible reply. Dial 1 sets its medium (an inner-speech character writes
sentences to herself; a condensed thinker fragments; an imagery character a scene; a felt-sense character
the feeling first and no reason — for example 「聽起來他有點累。有種被敷衍的感覺？先別問。」 for felt sense, 「問的是週末有沒有空。有。」 for a condensed thinker).
Dial 6 sets its order (person first, the ask first, or the room first; whether a contradiction is kept or
resolved). The scratch costs output tokens on that turn only and never enters history, the app, Telegram, the
memory observe or any later request. An "image" in the scratch is text describing an image; the paradox stays
and does not matter — the goal is the effect on the reply that follows. The representation is two things per
choice: the trait text and a one-line scratch instruction (medium and order).

The four checks as posed on 2026-10-15: (1) the scratch must be short and must never leak — the scrubber also
handles an unterminated tag at a block boundary, verify end to end on the streamed path; (2) the output checks
must run on the visible text only, verify; (3) the scratch is not stored, so the fidelity eval needs a debug log
to see it; (4) the shim's `<tool_call>` parser must ignore the think block, verify.

**Answered 2026-10-19 (0.8.10).** The shim is the one place that sees the raw model text, and it never streams
upstream (`stream` is forced off and the reply re-delivered), so the block is removed there — `stripThink` in
`556d/internal/shim/textproto.go`: closed pairs anywhere (`think`, `thinking`, `reasoning`, `thought`), and an open
tag at the start of a line with no close (the model ran out of tokens) to the end of the text — before the
tool-call parser runs and before Hermes stores, streams or checks anything. That settles (1), (2) and (4) at once:
Hermes, the hub, the app, Telegram, the memory observe, the appraisal and the output checks only ever receive the
visible text; Hermes's own scrubbers (`agent/think_scrubber.py`, `strip_think_blocks` with its
unterminated-at-line-start pattern) stay as a second net. (3): the shim logs the removed scratch, `[shim] lane=…
scratch: "…"`, cut at four hundred runes; nothing stores it. A `<tool_call>` written inside the scratch is not a
tool call (test in `hygiene_test.go`). `stripThink` runs on the shim's text-protocol path only; the native-tools
passthrough path filters the system prompt but does not strip — and it is unreachable today, because the chat
connection is built without a `native_tools` flag (`connections.go` `applyConnections`), so every backend goes
through the text protocol. The instruction itself is compiled by the skill from the dial 1 and 6 choices —
`scratch_line` in `tools/soul_writer.py`: one head sentence (回覆之前，先在 <think> 和 </think> 之間用兩三行寫下你腦子裡
先出現的東西，再寫要說的話…), one per medium, one per 第一眼, one per 矛盾 — into 怎麼聽、怎麼想、怎麼回, on both
paths, only when `profile.json` has `scratch: true` (the 確認 step's 回覆前先想 switch). Off by default: it costs
output tokens every turn, and the first measurement of what it buys is the probe (§2.3).

### 2.7 The clock and dates (built 0.8.4: the line and the timezone; 0.8.5: Hermes's date paragraph dropped; 0.9.0: the zone from the connections; the cast's relative dates are untouched)

One line at the top of the state block, from the engine's own clock: 現在：2026/10/19（一）22:40, the first line
under the title. The block is per turn and already in the user message, so it costs nothing in prefix cache and
reaches every path (app, Telegram, voice, cue, relay — all run the same hook). The zone: `home/models.json`
`timezone` (設定 → 全域 → 模型連線, no default) → `psyche.json` `time.timezone_offset_h`, written before every
start, and `HERMES_TIMEZONE` on every gateway, so the engine and Hermes agree; Hermes's own date paragraph is
dropped by the shim regardless (0.8.5, its weekday was wrong). Dates in a skill-written SOUL are absolute and
live only in 時間線 (§2.4); seeds carry `at` and `tools/seed-memories.py` stores them at that date (0.8.0). The
cast's hand-written SOULs keep their relative dates (a 「半年前…」 sentence drifts once she can see the clock)
until the skill rewrites them (§3 item 6).

### 2.8 The vendor-text filter and the wrappers (built 0.8.4–0.8.6; the tools decision taken 2026-10-19: none at baseline)

Target reached: the SOUL, one platform line, the memory rule and 關於你 in zh-TW — and nothing that names a
product, a machine, a model or the app. No date line (the clock is tier 2) and no tools at baseline. Means, in
order of cost, as built:

1. `config.yaml`, written by `556d/internal/api/hygiene.go` before every start (idempotent): the three switches
   off (`agent.task_completion_guidance`, `agent.parallel_tool_call_guidance`, `agent.environment_probe`);
   `platform_hints.api_server`, `.telegram` and `.discord` with a `replace` text in zh-TW (§1.2 block 9);
   `memory` removed from every `platform_toolsets` list (0.8.6; `new-companion.ps1` writes empty lists, and
   `connections.go` adds an empty list for a platform that has none, because without one Hermes falls back to its
   ~20 default tools).
2. The shim (`556d/internal/shim/hygiene.go`), which sees every request on every platform: drops the paragraphs
   that have no switch **by paragraph prefix**, not exact text — three of them carry machine-specific values
   (host, home, profile path) — help, finish, parallel, steer, host, shell, WSL, probe, profile, and the whole
   date paragraph (§1.2); deterministic, so the prefix stays byte-stable per session; a log line when the dropped
   set changes; one warning if a Hermes prompt has no help paragraph (the vendor text changed — the first thing to
   look at after a Hermes bump). Its own preamble reworded (`textproto.go`), and the `openmini_reply` unwrap.
3. The wrappers: kokoro's memory rule and the 關於 header in zh-TW as a plugin section (§1.2 block 11); psyche's
   note around 【她現在】 in zh-TW (§1.4). Hermes's note inside `<memory-context>` stays as the one English
   sentence she still reads — kept, decided 2026-10-19, not worth a second filter.
4. The stored prompt (0.11.0): Hermes continues a session with the system prompt it stored when the session opened
   (`agent/conversation_loop.py` — a continuing session reuses the exact bytes for the prefix cache; a null stored
   prompt is rebuilt that turn). The frozen plugin sections and the SOUL itself therefore change only for a new session
   — so before every start 556d drops the stored prompt of her live sessions (`Transcript.ForgetStoredPrompts`); Hermes
   logs `rebuilding from scratch this turn`, re-reads SOUL.md, the people files and the sections, and stores the new
   bytes. Same conversation, nothing copied, one prefix-cache miss per restart.

Settled (the 10-15 "open" items): prefix match over exact text; the memory-context note is kept; **option C** —
no tools at baseline — taken 2026-10-19 after the 0.8.5 test on the test character (`[]` → zero tools and a normal reply;
`[web]` → `web_search` / `web_extract` under the reworded preamble and a real search): in 79 turns the two kokoro
tools were never called and a tool that does not exist eight times (`around-the-soul.md` §0, §2). Memory is
injected, not a tool; an extension brings the scaffold back for that character only, and the preamble was
reworded for that case rather than deleted.

### 2.9 Authoring — the character package and the soul skill (decided 2026-10-16; built 0.8.0–0.8.3 as `tools/soul_writer.py`, the 新角色 page 0.8.1)

**Principle.** The LLM is used in exactly two places: once at authoring time, inside a skill a person reviews,
and once at runtime, to write her reply. Everything between — the files, the numbers, the state, the prompt
assembly — is deterministic code. Inputs are human-owned, outputs are generated, and nothing regenerates on
its own. The human-owned rule of §2.1 survives as: inputs human-owned, output generated. This replaces the
multiple-choice compile of §2.5 for dials 1 and 6 (the choices remain as recorded labels, see below) and the
band templates for the meters; the simple path (§2.10) keeps both as the backup.

**Not for the current cast.** The schema and the skill were tried on new, disposable characters first (an example
description in `templates/character/example`; then a test character, the first made on the page). The cast keeps its
files until a generated SOUL scores above them on the fidelity probe (§2.3); the main character's description was
written fresh from her existing files (0.8.10) and run through the skill, and her SOUL is replaced by the generated
one only as a diff, approved (still pending, §3 item 6).

**The character package** — `characters/<id>/`, two kinds of content (graph: `character-files.d2`):

| Kind | Files | Who writes | What |
| --- | --- | --- | --- |
| inputs, written | `describe/*.md` (ten files: 01-她是誰 … 10) | the person, in their own words, any shape | who she is; her background as a story; what happened to her, each event dated with what it left behind; how she talks; six short answers on how she thinks (§2.5's prompts); how she relates — anger, sadness, jealousy, being teased, being flattered, how she apologizes and makes up, what she refuses to do or promise; likes, dislikes, interests, pet peeves; stances she would argue about (ten is the target, some the user disagrees with); how she sees the user and each other character; optional: daily rhythm and current project, lines she actually said |
| inputs, confirmed | `profile.json` | the skill proposes, the person confirms or moves a slider | Big Five and the six constants; the five thinking meters, each with the skill's one line of evidence; the dial 1 and 6 choices; `closeness` (一開始多熟, 0.8.9); `scratch` (回覆前先想, 0.8.10); pronoun; schedule |
| outputs, generated and versioned | `SOUL.md`, `seeds.jsonl` (with `at`), `people/*.md`, `psyche.json` (Big Five, constants, cares_about, `thinking`, `thinking_choices`, the `relationships.你` prior — the app's 主動 sliders write it too), `build/` (one file per phase), `soul.lock.json` (input hashes + skill version) | the skill, then code | a regeneration is always explicit and shows a diff; the lock file says which inputs produced the current outputs and flags `stale` inputs |

**The soul skill** — `tools/soul_writer.py`, eight phases (`PHASES`: intake → structure → thinking → voice →
reactions → parts → assemble → verify), each writing into `build/` and stopping for review (nuwa's checkpoints in
companion form); a part can be regenerated alone (`--phase`, `--from`), so the whole SOUL is never one request:

1. **Intake.** Read `describe/`, list what is missing, print follow-up questions — especially for the voice
   and for part 5 (ex-skill's intake questions are the model: how she shows anger, how she apologizes, what she
   never says out loud). 「全部」 on the page runs the intake alone first and stops on a thin description.
2. **Structure.** Dated events (`at` only when the description gives a date) → the 時間線 lines, the seeds and the
   "what it left behind" sentences for part 1; influences → 影響過你的人與事; stances, refusals, tensions,
   cares_about; a vagueness audit — every line that cannot predict behaviour is flagged (有主見 fails,
   被放鴿子會記住，雖然嘴上說沒關係 passes).
3. **Thinking.** Proposed meters with one line of evidence each; proposed dial 1 and 6 choices; proposed Big Five
   and constants if blank. Into `profile.json` after confirmation (`--yes` accepts the
   proposals). The number never comes from the LLM alone.
4. **Voice.** Expression DNA, 口頭禪 and particles, words she never uses; the sample lines (五句會說、五句不會說)
   generated last, from the finished voice section.
5. **Reactions.** Part 5 from the intake answers: the engine decides when (strategy, timing, whether a topic is
   open); the SOUL says what it looks like on her.
6. **Parts.** The first three parts (background; likes and dislikes; 怎麼聽、怎麼想、怎麼回 and 怎麼判斷、怎麼決定)
   and the person files, from the description, the structure and the confirmed thinking habits in words.
7. **Assemble.** Code, not a model: the six-part SOUL in zh-TW with 時間線 and 影響過你的人與事 after part 1 and the
   scratch line when `scratch` is set; then the mechanical checks — no theory or machine words, no Arabic digits
   outside 時間線 and list numbering, no simplified characters (common slips repaired), the six sections present,
   size 2,500–4,000 characters not counting the dated sections; third-person drift is a warning; a failed check
   refuses to write.
8. **Verify.** The blind read-back: the model reads only the finished SOUL and names the dials, compared to the
   confirmed meters and choices — its own prompt, never the writer's (the writer must not grade itself). The
   fidelity probe (§2.3) is a separate tool. Fix the inputs, never the output, and rerun from the phase that
   changed.

**The non-meter dials under the skill.** Dials 1, 4 and 6 are no longer multiple choice with canned text: the
skill reads the description and writes those sections in her voice. The labels do not disappear — the skill
outputs its reading of each choice as a structured field, because two things still need a label: the scratch
instruction for dials 1 and 6 (§2.6) and the blind validation, which needs an intended answer to compare
against. Dials 2, 3 and 5 still need numbers because the engine reads them.

**What the person gives.** Written, any shape: the ten items of the inputs table. Confirmed, not written: the
proposals in `profile.json`, any flagged sentence rewritten or dropped, and the generated files approved as a
diff before install. Not needed at all: questionnaires, invented numbers, SOUL text, a seed file, dates copied
twice, labels, theory. A hand-written SOUL stays possible; it is then an input, and the skill's job is only to
check it.

**Install.** The page's 安裝 runs `install-character.ps1` (creates the profile when missing; copies SOUL.md,
companion.json, psyche.json and people/*.md) and then `tools/seed-memories.py` (loads `seeds.jsonl`, a seed's `at`
stored as its date; the embedder up, she is not running) as one job. It compiles nothing by LLM: `psyche.json` is
already written by the skill from `profile.json` (`build_psyche`), the scratch instruction by `assemble`. Since
the work after 0.9.0 the install's copy is only the first: 556d copies SOUL.md, psyche.json and people/*.md from
the package before every start (§2.4), so an edit in the package wins and the profile is rebuildable.

**Runtime.** Unchanged by authoring: the SOUL enters the system prompt (tier 1), the meters enter the engine,
the 想法 line is rendered by the engine. The skill never runs while she is live; the engine never writes a word
of the SOUL. The app page (設定 → 角色 → 新角色, 0.8.1) runs the same skill behind 556d as a job
(`POST /api/characters/<id>/run`, one job per package, its output in `build/run.log`, hub event `character.job`),
on the 寫靈魂 connection (`--model` and `--base-url` from `home/models.json`; the page shows the configured model
instead of a menu, 0.9.0), phase by phase or 「全部」, shows the proposals with their evidence for confirmation
(確認, with 一開始多熟 and 回覆前先想), and installs from the page; a package whose SOUL is hand-written (no lock
file) is marked 手寫 and never overwritten without `--force`.

### 2.10 The simple path (built 0.8.10: `soul_writer.py simple <id>`, `POST /api/characters/<id>/simple`, the 簡單版 fold on the 產生 step — sliders, choices, three boxes, no model)

The full path asks for ten written sections; some people will not write them. The backup is the deterministic
compile of §2.5 kept as a first-class route, so a character exists after five minutes in Settings:

- **Sliders and choices** in `profile.json`: the Big Five and the six constants, the five thinking meters
  (`thinking`), the dial 1 and 6 choices (`choices`), `scratch`.
- **Three short boxes**: `simple.who` (who she is), `simple.talk` (how she talks), `simple.refuses` (one refusal
  per line).
- **Compile, no LLM** (`build_simple` in `tools/soul_writer.py`): the who box verbatim as part 1; 喜歡與不喜歡
  「（還沒寫）」; 怎麼聽、怎麼想、怎麼回 = one sentence per meter from its band (`BAND_TEXT`: low below 0.4, high above
  0.6, else mid) + one sentence per choice (`CHOICE_TEXT`) + the scratch line when set; 怎麼判斷、怎麼決定 = the
  refusals as bullets; 說話的方式 = the talk box (or 用口語，像在傳訊息：通常一到三句。) + the fixed guardrail bullets;
  遇到事情的時候 = sentences from the constants' bands (`REACT_TEXT`: expressiveness low / high, humor_coping high,
  tsundere_tendency high, assertiveness low / high); 誰在跟你說話 = the fixed line. `seeds.jsonl` empty,
  `people/你.md` a default, `psyche.json` from the same `build_psyche`, `soul.lock.json` with model `simple`. The
  output files are the same as the full path's, so install and runtime do not care which path produced them.
- **What it costs**: flatter text (a band sentence, not her voice), no sample lines, no stances, no vagueness
  audit; the size check does not apply (the other checks are recorded in `build/check.md`) — the fidelity probe
  will score lower, and that is stated, not hidden.
- **The two paths compose.** The skill accepts sliders as confirmed input, so a person can start on the simple
  path and run the skill later on the same inputs plus a short description; the skill fills the rest and
  proposes nothing the person already set. A hand-written SOUL (no lock file) is never overwritten by either path
  without `--force`.

| Dial | Simple path control | Compiled text (`tools/soul_writer.py`) |
| --- | --- | --- |
| 1 思考媒介 | `choices.medium_primary`, one of six (`medium_secondary` is recorded, no sentence) | `CHOICE_TEXT`: 想事情的時候你腦子裡是句子，會跟自己來回講。／…是幾個關鍵字，不成句。／…是畫面。／你先有一種感覺，字是之後才來的。／你先聽到語氣和節奏。／你知道自己在想什麼，但沒有字也沒有畫面。 |
| 2 深思預算 | `thinking.rationality`, `thinking.experientiality` | `BAND_TEXT`, one sentence per band — rationality high 你想好才回，寧可慢一點也不要講錯。, low 你先回再想，回完才會覺得剛才講太快。 |
| 3 調節焦點 | `thinking.promotion`, `thinking.prevention` | `BAND_TEXT` — prevention high 你預設在防出錯，先看哪裡會壞。 |
| 4 解讀偏向 | nothing | nothing on the simple path; the engine's 想法 line covers the moment |
| 5 事後處理 | `thinking.maximizing`; rumination is the 主動 slider 想不開的程度 | `BAND_TEXT` — maximizing low 差不多就好，你不會一直找更好的。 |
| 6 情境權重 | `choices.first_look` (事情本身 / 誰跟誰 / 現場的氣氛), `contradiction`, `cause` | `CHOICE_TEXT`, one line each — 你第一眼看事情本身。, 遇到矛盾你兩邊都留著。, 出事的時候你先看處境。 |

## 3. The order it was built in

1. **Prompt hygiene** ✅ 0.8.4–0.8.6 — §2.8 items 1–3, the clock line and timezone (§2.7); the tools decision after
   the test on the test character: option C taken (0.8.6). Seed `at` came with the skill (0.8.0). Absolute dates: only in
   skill-written SOULs; the cast's relative dates stay until item 6. Small, no new behaviour, and every later eval
   ran on a clean prompt.
2. **Authoring groundwork** ✅ 0.8.0–0.8.3, 0.8.10 — the `describe/` template and `profile.json` schema, the
   skill's phase prompts and the 新角色 page (§2.9), the simple-path templates (§2.10); `install-character.ps1` +
   `seed-memories.py` as the page's install (psyche.json is the skill's output, seed dates from `at`); the
   fidelity probe (§2.3). Disposable characters were written through the skill and installed (the example description, one made on the page); the
   probe's gold exists for the main character only, so no test character has been scored against a gold of its own. **Not built:
   the blind questionnaire** (§2.5) — no such test exists in `tests/`, no zh-TW instruments in the repo.
3. **The dated part of who she is** — §2.4: ✅ in the SOUL (時間線, 影響過你的人與事, written by the skill;
   seeds still go to the store for retrieval); the 0.8.7 pinned tags were retired, and the package is the character.
4. **The thinking module** ✅ 0.8.8 — §2.5: the `thinking` block with five meters and the two recorded choices, the
   想法 renderer, rumination as a knob (`character.rumination`), dial 4's rendered line, and the reading-care scalar
   (2.2 below) inside it; `plugins/psyche/tests/test_thinking.py` (six tests; a simulator scenario per meter beyond
   these: not verified). The blind validation on the test character: not built (item 2).
5. **The five conversation mechanisms** ✅ built 0.8.9 (`inner-life.md`, the five mechanisms section;
   `relation.depth_now` / `depth_words`, `trust_uncertainty`, `strategy(pleasure=, uncertainty=)`, the engine's
   `withheld` register with the appraisal's `withheld` field and the `unsaid` occasion; the author's closeness bar
   → `relationships.你` — since 0.12.0 the skill proposes no band, and what you went through together is memory only). Fixed after 0.9.0: the register holds six per counterpart, not six in all, and an unsaid
   thing leaves it when the message really went out (`sent`), not when the urge fired. As planned (checked
   2026-10-14 against the engine), by cost: rendering the disclosure depth per counterpart and letting the 表現
   line cap what she opens up about (the number existed and nothing read it); trust variance from the Beta pair
   weighting 玩笑／反話 (uncertainty → indirectness); pleasure weighting 直說 and the length hint (good mood = more
   direct, less polite — absent before, nothing pointed the wrong way); a withheld-things register shaped like
   `share_backlog` feeding rumination and the proactive urge (the most valuable; the appraisal reads her own reply
   for what she sidestepped, the precedent being the 2026-10-14 promise rule); the reading-care scalar in the
   theory of mind (closer and tired = less careful), rendered only at extremes, folded into item 4. The first three
   touch the same strategy selector as dial 3 and came after item 4.
6. **The cast** — open: when a generated SOUL scores above the main character's on the probe, the main character
   through the skill from a fresh description, approved as a diff; then the other two. **0.8.10:** the probe exists
   (`tools/fidelity_probe.py`, gold in `tests/fidelity/<id>.json` for the main character, scoring test in
   `tests/test_fidelity_probe.py`) — recognition against the three-SOUL lineup, twenty 像不像她會說 lines, ten A/B
   takes, on the text alone (no engine, a quiet block). The main character's skill-made candidate: her description
   was drafted from her files and run through the skill (on gemini through the proxy at the time; since 0.9.0 the
   skill and the probe use the 寫靈魂 connection) — 4,041 chars, forced past the size check by forty-one; blind
   read-back 7/9; the probe scored both SOULs 0.96 (recognition 7/8 each, voice 20/20, takes 10/10 — a tie at the
   ceiling; the gold must get harder). The cast's files are untouched: the swap is the user's call on the diff.
7. **The hidden scratch** — §2.6 ✅ built 0.8.10, opt-in (`scratch` in profile.json), the four checks answered.
8. **Keyword triggers** — tier 3 (§2.2) ✅ built 0.8.10: kokoro's `_with_triggers` — a roster name, a person
   file's name or your name in the message fires an exact BM25 lookup (`trigger_k` rows, default three) under a
   `By name` title, minus what similarity already brought; `triggers: false` in kokoro.json turns it off.

**Still unbuilt at 0.10.0:** the blind questionnaire (§2.5, item 2); the cast swap (item 6) and with it the cast's
relative dates (§2.7); dial 3's expression strategy weights and dial 5's cap on dial 2's budget (§2.5); places as
triggers (§2.2); a harder probe gold (§2.3).

The 0.7.x manual checklist (one tick in fifty-five) is run on the clean prompt inside this cycle, not after
it: the mailbox, forgetting, the two kinds of promise and the relay all touch the paths these changes touch.
