// Mode 2 — conversation mode: the mic stays open, Silero VAD (in the browser, via
// @ricky0123/vad-web) cuts speech, and the endpointing from the earlier voice_agent_vad.py is laid
// on top: a grace window after each cut so mid-sentence pauses merge into ONE turn, a pre-roll so
// the first syllable survives, a minimum so blips are dropped, a hard cap per turn.
import { MicVAD } from '@ricky0123/vad-web';
import { BASE } from '../api';
import type { VoiceHandsFree } from '../api';
import { concatFloat32, encodeWav } from './audio';

const SR = 16000;
const FRAME_MS = 32; // silero v5: 512 samples at 16 kHz

export type HandsFreeHandlers = {
  onTurn(wav: Blob, seconds: number): void;
  onListening(): void;
  onIdle(): void;
  onLog?(line: string): void;
};

export type HandsFreeController = { pause(): void; resume(): void; stop(): void };

export async function startHandsFree(p: VoiceHandsFree, h: HandsFreeHandlers): Promise<HandsFreeController> {
  let pending: Float32Array[] = [];
  let grace: ReturnType<typeof setTimeout> | null = null;
  let paused = false;
  const seconds = () => pending.reduce((n, a) => n + a.length, 0) / SR;

  const finalize = () => {
    if (grace) { clearTimeout(grace); grace = null; }
    if (!pending.length) return;
    const secs = seconds();
    const all = concatFloat32(pending);
    pending = [];
    h.onIdle();
    if (secs >= p.min_turn_s) h.onTurn(encodeWav(all, SR), secs);
    else h.onLog?.(`too short (${secs.toFixed(2)} s), ignored`);
  };

  const vad = await MicVAD.new({
    model: 'v5',
    baseAssetPath: BASE + '/vad/',
    onnxWASMBasePath: BASE + '/vad/',
    positiveSpeechThreshold: p.threshold,
    negativeSpeechThreshold: Math.max(0.05, p.threshold - 0.15),
    redemptionMs: Math.max(FRAME_MS, p.min_silence_ms),           // silence that closes a cut
    preSpeechPadMs: Math.max(FRAME_MS, p.pre_roll_s * 1000),       // keep the first syllable
    minSpeechMs: Math.max(FRAME_MS, p.min_turn_s * 1000),          // blips -> onVADMisfire
    onSpeechStart: () => {
      if (grace) { clearTimeout(grace); grace = null; } // voice resumed: same turn continues
      h.onListening();
    },
    onSpeechEnd: (audio: Float32Array) => {
      pending.push(audio);
      if (seconds() >= p.max_turn_s) { finalize(); return; }
      grace = setTimeout(finalize, Math.max(0, p.grace_s) * 1000);
    },
    onVADMisfire: () => { if (!pending.length) h.onIdle(); },
  });
  vad.start();

  return {
    pause() {
      // echo guard: whatever the mic caught while she speaks is hers, not the Producer's
      paused = true;
      vad.pause();
      if (grace) { clearTimeout(grace); grace = null; }
      pending = [];
    },
    resume() { if (paused) { paused = false; vad.start(); } },
    stop() { if (grace) clearTimeout(grace); pending = []; vad.destroy(); },
  };
}
