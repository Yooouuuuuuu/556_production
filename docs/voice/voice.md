# Voice — two modes in the chat window

Living doc; built 2026-10-03 → 2026-10-06 (0.4.0). Graph: `voice.d2`. Decisions: `../DECISIONS.md`
(2026-10-02 connectors first, 2026-10-03 two modes, Fish Audio first).

## Two modes

- **Mode 1, press-to-record.** 🎙 starts recording, 🎙 again stops. The browser decodes and resamples
  the take to 16 kHz WAV, one transcription runs, and the text lands in the composer for you to send or
  edit. The turn is a normal text turn, no TTS.
- **Mode 2, conversation mode (hands-free).** The mic stays open. Silero VAD runs in the browser
  (`@ricky0123/vad-web`, model v5) and cuts speech; the endpointing from the earlier voice agent sits on
  top: threshold 0.5, a cut after 500 ms of silence, 0.4 s pre-roll so the first syllable survives, a
  0.9 s grace window so a pause inside a sentence merges into one turn, a 0.35 s minimum, a 30 s cap.
  The loop is strictly one-to-one: one transcription → one chat turn → one synthesis → one playback.
  Cuts made while she answers wait in a FIFO; the text box is locked; the echo guard pauses the mic while
  she speaks (for speakers).
- **Voice turns are ordinary turns.** Same session, same memory, same state block, same Telegram mirror.
  The app sends `X-556-Voice: 1`; 556d prepends a spoken-style hint (short, natural, no markdown) as a
  system message in the API request. The avatar window plays the audio and lip-syncs; without it the
  office window plays.

## Connectors (`home/voice.json`, 設定 → 語音連線; per character 角色 → 聲音)

- **A voice per character** (2026-10-14): `home/profiles/<id>/voice.json` holds an override with the same `tts` / `stt`
  shape; a block whose kind is `inherit` uses the global connector, `none` switches that side off for the character,
  and a configured block replaces it with empty fields (base_url, key, model, format, language) filled from the global
  block of the same kind — so one character can be another Fish Audio `reference_id` and nothing else. 556d resolves
  the effective config per request: `?companion=` else the character on stage (`voice.Effective`). Hands-free
  parameters are global.

- **Fish Audio first** (best zh / ja): TTS `POST /v1/tts` with a `reference_id` voice and the `model`
  header (s1 by default; the model is chosen in Settings); ASR `POST /v1/asr` multipart with model
  `transcribe-1`. When both sides are Fish the STT key reuses the TTS key.
- OpenAI-compatible: `/audio/speech`, `/audio/transcriptions`.
- Hands-free parameters live under `handsfree` in `voice.json` and in the dev registry; Settings has a
  TTS → STT round-trip test.
- Reply text is sanitized before TTS (no markdown, no emoji, no code); 556d caches the audio and serves it
  at `/cache/audio/<id>` with CORS for the avatar window.

## What is next

- Built 0.6.0: an event turn (she speaks first) is spoken per the 主動 override — follow the conversation mode,
  always, or never (the store calls the same speak route; the avatar plays it).
- Inner life, stage 7: TTS prosody (pitch, rate) and Live2D parameters driven by her state; micro-expressions
  for suppressed emotions (`../inner-life/inner-life.md` §15).
- Known gap: Fish transcripts come back in simplified Chinese; a zh-TW conversion step is pending.
- Voice over Telegram (voice notes) is future work; channels are text only.
