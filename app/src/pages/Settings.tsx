import { useEffect, useState } from 'react';
import { api, CompanionInfo, Settings as S } from '../api';
import { VoiceSettings } from './VoiceSettings';
import { DevSettings } from './DevSettings';
import { Character } from './Character';
import { useStore } from '../store';
import { t } from '../i18n';

// 設定 in two layers. 全域: you (name, reply language), the app (character window on start, Telegram
// mirror), the global voice connectors (home/voice.json) and the backend developer knobs. 角色: the
// list of characters; one character's page (Character.tsx) holds everything that is its own. 556d
// edits the character on stage, so opening a page switches the stage to that character first.
// Note: 556d applies your name and reply language into the character on stage (people/你.md,
// kokoro.json of the selected profile) and that one needs a restart.
export function Settings() {
  const [tab, setTab] = useState<'global' | 'characters'>('global');
  const [open, setOpen] = useState<string | null>(null);
  const [items, setItems] = useState<CompanionInfo[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const { selected, setSelected } = useStore();

  useEffect(() => {
    if (tab !== 'characters') return;
    const load = () => api.companions().then((r) => setItems(r.companions ?? [])).catch((e) => setNotice(String(e)));
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [tab]);

  async function openPage(name: string) {
    if (name !== selected) {
      try { await api.select(name); setSelected(name); } catch (e) { setNotice(String(e)); return; }
    }
    setOpen(name);
  }

  const seg = (on: boolean) => `px-3 py-1 rounded text-sm ${on ? 'bg-white/15' : 'hover:bg-white/5 opacity-70'}`;
  const current = open ? items.find((c) => c.name === open) : undefined;

  return (
    <div className="h-full flex flex-col">
      <div className="flex gap-1 px-5 pt-4">
        <button className={seg(tab === 'global')} onClick={() => { setTab('global'); setOpen(null); }}>{t('settings.tab_global')}</button>
        <button className={seg(tab === 'characters')} onClick={() => setTab('characters')}>{t('settings.tab_characters')}</button>
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === 'global' ? <GlobalSettings /> : open && current ? <Character info={current} onBack={() => setOpen(null)} /> : (
          <div className="h-full overflow-y-auto p-5 max-w-2xl space-y-4">
            <p className="text-xs opacity-60">{t('settings.characters_note')}</p>
            {notice && <p className="text-sm text-red-300">{notice}</p>}
            {items.length === 0 && <p className="opacity-60">{t('roster.empty')}</p>}
            <ul className="space-y-2">
              {items.map((c) => (
                <li key={c.name}>
                  <button className={`w-full text-left rounded-xl px-4 py-3 bg-white/5 hover:bg-white/10 flex items-center gap-3 ${c.name === selected ? 'ring-1 ring-pink-400/60' : ''}`} onClick={() => openPage(c.name)}>
                    <span className={`w-2.5 h-2.5 rounded-full ${c.active ? (c.hermes_connected ? 'bg-green-400' : 'bg-amber-400') : 'bg-white/20'}`} />
                    <span className="font-medium">{c.display_name || c.name}</span>
                    <span className="text-xs opacity-50">{c.name}</span>
                    {c.name === selected && <span className="text-xs px-1.5 rounded bg-pink-500/30">{t('roster.on_stage')}</span>}
                    <span className="ml-auto opacity-50">›</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function GlobalSettings() {
  const { showCues, setShowCues } = useStore();
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
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showCues} onChange={(e) => setShowCues(e.target.checked)} />
          {t('settings.show_cues')}
        </label>
        <p className="text-xs opacity-60">{t('settings.show_cues_note')}</p>
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
