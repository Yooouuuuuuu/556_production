import { useEffect, useState } from 'react';
import { t } from '../i18n';
import { api } from '../api';
import { Chat } from './Chat';
import { Settings } from './Settings';

// Office window: header (status, tabs, avatar toggle) + Chat / Settings.
export function Office({ initialTab = 'chat' }: { initialTab?: 'chat' | 'settings' }) {
  const [tab, setTab] = useState<'chat' | 'settings'>(initialTab);
  useEffect(() => { setTab(initialTab); }, [initialTab]); // follow #/settings deep links
  const [status, setStatus] = useState<string>(t('status.connecting'));

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const c = await api.companion();
        if (alive) setStatus(c.hermes_connected ? t('status.ready') : t('status.hermes_down'));
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
        <span className="text-xs opacity-60">{status}</span>
        <nav className="ml-auto flex gap-1">
          <button className={`px-3 py-1 rounded ${tab === 'chat' ? 'bg-white/15' : 'hover:bg-white/5'}`} onClick={() => setTab('chat')}>{t('tab.chat')}</button>
          <button className={`px-3 py-1 rounded ${tab === 'settings' ? 'bg-white/15' : 'hover:bg-white/5'}`} onClick={() => setTab('settings')}>{t('tab.settings')}</button>
          <button className="px-3 py-1 rounded bg-pink-500/30 hover:bg-pink-500/50" onClick={() => window.desktop?.toggleAvatar()}>{t('avatar.toggle')}</button>
        </nav>
      </header>
      <main className="flex-1 overflow-hidden">
        {tab === 'chat' ? <Chat /> : <Settings />}
      </main>
    </div>
  );
}
