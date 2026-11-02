import { useEffect, useState } from 'react';
import { api, Settings as S } from '../api';
import { VoiceSettings } from './VoiceSettings';
import { ConnectionsSettings } from './ConnectionsSettings';
import { DevSettings } from './DevSettings';
import { useStore } from '../store';
import { TIME_FORMATS, fmtDateTime } from '../fmt';
import { t } from '../i18n';

// 設定 (the gear at the bottom of the roster column) is its own screen since 0.13.0, with five pages down the left:
// 你 (name, reply language), 程式 (character window on start, Telegram mirror, system notes, dates), 模型連線
// (home/models.json), 語音連線 (the global STT / TTS connectors) and 開發者 (the backend knobs). Nothing of one
// character lives here — her own pages are the 角色 tab of her pane. 新角色 sits in the header because creating a
// character is not about any one character either. 你 and 程式 share one save bar that names the unsaved fields;
// 模型連線 and 語音連線 save themselves. Note: your name and reply language reach every character on save and each
// needs a restart (556d writes people/你.md and kokoro.json).

type Page = 'you' | 'app' | 'models' | 'voice' | 'dev';
const PAGES: { key: Page; label: string }[] = [
  { key: 'you', label: 'settings.you' }, { key: 'app', label: 'settings.app' }, { key: 'models', label: 'conn.title' },
  { key: 'voice', label: 'settings.voice' }, { key: 'dev', label: 'settings.nav_dev' },
];
const OWN_FIELDS = ['your_name', 'reply_language', 'show_avatar_on_start', 'mirror_to_telegram'] as const;
const FIELD_LABEL: Record<(typeof OWN_FIELDS)[number], string> = { your_name: 'settings.your_name', reply_language: 'settings.reply_language', show_avatar_on_start: 'settings.show_avatar_on_start', mirror_to_telegram: 'settings.mirror_to_telegram' };
const clock = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export function Settings({ onBack, onNew }: { onBack(): void; onNew(): void }) {
  const [page, setPage] = useState<Page>('you');
  const { showCues, setShowCues, timeFormat, clock24, setTimeFormat, setClock24 } = useStore();
  const [s, setS] = useState<S | null>(null);
  const [orig, setOrig] = useState<S | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState('');
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [dev, setDev] = useState<boolean>(() => { try { return localStorage.getItem('556.dev') === '1'; } catch { return false; } });
  const toggleDev = (on: boolean) => { setDev(on); try { localStorage.setItem('556.dev', on ? '1' : '0'); } catch { /* ignore */ } };

  useEffect(() => {
    api.settings().then((r) => { setS(r.settings); setOrig(r.settings); }).catch((e) => setNotice({ kind: 'err', text: String(e) }));
  }, []);

  const set = <K extends keyof S>(k: K, v: S[K]) => s && setS({ ...s, [k]: v });
  const dirty = s && orig ? OWN_FIELDS.filter((k) => (s[k] ?? null) !== (orig[k] ?? null)) : [];

  async function save() {
    if (!s) return;
    setSaving(true); setNotice(null);
    try {
      const r = await api.updateSettings({ your_name: s.your_name, reply_language: s.reply_language, mirror_to_telegram: s.mirror_to_telegram, show_avatar_on_start: s.show_avatar_on_start });
      setS(r.settings); setOrig(r.settings); setSavedAt(clock());
      setRestartNeeded(r.restart_required);
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

  const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-accent/60';
  const label = 'block text-xs opacity-70 mb-1';
  const cur = PAGES.find((p) => p.key === page)!;
  const ownPage = page === 'you' || page === 'app';

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-white/10 bg-panel">
        <button className="px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/15" onClick={onBack}>{t('shell.back')}</button>
        <span className="font-semibold">{t('tab.settings')}</span>
        <span className="text-xs text-muted">{t('settings.global_note')}</span>
        <button className="ml-auto shrink-0 px-3 py-1.5 rounded-lg text-sm bg-accent/20 text-link hover:bg-accent/30" onClick={onNew}>{t('newchar.button')}</button>
      </div>

      <div className="flex-1 min-h-0 flex">
        <nav aria-label={t('tab.settings')} className="w-[200px] shrink-0 bg-panel border-r border-white/10 p-2.5 flex flex-col gap-0.5">
          {PAGES.map((p) => (
            <button key={p.key} className={`text-left px-3 py-2 rounded-lg text-sm ${page === p.key ? 'bg-accent/20 text-ink font-medium' : 'hover:bg-white/5'} ${p.key === 'dev' ? 'text-muted' : ''}`} onClick={() => setPage(p.key)}>{t(p.label)}</button>
          ))}
        </nav>

        <section className="flex-1 min-w-0 flex flex-col">
          <div className="px-6 pt-4 pb-2 flex items-center gap-3">
            <nav aria-label="路徑" className="text-xs text-muted flex items-center gap-2"><span>{t('tab.settings')}</span><span aria-hidden="true">›</span><span className="text-ink">{t(cur.label)}</span></nav>
            {ownPage && <span className="text-[11px] px-2 py-0.5 rounded-full bg-warn/15 text-warn">{page === 'you' ? t('character.when_restart') : t('settings.when_app')}</span>}
          </div>
          <div className="flex-1 overflow-y-auto px-6 pb-6">
            <div className="max-w-2xl space-y-5">
              {notice && <p className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</p>}

              {page === 'you' && (s ? (
                <section className="space-y-4">
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
              ) : <p className="text-sm opacity-60">{t('status.connecting')}</p>)}

              {page === 'app' && (s ? (
                <section className="space-y-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={s.show_avatar_on_start} onChange={(e) => set('show_avatar_on_start', e.target.checked)} />
                    {t('settings.show_avatar_on_start')}
                  </label>
                  <div>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={s.mirror_to_telegram ?? true} onChange={(e) => set('mirror_to_telegram', e.target.checked)} />
                      {t('settings.mirror_to_telegram')}
                    </label>
                    <p className="text-xs opacity-60 mt-1">{t('settings.mirror_note')}</p>
                  </div>
                  <div className="border-t border-white/10 pt-4 space-y-3">
                    <p className="text-xs text-muted">{t('settings.local_note')}</p>
                    <div>
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={showCues} onChange={(e) => setShowCues(e.target.checked)} />
                        {t('settings.show_cues')}
                      </label>
                      <p className="text-xs opacity-60 mt-1">{t('settings.show_cues_note')}</p>
                    </div>
                    <div>
                      <label className={label}>{t('settings.time_format')}</label>
                      <select className={field} value={timeFormat} onChange={(e) => setTimeFormat(e.target.value as any)}>
                        {TIME_FORMATS.map((f) => <option key={f} value={f}>{t('settings.time_format_' + f)} — {fmtDateTime(Date.now() / 1000, f, clock24)}</option>)}
                      </select>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={clock24} onChange={(e) => setClock24(e.target.checked)} />
                      {t('settings.clock24')}
                    </label>
                  </div>
                </section>
              ) : <p className="text-sm opacity-60">{t('status.connecting')}</p>)}

              {page === 'models' && <ConnectionsSettings />}
              {page === 'voice' && <VoiceSettings />}
              {page === 'dev' && (
                <section className="space-y-3">
                  <label className="flex items-center gap-2 text-sm opacity-80">
                    <input type="checkbox" checked={dev} onChange={(e) => toggleDev(e.target.checked)} />
                    {t('dev.toggle')}
                  </label>
                  {dev && <DevSettings groups={['backend']} onRestart={restart} />}
                </section>
              )}
            </div>
          </div>

          {(ownPage || restartNeeded) && (
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
    </div>
  );
}
