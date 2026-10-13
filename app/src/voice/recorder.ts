// Mode 1 — press to record, press again to stop: one MediaRecorder clip, decoded and resampled to
// 16 kHz mono WAV (the same container conversation mode sends — Fish's ASR rejects webm/opus),
// sent to STT; the text lands in the composer for you to send.
import { encodeWav } from './audio';

export class PushToTalk {
  private rec: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];

  get active(): boolean { return !!this.rec && this.rec.state === 'recording'; }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    this.rec = new MediaRecorder(this.stream, { mimeType: mime });
    this.chunks = [];
    this.rec.ondataavailable = (e) => { if (e.data.size) this.chunks.push(e.data); };
    this.rec.start(250);
  }

  async stop(): Promise<Blob> {
    const clip = await this.stopRaw();
    if (clip.size < 1000) throw new Error('no audio recorded');
    return toWav16k(clip);
  }

  private stopRaw(): Promise<Blob> {
    return new Promise((resolve) => {
      const rec = this.rec;
      if (!rec) { resolve(new Blob([], { type: 'audio/webm' })); return; }
      rec.onstop = () => {
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.rec = null;
        resolve(new Blob(this.chunks, { type: rec.mimeType || 'audio/webm' }));
      };
      rec.stop();
    });
  }
}

// Decode whatever the browser recorded and render it as 16 kHz mono PCM.
async function toWav16k(blob: Blob): Promise<Blob> {
  const ac = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await ac.decodeAudioData(await blob.arrayBuffer());
  } finally {
    await ac.close();
  }
  const frames = Math.max(1, Math.ceil(decoded.duration * 16000));
  const oac = new OfflineAudioContext(1, frames, 16000);
  const src = oac.createBufferSource();
  src.buffer = decoded;
  src.connect(oac.destination);
  src.start();
  const out = await oac.startRendering();
  return encodeWav(out.getChannelData(0), 16000);
}
