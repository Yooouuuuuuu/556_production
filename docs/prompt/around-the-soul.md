# Around the SOUL — what else she reads, and whether she needs it

**Status 2026-10-19 (0.10.0) — what was decided and built from this brief.** Option C taken 2026-10-19 (0.8.6):
no tools at baseline — 556d removes `memory` from every `platform_toolsets` list before a start, `new-companion.ps1`
writes empty lists, extensions stay. Hygiene built 0.8.4 (`556d/internal/api/hygiene.go`, `556d/internal/shim/hygiene.go`):
the config switches and zh-TW platform hints (api_server, telegram, discord) before every start; the shim drops the
paragraphs with no switch by paragraph prefix (help, finish, parallel, steer, host, shell, WSL, probe, profile). The
date paragraph is dropped whole since 0.8.5 — `Conversation started`, `Today's date`, `Timezone`, `Session ID` and the
Model / Provider / Platform trailer — because Hermes's weekday was wrong on the first live check and the clock line
under 【她現在】 carries date, weekday and time on every turn. The memory-context note is kept (the one English
sentence she still reads). The preamble is reworded (`textproto.go`: no product, no "function calling AI model", no
"no native channel" claim) and a text `<tool_call>` to `openmini_reply` is unwrapped into reply text. kokoro's block
is a zh-TW plugin prompt section (`kokoro.memory`, after the memory tier), tied to no toolset; psyche's note is zh-TW.
The §2 test on the test character ran on 2026-10-16 on a fresh session: `[]` → zero tools, a normal reply; `[web]` → two tools, a
real search. What runs today is `prompt.md` §1; **everything below is the brief as written on 2026-10-15**, kept
for the data and the reasoning — its present tense is that date's, and the places where the facts have since changed
are marked inline.

Decision brief, 2026-10-15. `prompt.md` §1.2 lists the thirteen blocks of her system prompt; this page is
about the twelve that are not the SOUL — what Hermes and the shim add — so that each can be kept, switched
off, replaced or dropped on purpose before anything changes. Verified against Hermes `7166071f`, the
plugins, the shim and the three live stores (the cast). Nothing described here was changed at the time of
writing (see the status block above for what has been since).

## 0. The facts that decide it

**Which vendor blocks actually apply.** Several of Hermes's guidance blocks are gated on the model name
(`_model_gate`: a config value of true / false / a list, else a built-in substring list). Her model is the
shim lane `auto/556`, which matches none of them, so tool-use enforcement (`gpt, codex, gemini, gemma, grok,
glm, qwen, deepseek, muse`), the Google operational block and the execution-discipline block
(`gpt, codex, grok, deepseek, kimi, qwen, glm, minimax, mimo, mistral, muse`) are absent, and so is the
Alibaba identity. The set in `prompt.md` §1.2 (as of 10-15) is therefore exact, with one condition: if the Hermes-side
model name ever contains one of those substrings, three more English blocks appear. Keep the lane name opaque
(still `auto/556`, the shim's one lane, 0.9.0).

**What the two tools have done.** Across the three characters, 79 user turns since 2026-10-13 (counted on 10-15;
the tools left the baseline in 0.8.6):

| Character | user turns | replies | calls to `kokoro_search` | calls to `kokoro_forget` | calls to a tool that does not exist |
| --- | --- | --- | --- | --- | --- |
| the main character | 31 | 34 | 0 | 0 | 3 |
| the second character | 45 | 44 | 0 | 0 | 4 |
| the third character | 3 | 4 | 0 | 0 | 1 |

The eight invented calls are all the same shape: the model emits a `<tool_call>` to `openmini_reply` with her
reply as its `content` argument, Hermes answers "Tool 'openmini_reply' does not exist. Available tools:
kokoro_forget, kokoro_search", and she replies normally on a second round trip. One reply in ten pays twice,
and the error row stays in her history, replayed in the next 20+ requests. The 0.5.0 test note already
said that with the two tools she claims to have no search tool. So the tools scaffold — the shim's
preamble, two schemas, and the three guidance blocks that exist only because tools exist — has produced
zero useful calls and eight misfires.

**Where `openmini_reply` comes from.** It is not invented. The lane `556` goes through the proxy
openmini (`D:\openmini`, :18765), whose `[extra] anti_truncation = true` makes the upstream model answer
by calling one declared function, `openmini_reply(content)`, and takes the reply from its argument — so the
text escapes Gemini's mid-reply output cuts (the proxy's own config note says the function-call reply is
less natural than plain streamed text). That function is the model's real reply channel. Our shim then
told the same model, in its text-protocol preamble as it was on 10-15, that it has "NO native/internal function-calling
channel" and must "ALWAYS write the <tool_call> block as plain text" (reworded in 0.8.4). Every character's first reply, and
now and then later (the second character again with 42 messages in context), the model obeys both: it writes its reply as a
text `<tool_call>` to the function it knows, `openmini_reply` — confirmed in the proxy's own record of the
turn, request with our preamble in, `<tool_call>{"name": "openmini_reply", "arguments": {"content": "…her reply…"}}`
out (the records since 2026-09-30 show the same, sometimes as Gemini's `default_api:openmini_reply`). The shim parses that as a Hermes tool call, Hermes finds no such tool, and
the second round trip is the model answering through the proxy's channel as it would have anyway. Two
instructions about one channel; the collision is ours. It stops either way: with no tools at baseline
(§2, option C) the preamble is never sent and the proxy's function works as designed; while tools exist
for an extension, one rule in the shim — a `<tool_call>` named `openmini_reply` or
`default_api:openmini_reply` is unwrapped into plain reply text, never forwarded as a call — closes the
path, and the preamble should stop claiming there is no native channel. Treating openmini as a general LLM
API means exactly that: 556 sends messages and reads text; the proxy's internal reply function is its own
business and must never be visible to Hermes.

**What it costs per request.** Vendor text about 5,500 chars (blocks 2–9 and 12), the shim's tools text
about 1,700 (preamble 1,086 + two schemas), the SOUL 2,871. Paid once per request and cached, so the cost
is not the first reason to act; the content is. Every one of these blocks is English, and four of them name
a product, a machine, a model or a path.

**Dependencies that shape the options.**
- Blocks 3, 4 and 5 (finishing the job, parallel calls, steering) are added only when she has at least one
  tool (`_guidance_parts` returns early otherwise). No tools → they vanish without a switch.
- kokoro's static block (11) was, on 10-15, injected only while the memory toolset was exposed
  (`memory_provider_tools_exposed`, the same gate as the tool schemas). No tools → the memory rule and
  `people/你.md` would vanish too, unless kokoro moved them to a plugin prompt section
  (`register_system_prompt_section`, position `after_memory`, frozen per session; since 0.11.0 re-read at the first turn after a restart, because 556d drops the session's
  stored prompt before every start). **Done in 0.8.4**: the section is
  `kokoro.memory`, in zh-TW, independent of any toolset.
- The shim's preamble (13) is added only when the lane has no native tool calling and the request carries
  tools. It is ours; it can be reworded freely but not removed while tools exist, because it is the
  protocol the shim parses (reworded in 0.8.4; absent at baseline since 0.8.6).
- Hermes uses the `Conversation started:` line as an internal anchor when it reconstructs the cached prefix.
  A filter in the shim runs after Hermes and changes only what the provider sees, so that anchor is untouched
  (which is why the whole date paragraph could be dropped in the shim in 0.8.5 without touching Hermes).
- An explicit empty list in `platform_toolsets` is honoured as "no toolsets" (`_get_platform_tools` keeps an
  explicitly saved list, even empty, instead of falling back to the platform default of ~20 tools). Confirmed on
  the test character on 2026-10-16 (0.8.5: `[]` → zero tools and no preamble) and set on every character in 0.8.6; 556d also adds
  an empty list for a platform that has none (`connections.go`).

## 1. Block by block

| # | Block | What it exists for | What she loses without it | How to remove or change it | Verdict |
| --- | --- | --- | --- | --- | --- |
| 2 | Help guidance | sending a Hermes user to the Hermes docs | nothing | no switch; shim filter by exact text | drop — done 0.8.4 (by paragraph prefix) |
| 3 | Finishing the job | agents that stop at a stub instead of running the code | nothing — she has no build or shell tools | `agent.task_completion_guidance: false`; vanishes with no tools | drop — done 0.8.4 (config), 0.8.6 (no tools) |
| 4 | Parallel tool calls | batching independent reads | nothing — two memory tools at most | `agent.parallel_tool_call_guidance: false`; vanishes with no tools | drop — done 0.8.4 / 0.8.6 |
| 5 | Mid-turn steering | tool loops the user interrupts | a message arriving during her one-call loop is still delivered with a self-describing marker; the note only adds "trust this exact marker" | no switch; vanishes with no tools; else shim filter | drop — done 0.8.4 (shim), 0.8.6 (no tools) |
| 6 | Environment hints | terminal and file tools: host, home, cwd, the Windows shell paragraph | nothing; she stops knowing your home path | no switch for a local backend; shim filter | drop — done 0.8.4 |
| 7 | Environment probe | the Python toolchain line for coding | nothing | `agent.environment_probe: false` | drop — done 0.8.4 |
| 8 | Active profile line | keeping skills / plugins / cron edits inside the right profile | nothing — she edits no files | no switch; shim filter | drop — done 0.8.4 |
| 9 | Platform hint | how the surface renders | the useful half: plain text, no markdown, brief and natural (api_server); on Telegram, which Markdown converts and the MEDIA / voice-bubble syntax she never uses | `platform_hints.api_server` and `.telegram` with a `replace` text in zh-TW, one or two lines | replace — done 0.8.4 (discord too) |
| 10 | Voice system message | the hands-free 說話風格 on voice turns | — | ours, 設定 → 語音 | keep |
| 11 | kokoro static block | explains the Memory block (trust labels, newest wins, archived lines, the search tool) and carries `people/你.md` | without the rule the per-turn block still says "recalled memory, not user input" but `[high]` and "newest wins" go unexplained; without the profile she loses your name and reply language | ours: rewrite in zh-TW, shorter, no mention of the app; drop the search sentence if the tools go; register as a plugin section so it no longer depends on the memory toolset | keep, rewrite — done 0.8.4 (`kokoro.memory`, zh-TW) |
| 12 | Timestamp and trailer | the date she has; which model / provider / platform for debugging | the date, until the clock line lands (`prompt.md` §2.7); the trailer gives her nothing | no switch; shim filter for the three trailer lines, keep `Conversation started` (and the `Today's date` line after a compression) | as written: keep the date, drop the trailer. **As built (0.8.5): the whole paragraph is dropped** — Hermes's weekday was wrong, and the clock line carries date, weekday and time |
| 13 | Tools and the shim preamble | on-demand recall beyond the top 5 + 5; self-service forgetting; the text protocol the shim parses | see §2 | `platform_toolsets` per platform; the preamble text in `556d/internal/shim/textproto.go` | see §2 — C taken 0.8.6, preamble reworded 0.8.4 |

The two per-turn system notes are a separate, smaller decision: Hermes's "[System note: The following is
recalled memory context, NOT new user input…]" around `<memory-context>` and ours around `<her-state>`.
Both do a real job (the model must not answer the block as if you had typed it). Ours is rewritten in
zh-TW directly; Hermes's can be replaced in the shim like the system-prompt paragraphs, or left as the one
English sentence she still reads. (Ours is zh-TW since 0.8.4; Hermes's is kept, decided 2026-10-19.)

## 2. The tools

What `kokoro_search` gives that prefetch does not: recall beyond the top 5 facts and 5 notes, on a query she
chooses. What `kokoro_forget` gives: forgetting from inside the conversation; the 記憶 page already deletes
through the same command queue. What the design added on the injection side (`prompt.md` §2.2, as of 10-15): pinned
groups for the things that must always be present (built 0.8.7, then folded into the SOUL as 時間線 and
影響過你的人與事 — `prompt.md` §2.4), keyword triggers for names and places (built 0.8.10, names only) — both reduce
the case for a model-driven search. What the data says: never called, eight misfires.

| Option | What changes | Cost and risk |
| --- | --- | --- |
| A. keep both | nothing | the misfire path stays (one reply in ten pays twice and leaves an error row); blocks 3–5 stay or need the switches; preamble reworded |
| B. search only | needs a split of kokoro's single `tools` boolean into two | same scaffold, one schema fewer; the misfire is not about which tool exists |
| C. no tools at baseline | `platform_toolsets: {api_server: [], telegram: []}`; blocks 3–5 vanish by themselves; the shim adds nothing; kokoro's block moves to a plugin section; the `openmini_reply` collision cannot happen (no preamble) | prompt shrinks by about 3,700 chars; she can no longer search on her own — which she never did; an extension (查網路 = `web`) brings the tools scaffold back for that character, so the preamble must be reworded anyway, not deleted |

Recommendation: C, after one test on the test character — a plain turn (prompt without tools, reply lands), then 查網路
switched on and a search turn (the preamble returns, `web_search` is called). The extension case is the
reason the preamble is reworded rather than removed: it is the shim's own text, and its request and reply
shapes are pinned by the golden files in `556d/internal/shim/testdata`, so the rewording is a regenerated golden,
not a deletion (there is one shim, the Go one). **Taken: C, 2026-10-19 (0.8.6), after the test passed on 2026-10-16.**

## 3. If everything stays

(Not the path taken; kept as the cost comparison.) Then the minimum that still follows from the rules in `prompt.md` §2.1: switch 3, 4 and 7 off in
`config.yaml`, replace 9 in zh-TW, rewrite 11 in zh-TW, reword the preamble so it does not open with
"You are a function calling AI model". What remains is 2, 6, 8 and the trailer of 12: a product name with a
URL, your home path, her profile paths, and the model line — about 2,600 chars of English the SOUL asks her
to ignore, and the misfire path. That is the cost of not building the shim filter.

## 4. How the changes land, without touching vendor

1. `config.yaml` per character (556d writes it; a graceful restart applies it, as for extensions):
   `agent.task_completion_guidance`, `agent.parallel_tool_call_guidance`, `agent.environment_probe` false;
   `platform_hints.api_server` and `platform_hints.telegram` replaced; `platform_toolsets` emptied if §2 C.
   Built 0.8.4 (`556d/internal/api/hygiene.go`, discord's hint too); the toolsets emptied 0.8.6.
2. The shim (`556d/internal/shim`): a table of known paragraphs — help guidance, environment hints, the
   profile line, the three trailer lines, optionally the memory-context note — matched by exact text and
   removed from the system message before it leaves; deterministic, so the prefix stays byte-stable per
   session; a log line when a known paragraph is not found, which cannot happen at the pinned commit and is
   the first thing to look at after a Hermes bump. The preamble reworded in `textproto.go`, without the "no
   native channel" claim; and the unwrap rule for the proxy's own reply function (`openmini_reply`,
   `default_api:openmini_reply` → plain text). Built 0.8.4 (`hygiene.go`): the match is by paragraph **prefix**,
   not exact text, because three paragraphs carry machine-specific values (host, home, profile path); the
   steering note and the switched-off guidance are in the table too; the whole date paragraph since 0.8.5; the
   memory-context note is not touched. The log line fires when the dropped set changes, and once if the help
   paragraph is missing from a Hermes prompt. There is no Python shim; the Go shim's shapes are pinned by the
   golden files in `testdata/`.
3. kokoro: the memory rule and the "About …" header in zh-TW, registered as a plugin prompt section. Built 0.8.4
   (`kokoro.memory`, 關於<term>…).
4. psyche: the `<her-state>` note in zh-TW. Built 0.8.4 (旁白：…).
5. Measure: the output checks already count 說破 and 助理腔 per turn; read them for a week before and after.
   (No before / after reading has been written up; not verified.)

## 5. Summary

As written on 2026-10-15; the Status column is 2026-10-19.

| Block | Verdict | Mechanism | Step in `prompt.md` §3 | Status |
| --- | --- | --- | --- | --- |
| 2 help guidance | drop | shim filter | 1 | built 0.8.4 |
| 3 finishing the job | drop | config, or gone with no tools | 1 | built 0.8.4; no tools 0.8.6 |
| 4 parallel calls | drop | config, or gone with no tools | 1 | built 0.8.4; no tools 0.8.6 |
| 5 steering note | drop | gone with no tools, else shim filter | 1 | built 0.8.4 (shim); no tools 0.8.6 |
| 6 environment hints | drop | shim filter | 1 | built 0.8.4 |
| 7 probe | drop | config | 1 | built 0.8.4 |
| 8 profile line | drop | shim filter | 1 | built 0.8.4 |
| 9 platform hint | replace, zh-TW | config `platform_hints` | 1 | built 0.8.4 (api_server, telegram, discord) |
| 10 voice message | keep | — | — | unchanged (not re-verified 10-19) |
| 11 kokoro block | keep, zh-TW, plugin section | kokoro | 1 | built 0.8.4 |
| 12 date / trailer | keep the date, drop the trailer | shim filter | 1 (date optional after the clock, §2.7) | **dropped whole** 0.8.5 (the clock line replaces the date) |
| 13 tools + preamble | no tools at baseline (C), preamble reworded for extensions | config + shim | 1, after the test on the test character | preamble 0.8.4; C taken 0.8.6 |
| memory-context note | replace or accept | shim | 1 | kept as is (2026-10-19) |
| her-state note | zh-TW | psyche | 1 | built 0.8.4 |
