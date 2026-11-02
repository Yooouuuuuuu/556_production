import { Component, useCallback, useEffect, useState, type ReactNode } from 'react';
import { api, BASE as BASE_URL, CompanionInfo } from '../api';
import { useStore } from '../store';
import { t } from '../i18n';
import { Chat } from './Chat';
import { State } from './State';
import { Memory } from './Memory';
import { Character } from './Character';
import { Settings } from './Settings';
import { NewCharacter } from './NewCharacter';

// The office window since 0.13.0 (docs/app/app.md): three doors, not five tabs. 名單 is the left column and is
// always there — who exists, who is online, who is current; picking one puts her on stage, which is also whose
// pages you see. The right pane is that one character: 聊天 · 狀態 · 記憶 · 角色 (her own settings). The gear at the
// bottom of the column opens 設定 — you and this program — as its own screen, with 新角色 beside it. On stage, viewed
// and talked to are one thing: the name lit in the column.

type Tab = 'chat' | 'state' | 'memory' | 'character';
type Screen = 'main' | 'settings' | 'new';

// A page that throws must not take the window with it: React unmounts the whole root on an uncaught render error,
// which looks like the app hanging (0.7.1: 狀態 on a null list). Show the error in place; switching tabs or pressing
// retry clears it.
class PageBoundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { console.error('[page]', error); }
  componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
  render() {
    if (this.state.error) {
      return (
        <div className="p-4 text-sm space-y-2">
          <div className="text-red-300">{t('page.error')}</div>
          <pre className="text-xs whitespace-pre-wrap opacity-70">{String(this.state.error.stack || this.state.error)}</pre>
          <button className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-xs" onClick={() => this.setState({ error: null })}>{t('page.retry')}</button>
        </div>
      );
    }
    return this.props.children;
  }
}

const initial = (name: string) => [...name.trim()][0] ?? '?';

// Her circle: the uploaded portrait (角色 → 基本) when she has one, else the first character of her name.
function Circle({ c, size = 'w-10 h-10', on = false }: { c: CompanionInfo; size?: string; on?: boolean }) {
  if (c.portrait_url) return <img src={BASE_URL + c.portrait_url} alt="" className={`${size} shrink-0 rounded-full object-cover`} />;
  return <span aria-hidden="true" className={`${size} shrink-0 rounded-full inline-flex items-center justify-center font-bold ${on ? 'bg-accent/25 text-link' : 'bg-white/8 text-soft'}`}>{initial(c.display_name || c.name)}</span>;
}

function statusOf(c: CompanionInfo) {
  return c.active ? (c.stopping ? t('roster.stopping') : c.hermes_connected ? t('roster.active') : t('roster.starting')) : t('roster.inactive');
}

export function Shell({ initialScreen = 'main' }: { initialScreen?: Screen }) {
  const [screen, setScreen] = useState<Screen>(initialScreen);
  const [newId, setNewId] = useState<string | null>(null); // the package the new-character screen opens on (her 角色 tab links there)
  useEffect(() => { setScreen(initialScreen); }, [initialScreen]); // #/settings deep link
  const [tab, setTab] = useState<Tab>('chat');
  const [items, setItems] = useState<CompanionInfo[]>([]);
  const [backend, setBackend] = useState<string>(t('status.connecting'));
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { selected, selectedName, setSelected } = useStore();

  // the column follows 556d: the list every 3 s, the stage (name, avatar) with it
  const load = useCallback(async () => {
    try {
      const [list, cur] = await Promise.all([api.companions(), api.companion()]);
      setItems(list.companions ?? []);
      if (cur.profile) setSelected(cur.profile, cur.name, BASE_URL + cur.avatar_model_url); // profile = her id, name = her display name
      else if (list.selected && list.selected !== selected) setSelected(list.selected);
      setBackend('');
    } catch {
      setBackend(t('status.backend_down'));
    }
  }, [selected, setSelected]);
  useEffect(() => { load(); const id = setInterval(load, 3000); return () => clearInterval(id); }, [load]);

  async function pick(name: string) {
    if (name === selected) return;
    try { await api.select(name); setSelected(name); setNotice(null); } catch (e) { setNotice(String(e)); }
  }
  async function act(name: string, action: 'start' | 'stop') {
    setBusy(name); setNotice(null);
    try { await api.companionAction(name, action); await load(); } catch (e) { setNotice(String(e)); } finally { setBusy(null); }
  }

  const current = items.find((c) => c.name === selected);
  const tabs: { key: Tab; label: string }[] = [
    { key: 'chat', label: t('tab.chat') }, { key: 'state', label: t('tab.state') }, { key: 'memory', label: t('tab.memory') }, { key: 'character', label: t('shell.tab_character') },
  ];

  if (screen === 'settings') return <Settings onBack={() => setScreen('main')} onNew={() => setScreen('new')} />;
  if (screen === 'new') return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-white/10 bg-panel">
        <button className="px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/15" onClick={() => setScreen('main')}>{t('shell.back')}</button>
        <span className="font-semibold">{t('newchar.title')}</span>
      </div>
      <div className="flex-1 overflow-hidden"><PageBoundary resetKey="new"><NewCharacter initialId={newId} onBack={() => { setNewId(null); setScreen('main'); }} /></PageBoundary></div>
    </div>
  );

  return (
    <div className="h-full flex">
      {/* 名單: who */}
      <nav aria-label={t('tab.roster')} className="w-[260px] shrink-0 bg-panel border-r border-white/10 flex flex-col">
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <span className="font-semibold">{t('tab.roster')}</span>
          <button className="w-8 h-8 rounded-lg bg-accent/20 text-link hover:bg-accent/30 text-lg leading-none" title={t('newchar.button')} aria-label={t('newchar.button')} onClick={() => setScreen('new')}>＋</button>
        </div>
        <ul className="flex-1 overflow-y-auto px-2 space-y-0.5">
          {items.length === 0 && <li className="px-3 py-2 text-xs opacity-60">{t('roster.empty')}</li>}
          {items.map((c) => {
            const on = c.name === selected;
            return (
              <li key={c.name}>
                <div className={`w-full rounded-xl px-2.5 py-2 flex items-center gap-3 cursor-pointer ${on ? 'bg-accent/20' : 'hover:bg-white/5'}`} onClick={() => pick(c.name)}>
                  <Circle c={c} on={on} />
                  <div className="flex-1 min-w-0">
                    <div className={`truncate ${on ? 'font-semibold' : 'font-medium'}`}>{c.display_name || c.name}</div>
                    <div className="text-xs text-muted truncate">{statusOf(c)}{(c.channels ?? []).length > 0 ? ` · ${(c.channels ?? []).join(', ')}` : ''}</div>
                  </div>
                  {c.active
                    ? <span aria-hidden="true" className={`w-2 h-2 rounded-full ${c.hermes_connected ? 'bg-ok' : 'bg-warn'}`} />
                    : <button className="px-2.5 py-1 rounded-lg text-xs border border-white/15 hover:bg-white/10 disabled:opacity-40" disabled={busy === c.name} onClick={(e) => { e.stopPropagation(); act(c.name, 'start'); }}>{t('roster.start')}</button>}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="border-t border-white/10 px-2 py-2">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/5 text-left" onClick={() => setScreen('settings')}>
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3 1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8 1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
            <span>{t('tab.settings')}</span>
          </button>
          <div className="px-3 pb-1 text-[11px] text-muted">{backend || notice || t('shell.ready')}</div>
        </div>
      </nav>

      {/* this one */}
      <main className="flex-1 min-w-0 flex flex-col">
        {!current ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted">{items.length === 0 ? t('roster.empty') : t('shell.pick')}</div>
        ) : (
          <>
            <header className="flex items-center gap-3 px-5 py-2.5 border-b border-white/10">
              <Circle c={current} size="w-8 h-8" on />
              <span className="font-semibold">{current.display_name || current.name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${current.active ? 'bg-ok/15 text-ok' : 'bg-white/8 text-muted'}`}>{statusOf(current)}</span>
              <nav aria-label={current.display_name || current.name} className="ml-3 flex gap-0.5 rounded-xl bg-white/5 p-0.5">
                {tabs.map((x) => (
                  <button key={x.key} className={`px-3.5 py-1.5 rounded-lg text-sm ${tab === x.key ? 'bg-accent text-accent-ink font-semibold' : 'hover:bg-white/10'}`} onClick={() => setTab(x.key)}>{x.label}</button>
                ))}
              </nav>
              <div className="ml-auto flex gap-1.5">
                <button className="px-3 py-1.5 rounded-lg text-sm border border-white/15 hover:bg-white/10" onClick={() => window.desktop?.toggleAvatar()}>{t('shell.avatar')}</button>
                {current.active
                  ? <button className="px-3 py-1.5 rounded-lg text-sm border border-white/15 hover:bg-white/10 disabled:opacity-40" disabled={busy === current.name || current.stopping} onClick={() => act(current.name, 'stop')}>{t('roster.stop')}</button>
                  : <button className="px-3 py-1.5 rounded-lg text-sm bg-accent text-accent-ink font-medium hover:bg-accent/90 disabled:opacity-40" disabled={busy === current.name} onClick={() => act(current.name, 'start')}>{t('roster.start')}</button>}
              </div>
            </header>
            <div className="flex-1 overflow-hidden">
              <PageBoundary resetKey={`${selected}:${tab}`}>
                {tab === 'chat' ? <Chat /> : tab === 'state' ? <State /> : tab === 'memory' ? <Memory /> : <Character info={current} embedded onOpenPackage={(id) => { setNewId(id); setScreen('new'); }} />}
              </PageBoundary>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
