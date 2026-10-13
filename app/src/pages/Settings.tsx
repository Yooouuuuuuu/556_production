import { useEffect, useState } from 'react';
import { api, Settings as S, VoiceConfig } from '../api';
import { VoiceSettings } from './VoiceSettings';
import { DevSettings } from './DevSettings';
import { t } from '../i18n';

// Settings tab: bound to 556d /api/settings. Hermes-facing values need a restart (button here);
// changing the embedder additionally requires re-embedding the memory store.
export function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [dev, setDev] = useState<boolean>(() => { try { return localStorage.getItem('556.dev') === '1'; } catch { return false; } });
  const toggleDev = (on: boolean) => { setDev(on); try { localStorage.setItem('556.dev', on ? '1' : '0'); } catch { /* ignore */ } };

  useEffect(() => {
    api.settings().then((r) => setS(r.settings)).catch((e) => setNotice({ kind: 'err', text: String(e) }));
    api.models().then((r) => setModels(r.models.flatMap((m) => m.models))).catch(() => {});
  }, []);

  if (!s) return <p className="p-4 opacity-60">{t('status.connecting')}</p>;

  const set = <K extends keyof S>(k: K, v: S[K]) => setS({ ...s, [k]: v });

  async function save() {
    if (!s) return;
    setSaving(true);
    setNotice(null);
    try {
      const r = await api.updateSettings(s);
      setS(r.settings);
      setRestartNeeded(r.restart_required);
      setNotice({
        kind: r.reembed_required ? 'warn' : 'ok',
        text: r.reembed_required ? t('settings.saved_reembed') : r.restart_required ? t('settings.saved_restart') : t('settings.saved'),
      });
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
      <section className="space-y-3">
        <h2 className="font-semibold">{t('settings.producer')}</h2>
        <div>
          <label className={label}>{t('settings.producer_name')}</label>
          <input className={field} value={s.producer_name ?? ''} placeholder={t('settings.producer_unnamed')} onChange={(e) => set('producer_name', e.target.value)} />
          <p className="text-xs opacity-60 mt-1">{t('settings.producer_note')}</p>
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
        <h2 className="font-semibold">{t('settings.companion')}</h2>
        <div>
          <label className={label}>{t('settings.companion_name')}</label>
          <input className={field} value={s.companion_name} placeholder={t('settings.unnamed')} onChange={(e) => set('companion_name', e.target.value)} />
        </div>
        <div>
          <label className={label}>{t('settings.avatar_model')}</label>
          <select className={field} value={s.avatar_model} onChange={(e) => set('avatar_model', e.target.value)}>
            {[s.avatar_model, ...models.filter((m) => m !== s.avatar_model)].map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
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

      <section className="space-y-3">
        <h2 className="font-semibold">{t('settings.memory')}</h2>
        <div>
          <label className={label}>{t('settings.memory_language')}</label>
          <select className={field} value={s.memory_language} onChange={(e) => set('memory_language', e.target.value)}>
            <option value="zh-TW">繁體中文 (zh-TW)</option>
            <option value="en">English (en)</option>
          </select>
          <p className="text-xs opacity-60 mt-1">{t('settings.memory_language_note')}</p>
        </div>
        <div>
          <label className={label}>{t('settings.context_turns')}</label>
          <input className={field} type="number" min={2} max={200} value={s.context_turns} onChange={(e) => set('context_turns', Number(e.target.value))} />
        </div>
      </section>

      <VoiceSettings />

      <label className="flex items-center gap-2 text-sm opacity-80">
        <input type="checkbox" checked={dev} onChange={(e) => toggleDev(e.target.checked)} />
        {t('dev.toggle')}
      </label>
      {dev && <DevSettings onRestartHer={restart} />}

      <div className="flex items-center gap-3 pt-2">
        <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={saving} onClick={save}>{t('settings.save')}</button>
        {restartNeeded && <button className="px-4 py-2 rounded-xl bg-amber-500/70 hover:bg-amber-500 text-white" onClick={restart}>{t('settings.restart')}</button>}
        {notice && <span className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</span>}
      </div>
    </div>
  );
}
