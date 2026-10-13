# Diagrams — where we are, and what is proposed

D2 sources live in `docs/diagrams/*.d2` and are read as source (render with
`d2 docs/diagrams/<name>.d2 out.svg` if you want a picture). **Dashed, pink = proposed, not built**
(Discord, MCP). Everything else is what runs as of 2026-10-03, including the two memory layers.

## 1. Structure — one process per character, every surface is a peer

Source: [`diagrams/structure.d2`](diagrams/structure.d2)

- Her `hermes gateway run` is her only Hermes process. Its API server is the app's route; its
  adapters are her channels (her own accounts). 556d is the hub around her, never a chat
  participant: it starts/stops her, shows her conversation, mirrors app turns into Telegram, and
  reads her stores read-only (and opens her one session at start).
- Shared across characters: the model shim, the embedder, 556d. Per character: process, API port
  and key, `state.db` (history), `memory/<name>.db` (memory), SOUL/config/.env.

## 2. One turn — app, Telegram, and a stop right after a reply

Source: [`diagrams/turn-flow.d2`](diagrams/turn-flow.d2)

- Exactly one session per character. 556d opens it when you start her from the roster (never a
  message, from any surface); both surfaces join it, and the gateway rebuilds the context from
  `state.db` every turn, so each side sees the other's turns. 556d never proxies Telegram. `/new` and
  the other gateway slash commands are admin-only on her Telegram, so no message can open a second session.
- Memory work per turn: one embedding + search before the reply (tens of ms), one LLM call after
  the reply in the background (~5–7 s), serialized.
- Two mirrors: app → Telegram as plain text; Telegram → app through the follower, with a badge.

## 3. History vs memory — three layers, one priority rule

Source: [`diagrams/memory-layers.d2`](diagrams/memory-layers.d2)

- History is not memory. History = the session store (verbatim, compressed never deleted).
  Long-term = tagged facts the pipeline judged worth keeping. Short-term = one LLM-written dated
  line per turn worth recalling later, a safety net for missed or mis-written facts (built 2026-10-03).
- Still one observe call per turn; it may return two strings (`ops` for long, `note` for short). Still
  one embedding per prefetch, then both layers searched at once: the bigger layer starts first on its own
  read connection, the smaller follows immediately on the calling thread, nothing waits but the final join;
  hybrid (dense + BM25, RRF), top 5 each, a few ms per search.
- Priority when they disagree: history first; then the newest entry regardless of layer; long
  breaks ties; the pipeline supersedes the stale long fact afterwards.
- One file with a layer column (one owner, one backup), not two database files. 記憶 shows the long
  layer; a toggle shows the short layer.

## 4. Voice — two modes in the chat window

Source: [`diagrams/voice.d2`](diagrams/voice.d2)

- Mode 1: press-to-record, transcript into the composer, sent as text. Mode 2: conversation mode, mic always
  open, VAD endpointing from the earlier voice agent, strict one-to-one loop with a FIFO, text box locked.
- Voice turns are ordinary turns with a spoken-style hint; the avatar plays and lip-syncs the reply.

## 5. Lifecycle — nothing auto-starts, every stop is graceful

Source: [`diagrams/lifecycle.d2`](diagrams/lifecycle.d2)

- Roster stop, app quit and app death take the same path: wait for the memory pipeline to catch
  up with the last turn, planned-stop marker, drain, exit; kill only after 60 s.
