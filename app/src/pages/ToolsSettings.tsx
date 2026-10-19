import { useEffect, useState } from 'react';
import { api, ToolExtension } from '../api';
import { t } from '../i18n';

// What she can DO besides talking. Baseline = no tools (0.8.6: memory is injected, not a tool). Extensions are per character,
// written into her config; a restart applies them (no hot toggling by design).
export function ToolsSettings({ onChanged }: { onChanged(): void }) {
  const [exts, setExts] = useState<ToolExtension[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.tools().then((r) => setExts(r.extensions)).catch(() => setExts([]));
  }, []);

  async function toggle(e: ToolExtension) {
    setBusy(e.key);
    setError(null);
    try {
      const r = await api.setTool(e.key, !e.enabled);
      setExts(r.extensions);
      onChanged();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="font-semibold">{t('settings.tools')}</h2>
      <p className="text-xs opacity-60">{t('settings.tools_note')}</p>
      <div className="space-y-2 rounded-xl bg-white/5 p-3">
        <div className="flex items-center gap-2 text-sm opacity-80">
          <input type="checkbox" checked disabled />
          <span>{t('settings.tools_baseline')}</span>
        </div>
        {exts.map((e) => (
          <label key={e.key} className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={e.enabled} disabled={busy === e.key} onChange={() => toggle(e)} />
            <span>
              <span className="font-medium">{e.label}</span>
              {e.acts_in_world && <span className="ml-2 text-xs text-amber-300">{t('settings.tools_acts')}</span>}
              <span className="block text-xs opacity-60">{e.help}</span>
            </span>
          </label>
        ))}
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}
    </section>
  );
}
