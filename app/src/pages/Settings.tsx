import { useEffect, useState } from 'react';
import { api, Settings as S } from '../api';
import { VoiceSettings } from './VoiceSettings';
import { DevSettings } from './DevSettings';
import { t } from '../i18n';

// 設定 — the global layer: you (name, reply language), the app (character window on start, Telegram
// mirror), the voice connectors (home/voice.json) and the backend developer knobs (556d.toml, shim).
// Everything that belongs to one character is on that character's page under 名單 (Character.tsx).
// Note: 556d applies your name and reply language into the character on stage (people/你.md,
// kokoro.json of the selected profile); the global page saves the value once and restarts that one.
export function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [dev, setDev] = useState<boolean>(() => { try { return localStorage.getItem('556.dev') === '1'; } catch { return false; } });
  const toggleDev = (on: boolean) => { setDev(on); try { localStorage.setItem('556.dev', on ? '1' : '0'); } catch { /* ignore */ } };

  useEffect(() => {
    api.settings().then((r) => setS(r.settings)).catch((e) => setNotice({ kind: 'err', text: String(e) }));
  }, []);

  if (!s) return <p className="p-4 opacity-60">{t('status.connecting')}</p>;

  const set = <K extends keyof S>(k: K, v: S[K]) => setS({ ...s, [k]: v });

  async function save() {
    if (!s) return;
    setSaving(true);
    setNotice(null);
    try {
      const r = await api.updateSettings({ your_name: s.your_name, reply_language: s.reply_language, mirror_to_telegram: s.mirror_to_telegram, show_avatar_on_start: s.show_avatar_on_start });
      setS(r.settings);
      setRestartNeeded(r.restart_required);
      setNotice({ kind: 'ok', text: r.restart_required ? t('settings.saved_restart') : t('settings.saved') });
    } catch (e) {
      setNotice({ kind: 'err', text: String(e) });
    } finally {
      setSaving(false);
    }
  }

  async function restart() {
    await api.restartHermes();
    setRestartNeeded(false);
    setNotice({ kind: 'ok', text: t('settings.restarting') });
  }

  const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-pink-400/60';
  const label = 'block text-xs opacity-70 mb-1';

  return (
    <div className="h-full overflow-y-auto p-5 max-w-2xl space-y-5">
      <p className="text-xs opacity-60">{t('settings.global_note')}</p>

      <section className="space-y-3">
        <h2 className="font-semibold">{t('settings.you')}</h2>
        <div>
          <label className={label}>{t('settings.your_name')}</label>
          <input className={field} value={s.your_name ?? ''} placeholder={t('settings.you_unnamed')} onChange={(e) => set('your_name', e.target.value)} />
          <p className="text-xs opacity-60 mt-1">{t('settings.you_note')}</p>
        </div>
        <div>
          <label className={label}>{t('settings.reply_language')}</label>
          <select className={field} value={s.reply_language ?? ''} onChange={(e) => set('reply_language', e.target.value)}>
            <option value="">{t('settings.reply_language_follow')}</option>
            <option value="en">English</option>
            <option value="zh-CN">简体中文</option>
            <option value="zh-TW">繁體中文</option>
            <option value="ja">日本語</option>
          </select>
          <p className="text-xs opacity-60 mt-1">{t('settings.reply_language_note')}</p>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">{t('settings.app')}</h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.show_avatar_on_start} onChange={(e) => set('show_avatar_on_start', e.target.checked)} />
          {t('settings.show_avatar_on_start')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={s.mirror_to_telegram ?? true} onChange={(e) => set('mirror_to_telegram', e.target.checked)} />
          {t('settings.mirror_to_telegram')}
        </label>
        <p className="text-xs opacity-60">{t('settings.mirror_note')}</p>
      </section>

      <div className="flex items-center gap-3">
        <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={saving} onClick={save}>{t('settings.save')}</button>
        {restartNeeded && <button className="px-4 py-2 rounded-xl bg-amber-500/70 hover:bg-amber-500 text-white" onClick={restart}>{t('settings.restart')}</button>}
        {notice && <span className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</span>}
      </div>

      <VoiceSettings />

      <label className="flex items-center gap-2 text-sm opacity-80">
        <input type="checkbox" checked={dev} onChange={(e) => toggleDev(e.target.checked)} />
        {t('dev.toggle')}
      </label>
      {dev && <DevSettings groups={['backend']} onRestart={restart} />}
    </div>
  );
}
