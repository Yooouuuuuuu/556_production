import { useEffect, useState } from 'react';
import { api, VoiceConfig, VoiceHandsFree, VoiceProvider } from '../api';
import { t } from '../i18n';

// Cloud STT / TTS connectors. Without `companion`: the global connectors (home/voice.json) and the
// conversation-mode parameters. With `companion`: that character's override (profile voice.json) —
// each block may say "inherit" (use the global connector), "none", or a provider of its own; the
// effective result 556d will use is shown under each block. Two voice modes live in the chat:
// press-to-record (STT into the composer) and conversation mode (VAD loop, spoken answers).
const empty = (kind = 'none'): VoiceProvider => ({ kind, base_url: '', api_key: '', model: '', voice: '', format: 'mp3', language: '' });
const defaultHF = (): VoiceHandsFree => ({ threshold: 0.5, min_silence_ms: 500, pre_roll_s: 0.4, grace_s: 0.9, min_turn_s: 0.35, max_turn_s: 30, echo_guard: true, spoken_style: '' });

export function VoiceSettings({ companion }: { companion?: string }) {
  const base = companion ? 'inherit' : 'none';
  const [cfg, setCfg] = useState<VoiceConfig>({ tts: empty(base), stt: empty(base), handsfree: defaultHF() });
  const [effective, setEffective] = useState<VoiceConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [audio, setAudio] = useState<string | null>(null);

  const take = (r: { voice: VoiceConfig; effective?: VoiceConfig }) => {
    setCfg({ tts: { ...empty(base), ...r.voice.tts, api_key: '' }, stt: { ...empty(base), ...r.voice.stt, api_key: '' }, handsfree: { ...defaultHF(), ...(r.voice.handsfree ?? {}) } });
    setEffective(r.effective ?? null);
  };
  useEffect(() => {
    setResult(null);
    setAudio(null);
    api.voice(companion).then(take).catch(() => {});
  }, [companion]);

  const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-accent/60';
  const label = 'block text-xs opacity-70 mb-1';
  const upd = (side: 'tts' | 'stt', k: keyof VoiceProvider, v: string) => setCfg({ ...cfg, [side]: { ...cfg[side], [k]: v } });
  const hf = cfg.handsfree ?? defaultHF();
  const updHF = (k: keyof VoiceHandsFree, v: number | boolean | string) => setCfg({ ...cfg, handsfree: { ...hf, [k]: v } });
  const num = (k: keyof VoiceHandsFree, name: string, step: number) => (
    <div><label className={label}>{name}</label><input className={field} type="number" step={step} value={hf[k] as number} onChange={(e) => updHF(k, Number(e.target.value))} /></div>
  );

  async function save() {
    setSaving(true);
    setResult(null);
    try {
      const r = await api.updateVoice(companion ? { tts: cfg.tts, stt: cfg.stt } : cfg, companion);
      take(r);
      setResult(t('settings.voice_saved'));
    } catch (e) {
      setResult(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    setResult(null);
    setAudio(null);
    try {
      const r = await api.testVoice(undefined, companion);
      const parts = [
        `TTS: ${r.tts.ok ? `ok ${r.tts.ms} ms, ${r.tts.bytes} bytes` : r.tts.error}`,
        `STT: ${r.stt.ok ? `ok ${r.stt.ms} ms → 「${r.stt.text}」` : r.stt.error}`,
      ];
      setResult(parts.join('　|　'));
      if (r.tts.audio_data_url) setAudio(r.tts.audio_data_url);
    } catch (e) {
      setResult(String(e));
    } finally {
      setTesting(false);
    }
  }

  const kindLabel = (k: string) => (k === 'inherit' ? t('settings.voice_kind_inherit') : k === 'none' ? t('settings.voice_kind_none') : k === 'fish-audio' ? t('settings.voice_kind_fish') : t('settings.voice_kind_openai'));
  const effLine = (side: 'tts' | 'stt') => {
    const p = effective?.[side];
    if (!p) return null;
    const bits = [kindLabel(p.kind), p.model, side === 'tts' ? p.voice : p.language].filter(Boolean);
    return <p className="text-[11px] opacity-50">{t('settings.voice_effective')}: {bits.join(' · ')}</p>;
  };

  const block = (side: 'tts' | 'stt', title: string) => {
    const p = cfg[side];
    const off = p.kind === 'none' || p.kind === 'inherit';
    return (
      <div className="space-y-2 rounded-xl bg-white/5 p-3">
        <h3 className="text-sm font-medium">{title}</h3>
        <div>
          <label className={label}>{t('settings.voice_kind')}</label>
          <select className={field} value={p.kind} onChange={(e) => upd(side, 'kind', e.target.value)}>
            {companion && <option value="inherit">{t('settings.voice_kind_inherit')}</option>}
            <option value="none">{t('settings.voice_kind_none')}</option>
            <option value="openai-compatible">{t('settings.voice_kind_openai')}</option>
            <option value="fish-audio">{t('settings.voice_kind_fish')}</option>
          </select>
        </div>
        {!off && (
          <>
            <div><label className={label}>{t('settings.voice_base_url')}</label><input className={field} value={p.base_url} placeholder={p.kind === 'fish-audio' ? 'https://api.fish.audio' : 'https://api.openai.com/v1'} onChange={(e) => upd(side, 'base_url', e.target.value)} /></div>
            <div><label className={label}>{t('settings.voice_api_key')} {p.api_key_set && <span className="opacity-60">{t('settings.voice_api_key_set')}</span>}</label><input className={field} type="password" value={p.api_key ?? ''} onChange={(e) => upd(side, 'api_key', e.target.value)} /></div>
            <div><label className={label}>{t('settings.voice_model')}</label><input className={field} value={p.model} placeholder={p.kind === 'fish-audio' ? (side === 'tts' ? 's1' : 'transcribe-1') : side === 'tts' ? 'gpt-4o-mini-tts' : 'whisper-large-v3-turbo'} onChange={(e) => upd(side, 'model', e.target.value)} /></div>
            {side === 'tts' && <div><label className={label}>{t('settings.voice_voice')}</label><input className={field} value={p.voice ?? ''} placeholder={p.kind === 'fish-audio' ? t('settings.voice_reference_id') : 'alloy'} onChange={(e) => upd(side, 'voice', e.target.value)} /></div>}
            {side === 'stt' && <div><label className={label}>{t('settings.voice_language')}</label><input className={field} value={p.language ?? ''} placeholder="zh" onChange={(e) => upd(side, 'language', e.target.value)} /></div>}
          </>
        )}
        {companion && effLine(side)}
      </div>
    );
  };

  return (
    <section className="space-y-3">
      <h2 className="font-semibold">{companion ? t('settings.voice_character') : t('settings.voice')}</h2>
      <p className="text-xs opacity-60">{companion ? t('settings.voice_character_note') : t('settings.voice_note')}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {block('tts', t('settings.tts'))}
        {block('stt', t('settings.stt'))}
      </div>
      {!companion && (
        <div className="space-y-2 rounded-xl bg-white/5 p-3">
          <h3 className="text-sm font-medium">{t('settings.voice_handsfree')}</h3>
          <p className="text-xs opacity-60">{t('settings.voice_handsfree_note')}</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {num('threshold', t('settings.voice_hf_threshold'), 0.05)}
            {num('min_silence_ms', t('settings.voice_hf_silence'), 50)}
            {num('pre_roll_s', t('settings.voice_hf_preroll'), 0.1)}
            {num('grace_s', t('settings.voice_hf_grace'), 0.1)}
            {num('min_turn_s', t('settings.voice_hf_minturn'), 0.05)}
            {num('max_turn_s', t('settings.voice_hf_maxturn'), 5)}
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={hf.echo_guard} onChange={(e) => updHF('echo_guard', e.target.checked)} />{t('settings.voice_hf_echo')}</label>
          <div><label className={label}>{t('settings.voice_hf_style')}</label><textarea className={field} rows={2} value={hf.spoken_style} onChange={(e) => updHF('spoken_style', e.target.value)} /></div>
        </div>
      )}
      <div className="flex items-center gap-3">
        <button className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 disabled:opacity-40" disabled={saving} onClick={save}>{t('settings.voice_save')}</button>
        <button className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 disabled:opacity-40" disabled={testing} onClick={test}>{testing ? t('settings.voice_testing') : t('settings.voice_test')}</button>
        {audio && <audio controls src={audio} className="h-8" />}
      </div>
      {result && <p className="text-sm opacity-80">{result}</p>}
    </section>
  );
}
