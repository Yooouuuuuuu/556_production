import { useEffect, useState } from 'react';
import { api, Settings as S } from '../api';
import { t } from '../i18n';

// Settings tab: bound to 556d /api/settings. Hermes-facing values need a restart (button here);
// changing the embedder additionally requires re-embedding the memory store.
export function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);

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
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">{t('settings.brain')}</h2>
        <div>
          <label className={label}>{t('settings.model_lane')}</label>
          <input className={field} list="lanes" value={s.model_lane} onChange={(e) => set('model_lane', e.target.value)} />
          <datalist id="lanes"><option value="auto/556" /><option value="auto/pro" /><option value="auto/code" /></datalist>
        </div>
        <div>
          <label className={label}>{t('settings.context_turns')}</label>
          <input className={field} type="number" min={2} max={200} value={s.context_turns} onChange={(e) => set('context_turns', Number(e.target.value))} />
        </div>
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
          <label className={label}>{t('settings.embedder_model')}</label>
          <input className={field} value={s.embedder_model} onChange={(e) => set('embedder_model', e.target.value)} />
          <p className="text-xs opacity-60 mt-1">{t('settings.embedder_note')}</p>
        </div>
      </section>

      <div className="flex items-center gap-3 pt-2">
        <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={saving} onClick={save}>{t('settings.save')}</button>
        {restartNeeded && <button className="px-4 py-2 rounded-xl bg-amber-500/70 hover:bg-amber-500 text-white" onClick={restart}>{t('settings.restart')}</button>}
        {notice && <span className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</span>}
      </div>
    </div>
  );
}
