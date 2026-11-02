import { useEffect, useState } from 'react';
import { api, BASE, CompanionInfo, Settings as S } from '../api';
import { ToolsSettings } from './ToolsSettings';
import { ProactiveSettings } from './ProactiveSettings';
import { DevSettings } from './DevSettings';
import { VoiceSettings } from './VoiceSettings';
import { t } from '../i18n';

// The 角色 tab of her pane (0.13.0): everything that belongs to this one character, in seven pages down the left —
// 基本 (name, Live2D model, portrait), 記憶 (language, context window), 能力 (toolsets), 主動 (gates, personality),
// 聲音 (her own voice over the global connectors), 頻道 (her channel accounts), 細節 (her config knobs). Each page
// says when a change takes effect; the pages this component saves itself (基本, 記憶) carry a save bar that names
// the unsaved fields. Her package — the description, the relationship — is the new-character page, linked below.

type Page = 'basic' | 'memory' | 'tools' | 'proactive' | 'voice' | 'channels' | 'knobs';
type When = 'now' | 'restart' | 'mixed';
const PAGES: { key: Page; label: string; when: When }[] = [
  { key: 'basic', label: 'character.nav_basic', when: 'now' },
  { key: 'memory', label: 'character.nav_memory', when: 'restart' },
  { key: 'tools', label: 'character.nav_tools', when: 'restart' },
  { key: 'proactive', label: 'character.nav_proactive', when: 'mixed' },
  { key: 'voice', label: 'character.nav_voice', when: 'now' },
  { key: 'channels', label: 'character.nav_channels', when: 'restart' },
  { key: 'knobs', label: 'character.nav_knobs', when: 'restart' },
];
const OWN_FIELDS = ['companion_name', 'avatar_model', 'memory_language', 'context_turns'] as const;
const FIELD_LABEL: Record<(typeof OWN_FIELDS)[number], string> = { companion_name: 'settings.companion_name', avatar_model: 'settings.avatar_model', memory_language: 'settings.memory_language', context_turns: 'settings.context_turns' };

const clock = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export function Character({ info, onBack, embedded = false, onOpenPackage }: { info: CompanionInfo; onBack?(): void; embedded?: boolean; onOpenPackage?(id: string): void }) {
  const [page, setPage] = useState<Page>('basic');
  const [s, setS] = useState<S | null>(null);
  const [orig, setOrig] = useState<S | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string>('');
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [portrait, setPortrait] = useState<string>(info.portrait_url ?? '');
  const [dev, setDev] = useState<boolean>(() => { try { return localStorage.getItem('556.dev') === '1'; } catch { return false; } });
  const toggleDev = (on: boolean) => { setDev(on); try { localStorage.setItem('556.dev', on ? '1' : '0'); } catch { /* ignore */ } };

  useEffect(() => {
    setS(null); setOrig(null); setPage('basic'); setNotice(null); setRestartNeeded(false);
    api.settings().then((r) => { setS(r.settings); setOrig(r.settings); }).catch((e) => setNotice({ kind: 'err', text: String(e) }));
    api.models().then((r) => setModels(r.models.flatMap((m) => m.models))).catch(() => {});
  }, [info.name]);
  useEffect(() => { setPortrait(info.portrait_url ?? ''); }, [info.name, info.portrait_url]);

  const set = <K extends keyof S>(k: K, v: S[K]) => s && setS({ ...s, [k]: v });
  const dirty = s && orig ? OWN_FIELDS.filter((k) => s[k] !== orig[k]) : [];

  async function save() {
    if (!s) return;
    setSaving(true); setNotice(null);
    try {
      const r = await api.updateSettings({ companion_name: s.companion_name, avatar_model: s.avatar_model, memory_language: s.memory_language, context_turns: s.context_turns });
      setS(r.settings); setOrig(r.settings); setSavedAt(clock());
      setRestartNeeded(r.restart_required);
      if (r.reembed_required) setNotice({ kind: 'warn', text: t('settings.saved_reembed') });
    } catch (e) {
      setNotice({ kind: 'err', text: String(e) });
    } finally {
      setSaving(false);
    }
  }
  function discard() { if (orig) setS(orig); }
  async function restart() {
    await api.restartHermes();
    setRestartNeeded(false);
    setNotice({ kind: 'ok', text: t('settings.restarting') });
  }
  async function uploadPortrait(f: File) {
    setNotice(null);
    try { const r = await api.uploadPortrait(info.name, f); setPortrait(r.portrait_url); } catch (e) { setNotice({ kind: 'err', text: String(e) }); }
  }
  async function removePortrait() {
    setNotice(null);
    try { await api.removePortrait(info.name); setPortrait(''); } catch (e) { setNotice({ kind: 'err', text: String(e) }); }
  }

  const cur = PAGES.find((p) => p.key === page)!;
  const status = info.active ? (info.stopping ? t('roster.stopping') : info.hermes_connected ? t('roster.active') : t('roster.starting')) : t('roster.inactive');
  const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-accent/60';
  const label = 'block text-xs opacity-70 mb-1';
  const whenPill = (w: When) => (
    <span className={`text-[11px] px-2 py-0.5 rounded-full ${w === 'now' ? 'bg-ok/15 text-ok' : w === 'restart' ? 'bg-warn/15 text-warn' : 'bg-white/8 text-soft'}`}>
      {w === 'now' ? t('character.when_now') : w === 'restart' ? t('character.when_restart') : t('character.when_mixed')}
    </span>
  );

  return (
    <div className="h-full flex">
      <nav aria-label={t('shell.tab_character')} className="w-[170px] shrink-0 border-r border-white/10 p-2.5 flex flex-col gap-0.5">
        <div className="px-2.5 pb-2 text-[11px] text-muted">{embedded ? t('shell.tab_character') : info.display_name || info.name}</div>
        {PAGES.map((p) => (
          <button key={p.key} className={`text-left px-3 py-2 rounded-lg text-sm ${page === p.key ? 'bg-accent/20 text-ink font-medium' : 'hover:bg-white/5'}`} onClick={() => setPage(p.key)}>{t(p.label)}</button>
        ))}
        {onOpenPackage && <button className="mt-auto text-left px-3 py-2 rounded-lg text-xs text-link hover:bg-white/5" onClick={() => onOpenPackage(info.name)}>{t('character.package_link')}</button>}
      </nav>

      <section className="flex-1 min-w-0 flex flex-col">
        <div className="px-6 pt-4 pb-2 flex flex-wrap items-center gap-3">
          {!embedded && onBack && <button className="text-sm opacity-70 hover:opacity-100" onClick={onBack}>{t('character.back')}</button>}
          <nav aria-label="路徑" className="text-xs text-muted flex items-center gap-2">
            <span>{embedded ? t('shell.tab_character') : info.display_name || info.name}</span><span aria-hidden="true">›</span><span className="text-ink">{t(cur.label)}</span>
          </nav>
          {whenPill(cur.when)}
          {!embedded && <span className="text-xs text-muted ml-auto">{status}</span>}
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-6">
          <div className="max-w-3xl space-y-5">
            {notice && <p className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</p>}

            {page === 'basic' && (s ? (
              <section className="space-y-4">
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
                <div>
                  <label className={label}>{t('character.portrait')}</label>
                  <div className="flex items-center gap-3">
                    {portrait
                      ? <img src={BASE + portrait} alt="" className="w-14 h-14 rounded-full object-cover" />
                      : <span aria-hidden="true" className="w-14 h-14 rounded-full bg-accent/25 text-link inline-flex items-center justify-center text-xl font-bold">{[...(info.display_name || info.name)][0]}</span>}
                    <label className="px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/15 cursor-pointer">
                      {t('character.portrait_upload')}
                      <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadPortrait(f); e.target.value = ''; }} />
                    </label>
                    {portrait && <button className="px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/15" onClick={removePortrait}>{t('character.portrait_remove')}</button>}
                  </div>
                  <p className="text-xs opacity-60 mt-1">{t('character.portrait_note')}</p>
                </div>
              </section>
            ) : <p className="text-sm opacity-60">{t('status.connecting')}</p>)}

            {page === 'memory' && (s ? (
              <section className="space-y-4">
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
            ) : <p className="text-sm opacity-60">{t('status.connecting')}</p>)}

            {page === 'tools' && <ToolsSettings onChanged={() => setRestartNeeded(true)} />}
            {page === 'proactive' && <ProactiveSettings onChanged={() => setRestartNeeded(true)} />}
            {page === 'voice' && <VoiceSettings companion={info.name} />}
            {page === 'channels' && (
              <section className="space-y-3">
                <p className="text-xs opacity-60">{t('character.channels_note')}</p>
                <DevSettings groups={['channels']} tone="plain" onRestart={restart} />
              </section>
            )}
            {page === 'knobs' && (
              <section className="space-y-3">
                <label className="flex items-center gap-2 text-sm opacity-80">
                  <input type="checkbox" checked={dev} onChange={(e) => toggleDev(e.target.checked)} />
                  {t('dev.toggle')}
                </label>
                {dev && <DevSettings groups={['model', 'memory']} onRestart={restart} />}
              </section>
            )}
          </div>
        </div>

        {(page === 'basic' || page === 'memory' || restartNeeded) && (
          <footer className="flex flex-wrap items-center gap-3 px-6 py-3 border-t border-white/10 bg-panel">
            <span aria-hidden="true" className={`w-2.5 h-2.5 rounded-full ${dirty.length ? 'bg-warn' : 'bg-ok'}`} />
            <span className="text-sm">{dirty.length ? t('character.unsaved') + dirty.map((k) => t(FIELD_LABEL[k])).join('、') : savedAt ? `${t('character.saved_at')} ${savedAt}` : t('character.no_changes')}</span>
            {restartNeeded && <span className="text-xs text-warn">{t('settings.saved_restart')}</span>}
            <div className="ml-auto flex gap-2">
              {restartNeeded && <button className="px-3 py-1.5 rounded-lg text-sm bg-amber-500/70 hover:bg-amber-500 text-white" onClick={restart}>{t('settings.restart')}</button>}
              {dirty.length > 0 && <button className="px-3 py-1.5 rounded-lg text-sm border border-white/15 hover:bg-white/10" onClick={discard}>{t('character.discard')}</button>}
              <button className="px-4 py-1.5 rounded-lg text-sm bg-accent hover:bg-accent/90 text-accent-ink font-medium disabled:opacity-40" disabled={saving || dirty.length === 0} onClick={save}>{t('settings.save')}</button>
            </div>
          </footer>
        )}
      </section>
    </div>
  );
}
