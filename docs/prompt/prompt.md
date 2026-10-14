# The prompt — what she reads before she speaks

Last verified 2026-10-15 against Hermes `7166071f` (`agent/system_prompt.py`, `agent/prompt_builder.py`,
`gateway/platforms/api_server.py`), `plugins/kokoro`, `plugins/psyche`, `556d/internal/shim/textproto.go`
and 西's live `state.db`. Graph: `prompt.d2` (one request top to bottom, who writes each piece, how many
copies it costs).

This folder owns everything the model reads in one request and the design that reshapes it: the SOUL and
its parts, what Hermes and the shim put around the SOUL, the history, the last message with its blocks,
the clock, the pinned groups, the thinking dials. The SOUL is its first and largest subject, but the
folder is named for the whole: the vendor filter, the clock line, the wrapper language and the request
order are not the SOUL, and nobody would look for them under "soul". §1 is what runs today (0.7.8),
verified; §2 is decided and not built; §3 is the order to build it in. Decisions are logged in
`../DECISIONS.md` (2026-10-14 and 2026-10-15, tag `[prompt]`).

## 1. One request today

One request = the system prompt, then the history, then one last user message. Her process (one Hermes
per character, `../structure/structure.md` §3) builds it the same way for the app, Telegram, voice, a
【事件】 cue and a relay turn from another character. Per platform only two things differ: the platform
hint (§1.2, block 9) and the toolset, which `platform_toolsets` sets to `memory` everywhere, so she always
carries exactly two tools, `kokoro_search` and `kokoro_forget`.

| Piece | Copies per request | Written by | Changes when |
| --- | --- | --- | --- |
| system prompt (§1.2) | 1, cached prefix | author (SOUL), kokoro (static block), Hermes (everything else), shim (tools) | her restart; a context compression (`Today's date` line appears) |
| history (§1.3) | every row in the window, 20+ | as sent at the time, blocks included | every turn (one more row) |
| last user message (§1.4) | 1 | you / 556d (text), kokoro (memory), psyche (state) | every turn |

The base prompt was measured at about 2.5k tokens on 0.5.0 (`TEST-LIST`, "minimal = 2 tools"). That figure
was read as the cost of the two tools. It is the cost of the whole scaffold below, most of which is not hers.

### 1.2 The system prompt, block by block

`build_system_prompt_parts` assembles three cache tiers, stable → context → volatile, from the same inputs
on every request, so the bytes are identical until her restart or a compression. For 西 (platform
`api_server`, model `auto/556`, two tools, Hermes's own memory store off, local backend) the order is:

| # | Block | Text, in short | Chars | Fits her? | Switch |
| --- | --- | --- | --- | --- | --- |
| 1 | **SOUL.md** | her identity, first; today four sections: 你的背景, 你的性格, 誰在跟你說話, 說話的方式 | 2,871 (西) | ours | the author |
| 2 | Help guidance | "You run on Hermes Agent (by Nous Research). When the user needs help with Hermes itself… the documentation at https://hermes-agent.nousresearch.com/docs is the authoritative reference… Point the user there" | 466 | no — names her as a product right after her SOUL | none |
| 3 | Finishing the job | "When the user asks you to build, run, or verify something, the deliverable is a working artifact backed by real tool output… NEVER substitute plausible-looking fabricated output" | 769 | no — assistant posture | `agent.task_completion_guidance: false` |
| 4 | Parallel tool calls | "request them together in a single response… batch independent reads, searches, web fetches" | 618 | pointless for two memory tools | `agent.parallel_tool_call_guidance: false` |
| 5 | Mid-turn user steering | "Mid-turn, the user can steer you: Hermes appends their message to the end of a tool result, wrapped exactly as…" | 724 | irrelevant | none while tools are loaded |
| 6 | Environment hints | "Host: Windows (11)", "User home directory: C:\Users\…", "Current working directory: …", a note on hostnames, and a long paragraph on the Windows shell (bash, MSYS paths, PTY) | ~1,600 | no — the machine and your home path | none for a local backend |
| 7 | Environment probe | one line: "Python toolchain: python3=missing, python=3.11.16, pip→python3.14, uv=installed." | ~90 | no | `agent.environment_probe: false` |
| 8 | Active profile line | "Active Hermes profile: xi. This session reads and writes …/profiles/xi/. The default profile's data lives at …/skills/, …/plugins/, …/cron/… Do NOT modify another profile's…" | ~350 | no — paths and internals | none |
| 9 | Platform hint | api_server: "You're responding through an API server. The rendering layer is unknown — assume plain text. No markdown… Keep responses brief and natural. File/media delivery: images referenced as MEDIA:/absolute/path tags…"; telegram has its own | 712 / 617 | half — plain text yes, MEDIA noise | `platform_hints.<platform>: {replace: "…"}` in config.yaml |
| 10 | Voice system message | context tier, voice turns only: 556d sends the hands-free 說話風格 text as the request's `system_message`; Hermes injects it for that call and never caches it | — | ours | 設定 → 語音 |
| 11 | kokoro static block | volatile tier, ours: the memory rule paragraph (English: "Memory about the user is injected per turn as a 'Memory' block… trust labels… Use kokoro_search for anything not in the block"), then "About <her term for you> (profile maintained in the app; a per-turn note says who is talking to you right now):" + `people/你.md` | ~800 + 393 | fits, but English and talks about the app | `kokoro.json` `system_prompt_block`; the header is one line in the plugin |
| 12 | Timestamp and trailer | "Conversation started: Monday, October 13, 2026 (…zone…)"; after a rebuild also "Today's date (as of the last context rebuild): …"; then "Model: auto/556", "Provider: custom", "Platform: api_server" | ~200 | the date yes; the trailer no | none (Session ID only with `pass_session_id`) |
| 13 | Tools, by the shim | not Hermes: on a lane without native tool calling, 556d's shim appends to the system message its own preamble — "You are a function calling AI model. You are provided with function signatures within <tools>… output EXACTLY… <tool_call>… IMPORTANT: you have NO native/internal function-calling channel in this session…" — followed by the two schemas | 1,086 + schemas | ours; opens with "You are a function calling AI model" | `556d/internal/shim/textproto.go` (byte-identical to the Python shim's `TOOLS_PROMPT`, parity-tested) |

Not in her prompt, verified: the coding posture and workspace snapshot (`api_server` is not an interactive
coding platform); the skills index (no skills tools); tool-use enforcement, Google and execution guidance
(gated on the model name, and `auto/556` matches none of their lists); the Alibaba identity; Hermes's
built-in memory and USER.md blocks (that store is off); project context files (no AGENTS.md or
`.hermes.md` in her cwd or home); the Bot Mode protocol.

**Time.** She has no clock. The one line is the conversation's start date, and `Today's date` appears only
after a compression; for the hour Hermes expects the model to run `date` in a terminal she does not have.
Her session is endless (西's opened 2026-10-13 22:35 and is still the same session), so she knows the date
approximately and the hour never — except a proactive cue's 現在是…, the MM/DD stamp on short notes, and
the 在做 line, which is the engine's clock leaking through.

**Verdict.** She opens with her SOUL and is then told, in English, that she runs on a Nous Research product
with a docs URL, must ship working artifacts, which Windows machine and user home she runs on, where her
profile folders are, which model, provider and platform she is, and that she is a function calling AI
model. The SOUL says 不解釋自己是程式、模型或系統, and the output checks (說破, 助理腔) flag exactly these
leaks on the way out. It has held because the model mostly ignores the scaffold. Blocks 3, 4, 7 and 9 have
a switch today; 2, 6, 8 and 12 have none, and vendor is never edited — the one place we own that sees every
request is the shim (§2.8). The block-by-block decision — keep, switch off, replace or drop, with what she
loses in each case and what the two tools have actually done — is `around-the-soul.md`.

### 1.3 History

Every row in the window is replayed exactly as it was sent. Hermes keeps two columns per message:
`content`, the typed text the app shows, and `api_content`, the bytes the model actually received; replay
substitutes `api_content`. So each past user row still carries the memory block and the state block that
were glued onto it that turn. 西's live session, last 40 user rows: 29 carry `<memory-context>`, 31 carry
`<her-state>`; the newest is 1,147 chars, of which 9 were typed, 685 memory, 422 state. With
`compression.protect_last_n: 20` a request carries at least twenty such rows, so **a line injected per
turn is paid twenty-plus times per request; a line in the system prompt once, and cached.** That is the
cost rule everything in §2 follows. Assistant rows are stored as replied; closed `<think>…</think>` pairs
are stripped before storage (`strip_think_blocks`; zero stored replies contain one).

### 1.4 The last user message

Three pieces glued with blank lines, in this order (content → memory → plugin context, confirmed in the
stored bytes):

1. **The text.** What you typed; or the narrator cue (`【事件】…`, `psyche/events.py`), which is why a failed
   cue turn is discarded (`../app/app.md` 0.7.4); or another character's message, late ones prefixed
   「（M/D HH:MM 留的話）」 (`../inner-life/inner-life.md` §18).
2. **`<memory-context>`** — wrapper by Hermes's memory manager, text by kokoro. "[System note: The following
   is recalled memory context, NOT new user input. …]", then "Facts (long-term):" top 5 with trust labels and
   tags, "Notes (recent, dated):" top 5, "[archived: … — contents withheld; offer to discuss]" for consented
   topics; 你 rendered as her term for you. When another character is talking: "現在跟你說話的是<name>，不是
   <your term>。About <name> (person file):" + `people/<name>.md`. Absent on trivial prompts
   (`is_trivial_prompt`). `../memory/memory.md`.
3. **`<her-state>`** — psyche's `pre_llm_call`. "[System note: 【她現在】 is the character's own current inner
   state, produced by the state engine — NOT user input. Let it colour tone and choices as the 表現 line
   says; never quote it, never mention it or any numbers.]", then 【她現在】 with at most `max_lines` (8)
   lines: 在做, 心情, 心裡, 表現, 對他 / 對<name>, 掛念, 轉變, 原則 — words, never numbers
   (`../inner-life/inner-life.md` §15).

Then she writes. The reply passes `transform_llm_output` (output checks, record only) and the shim's
`<tool_call>` parser, and lands in the app, Telegram or the voice path.

### 1.5 What the docs said before this folder

`DECISIONS` 2026-10-02 named a "prompt layer" of settings-driven text around the SOUL and promised a design
pass; 2026-10-06 cut Hermes's 20 default tools to two; `STACK` says client system prompts are not sent;
`inner-life` §2 names the shim as a possible injection point. None inventoried the vendor text around the
SOUL, so no fix was ever routed. This doc is that design pass; the 2026-10-02 entry now points here.

## 2. The design (decided 2026-10-14 / 15, not built)

### 2.1 Rules

- The engine is the single writer of feelings. The LLM reads state, never writes it.
- Numbers never reach the model: `psyche.json` holds numbers, the state block renders words, the SOUL is words.
- Per-turn injection is paid 20+ times per request; the state block stays at eight lines of state.
- The SOUL is human-owned. Nothing in the pipeline rewrites it without a person approving; trait growth, if
  it ever comes, goes through a correction path with approval.
- All character text is zh-TW with 台灣 particles, and nothing she reads names a product, a machine, a model
  or the app.
- Vendor is never edited: changes land in `config.yaml` switches, the plugins, 556d and the shim.
- Parameter discipline: every new constant ships with a simulator scenario and a visible consequence (a
  rendered line or a changed strategy). If nothing observable changes, it is not added.

### 2.2 Three homes by cost

| Home | Copies | What goes there | Budget |
| --- | --- | --- | --- |
| tier 1 — system prompt | 1, cached; rebuilt at her restart or a compression | the SOUL; beside it the **pinned groups** (§2.4) rendered into kokoro's static block; the memory rule in zh-TW; the date | SOUL 2,500–4,000 chars, pinned about 1,000 |
| tier 2 — per turn, tiny | 1 per turn, ×20+ in history | the state block with the **clock line** (§2.7), and the optional 想法 line (§2.5) | eight lines of state |
| tier 3 — per turn, only when it hits | 0 or 1 per turn | similarity recall top 5 + 5 as today, plus **keyword triggers** for names and places (子睿's history fires when 子睿 is mentioned) — the lorebook tier `memory.md` reserved | as today |

The decision rule, SOUL vs memory: **does it have to shape every reply, even when nobody brings it up?**
Yes → SOUL (a disposition). No, topic-bound, dated, or could become untrue → memory. Memory can retrieve
a fact by topic but never a habit of speaking. The awkward middle — always present but slowly changing
(current stances, where she stands with each person) — is tier 1 via pinned tags, not a new self file.
"Too heavy for the SOUL" stops being a reason to push things into memory; the only question is whether a
line must act on every turn.

### 2.3 The six-part SOUL

| Part | Holds | Home |
| --- | --- | --- |
| 1 | background as prose; formative events as the traits they left behind, no dates | SOUL.md |
| 2 | likes, dislikes, interests, pet peeves | SOUL.md |
| 3 | thinking and deciding: 3–5 ways she judges things, 5–8 decision rules, values in order, what she refuses (the promise mechanism reads this: a loop opens only if she agreed, and whether she agrees is the SOUL's business), 2–3 unresolved tensions, and the new section 我怎麼聽、怎麼想、怎麼回 (§2.5) | SOUL.md |
| 4 | speaking habit: expression DNA per character — sentence length and rhythm, 口頭禪 and particles (欸 啦 吼), punctuation and emoji, one long message or three short, how she opens and closes, what short-and-annoyed looks like on her, what she types when she does not want to answer; words she never uses | SOUL.md |
| 5 | situational reactions: what angry, sad, jealous, teased, flattered and making-up look like on her; a fallback table (outside her written world, he is down, he asks for assistant work, he flirts, he is rude — the engine decides the strategy, the SOUL says what it looks like on her); five sample lines 她會這樣說 and five 不會這樣說 | SOUL.md |
| 6 | shared history per person = seeds and person files, dated | the store (`seeds.jsonl` gets an `at` field passed as `ts`, with the absolute date also in the text) and `people/<name>.md` |

Today all three SOULs share a word-for-word identical 說話的方式 block; what separates 子睿 from 子晴 is a few
adjectives. Ten stances per character (opinions she would argue about, some you disagree with) so a reader
can predict her take on a new topic. Vagueness audit: 有主見 is not operational, 被放鴿子會記住，雖然嘴上說沒關係
is. Validation: a fidelity probe in `tests/` — a blind judge guesses which character wrote a reply, ten
"would she say this" lines, ten novel topics scored against her stance list; one SOUL change at a time, keep
it only if the score holds.

### 2.4 Pinned groups

A group is a tag: every long memory carries 1–3 lowercase English slugs the observe LLM chooses each turn
(it sees the existing tags with counts and is told to reuse); no taxonomy exists; tags sit in an indexed
join table; `search` accepts tag filters but nothing per turn uses them. Pinning is: a short list of reserved
tag names in `kokoro.json`, named with their meaning in the observe prompt (or the LLM writes `history`
where you meant `timeline`); kokoro's static block renders every active row of those tags, capped about
eight lines per tag, newest first, next to the memory rule and `people/你.md`. Names: timeline (absolute
dates), influences, stances, refusals, where she stands with each person. Current focus stays in the life
sim (`psyche.json` projects; the block already says 在做). Who writes them: seeds and your hand — the observe
prompt stores facts about the user only; a self track in the pipeline is a separate decision. A row written
mid-session shows after the next rebuild; Hermes has `invalidate_system_prompt`, so a seed change can force it.

### 2.5 The thinking dials

Six stable, replicated dimensions of how people think (the 2026-10-14 brief; references to be verified
before they enter `inner-life.md` Appendix D). Meters, never booleans; two of them are two independent
scores. Thinking control is a new, separate module: it reads emotion state, energy, fatigue, arousal,
hurt and closeness and never writes any of it; its meters never change an emotion's intensity or half-life.

| Dial | zh-TW | Home | Numbers in `psyche.json` `thinking` | Engine reads it | Exists today |
| --- | --- | --- | --- | --- | --- |
| 1 medium of thought | 思考媒介 | SOUL, multiple choice | none | no | nothing |
| 2 deliberation | 深思預算 | SOUL + meters | `rationality`, `experientiality` (independent) | reply-shape hint (length), the Telegram delay; split messages do not exist | the hint uses energy, fatigue, arousal only |
| 3 orientation | 調節焦點 | SOUL + meters | `promotion`, `prevention`, defaults from E and N | expression strategy weights only — not the impact gains, which stay with E and N | gains already `0.7 + 0.6E` / `0.7 + 0.6N` |
| 4 interpretation | 解讀偏向 | SOUL prose + one rendered line | none | already: attachment anxiety and avoidance, self-esteem stability, the hurt ledger | covered; the block never says 容易往壞處想 |
| 5 aftermath | 事後處理 | SOUL + one meter | `maximizing`; reflection prose only (no consumer) | caps dial 2's budget; raises the chance of a clarifying question | rumination is hard-coded `0.6 × intensity × N × idle attention`, ≤ 3 revisits — it becomes an authorable knob on the emotion side, not a thinking meter |
| 6 context weighting | 情境權重 | SOUL, multiple choice | none | no (the 原因 factor could later soften anger via the appraisal's responsibility field — noted, not planned) | nothing |

Every number has a Big Five default so a blank block still works. **Words only, in two layers:** trait text
written once by the author into 我怎麼聽、怎麼想、怎麼回, and a state line 想法： rendered by the engine only
when this turn differs from her trait (a meter read against the moment crosses a threshold; below it the
line is absent and the SOUL sentence stands). The moment is what is known before her reply, because
prefetch never waits for the appraisal: energy, fatigue, arousal, the hurt gate for this counterpart, bond,
and whether the message touches an open loop (a string match). Dial 4's line comes from the emotion side.
One block, two writers; the separation is in the engine, not the layout.

| Meter | Trait text in the SOUL (西) | 想法 line, only when it differs |
| --- | --- | --- |
| rationality | 我通常先回再想，講完才發現不對 | 想法：這件事不小，她會想一下再回 |
| experientiality | 沒把握的時候我憑感覺，不太會先問 | 想法：今天沒力氣猜，直接問他 |
| promotion | 唱歌的事我先看能變成什麼 | 想法：這題她先看會不會出錯 |
| prevention | 跟人有關的事我先看會不會出錯 | 想法：心情好，先看能變成什麼 |
| maximizing | 差不多就好，我不會一直找更好的答案 | 想法：她會問清楚再答，不想隨便 |
| dial 4 (no meter) | 看不清楚的時候我會往「他沒那麼在意我」想 | 想法：今天特別容易往壞處想 |

**Dials 1 and 6 are multiple choice**, because prose-only gets forgotten and the instruments are profiles,
not axes. The rule that makes it safe: **the label never reaches the model.** The config holds the choice,
`install-character.ps1` compiles it into two or three lines of behaviour in her voice (written once by us
per option), and that text is what enters the SOUL — a named theory becomes a performance, the output checks
flag theory words, and the dial 6 terms carry cultural baggage the behaviour does not.

Dial 1, 思考媒介: a primary and up to one secondary.

| Choice | What the compiled text makes her do |
| --- | --- |
| 內在語言，對話式 | hesitates in sentences, rehearses what she would say to someone, quotes her own inner back-and-forth: 「我剛才還在跟自己吵要不要說」 |
| 內在語言，壓縮式 | thinks in fragments and keywords, replies short and sure, rarely narrates the thinking |
| 畫面 | explains by scenes and comparisons, remembers places and faces first: 「我腦中就是那個畫面」 |
| 感覺與身體 | knows before she can say why, reports the feeling first and the reason later: 「就是有一種怪怪的感覺」 |
| 聲音與節奏 | notices tone and rhythm before words, describes moods as sounds (西's primary) |
| 無聲的想法 | knows what she thinks without words or pictures; answers plainly and struggles to explain how she got there |

Dial 6, 情境權重: three separate choices, matching the instrument's factors.

| Factor | Choices | What the compiled text makes her do |
| --- | --- | --- |
| 第一眼看什麼 | 事情本身 / 誰跟誰 / 現場的氣氛 | the order she answers in: the literal ask first, the person's state first, or the situation first |
| 遇到矛盾 | 兩邊都留著 / 選一邊 | 「兩邊都有道理」 and holds both, versus picks one and says so |
| 事情的原因 | 先看人 / 先看處境 | blames the person or the circumstances when something goes wrong |

Examples agreed: 西 — sound and felt sense first, verbalizes late; replies on feel, checks after;
promotion in music, prevention with people; ruminates, satisfices; context first (who, what mood, then the
ask); reads ambiguity as 他沒那麼在意我. 子晴 — dialogic inner speech; both deliberation scores moderate;
promotion high; reflects, satisfices; relationship first; reads ambiguity as nothing. 子睿 — pictures and
condensed inner speech; thinks before replying, stops at good enough; prevention high; moderate maximizer
on code only; focal first; withholds judgement (資訊不足).

**Authoring and validation.** The author answers the instruments as the character — REI, RFQ and the
Maximization short form for the meters, the IRQ and the Analysis–Holism scale for the choices — and the
scores go into `psyche.json`, the prose into the SOUL. Then the model answers the same instruments blind,
as the character, with the full stack at a quiet state (state block on, no active instances, or mood leaks
into trait answers), and the answers must land on the authored scores and choices. The instruments need
zh-TW versions. This is sharper than a style-recognition eval and complements the fidelity probe of §2.3.

### 2.6 Dials 1 and 6 as a process: the hidden scratch (proposed, four checks before it is decided)

A transformer has no state between tokens except the tokens: every token is produced by attending over the
whole context, and its only thinking is the text it has already written. Attention is not flat — the start
and the end of the context pull hardest, the middle least — so the SOUL at the top and the state block at
the bottom already sit in the two strong positions. Only two levers change the computation: what is in the
context, and the order of the tokens she generates; everything else changes wording. If she writes nothing
before the answer there is no medium and no order at all.

So dials 1 and 6 become a process, not a style, through a short hidden scratch — two or three lines inside
`<think>…</think>` before the visible reply. Dial 1 sets its medium (an inner-speech character writes
sentences to herself; a condensed thinker fragments; an imagery character a scene; a felt-sense character
the feeling first and no reason — 西: 「聽起來他有點累。有種被敷衍的感覺？先別問。」 子睿: 「問的是週末有沒有空。有。」).
Dial 6 sets its order (person first, the ask first, or the room first; whether a contradiction is kept or
resolved). Hermes strips closed think pairs at the storage boundary, so the scratch costs output tokens on
that turn only and never enters history, the app, Telegram, the memory observe or any later request. An
"image" in the scratch is text describing an image; the paradox stays and does not matter — the goal is
the effect on the reply that follows. The representation is two things per choice: the compiled trait text
and a one-line scratch instruction (medium and order).

To settle before it goes in: (1) the scratch must be short and must never leak — the scrubber also handles
an unterminated tag at a block boundary, verify end to end on the streamed path; (2) the output checks must
run on the visible text only, verify; (3) the scratch is not stored, so the fidelity eval needs a debug log
to see it; (4) the shim's `<tool_call>` parser must ignore the think block, verify.

### 2.7 The clock and dates

One new line at the top of the state block, from the engine's own clock: 現在：2026/10/14（二）22:40. The
block is already per turn and already in the user message, so it costs nothing in prefix cache and reaches
every path (app, Telegram, voice, cue, relay — all run the same hook). With it: pin `HERMES_TIMEZONE=Asia/Taipei`
in her spawn env so Hermes and `psyche.json`'s `timezone_offset_h` agree; make dates in the SOUL absolute or
absent (半年前四個人一起吃火鍋 drifts once she can see the clock); seeds carry `at` (§2.3 part 6).

### 2.8 The vendor-text filter and the wrappers

Target system prompt: the SOUL, the pinned groups, the memory rule in zh-TW, the date, the two tools —
and nothing that names a product, a machine, a model or the app. Means, in order of cost:

1. `config.yaml`: `agent.task_completion_guidance: false`, `agent.parallel_tool_call_guidance: false`,
   `agent.environment_probe: false`; `platform_hints.api_server` and `platform_hints.telegram` with a
   `replace` text in zh-TW (plain text, brief, no MEDIA paragraph).
2. The shim (`556d/internal/shim`), which sees every request on every platform: drop the paragraphs that
   have no switch — help guidance, environment hints, the active profile line, the model / provider /
   platform trailer — by exact text, so the prefix stays byte-stable per session; reword its own
   function-calling preamble (ours) so it does not open with "You are a function calling AI model".
3. The wrappers in zh-TW, naming nothing: kokoro's memory rule (`system_prompt_block`) and its "About …"
   header, the two system notes inside `<memory-context>` (Hermes's, so it is rewritten in the shim or
   accepted) and `<her-state>` (ours).

Open: exact-text match versus anchors in the filter; whether the memory manager's system note is worth
touching in the shim or left as is; and whether she keeps any tool at baseline (`around-the-soul.md` §2:
never called in 79 turns, eight calls to a tool that does not exist).

## 3. The order to build it in

1. **Prompt hygiene** — §2.8 items 1–3, the clock line and timezone (§2.7), absolute dates and seed `at`.
   Small, no new behaviour, and every later eval runs on a clean prompt.
2. **The SOUL rewrite** — §2.3 for 西 as the pilot: six parts, expression DNA, sample lines, ten stances,
   the fallback table, the vagueness audit; the fidelity probe in `tests/`; then 子晴 and 子睿.
3. **Pinned groups** — §2.4: reserved tags in `kokoro.json`, the observe prompt names them, the static block
   renders them; seeds for timeline and influences.
4. **The thinking module** — §2.5: the `thinking` block with five meters and the two choice sets, the compile
   step in `install-character.ps1`, the 想法 renderer, rumination as a knob, the questionnaire authoring and
   the blind validation.
5. **The hidden scratch** — §2.6, after its four checks pass.
6. **Keyword triggers** — tier 3 (§2.2), when a store has enough named things to need them.

Beside this, in the inner life and in this order by cost (checked 2026-10-14 against the engine; they
belong to `inner-life.md` when built): rendering the disclosure depth per counterpart and letting the 表現
line cap what she opens up about (the number exists and nothing reads it); trust variance from the Beta pair
weighting 玩笑/反話 (uncertainty → indirectness); pleasure weighting 直說 and the length hint (good mood =
more direct, less polite — absent today, nothing points the wrong way); a withheld-things register shaped
like `share_backlog` feeding rumination and the proactive urge (the most valuable of the five; the
appraisal reads her own reply for what she sidestepped, the precedent being the 2026-10-14 promise rule);
a reading-care scalar in the theory of mind (closer and tired = less careful), rendered only at extremes.
Items 2–4 touch the same strategy selector as dial 3 and come after step 4.
