# Plan — channel bindings per character (Telegram + Discord first, text only)

Status: 2026-10-02 — §1 profile layout, §2 processes/lifecycle API and the roster UI are BUILT and
verified. **§2 decided and built 2026-10-02 evening: ONE process per character** — her `hermes gateway run`
carries the API server (the app's route) and her channel adapters; `hermes serve` is gone (the first live
Telegram test showed the two-process shape: two memory owners and no shared recent context). §3/§4 **Telegram live 2026-10-02 17:10**: her own bot (@mane_556_bot), token + allowlist in her
`.env`, started from the roster → gateway "Connected to Telegram (polling mode)" in 12 s → first DM
answered through the Gemini lane; her store created, pipeline observed the turn (noop for 'hi').
Discord postponed by the user. Open question: Telegram draft-streaming + final send logged a
"possible duplicate send" warning — if the reply shows twice, set `display.platforms.telegram.streaming: false`
in her config.yaml. `new-companion.ps1` creates the
next character from `templates/companion/`.

Original plan, 2026-10-02. Builds on DECISIONS "companion lifecycle" (manual start/stop, several
active, bindings strictly per character, accounts are the character's own) and "her name 真音".

## 1. One character = one Hermes profile

Hermes already has the unit we need: a **profile** is a HERMES_HOME of its own (`hermes -p <name>`),
and production D:\Hermes runs three Discord bots exactly this way (`hermes -p chatbot gateway run`).
So a 556 character is a profile directory under the app home:

```
home/
├─ config.yaml, SOUL.md, …          the "default" profile (today's single companion; becomes the agency shell)
└─ profiles/
   └─ mane/                          真音 — her HERMES_HOME
      ├─ config.yaml                 model → shim lane, memory.provider: kokoro, gateway platforms
      ├─ kokoro.json                 db: memory/{profile}.db → home/profiles/mane/memory/mane.db
      ├─ SOUL.md, USER.md            her persona; the Producer's name lives in USER.md
      ├─ .env                        TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, allowlists (hers, never shared)
      ├─ plugins/kokoro → ../../../plugins/kokoro   (junction; user plugins are per HERMES_HOME)
      ├─ memory/mane.db, backups/, logs/
      └─ sessions, state.db, …       Hermes's own
```

`setup-vendor.ps1` grows a "new character" step that creates this layout from a template.

## 2. Processes per active character (556d supervisor)

| process | command | serves |
|---|---|---|
| gateway | `hermes gateway run` (HERMES_HOME = her dir, `API_SERVER_KEY/HOST/PORT` in env) | the app (API server platform, `/v1/chat/completions` + sessions API) **and** Telegram / Discord adapters; kokoro memory, single owner |

Decided 2026-10-02: **one process per character, one route for chat and memory**. The app UI and the
channels are peers calling her gateway; nothing else runs Hermes for her. **One conversation**: the app
continues her Telegram DM session by id (556d creates + stamps it when the app speaks first), so history
is shared; 556d shows Telegram turns in the app (session-store follower) and mirrors app turns into
Telegram (plain text, no LLM). Memory is not used for continuity. 556d never becomes the Telegram client.

Shared across characters: the shim (lanes), the embedder sidecar, 556d itself. Per character: her API
port and key, her gateway process, the store, the accounts.

Lifecycle API in 556d: `GET /api/companions` (roster: name, active, ports, bound channels),
`POST /api/companions/{name}/start`, `POST /api/companions/{name}/stop`; app close stops all.
The office window gets the roster; the chat/memory/avatar surfaces bind to the selected active one.

## 3. Accounts and binding (what only the Producer can create)

Telegram (her own bot account):
1. @BotFather → `/newbot` → name 真音, username e.g. `mane_556_bot` → token → `TELEGRAM_BOT_TOKEN`.
2. `TELEGRAM_ALLOWED_USERS=<your numeric id>` (from @userinfobot) so only the Producer can DM her at first.
3. DM-first; group chats later (`telegram.allowed_chats`).

Discord (her own bot account):
1. Developer Portal → New Application 真音 → Bot → token → `DISCORD_BOT_TOKEN`.
2. Privileged intents: **Message Content Intent on** (production gotcha), Server Members if allowlists by role.
3. Invite URL: scopes `bot` (+ `applications.commands`), permissions: read/send messages, threads, reactions.
4. `DISCORD_ALLOWED_USERS=<your id>`; `discord.require_mention` stays on in servers; DMs first.

Either `hermes -p mane gateway setup` (wizard) or write her `.env` + `config.yaml` directly
(config-as-files is the 556 way). Tokens never leave her profile directory; nothing is shared with
the default profile or with production D:\Hermes.

## 4. Test plan (text only)

1. Create `home/profiles/mane/` with SOUL/USER/kokoro.json/.env; `hermes -p mane` one-shot smoke.
2. `hermes -p mane gateway run` → DM her on Telegram → reply arrives; same on Discord.
3. Memory is hers across surfaces: tell her a fact on Telegram, open the app bound to Mane, ask →
   recall shows it (same `mane.db`); the memory page lists it.
4. Lifecycle: stop her from the roster → the bot goes offline; start again → online; app close → all off.
5. Guardrails: a stranger DMing her gets nothing (allowlist); a message to the default profile's
   accounts (none) does not reach her.

Out of scope now: voice over channels, group-chat etiquette, proactive pushes from the gateway into
the app window (that is the "556 platform adapter" item), multi-human memory attribution in servers
(the L2 pipeline will need the speaker identity; the store's subject rule already keeps 製作人 vs others).

## 5. What I'll need from you

The two tokens (into her `.env`, I never need to see them in chat), your Telegram numeric id and
Discord user id for the allowlists, and the Discord server (or DM only) to test in.
