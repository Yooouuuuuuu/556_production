// Small audio helpers for the voice modes: PCM -> WAV for the STT upload, and playback with a
// completion promise (the office window is the one speaker; the avatar only lip-syncs).

export function encodeWav(samples: Float32Array, sampleRate = 16000): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

export function concatFloat32(parts: Float32Array[]): Float32Array {
  const out = new Float32Array(parts.reduce((n, a) => n + a.length, 0));
  let o = 0;
  for (const a of parts) { out.set(a, o); o += a.length; }
  return out;
}

export function playUrl(url: string): { done: Promise<void>; stop(): void } {
  const el = new Audio(url);
  el.crossOrigin = 'anonymous';
  let resolve!: () => void;
  const done = new Promise<void>((r) => { resolve = r; });
  el.onended = () => resolve();
  el.onerror = () => resolve();
  el.play().catch(() => resolve());
  return { done, stop() { try { el.pause(); el.src = ''; } catch { /* already gone */ } resolve(); } };
}
