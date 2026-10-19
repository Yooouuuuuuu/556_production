# Decisions log

One record for the whole project. Each heading carries its date and its part in brackets — [structure]
[memory] [app] [voice] [inner-life]. Versions live here: a redesign is a new entry that says what it
replaces; the designs themselves are in the part folders. Entries are grouped as they were written, not
strictly sorted.

## Decided (2026-10-07) — the inner life: kickoff decisions [inner-life]
Design: `inner-life/inner-life.md` (its §0 lists every decision applied).
- Evaluation A and memory observe are separate requests fired in parallel after the reply (1 + 2); prefetch never waits — results shape the next turn.
- The psyche engine lives inside her Hermes process as a Python plugin beside kokoro (single writer, event-sourced `psyche.db` in her profile); 556d stays the hub. Hermes cron is not used: the engine's own tick fires due loops and reminders and posts event turns through her API.
- Output checks record only, block nothing, at first.
- Versions: 0.5.0 = tools + the state-block milestone (her replies carry a state that matches the last day); 0.6.0 = proactive; 0.7.0 = three characters with full backgrounds for real tests. Full v2 docs ship inside 0.5.0.
- 製作人 → 你 (see v1 DECISIONS 2026-10-07): stored subject 你, rendered as her term for you.
- Time constants keep their research defaults and are overridable in Settings; long-term thresholds are discussed before 0.7.0.

## Built (2026-10-13) — inner life stages 5–6: relationships, hurt / repair, three characters [inner-life] [structure]
- The counterpart of a turn comes from the session key: her conversation with you (Telegram DM key or
  `556:app`), or `556:agent:<name>` for another character. Both plugins resolve it from `state.db`; neither talks
  to the other. Loops, instances, appraisals and relationship state carry the counterpart id, never the display
  name (rows from before 0.7.0 that hold the display term count as yours).
- kokoro keeps one store per character and one pipeline per counterpart: memories about another character are
  written with that character's name as the subject; the store's fixed subject word 你 stays for you.
- Inter-agent conversations run through 556d, not plugin to plugin: 556d knows every character's API port and key,
  owns session creation, enforces one conversation per pair at a time and the turn cap, and emits `relay.turn`.
  The initiator's message is its own event turn (so it is a row in its session with the other); the plugin posts
  it to `/api/relay`; 556d delivers it as a user turn in the other character's session and carries the reply back.
- Hurt is proportional to closeness ((0.5 + bond) in the ledger's opening formula) — a stranger's slight barely
  registers, a friend's lingers two to three days; an apology that owns the fault halves it, a false-belief
  correction leaves a fifth. Trend forgiveness slope ≈ 0.003/h from agreeableness and commitment (design: linear).
- Display rules mute what she shows by closeness (0.5 + 0.5·bond): with someone she has just met her feelings
  stay mostly inside, which is the design's 剛認識時是熱情，熟了才是撒嬌.
- Attachment strength grows at k_attachment × bond × responsiveness (≈ 0.25 after 90 days of an hour a day) — faster
  than the literature's two years so it is observable in tests; a knob in `relation`.
- Your feedback on a feeling adjusts that emotion type's gain by ±5 % (bounded 0.5–2×) through a replayable command;
  「不該是這種情緒」 is only logged.
- Character ids are folders, display names live in `companion.json` and the SOUL, so renaming is a copy and an edit.
- The cast is the user's own (2026-10-13) and lives in `characters/`, ignored by version control: a main conversation
  partner and a couple close to the user; no agency framing, no role word (製作人) in their files. Big Five numbers are
  percentile ÷ 100 (0.50 = an average adult), so inventory results map in directly and T-scores go through the
  normal curve.
- Who is talking must be in the message itself: with the speaker only in a memory-block note, a character still called
  the other one 「製作人」 (the SOUL and the history outweigh a note). The relay prefixes every delivered message with the speaker's
  display name, the block's first line names the counterpart, and the SOULs make the producer a role.

## Incident (2026-10-14) — the subject word is the store's, never a pipeline's [memory]
- A second pipeline on a store must never carry a subject of its own: KeepsakeDB's pipeline treated a differing
  configured subject as "the user renamed the word" and rewrote every memory. Rule now: the store owns the word; a
  rename is explicit (`migrate_subject=True`, only the main pipeline, only from Settings); counterpart pipelines speak
  about the other character through `pl.subject` alone. Repairs go through the API (snapshot / seeds / reviewed rules),
  never raw SQL, so history and embeddings stay right.

## Decided (2026-10-14) — the hurt ledger and memory [inner-life] [memory]
- The ledger keeps only hurts (TRIM); good things live in trust, warmth, bond and gratitude. No kindness ledger for now.
- An entry exists only above an opening threshold (`relation.hurt_open_min` 0.1) and is in the prompt the whole time
  it is open — no hidden interval. While it is open, what that turn left in memory is held (KeepsakeDB `hold`: kept,
  not shown, not hinted). Forgiven by time → released as `舊帳` with the date and a render prefix; closed by an apology
  or a correction → released plain. The appraisal sees open entries: a revisit without owning it raises the entry
  (`revisited_hurt`), an apology cuts the ledger. Tags remain an organising handle, never a search scope.

## Decided (2026-10-14) — the 狀態 page and loops [app] [inner-life]
- No light for the model lane: a character's status is online / offline / starting… / stopping… and nothing else; a
  failed turn shows in the chat as a system note. The feedback buttons on feelings (±5 % gain) are gone from the page.
- A loop ends with an outcome. Said = done (a reminder, her promise, a report; a report with nothing found is 沒成);
  settled in conversation = done; seven days = 沒成; forgot stays its own word. The page shows two groups (進行中 /
  已結束) with five words, finished items for seven days after the day they finished. One timeline by day replaces
  the event and appraisal lists; the date and clock format are the person's choice (設定 → 全域 → 程式).
- The same thing said again refreshes the one loop (the appraisal reports `loops.refresh`; the engine merges
  near-duplicates by text similarity or cue time). Vague promises like 「晚點再說」 are legitimate loops.
- 記性: `character.memory_reliability` 0–1, default 0.8 and on for every character; P(remember) = 記性 + 0.3 if
  important − 0.3 × how much worse than usual her mood is.

## Decided (2026-10-14) — mailbox, forgetting, undelivered [inner-life]
- Characters message each other through a mailbox: a message for a character who is not running waits in
  `home/mailbox/<id>.json` and is delivered when she starts, continuing the conversation (late delivery carries the
  time it was left; 7-day TTL; 20 per pair). Asking another character is therefore "send once, wait up to 48 h".
- A due item the platform could not deliver is not used up: it backs off (5/15/60 min, then hourly) and after 6 h is
  marked 忘了 — in the character's world there is no "backend down", she forgot. Forgetting is also a character
  parameter: 記性 `character.memory_reliability` (0–1, default 0.8 for every character, `forgets` on by default):
  P(remember) = 記性 + 0.3 for an important item − 0.3 × how much worse than usual her mood is; decided at the due
  moment with the seeded rng. The
  state page shows 忘了 at once (transparency over surprise).

## Decided (2026-10-14) — two kinds of promise [inner-life]
- A promise opens a loop only when she actually agreed in her reply (the appraisal reports `agreed`); whether she
  agrees is her SOUL and the relationship state she sees, not a numeric affection gate.
- A promise that concerns only her and the other person (a wake-up call, 「等我一下」) is forced through every gate at
  its time, like a reminder you asked for. The 00:54 case showed the other kind: a promise that needs another
  character (「幫你問子睿」) is carried to that character at her free time through the relay, answered by that
  conversation's appraisal, and reported back only when she is up, outside your no-disturb hours and when your
  presence model says you are around. No answer → retry at the next free slot, give up after `ask_retry_max`.
- The narrator cue behind a proactive turn is never the user's words: 556d tags it, the app hides it by default and
  can show it as a note (設定 → 全域 → 程式).

## Built (2026-10-19) — the thinking module, first pass [inner-life] [prompt]
- `plugins/psyche/thinking.py`, separate from the emotion engine: reads energy, fatigue, arousal, pleasure, anxiety,
  the hurt gate and closeness, writes nothing. Five meters in `psyche.json` `thinking` with Big Five defaults for
  blanks (promotion ≈ E, prevention ≈ N, rationality ≈ C, the rest 0.5); the two choice sets are recorded only.
- One optional 想法 line after 表現, first rule that fires: interpretation bias (dial 4, from the emotion side),
  stakes, no energy, mood lifting or dropping the default framing, reading care at the extremes (mechanism 2.2 lives
  here), the maximizer's clarifying question. Thresholds are design values, to be tuned by the simulator scenarios.
- Rumination became `character.rumination` (blank = neuroticism), an emotion-side knob, not a thinking meter.
- 設定 → 角色 → 主動 gains the five sliders and 想不開的程度; applied at her next start like the personality sliders.
- Not here: the hidden scratch (§2.6), keyword triggers, the blind questionnaire.

## Decided (2026-10-19) — no tools at baseline; the avatar parked [prompt] [structure] [app]
- Option C from `prompt/around-the-soul.md` §2, after the 真音 test: every character's `platform_toolsets` lists are empty
  at baseline (556d removes `memory` from them before a start; `new-companion.ps1` writes empty lists). Memory is
  injected every turn by kokoro's prompt section and the Memory block and is not a tool; the two kokoro tools were
  never called in 79 turns, and without tools the three tool-only guidance blocks and the shim's preamble never appear.
  An extension (查網路) brings the scaffold back for that character only; the preamble was reworded for that case.
- The avatar window is hidden by default. Nothing about the avatar is designed or touched until the core
  (`prompt.md` §3) is done.

## Built (2026-10-16) — prompt hygiene, first pass [prompt] [structure]
- The vendor text has two kinds of removal and both run every time: the switches Hermes offers are written into her
  `config.yaml` before every start (idempotent), and the paragraphs with no switch are dropped by the shim by their
  shape — a paragraph that starts with a known first line — rather than by exact text, because three of them carry
  machine-specific values (host, home, profile path). The shim logs what it dropped whenever the set changes and
  warns once if a Hermes prompt arrives without the help paragraph (a Hermes bump changed the text).
- The shim's preamble was ours to reword; the protocol it parses is unchanged, so the golden files were regenerated
  from the Go code and reviewed (only the preamble differs). A text `<tool_call>` to the proxy's own reply function is
  reply text, never a tool call: unwrapped, logged.
- kokoro's memory rule and 關於你 moved from the provider's system-prompt block (gated on the memory toolset) to a
  plugin prompt section, in zh-TW, so they survive if the tools go. KeepsakeDB's block titles (`Memory`, `Facts
  (long-term)`, `Notes (recent, dated)`) stay English: they are the pinned library's, explained in zh-TW.
- The clock is the first line under 【她現在】, from the engine's own zone; the block's cap counts state lines, the
  clock is extra. `HERMES_TIMEZONE` comes from `556d.toml` (default Asia/Taipei) so Hermes's date line agrees.
- Live check on a second daemon (new binary, spare ports, 真音): a resumed session keeps the tool list and the
  prompt pieces it was born with — 真音's 2026-10-03 session still offered seventeen tools and the switched-off
  guidance; on a fresh session the config switches took and `[memory]` gave exactly the two kokoro tools. So the
  config half applies to new sessions, and the shim half is what protects the cast's endless sessions. Hermes's
  own date line came out wrong (Monday for 2026-10-13, a Tuesday), so the whole date paragraph is dropped now
  rather than after a week; the clock line carries date, weekday and time.
- The 真音 tools test passed: with `platform_toolsets: []` she answers with zero tools and no preamble; with
  `[web]` she gets `web_search` / `web_extract` under the reworded preamble and really searches. Option C is
  viable; switching the baseline is the user's call.
- Not done here: the tools-at-baseline switch itself, Hermes's memory-context note (kept), the cast's relative
  dates (the cast is untouched until the skill rewrites it).

## Decided (2026-10-16) — authoring: the soul skill, a test character first, the slider path as backup [prompt]
- A character is written in two layers: inputs the person owns (`describe/*.md` in their own words, `profile.json`
  with the numbers and choices the engine reads, `companion.json`, `kokoro.json`) and outputs a skill generates
  (SOUL.md in six parts, dated seeds, person files, psyche.json, a lock file naming the inputs that produced them).
  The LLM is used in exactly two places: here, at authoring time, under review; and at runtime to write her reply.
  Everything between is deterministic code. Nothing regenerates on its own. The 2026-10-14 "human-owned SOUL" rule
  becomes "inputs human-owned, output generated".
- The skill runs in phases, each stopping for review, a part regenerable alone, never the whole SOUL in one request:
  intake (what is missing, follow-up questions), structure (dated events and the trait each left, seeds, stances,
  refusals, tensions, cares_about, a vagueness audit), thinking (the five meters and the dial 1 / 6 choices proposed
  with one line of evidence each; the person confirms), voice, reactions, parts, assemble (code), verify (a blind
  read-back of the SOUL compared to the confirmed meters and choices). Mechanical checks gate the write: theory and
  machine words, digits, simplified characters, size 2,500–4,000, the six sections.
- Dials 1, 4 and 6 are written from the description, not compiled from a choice; the choice is still recorded as a
  label, for the scratch instruction and the blind validation, and never reaches the model. Dials 2, 3 and 5 keep
  their numbers because the engine reads them; the numbers never come from the model alone.
- The slider-only path (§2.10) is the backup for people who will not write ten sections: the same outputs from
  sliders, choices and three short boxes, with template sentences, no LLM; the two paths compose. Built with the app
  button (0.8.1), not before.
- The cast is untouched. The schema is tried on a new disposable character (阿凜, `templates/character/example`) on
  both lanes, gemini flash and claude sonnet, with the same description, so the gap between the two can be seen before
  a lane is chosen for the button. 西, 子晴 and 子睿 move only when a generated character beats them on the fidelity probe.
- Version order set by the user: 0.8.0 the skill, 0.8.1 the create-character button wired to it, everything else in
  `prompt.md` §3 after that.

## Decided (2026-10-15) — the prompt: what she reads before she speaks [prompt] [structure] [inner-life]
- New part `docs/prompt/` (`prompt.md`, `prompt.d2`): one request verified block by block, and the design
  that reshapes it. Replaces the 2026-10-02 "prompt layer" entry, which promised this design pass.
- Found 2026-10-14: Hermes puts about 5k chars of English vendor text around the SOUL — help guidance naming
  her as a Nous Research product with a docs URL, assistant-posture guidance, the Windows host and home path,
  the profile paths, the model / provider / platform trailer — and the shim opens its tools text with "You
  are a function calling AI model". None of it was documented; the output checks (說破, 助理腔) flag exactly
  these leaks on the way out. Decided: switch off what has a switch in `config.yaml`, drop the rest in the
  shim by exact text, reword the shim's preamble, rewrite the wrappers in zh-TW. Vendor stays unedited.
- Cost rule, verified in `state.db`: history replays every past user row with its memory and state blocks
  (`api_content`), so a per-turn line is paid 20+ times per request and a system-prompt line once, cached.
  Hence three homes by cost; the SOUL-vs-memory rule ("must it shape every reply even when nobody brings it
  up?"); the six-part SOUL (parts 1–5 in SOUL.md, part 6 dated in the store); pinned groups as reserved tags
  rendered into kokoro's static block; the clock line at the top of the state block with a pinned timezone
  and absolute dates; the six thinking dials — five meters in a `thinking` block of `psyche.json`, two
  multiple-choice sets whose labels never reach the model, one optional 想法 line, rumination as a knob;
  and the hidden pre-reply scratch for dials 1 and 6 as a proposal behind four checks. Build order: `prompt.md` §3.
- `around-the-soul.md` is the decision brief for the twelve blocks that are not the SOUL: keep / off / replace /
  drop per block, and the tools question with the data — in 79 turns the three characters never called
  `kokoro_search` or `kokoro_forget` and eight times called a tool Hermes does not have (`openmini_reply`,
  her reply as its argument — the proxy openmini's own anti-truncation reply function, which our shim's
  "no native channel" preamble made the model write out as text), each costing a second round trip and an
  error row in history. Recommended
  there, not yet decided: no tools at baseline, the preamble reworded for extensions. Nothing changes before
  the decision.

## Decided (2026-10-15) — vendoring by submodule; plain git [structure]
- `vendor/hermes-agent` and `vendor/keepsakedb` are git submodules: Hermes at upstream `7166071f` (fetched
  shallow, `ignore = dirty` because the runtime writes caches inside), KeepsakeDB at its release tag (`v1.0.1`).
  One mechanism for both engines; the pins travel with a clone; nothing is copied by hand. The committed copy
  under `vendor/keepsakedb` and `tools/vendor-keepsake.ps1` lasted one day and are gone.
- The repo is plain git from here (it had been jj colocated on git): jj cannot hold a submodule. GitHub stays
  release-only — fold with `git reset --soft <previous release>` and commit `vX.Y.Z`. The local `.jj`
  directory and `refs/jj/*` are leftovers to delete.

## Built (2026-10-08) — inner life stages 3–4: proactive [inner-life]
- Urges are decided live only and recorded as replayable `proactive_fired` events; replay re-applies the record,
  a fast-forward after a stop decides nothing (no back-fill), a due loop fires at the first live tick. The first live
  run showed why: a replay-decided urge set a pending flag that blocked the real reminder for an hour.
- The gateway's planned-stop drain exits without unloading plugins, so the engine snapshots every 5 minutes, after
  every applied record and rendered block, and from an `atexit` hook.
- The event turn is a narrator's cue, not an instruction to "send a message": worded as an instruction, Gemini
  invented a reply tool (`openmini_reply`). A platform error in her answer counts as silence on both sides.
- A reminder you asked for passes every gate but "off" and "stopped" — including the conversation and no-disturb
  gates — because it is time-critical and yours; everything spontaneous respects them all.
- Her own event turns are user rows in `state.db`: the follower hides them, kokoro does not observe them, and the
  stop wait ignores them.
- 主動 settings are hot (the engine re-reads `psyche.json` each tick for proactive, busyness, cares_about); the
  dynamics (personality, constants, schedule, time constants) still apply at her next start. The 狀態 page acts
  through a `commands` table, like memory deletes.
- Attachment strength is a fixed 0.4 until L5 grows it (0.7.0); the one counterpart is you.

## Built (2026-10-07) — inner life stages 0–2: how it was wired, what the first runs decided [inner-life]
- Stage 0 answers. Hermes's `pre_llm_call` hook returns `{"context": …}` and Hermes appends it to the USER message
  right after the `<memory-context>` block, never the system prompt — exactly where the design wanted the state block;
  `post_llm_call` fires once per turn after the tool loop with the user text, the reply, session and turn ids;
  `transform_llm_output` exists for the record-only checks (0.6.0). Hermes user plugins are opt-in (`plugins.enabled`);
  a memory provider is activated by `memory.provider` instead, which is why kokoro never needed the list. The
  compression summary prompt is not a config key (`_build_summary_prompt` in the vendor compressor): compression stays
  unaware of emotion and the block's 轉變 line covers the inertia. The shim cannot tell Hermes's own call kinds apart
  without a `pre_api_request` hook — parked; our own calls (observe, appraisal) are ours to tag if ever needed.
- Appraisal vector = the 8 core fields (v, R, u, cert, agent, intent, devalue, ambiguity) + other_focus / other_v (his
  fortune) + appeal + q; coping and norm are not asked for (prototypes skip missing fields). Magnitude anchors in the
  prompt keep the scale stable between turns.
- Turn id = sha1(session id | user text | reply)[:12], computed identically by kokoro (stamped on memories) and by
  psyche (from post_llm_call), so neither plugin talks to the other; the annotation retries for 15 minutes because the
  observe may land after the appraisal.
- Prototype threshold 0.6 (design 0.5) after the first live run spawned a weak joy from an apology; gratitude, anger,
  hurt, pride, shame require the event to be about her (other_focus < 0.5), gratitude also intent ≥ 0.5.
- An appraisal applies after the step of its tick on both the live path and replay, so replay == live and
  fast-forward == tick by tick (engine tests); the live path snapshots right after applying.
- `people/你.md` replaces `memories/USER.md`: Settings writes it, kokoro injects it, the old file is carried over once
  and removed. `new-companion.ps1` stays ASCII (PowerShell 5.1 reads a BOM-less script as ANSI) and writes templates
  without a BOM (a BOM in kokoro.json broke the memory provider).
- Deferred inside the 0.5.0 scope: the offline simulator CLI and the seed-sweep script (before 0.6.0's time
  skeleton, where they earn their keep); rumination, needs, relationships as planned.
- Milestone measured (LLM eval set, 6 turns on a throwaway character): expression gap 0.17, emotion named only when
  asked outright, meta leak 0, assistant mode 0. The block carried 有點失望 after the broken promise, 轉變 after the
  apology, 滿足 + 替他高興 after the good news; loops opened and closed.

## Decided (2026-09-29) — workspace, backbone, shim [structure]
- 2026-09-29 — Workspace: everything under `D:\dev\556_production` (placeholder name).
- 2026-09-29 — Backbone: Hermes Agent (own copy, fresh venv, isolated HERMES_HOME) replaces
  Artemis's OpenClaw role. Production D:\Hermes stays untouched.
- 2026-09-29 — Model access: via the existing shim (:18766) lanes; testing lane `auto/probe`.
- 2026-09-29 — Gemini-only for now (proxy :18765 behind the shim). The shim is mandatory for
  tool calling (proxy strips `tools`; direct mode = chat-only with silent tool hallucination).
  Full loop verified: chat, tools, memory write, cross-session recall.
- 2026-09-29 — Project runs its OWN shim copy (:18767, `shim\`) instead of touching the
  production shim; chat model = `agyapi/gemini-3.7-flash` via lane `auto/556_production`
  (tool calling verified on flash). `auto/pro` kept for heavier jobs.
- 2026-09-29 — Live2D: official free sample models first; polish/custom later.

## Decided (2026-09-30, continued) — the name 556 Production [structure]
- **System name: 556 Production** (556プロ / 心プロダクション). Goroawase こ(5)こ(5)ろ(6) =
  心 kokoro — an idol-agency-style name (765PRO lineage: the number encodes a word): a good
  place where hearts and minds are created. The system is the AGENCY; companions are the talent;
  the user is the Producer. AI/tech stays subtext, like 765 = Namco.
- Physical rename 556_production/ → 556 happens DURING the rewrite (renaming now breaks the venv's
  absolute paths + all launchers; the rewrite touches those anyway).
- Candidate flourish for later: Path C memory engine module named `kokoro` — her heart literally
  being the memory engine. Port family 556xx available if the rewrite renumbers services.

## Decided (2026-10-02) — companion lifecycle is a manual, per-companion action [structure]
- The app can hold **many companions**; the user picks which ones to **start** (manually) and each
  stays up until the user **stops that one** or closes the app (closing the app stops all).
  Several can be active at the same time; nothing auto-starts.
- **MCP bindings are strictly per character.** Every MCP server / channel binding belongs to
  exactly one companion and is configured on her; a call arriving through her binding goes to
  her and nobody else. No shared pool, no content-based routing across companions. If she is
  not active, that binding has no one behind it (the call fails / is not served).
  Concretely for channels: a Telegram binding is **the character's own Telegram account**
  (her bot token, her identity), never a shared "556 Production" account. 556 is the agency
  that runs her; the account, the contacts and the conversations are hers. One character may
  hold several bindings (Telegram, Discord, an MCP server); one binding never serves two.
- Consequences for the backend: one Hermes process per active companion (its own profile,
  HERMES_HOME, session) under the 556d supervisor, with per-companion ports; the embedder
  sidecar is shared. Each companion owns its own memory store file (`home/memory/<profile>.db`,
  one owner process each, so no writer conflicts); the memory page and the memory API become
  per-companion (`/api/memory?companion=`), replacing today's single `daemon.profile`.
- UI: the office window gets a roster with start/stop per companion and an "active" state.
  **The avatar does not change: it follows the companion the chat window is currently on.**
  With bindings strictly per character there is no fan-out policy to design: a channel's
  messages belong to its character; the hub only has to address the right active process.
- **Stopping is graceful** (2026-10-02 evening, found by the smoke test: a stop 3 s after a reply
  hard-killed her before the ~6 s memory observe landed → turn lost). Stop / app quit / app death
  all write Hermes's planned-stop marker so her gateway drains and kokoro waits for its observe;
  kill only after 60 s; and the stop first waits (≤ 30 s) for the pipeline to observe the newest turn, since
  Hermes queues that observe a few seconds after the reply. A stop therefore takes ~10 s and shows 收尾中.

## Decided (2026-10-02) — one route per character: her gateway is her only Hermes [structure]
- The first live Telegram test exposed the two-process shape (`hermes serve` for the app + `hermes
  gateway run` for Telegram): two owners of her memory, 📬 "no home channel" notices, and Telegram
  knowing nothing of what was just said in the app. **Fixed the same day: one `hermes gateway run`
  per active character.** Its API server platform (`API_SERVER_KEY/HOST/PORT`, key kept in her
  `companion.json`) is the app's route; its adapters are the channels'. The app UI and the
  channel/MCP bindings are peers at the same level, all calling her. 556d never runs Hermes for her
  any other way.
- **One conversation per character** (corrected the same night — the first cut kept one session per
  surface and faked continuity through memory; the user rejected both). Her Telegram DM session IS the
  conversation. The app continues it by id (`X-Hermes-Session-Id`); the gateway rebuilds context from
  `state.db` every turn, so Telegram and the app see one history. When the app speaks first, 556d creates
  the session through her API and stamps the Telegram routing identity (`sessions.source` +
  `session_key`) on the row, so her first Telegram message lands in it. History survives restarts
  (SQLite); auto-reset is off; compression summarizes, never deletes. 556d never proxies Telegram.
- **History is not memory.** Last-X-turns is the agent's session store; KeepsakeDB keeps only what the
  pipeline judges worth keeping. The recent-exchange layer was removed (KeepsakeDB 0.1.3).
- **Every surface shows in the app.** 556d follows the conversation (2 s poll of her session store) and
  broadcasts channel turns to the windows with a source badge; app turns are mirrored into Telegram.
- **(c) Telegram mirror**: after an app turn, 556d sends「你問我：q／我說：a」as plain text to her
  home channel through her own bot token — no LLM call, so the Telegram thread catches up with the
  app. Settings toggle (default on); `TELEGRAM_HOME_CHANNEL` is a registry knob.

## Decided (2026-10-07) — 製作人 → 你 [memory]
- Stored memories use 你 as the subject word: natural text, searchable, and what you see on the memory
  page. Injected or searched text renders 你 as her term for you (your name, else the role term 製作人),
  because her prompt already uses 你 for herself. No invented marker token (it would blind the search).
  In v2, a `subject` column decides which rows get which name per counterpart. SOUL keeps 製作人 as the
  role she addresses you by when no name is set.

## Decided (2026-10-06) — tools: a clean structure (0.5.0) [structure]
- **Baseline = memory only.** Every character carries exactly two tools, kokoro's `kokoro_search` and
  `kokoro_forget`, through Hermes's `memory` toolset (`platform_toolsets: {api_server: [memory],
  telegram: [memory]}`). Hermes's built-in memory writer is off (`memory_enabled` /
  `user_profile_enabled: false`): one memory system. kokoro injects `memories/USER.md` itself, so the
  Producer's profile stays in her prompt. Before this she silently carried Hermes's 20 default tools,
  shell and files included, in every prompt.
- **Extensions per character, in Settings.** 設定 → 她會的事 lists extensions (first: 查網路 =
  `web`, keyless through Hermes's free-tier ring and DuckDuckGo). Switching one writes her config.yaml;
  a graceful restart applies it. **No hot toggling** — simpler and stable. An extension that acts in
  the world is flagged; the approval/clarify answer path is built only when one is switched on.

## Decided (2026-10-03) — voice: two modes in the chat, Fish Audio first [voice]
- **Mode 1, press-to-record**: the default text chat gains a 🎙 button; press to record, press again to
  stop; the transcript lands in the composer and the Producer sends it like typed text. No TTS.
- **Mode 2, conversation mode (免手持)**: the mic stays open, Silero VAD runs in the browser, the
  endpointing from the earlier `voice_agent_vad.py` is kept (threshold 0.5, cut after 500 ms, pre-roll
  0.4 s, grace 0.9 s so pauses merge into one turn, min 0.35 s, max 30 s). Strict 1:1 pipeline: one
  transcription, one chat turn, one synthesis, one playback; cuts made while she answers queue FIFO.
  The text box is locked meanwhile. Voice turns carry an ephemeral spoken-style hint (short, no markdown)
  and replies are sanitized before TTS; they are ordinary turns otherwise (same session, memory, mirror).
- **Playback**: the avatar window plays and lip-syncs (it always exists, hidden unless shown); the office
  plays only when no window claims playback. Echo guard pauses the mic while she speaks (default on).
- **Connectors**: `fish-audio` next to `openai-compatible` (TTS `/v1/tts` with `reference_id`, ASR
  `/v1/asr`); keys stay in `home/voice.json`, entered in Settings, never in chat. Hands-free parameters
  live in the same file and in Settings. Telegram turns are not spoken by the app.

## Decided (2026-10-03) — two memory layers, one file; history stays history [memory]
- **Short layer** (KeepsakeDB 0.2.0): the same observe call that writes tagged long-term facts may
  also return one dated line — the episode of the turn when it could matter later (what the Producer
  asked for or did, a plan, a mood with its cause). No tags; surface stamped in meta; ring of 1000
  (`short_cap`), oldest dropped. Greetings, small talk and trivia return null. Purpose: a second chance
  when a long fact was missed or mis-written.
- **Read path**: one embedding, then every layer searched at once — the bigger layer (in-memory count)
  starts first on its own read-only connection, the smaller follows on the calling thread, only the
  final join waits. Hybrid (dense + BM25, RRF), top 5 each. Injected as `Facts (long-term)` and
  `Notes (recent, dated)` in one `Memory` block.
- **Priority told to her**: the conversation itself is ground truth; otherwise the newest entry wins
  whatever its layer; a fact beats a note only on a tie. The pipeline supersedes a stale fact afterwards.
- **One file, two layers** (a `layer` column), not two databases: one owner, one backup rotation, one
  memory page (long by default, toggle for the short layer).
- **At most one session, opened by the manual start**: 556d opens her conversation when she is started
  from the roster (create + Telegram routing stamp if none is live); a message never opens one. Hermes's
  slash commands (`/new`, `/reset`, `/model` …) are admin-only on her Telegram with a placeholder admin,
  so the Producer cannot fork the conversation from the phone; everything is set from the app.

## Decided (2026-10-02) — the Producer's name vs the memory subject [memory]
- Stored memories never contain the Producer's name as subject. The subject is a **fixed role
  marker per store**: 「製作人」 for zh-TW stores ("the Producer" for en), recorded in the store's
  meta like the tokenizer; other people are stored by their own names / relations. Reason: a name
  can be added after many rounds or changed later; a role marker never splits the corpus, never
  needs a migration or a re-embed. (Changing the marker itself is a deliberate migration:
  one text replace + re-embed.)
- The name lives in the prompt layer: Settings `producer_name` → written through to
  `home/USER.md` (Hermes injects it every turn) → she addresses him by name while the memory
  block says 製作人. The L2 pipeline prompt is told the current name so first-person mentions by
  name (e.g. his English name) still resolve to 製作人 and a different person with that name
  stays separate.
- Search is unaffected either way (a constant subject token has no discriminating power; probes
  are first-person and matched neither word, recall was 20/20).
- Test stores so far say 「使用者」 (harness default); the real store starts with 「製作人」.

## Decided (2026-10-02) — the prompt layer: Producer settings that shape her system prompt [app] [memory]
- Superseded 2026-10-15 by `prompt/prompt.md` (the design pass promised below) and the entry of that date.
- Two Settings now write into the selected companion's `memories/USER.md` as managed lines that
  Hermes injects every turn: the **Producer's name** (「名字：…」) and **her reply language**
  (「回覆語言：…」; default = follow the Producer; options en / zh-CN / zh-TW / ja). Both take effect
  after restarting her. Memory storage language and the fixed memory subject are separate knobs
  (kokoro.json) and are NOT affected by the reply language.
- These are the first entries of a **prompt layer** (settings-driven text around the hand-written
  SOUL). The user wants to go deeper here later: a generated block (name, reply language, channel
  etiquette, time/locale, relationship stage…) assembled per turn instead of managed lines in a
  file. Design pass to come; for now the managed-lines approach keeps SOUL.md human-owned.

## Decided (2026-10-02) — voice: connectors first, feature later [voice]
- STT / TTS are cloud services (GPU stays free); the app gets **connectors** now, the feature later.
  `home/voice.json` (agency-level keys, 0600) holds a TTS and an STT provider; the only kind
  implemented is **OpenAI-compatible** (`/audio/speech`, `/audio/transcriptions`), which covers
  OpenAI, Groq (STT), Fish Audio, Azure OpenAI and local proxies; vendor-specific APIs (ElevenLabs,
  MiniMax, Azure Speech) are later adapters behind the same `Speak` / `Transcribe` calls.
- Settings → 語音連線: configure, save, and **test** (TTS the phrase, then STT the audio — the round
  trip proves both). Per-companion voice choice (her voice id) lives in `companion.json` later.

## Decided (2026-10-02) — Settings principle: nothing is fixed in a config file [app]
- Settings has two tiers. **Non-technical knobs are shown directly** (製作人: name, her reply
  language; 她: name, Live2D, show on start; 記憶: storage language, context turns X; 語音連線).
  **Everything else is behind a "developer options" toggle with a warning**, rendered from
  556d's **config registry** (`/api/config`): every knob declared once with its file, path, type,
  scope (agency / selected companion), and the effect of changing it (restart her / restart the
  app / re-embed / reindex / migrate subject). Groups: her model (config.yaml), her memory engine
  (kokoro.json), her channel bindings (.env, tokens masked), the agency backend (556d.toml, shim
  routing). Writes go into the files in place (YAML keeps comments).
- Consequence in the engine: the two "constants" became changeable — KeepsakeDB now reindexes at
  open when the configured tokenizer differs from the store's, and migrates every memory when the
  subject word changes (rewrite + re-embed, logged in history). The configured value always wins.

## Parked (explicitly deferred by user) [all]
- ~~**Her name** (first companion) — decided AFTER the system; agency-first like the reference.~~
  **2026-10-02: first character = a fresh persona** (not a port of Bith), 556's first talent, framed
  as the agency's **manager** (經紀人／マネージャー) — the one who answers the phone, which is exactly the
  channel-binding job that comes next. The sample Live2D model (Hiyori) stays for now. First job with
  her: channel connections (Telegram, Discord) in **pure text**; voice over channels is future work.
  Name: "Kokoro" was considered and dropped the same day because the memory provider plugin is
  `kokoro` (her heart) and the user wants that name to stay. **Her name: 真音（まね, Mane）** —
  decided 2026-10-02: マネ is what idols call their manager, hidden in a real name meaning "true
  sound"; reads naturally in 繁中 (真音). Her name lands in: `SOUL.md` (fresh draft), settings
  `companion_name`, `home/memory/mane.db`, the account handles (e.g. `@mane_556_bot`).
- **MCP / channel list** — later; QQ excluded.
- **Whether the Wardrobe schema is adopted** — it's one candidate, not presumed.

## Open questions (2026-09-29; mostly answered since) [all]
- Which profile becomes the first companion character here (fresh SOUL vs port of Bith's)?
- TTS voice source/reference audio for GPT-SoVITS (when we get there).
- GPU budget: does local image-gen/TTS coexist with WSL Qwen (→ revisit Artemis VRAM tiering)?

## Decided (2026-09-30, 0.2.0 discussion) — Go daemon, Electron, Hermes surface [structure] [app]
- **Frontend stays as-is** for 0.2.0; 0.2.0 = backend rewrite.
- **`vendor/` is untouchable by definition**; if we edit it, it is not vendor. Hermes never edited.
- **Go** for the beside-Hermes layer (daemon `556d`: supervisor, shim, bridge, UI API): single
  static binary, cross-compiles to every OS, best fit for HTTP/WS + process supervision.
  **Python only inside Hermes** (memory provider, platform adapter, skills) — by contract.
- **No Rust, no Tauri.** Tauri is a window shell, not a TypeScript alternative; with Go fixed its
  Rust side is dead weight, and its small-binary benefit is what Wails gives in Go-land.
- **UI = TypeScript, one codebase**, identical under any shell. **Shell = Electron now** (bundled
  Chromium → avatar renders identically on every OS); **Wails later only if** we accept testing the
  avatar on three native webviews (WebView2 / WKWebView / WebKitGTK).
- **Hermes surface for chat = `tui_gateway` JSON-RPC over WS** (what Hermes Desktop uses):
  persistent agent, streaming, `profile` = talent switching. `api_server` optional. Proactive
  pushes need a Python platform-adapter plugin (0.2.x); cron agents run without memory provider.
- **Artemis exit**: reference clone kept until the frontend rewrite empties the ledger, then deleted.

## Decided (2026-09-30, after 0.2.0) — memory language, engine repo, frontend shape [memory] [app]
- **Memory language is a per-companion setting** (user-changeable; default zh-TW). "Mirror the
  input language" rejected (mixed stores defeat dedup — the zh/en Japan-trip duplicate).
  **Catch, documented in README + memory/memory.md**: the embedding model is user-changeable too, and a
  companion in another language (ja/fr/…) must be paired with an embedder that covers it.
- **Standalone memory engine**: own repo, pure Python library consumed by 556 via a thin Hermes
  MemoryProvider in `plugins/`. Name deferred (may take a `DB` suffix; "kokoro" collides with the
  Kokoro TTS model, so it stays 556-internal). Open before writing: whether the memory *pipeline*
  (extract/tag/merge/archive) lives inside the library or in 556 — proposal: layered library
  (storage+retrieval core; pipeline as an optional module) so the DB alone stays lightweight.
  **Decided 2026-10-01: KeepsakeDB** (`D:\dev\KeepsakeDB`), layered B — L1 store (SQLite: FTS5
  BM25 + dense, RRF), L2 pipeline pluggable/unpluggable, L3 integration for any agent; recommended
  all three together. SQLite is a trial, judged by the benchmark against Milvus Lite 3.x.
- **Conversation model**: backend keeps ONE endless conversation per companion; only the last X
  turns are in context (Hermes compression knobs; X user-settable later). Frontend shows the
  current X turns for now — revisit.
- **Hub architecture**: every UI/channel (office window, pet, Telegram, MCP…) connects to the
  backend; the backend fans events out to all connected services. Windows never talk to each
  other directly. Fan-out policy (what goes where) to be designed; end state: ask on Telegram,
  the pet answers on the desktop.
- **Approvals/clarify**: solved by toolset policy, not UI — the companion's toolset excludes
  approval-gated tools and the `clarify` tool. No prompt UI planned.
- **Proactive presence**: no limits/etiquette rules for now.
- **App model**: ONE Windows app, "556 Production" — office window with chat + settings, a button
  to show/hide the avatar (pet window belongs to the same app). Closing the app closes the whole
  backend (the app owns 556d's lifecycle); minimize/hide to the tray (bottom-right).
- Terminology: "companion" (not "talent") in docs and UI.

## Done (2026-10-01, 0.3.0 S5) — Artemis exit [structure]
- The Artemis ledger emptied (SPA and viewer replaced by the app) → `vendor/artemis/` deleted.
  What we learned from it lives in `structure/structure.md` §6, `STACK.md` pitfalls and this log.
- Retired: `ui/` (web-chat SPA, Electron pet, viewer), `avatar.cmd`, `pet.cmd`, the `/chat/`
  route and the SPA-compat endpoints. Diagnostics moved to `tools/`.
