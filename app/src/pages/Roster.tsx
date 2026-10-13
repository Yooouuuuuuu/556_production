import { useCallback, useEffect, useState } from 'react';
import { api, CompanionInfo } from '../api';
import { useStore } from '../store';
import { t } from '../i18n';
import { Character } from './Character';

// The roster: every character under home/profiles. Nothing starts by itself — you start and stop
// each one here; several can be active at once. "Switch" puts a character in the chat window (and
// therefore on the avatar). A character's own settings open from its row (Character.tsx); 556d edits
// the character on stage, so opening the page switches the stage to that character first.
export function Roster() {
  const [items, setItems] = useState<CompanionInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const { selected, setSelected } = useStore();

  const load = useCallback(async () => {
    try {
      const r = await api.companions();
      setItems(r.companions ?? []);
      if (r.selected !== selected) setSelected(r.selected);
    } catch (e) {
      setNotice(String(e));
    }
  }, [selected, setSelected]);

  useEffect(() => { load(); const id = setInterval(load, 3000); return () => clearInterval(id); }, [load]);

  async function act(name: string, action: 'start' | 'stop') {
    setBusy(name);
    setNotice(null);
    try {
      await api.companionAction(name, action);
      await load();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function pick(name: string) {
    try {
      await api.select(name);
      setSelected(name);
      return true;
    } catch (e) {
      setNotice(String(e));
      return false;
    }
  }

  async function openPage(name: string) {
    if (name !== selected && !(await pick(name))) return;
    setOpen(name);
  }

  const current = open ? items.find((c) => c.name === open) : undefined;
  if (open && current) return <Character info={current} onBack={() => setOpen(null)} />;

  return (
    <div className="h-full overflow-y-auto p-5 max-w-2xl space-y-4">
      <div>
        <h2 className="font-semibold">{t('roster.title')}</h2>
        <p className="text-xs opacity-60 mt-1">{t('roster.note')}</p>
      </div>
      {notice && <p className="text-sm text-red-300">{notice}</p>}
      {items.length === 0 && <p className="opacity-60">{t('roster.empty')}</p>}
      <ul className="space-y-2">
        {items.map((c) => (
          <li key={c.name} className={`rounded-xl px-4 py-3 bg-white/5 flex items-center gap-3 ${c.name === selected ? 'ring-1 ring-pink-400/60' : ''}`}>
            <span className={`w-2.5 h-2.5 rounded-full ${c.active ? (c.hermes_connected ? 'bg-green-400' : 'bg-amber-400') : 'bg-white/20'}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <button className="font-medium hover:underline" onClick={() => openPage(c.name)}>{c.display_name || c.name}</button>
                <span className="text-xs opacity-50">{c.name}</span>
                {c.name === selected && <span className="text-xs px-1.5 rounded bg-pink-500/30">{t('roster.on_stage')}</span>}
              </div>
              <div className="text-xs opacity-60 mt-0.5 flex gap-3">
                <span>{c.active ? (c.stopping ? t('roster.stopping') : c.hermes_connected ? t('roster.active') : t('roster.starting')) : t('roster.inactive')}</span>
                {(c.channels ?? []).length > 0 && <span>{t('roster.channels')}: {(c.channels ?? []).join(', ')}{c.active && c.gateway ? ` (${t('roster.gateway_on')})` : ''}</span>}
                {(c.channels ?? []).length === 0 && <span>{t('roster.no_channels')}</span>}
              </div>
            </div>
            <button className="px-3 py-1 rounded-lg text-sm bg-white/10 hover:bg-white/20" onClick={() => openPage(c.name)}>{t('roster.details')}</button>
            {c.name !== selected && <button className="px-3 py-1 rounded-lg text-sm bg-white/10 hover:bg-white/20" onClick={() => pick(c.name)}>{t('roster.switch')}</button>}
            {c.active
              ? <button className="px-3 py-1 rounded-lg text-sm bg-red-500/20 hover:bg-red-500/50 disabled:opacity-40" disabled={busy === c.name || c.stopping} onClick={() => act(c.name, 'stop')}>{t('roster.stop')}</button>
              : <button className="px-3 py-1 rounded-lg text-sm bg-pink-500/70 hover:bg-pink-500 text-white disabled:opacity-40" disabled={busy === c.name} onClick={() => act(c.name, 'start')}>{t('roster.start')}</button>}
          </li>
        ))}
      </ul>
    </div>
  );
}
