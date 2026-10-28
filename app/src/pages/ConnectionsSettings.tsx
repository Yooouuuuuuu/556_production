import { useEffect, useState } from 'react';
import { api, Connections, Endpoint, Use } from '../api';
import { t } from '../i18n';

// 設定 → 全域 → 模型連線 (home/models.json): one master endpoint; 對話, 記憶 and 寫靈魂 follow it or carry
// their own; the embedder (local llama-server or an endpoint); the timezone. Nothing has a default — the
// page shows what is still missing, and a character does not start until the list is empty. 「檢查」 asks an
// endpoint what models it serves and fills the picker; keys never come back from 556d (only a flag).

const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-pink-400/60';
const label = 'block text-xs opacity-70 mb-1';
const btn = 'px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-sm disabled:opacity-40';

type Probe = { busy: boolean; models: string[]; error?: string };

function EndpointFields({ ep, onChange, job, probe, onProbe, keySet }: {
  ep: Endpoint; onChange(next: Endpoint): void; job: string; probe: Probe; onProbe(): void; keySet: boolean;
}) {
  const set = <K extends keyof Endpoint>(k: K, v: Endpoint[K]) => onChange({ ...ep, [k]: v });
  const list = probe.models.length ? probe.models : (ep.model ? [ep.model] : []);
  return (
    <div className="space-y-2">
      <div>
        <label className={label}>{t('conn.method')}</label>
        <select className={field} value={ep.method || 'openai'} onChange={(e) => set('method', e.target.value)}>
          <option value="openai">{t('conn.method_openai')}</option>
        </select>
      </div>
      <div>
        <label className={label}>{t('conn.base_url')}</label>
        <input className={field} value={ep.base_url} placeholder="http://127.0.0.1:1234/v1" onChange={(e) => set('base_url', e.target.value)} />
      </div>
      <div>
        <label className={label}>{t('conn.api_key')} {keySet && <span className="opacity-60">{t('conn.api_key_set')}</span>}</label>
        <input className={field} type="password" value={ep.api_key ?? ''} onChange={(e) => set('api_key', e.target.value)} />
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className={label}>{t('conn.model')}</label>
          {list.length > 0 ? (
            <select className={field} value={ep.model} onChange={(e) => set('model', e.target.value)}>
              {!list.includes(ep.model) && <option value={ep.model}>{ep.model || t('conn.model_pick')}</option>}
              {list.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input className={field} value={ep.model} placeholder={t('conn.model_type')} onChange={(e) => set('model', e.target.value)} />
          )}
        </div>
        <button className={btn} disabled={probe.busy || !ep.base_url} onClick={onProbe} title={t('conn.check_note')}>{probe.busy ? '…' : t('conn.check')}</button>
      </div>
      {probe.error && <p className="text-xs text-red-300">{t('conn.check_failed')}：{probe.error}</p>}
      {!probe.error && probe.models.length > 0 && <p className="text-xs text-green-300">{t('conn.check_ok').replace('{n}', String(probe.models.length))}</p>}
      <span className="hidden">{job}</span>
    </div>
  );
}

export function ConnectionsSettings() {
  const [c, setC] = useState<Connections | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [keys, setKeys] = useState<Record<string, boolean>>({});
  const [probes, setProbes] = useState<Record<string, Probe>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);

  const idle: Probe = { busy: false, models: [] };
  const probeOf = (job: string) => probes[job] ?? idle;

  function take(r: { connections: any; missing: string[] }) {
    const x = r.connections;
    const ep = (e: any): Endpoint => ({ method: e.method || 'openai', base_url: e.base_url || '', api_key: '', model: e.model || '' });
    const use = (u: any): Use => ({ use: u.use === 'custom' ? 'custom' : 'master', ...ep(u) });
    setC({
      master: ep(x.master), chat: use(x.chat), memory: use(x.memory), soul: use(x.soul),
      embedder: { kind: x.embedder.kind || '', exe: x.embedder.exe || '', file: x.embedder.file || '', port: x.embedder.port || 0,
        base_url: x.embedder.base_url || '', api_key: '', model: x.embedder.model || '', dims: x.embedder.dims || 0 },
      timezone: x.timezone || '',
    });
    setKeys({ master: !!x.master.api_key_set, chat: !!x.chat.api_key_set, memory: !!x.memory.api_key_set, soul: !!x.soul.api_key_set, embedder: !!x.embedder.api_key_set });
    setMissing(r.missing || []);
  }

  useEffect(() => {
    api.connections().then(take).catch((e) => setNotice({ kind: 'err', text: String(e) }));
  }, []);

  if (!c) return <p className="text-sm opacity-60">{t('status.connecting')}</p>;

  async function probe(job: 'master' | 'chat' | 'memory' | 'soul' | 'embedder', ep: { base_url: string; api_key?: string }) {
    setProbes((p) => ({ ...p, [job]: { busy: true, models: [] } }));
    try {
      const r = await api.probeConnection({ base_url: ep.base_url, api_key: ep.api_key || '', job });
      setProbes((p) => ({ ...p, [job]: { busy: false, models: r.models || [], error: r.ok ? undefined : r.error } }));
    } catch (e) {
      setProbes((p) => ({ ...p, [job]: { busy: false, models: [], error: String(e) } }));
    }
  }

  async function save() {
    if (!c) return;
    setSaving(true); setNotice(null);
    try {
      const r = await api.updateConnections(c);
      take(r);
      const missingNow = r.missing || [];
      setNotice({ kind: missingNow.length ? 'warn' : 'ok', text: missingNow.length ? t('conn.saved_missing') : (r.restart_required ? t('settings.saved_restart') : t('settings.saved')) });
    } catch (e) {
      setNotice({ kind: 'err', text: String(e) });
    } finally {
      setSaving(false);
    }
  }

  const jobs: { key: 'chat' | 'memory' | 'soul'; title: string; note: string }[] = [
    { key: 'chat', title: t('conn.job_chat'), note: t('conn.job_chat_note') },
    { key: 'memory', title: t('conn.job_memory'), note: t('conn.job_memory_note') },
    { key: 'soul', title: t('conn.job_soul'), note: t('conn.job_soul_note') },
  ];
  const emb = c.embedder;
  const setEmb = (patch: Partial<typeof emb>) => setC({ ...c, embedder: { ...emb, ...patch } });

  return (
    <section className="space-y-4">
      <h2 className="font-semibold">{t('conn.title')}</h2>
      <p className="text-xs opacity-60">{t('conn.note')}</p>
      {missing.length > 0 && (
        <p className="text-xs text-amber-300">{t('conn.missing')}：{missing.join('、')}</p>
      )}

      <div className="rounded-xl bg-white/5 p-3 space-y-2">
        <h3 className="text-sm font-medium">{t('conn.master')}</h3>
        <EndpointFields ep={c.master} job="master" keySet={keys.master} probe={probeOf('master')}
          onChange={(ep) => setC({ ...c, master: ep })} onProbe={() => probe('master', c.master)} />
      </div>

      {jobs.map(({ key, title, note }) => {
        const u = c[key];
        return (
          <div key={key} className="rounded-xl bg-white/5 p-3 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-medium">{title}</h3>
              <select className={`${field} w-auto`} value={u.use} onChange={(e) => setC({ ...c, [key]: { ...u, use: e.target.value as 'master' | 'custom' } })}>
                <option value="master">{t('conn.use_master')}</option>
                <option value="custom">{t('conn.use_custom')}</option>
              </select>
            </div>
            <p className="text-xs opacity-60">{note}</p>
            {u.use === 'custom' && (
              <EndpointFields ep={u} job={key} keySet={keys[key]} probe={probeOf(key)}
                onChange={(ep) => setC({ ...c, [key]: { ...ep, use: 'custom' } })} onProbe={() => probe(key, u)} />
            )}
          </div>
        );
      })}

      <div className="rounded-xl bg-white/5 p-3 space-y-2">
        <h3 className="text-sm font-medium">{t('conn.embedder')}</h3>
        <p className="text-xs opacity-60">{t('conn.embedder_note')}</p>
        <div>
          <label className={label}>{t('conn.method')}</label>
          <select className={field} value={emb.kind} onChange={(e) => setEmb({ kind: e.target.value })}>
            <option value="">{t('conn.pick')}</option>
            <option value="llama">{t('conn.embed_llama')}</option>
            <option value="openai">{t('conn.embed_openai')}</option>
          </select>
        </div>
        {emb.kind === 'llama' && (
          <>
            <div><label className={label}>{t('conn.embed_exe')}</label><input className={field} value={emb.exe} placeholder="bin/llama/llama-server.exe" onChange={(e) => setEmb({ exe: e.target.value })} /></div>
            <div><label className={label}>{t('conn.embed_file')}</label><input className={field} value={emb.file} placeholder="models/bge-m3-Q8_0.gguf" onChange={(e) => setEmb({ file: e.target.value })} /></div>
            <div><label className={label}>{t('conn.embed_port')}</label><input className={field} type="number" value={emb.port || ''} placeholder="55602" onChange={(e) => setEmb({ port: Number(e.target.value) || 0 })} /></div>
          </>
        )}
        {emb.kind === 'openai' && (
          <>
            <div><label className={label}>{t('conn.base_url')}</label><input className={field} value={emb.base_url} placeholder="https://…/v1" onChange={(e) => setEmb({ base_url: e.target.value })} /></div>
            <div><label className={label}>{t('conn.api_key')} {keys.embedder && <span className="opacity-60">{t('conn.api_key_set')}</span>}</label><input className={field} type="password" value={emb.api_key ?? ''} onChange={(e) => setEmb({ api_key: e.target.value })} /></div>
          </>
        )}
        {emb.kind && (
          <div className="grid grid-cols-2 gap-2">
            <div><label className={label}>{t('conn.embed_model')}</label><input className={field} value={emb.model} placeholder="bge-m3" onChange={(e) => setEmb({ model: e.target.value })} /></div>
            <div><label className={label}>{t('conn.embed_dims')}</label><input className={field} type="number" value={emb.dims || ''} placeholder="1024" onChange={(e) => setEmb({ dims: Number(e.target.value) || 0 })} /></div>
          </div>
        )}
        <p className="text-xs opacity-60">{t('conn.embed_change_note')}</p>
      </div>

      <div className="rounded-xl bg-white/5 p-3 space-y-2">
        <h3 className="text-sm font-medium">{t('conn.timezone')}</h3>
        <input className={field} value={c.timezone} placeholder="Asia/Taipei" onChange={(e) => setC({ ...c, timezone: e.target.value })} />
        <p className="text-xs opacity-60">{t('conn.timezone_note')}</p>
      </div>

      <div className="flex items-center gap-3">
        <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={saving} onClick={save}>{t('settings.save')}</button>
        {notice && <span className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</span>}
      </div>
    </section>
  );
}
