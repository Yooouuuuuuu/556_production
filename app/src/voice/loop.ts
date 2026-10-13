// Conversation mode orchestrator — the strict 1:1 pipeline from voice_agent_vad.py:
//   complete turn -> ONE transcription -> ONE chat turn -> ONE synthesis -> ONE playback,
// turns cut while an exchange runs queue FIFO. The app's text box is locked while this runs.
import { create } from 'zustand';
import { api } from '../api';
import type { VoiceHandsFree } from '../api';
import { useStore } from '../store';
import { playUrl } from './audio';
import { startHandsFree, type HandsFreeController } from './handsfree';

export type Phase = 'off' | 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking';

type VoiceState = {
  handsfree: boolean;
  phase: Phase;
  queue: number;
  last: string | null;   // last transcript or note
  error: string | null;
  start(): Promise<void>;
  stop(): void;
};

let ctl: HandsFreeController | null = null;
let params: VoiceHandsFree | null = null;
const turns: Blob[] = [];
let pumping = false;
let player: ReturnType<typeof playUrl> | null = null;

export const useVoice = create<VoiceState>((set, get) => ({
  handsfree: false,
  phase: 'off',
  queue: 0,
  last: null,
  error: null,

  async start() {
    if (get().handsfree) return;
    set({ error: null, last: null });
    const v = await api.voice();
    if (v.voice.stt.kind === 'none' || v.voice.tts.kind === 'none') throw new Error('STT and TTS must both be connected (設定 → 語音連線)');
    params = v.voice.handsfree ?? null;
    if (!params) throw new Error('no hands-free parameters');
    set({ handsfree: true, phase: 'idle' });
    try {
      ctl = await startHandsFree(params, {
        onListening: () => { if (get().phase === 'idle') set({ phase: 'listening' }); },
        onIdle: () => { if (get().phase === 'listening') set({ phase: 'idle' }); },
        onTurn: (wav) => { turns.push(wav); set({ queue: turns.length }); void pump(); },
        onLog: (line) => set({ last: line }),
      });
    } catch (e) {
      set({ handsfree: false, phase: 'off', error: String(e) });
      throw e;
    }
  },

  stop() {
    ctl?.stop();
    ctl = null;
    turns.length = 0;
    player?.stop();
    set({ handsfree: false, phase: 'off', queue: 0 });
  },
}));

async function pump(): Promise<void> {
  if (pumping) return;
  pumping = true;
  try {
    while (turns.length && useVoice.getState().handsfree) {
      const wav = turns.shift()!;
      useVoice.setState({ queue: turns.length, phase: 'transcribing' });
      let text = '';
      try {
        text = (await api.transcribe(wav)).text.trim();
      } catch (e) {
        useVoice.setState({ error: String(e) });
        continue;
      }
      if (!text) { useVoice.setState({ last: '（聽不清楚，略過）' }); continue; }
      useVoice.setState({ phase: 'thinking', last: text, error: null });
      const reply = await sendAndWait(text);
      if (!reply || !useVoice.getState().handsfree) continue;
      useVoice.setState({ phase: 'speaking' });
      if (params?.echo_guard) ctl?.pause();
      try {
        const s = await api.speak(reply);
        await playback(s.audio_url, s.bytes ?? 0);
      } catch (e) {
        useVoice.setState({ error: String(e) });
      } finally {
        await api.speakEnd().catch(() => {});
        if (params?.echo_guard) ctl?.resume();
      }
    }
  } finally {
    pumping = false;
    if (useVoice.getState().handsfree) useVoice.setState({ phase: 'idle' });
  }
}

// The avatar window plays and lip-syncs the reply; if no window claims playback within 1.5 s
// (avatar not created), the office plays it itself.
async function playback(url: string, bytes: number): Promise<void> {
  const claimed = await waitStore((s) => !!s.speaking?.playing, 1500);
  if (!claimed) {
    player = playUrl(url);
    await player.done;
    player = null;
    return;
  }
  const est = (Math.max(5, bytes / 16000) * 1.5 + 5) * 1000; // mp3 ≈ 16 KB/s
  await waitStore((s) => s.speaking === null, est);
}

function waitStore(pred: (s: ReturnType<typeof useStore.getState>) => boolean, ms: number): Promise<boolean> {
  return new Promise((resolve) => {
    if (pred(useStore.getState())) { resolve(true); return; }
    let t: ReturnType<typeof setTimeout> | null = null;
    const unsub = useStore.subscribe((s) => { if (pred(s)) { unsub(); if (t) clearTimeout(t); resolve(true); } });
    t = setTimeout(() => { unsub(); resolve(false); }, ms);
  });
}

// One chat turn through the normal route (voice flag -> spoken style); the reply comes back on
// the hub as chat.complete for this companion, never through the POST response.
function sendAndWait(text: string): Promise<string> {
  return new Promise((resolve) => {
    const n0 = useStore.getState().lastReply?.n ?? 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const unsub = useStore.subscribe((s) => {
      const r = s.lastReply;
      if (r && r.n > n0 && !r.source) { // her reply to the app, not a Telegram turn the follower surfaced
        unsub();
        if (timer) clearTimeout(timer);
        resolve(r.status === 'stop' ? r.text : '');
      }
    });
    timer = setTimeout(() => { unsub(); resolve(''); }, 5 * 60 * 1000);
    api.send(text, 'office-voice', true).catch((e) => {
      unsub();
      if (timer) clearTimeout(timer);
      useVoice.setState({ error: String(e) });
      resolve('');
    });
  });
}
