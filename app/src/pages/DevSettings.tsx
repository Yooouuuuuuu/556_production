import { useEffect, useState } from 'react';
import { api, Knob } from '../api';
import { t } from '../i18n';

// Knobs from 556d's config registry (/api/config), rendered by group. Nothing is fixed in a file;
// everything here is writable. Effects are shown after saving (restart the character / restart the
// app / re-embed / reindex / migrate subject). `groups` picks which groups to show: the global 設定
// page shows the backend group, a character's page shows model + memory (developer tone) and the
// channel bindings as a plain section.
const GROUPS: { id: string; label: string }[] = [
  { id: 'model', label: 'dev.group.model' },
  { id: 'memory', label: 'dev.group.memory' },
  { id: 'channels', label: 'dev.group.channels' },
  { id: 'backend', label: 'dev.group.backend' },
];

export function DevSettings({ groups, tone = 'dev', onRestart }: { groups?: string[]; tone?: 'dev' | 'plain'; onRestart: () => Promise<void> }) {
  const [knobs, setKnobs] = useState<Knob[]>([]);
  const [edits, setEdits] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [effects, setEffects] = useState<Record<string, boolean>>({});

  const load = () => api.config().then((r) => { setKnobs(r.knobs); setEdits({}); }).catch((e) => setNotice(String(e)));
  useEffect(() => { load(); }, []);

  const dev = tone === 'dev';
  const field = `w-full rounded-lg bg-white/5 px-3 py-1.5 text-sm outline-none focus:ring-1 ${dev ? 'focus:ring-amber-400/60' : 'focus:ring-accent/60'}`;

  async function save() {
    if (Object.keys(edits).length === 0) return;
    setSaving(true);
    setNotice(null);
    try {
      const r = await api.updateConfig(edits);
      setEffects(r.effects);
      setNotice(r.errors.length ? r.errors.join('; ') : t('dev.saved'));
      await load();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setSaving(false);
    }
  }

  const val = (k: Knob) => (k.key in edits ? edits[k.key] : k.value ?? '');
  const input = (k: Knob) => {
    const v = val(k);
    switch (k.type) {
      case 'bool':
        return <input type="checkbox" checked={!!v} onChange={(e) => setEdits({ ...edits, [k.key]: e.target.checked })} />;
      case 'select':
        return (
          <select className={field} value={String(v)} onChange={(e) => setEdits({ ...edits, [k.key]: e.target.value })}>
            {(k.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        );
      case 'int':
      case 'float':
        return <input className={field} type="number" step={k.type === 'float' ? 'any' : 1} value={v} onChange={(e) => setEdits({ ...edits, [k.key]: k.type === 'int' ? parseInt(e.target.value || '0', 10) : parseFloat(e.target.value || '0') })} />;
      case 'secret':
        return <input className={field} type="password" placeholder={k.set ? t('dev.secret_set') : ''} value={k.key in edits ? edits[k.key] : ''} onChange={(e) => setEdits({ ...edits, [k.key]: e.target.value })} />;
      default:
        return <input className={field} value={String(v)} onChange={(e) => setEdits({ ...edits, [k.key]: e.target.value })} />;
    }
  };
  const effectLabel = (e: string) => t(`dev.effect.${e}`);
  const shown = GROUPS.filter((g) => !groups || groups.includes(g.id));
  const ring = dev ? 'ring-amber-400/60' : 'ring-accent/60';

  return (
    <section className={dev ? 'space-y-4 rounded-2xl border border-amber-400/40 bg-amber-500/5 p-4' : 'space-y-4'}>
      {dev && (
        <div>
          <h2 className="font-semibold text-amber-200">{t('dev.title')}</h2>
          <p className="text-xs text-amber-200/80 mt-1">{t('dev.warning')}</p>
        </div>
      )}
      {shown.map((g) => {
        const items = knobs.filter((k) => k.group === g.id);
        if (items.length === 0) return null;
        return (
          <div key={g.id} className="space-y-2">
            {(dev || shown.length > 1) && <h3 className="text-sm font-medium opacity-80">{t(g.label)}</h3>}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2">
              {items.map((k) => (
                <div key={k.key} className={k.key in edits ? `rounded-lg ring-1 ${ring} p-1 -m-1` : ''}>
                  <label className="block text-xs opacity-70 mb-0.5">
                    {k.label} {dev && <span className="opacity-50">· {k.key}</span>}
                    {k.effect !== 'none' && <span className="ml-1 opacity-50">· {effectLabel(k.effect)}</span>}
                  </label>
                  {input(k)}
                  {k.help && <p className="text-[11px] opacity-50 mt-0.5">{k.help}</p>}
                </div>
              ))}
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 flex-wrap">
        <button className={`px-4 py-2 rounded-xl text-white disabled:opacity-40 ${dev ? 'bg-amber-500/70 hover:bg-amber-500' : 'bg-accent hover:bg-accent/90'}`} disabled={saving || Object.keys(edits).length === 0} onClick={save}>
          {dev ? t('dev.save') : t('settings.save')} {Object.keys(edits).length > 0 && `(${Object.keys(edits).length})`}
        </button>
        {effects.restart_companion && <button className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20" onClick={onRestart}>{t('settings.restart')}</button>}
        {Object.keys(effects).filter((e) => effects[e]).length > 0 && (
          <span className="text-xs opacity-80">{t('dev.effects')}: {Object.keys(effects).filter((e) => effects[e]).map(effectLabel).join('、')}</span>
        )}
        {notice && <span className="text-sm opacity-80">{notice}</span>}
      </div>
    </section>
  );
}
