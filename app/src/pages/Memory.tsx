import { useCallback, useEffect, useState } from 'react';
import { api, MemoryItem, MemoryStats, MemoryTag } from '../api';
import { t } from '../i18n';

// Memory tab: what she remembers about you (KeepsakeDB store of the current profile).
// View + delete only, by design — to change a memory, tell her; the engine dedups and re-embeds.
export function Memory() {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [tags, setTags] = useState<MemoryTag[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [exists, setExists] = useState(true);
  const [q, setQ] = useState('');
  const [tag, setTag] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [layer, setLayer] = useState<'long' | 'short'>('long');
  const [busy, setBusy] = useState<number | null>(null);
  const [queued, setQueued] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.memory({ q, tag, archived: showArchived, limit: 500, layer });
      setExists(r.exists);
      setItems(r.memories);
      setTags(r.tags ?? []);
      setStats(r.stats ?? null);
    } catch (e) {
      setNotice({ kind: 'err', text: String(e) });
    }
  }, [q, tag, showArchived, layer]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { const id = setInterval(load, 10000); return () => clearInterval(id); }, [load]);

  async function remove(m: MemoryItem) {
    if (!window.confirm(`${t('memory.confirm')}\n\n${m.text}`)) return;
    setBusy(m.id);
    setNotice(null);
    try {
      const r = await api.deleteMemory([m.id], 'deleted from the 556 memory page');
      if (r.status === 'done') {
        setItems((xs) => xs.filter((x) => x.id !== m.id));
        setNotice({ kind: 'ok', text: t('memory.deleted') });
        load();
      } else {
        setQueued((s) => new Set(s).add(m.id));
        setNotice({ kind: 'warn', text: t('memory.queued') });
      }
    } catch (e) {
      setNotice({ kind: 'err', text: String(e) });
    } finally {
      setBusy(null);
    }
  }

  const fmtDate = (ts: number) => new Date(ts * 1000).toLocaleDateString();
  const chip = (active: boolean) => `px-2 py-0.5 rounded-full text-xs ${active ? 'bg-accent/40' : 'bg-white/10 hover:bg-white/20'}`;

  if (!exists) return <p className="p-5 opacity-60">{t('memory.no_store')}</p>;

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 pt-4 pb-3 space-y-3 border-b border-white/10">
        <div className="flex items-center gap-3 text-sm">
          <span className="font-semibold">{t('memory.title')}</span>
          {stats && (
            <span className="opacity-60">
              {stats.memories} {t('memory.unit')} · {stats.short} {t('memory.short_unit')} · {stats.archived} {t('memory.state.archived')} · {stats.superseded} {t('memory.state.superseded')} · {stats.tags} {t('memory.tags_unit')}
            </span>
          )}
          {stats && (
            <span className={`ml-auto text-xs ${stats.owner_alive ? 'text-green-300' : 'opacity-50'}`}>
              {stats.owner_alive ? t('memory.owner_online') : t('memory.owner_offline')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <input
            className="flex-1 rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-accent/60"
            placeholder={t('memory.search_placeholder')}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm whitespace-nowrap">
            <input type="checkbox" checked={layer === 'short'} onChange={(e) => setLayer(e.target.checked ? 'short' : 'long')} />
            {t('memory.show_short')}
          </label>
          <label className="flex items-center gap-2 text-sm whitespace-nowrap">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            {t('memory.show_archived')}
          </label>
        </div>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <button className={chip(tag === '')} onClick={() => setTag('')}>{t('memory.all_tags')}</button>
            {tags.map((x) => (
              <button key={x.tag} className={chip(tag === x.tag)} onClick={() => setTag(tag === x.tag ? '' : x.tag)}>
                {x.tag} <span className="opacity-60">{x.count}</span>
              </button>
            ))}
          </div>
        )}
        <p className="text-xs opacity-50">{t('memory.note')}</p>
        {notice && <p className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</p>}
      </div>

      <ul className="flex-1 overflow-y-auto divide-y divide-white/5">
        {items.length === 0 && <li className="p-5 opacity-60">{t('memory.empty')}</li>}
        {items.map((m) => (
          <li key={m.id} className={`px-5 py-3 flex gap-3 items-start ${m.archived ? 'opacity-60' : ''}`}>
            <div className="flex-1 min-w-0">
              <p className="whitespace-pre-wrap break-words">{m.text}</p>
              <p className="mt-1 text-xs opacity-60 flex flex-wrap gap-x-3 gap-y-1">
                <span>#{m.id}</span>
                <span>{fmtDate(m.created_at)}</span>
                {(m.tags ?? []).map((x) => <span key={x} className="px-1.5 rounded bg-white/10">{x}</span>)}
                {m.superseded && <span className="text-amber-300">{t('memory.state.superseded')}{m.archive_reason ? ` — ${m.archive_reason}` : ''}</span>}
                {m.archived === 1 && <span className="text-amber-300">{t('memory.state.archived')}{m.archive_reason ? ` — ${m.archive_reason}` : ''}</span>}
                {queued.has(m.id) && <span className="text-amber-300">{t('memory.queued_badge')}</span>}
              </p>
            </div>
            <button
              className="shrink-0 px-3 py-1 rounded-lg text-sm bg-red-500/20 hover:bg-red-500/50 disabled:opacity-40"
              disabled={busy === m.id || queued.has(m.id)}
              onClick={() => remove(m)}
            >
              {t('memory.delete')}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
