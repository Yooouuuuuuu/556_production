import { useEffect, useState } from 'react';
import { t } from '../i18n';
import { api, BASE as BASE_URL } from '../api';
import { Chat } from './Chat';
import { Settings } from './Settings';
import { Memory } from './Memory';
import { Roster } from './Roster';
import { useStore } from '../store';

// Office window: header (status, tabs, avatar toggle) + Chat / Settings.
type Tab = 'chat' | 'settings' | 'memory' | 'roster';

export function Office({ initialTab = 'chat' }: { initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(() => { setTab(initialTab); }, [initialTab]); // follow #/settings deep links
  const [status, setStatus] = useState<string>(t('status.connecting'));
  const { selected, selectedName, setSelected } = useStore();

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const c = await api.companion();
        if (!alive) return;
        if (c.profile) setSelected(c.profile, c.name, BASE_URL + c.avatar_model_url);
        setStatus(!c.profile ? t('status.no_companion') : !c.active ? t('status.inactive') : c.hermes_connected ? t('status.ready') : t('status.hermes_down'));
      } catch {
        if (alive) setStatus(t('status.backend_down'));
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-3 px-4 py-2 border-b border-white/10">
        <span className="font-semibold tracking-wide">556 Production</span>
        {selected && <span className="text-sm px-2 py-0.5 rounded-full bg-pink-500/30">{selectedName || selected}</span>}
        <span className="text-xs opacity-60">{status}</span>
        <nav className="ml-auto flex gap-1">
          <button className={`px-3 py-1 rounded ${tab === 'chat' ? 'bg-white/15' : 'hover:bg-white/5'}`} onClick={() => setTab('chat')}>{t('tab.chat')}</button>
          <button className={`px-3 py-1 rounded ${tab === 'roster' ? 'bg-white/15' : 'hover:bg-white/5'}`} onClick={() => setTab('roster')}>{t('tab.roster')}</button>
          <button className={`px-3 py-1 rounded ${tab === 'memory' ? 'bg-white/15' : 'hover:bg-white/5'}`} onClick={() => setTab('memory')}>{t('tab.memory')}</button>
          <button className={`px-3 py-1 rounded ${tab === 'settings' ? 'bg-white/15' : 'hover:bg-white/5'}`} onClick={() => setTab('settings')}>{t('tab.settings')}</button>
          <button className="px-3 py-1 rounded bg-pink-500/30 hover:bg-pink-500/50" onClick={() => window.desktop?.toggleAvatar()}>{t('avatar.toggle')}</button>
        </nav>
      </header>
      <main className="flex-1 overflow-hidden">
        {tab === 'chat' ? <Chat /> : tab === 'memory' ? <Memory /> : tab === 'roster' ? <Roster /> : <Settings />}
      </main>
    </div>
  );
}
