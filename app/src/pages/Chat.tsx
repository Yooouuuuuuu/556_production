import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useStore } from '../store';
import { t } from '../i18n';

// The office chat: last X turns from /api/history, live updates from the hub, IME-safe composer.
export function Chat() {
  const { messages, talking, connected, error, setHistory, connect } = useStore();
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const composing = useRef(false);

  useEffect(() => {
    connect();
    api.history().then((h) => setHistory(h.messages.map((m, i) => ({ id: `h${i}`, role: m.role, text: m.text, ts: m.ts }))))
      .catch(() => { /* backend not up yet; the header shows the status */ });
  }, []);

  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight }); }, [messages, talking]);

  async function send() {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft('');
    setSending(true);
    try {
      await api.send(text, 'office');
    } catch (e) {
      useStore.setState({ error: String(e) });
    } finally {
      setSending(false);
    }
  }

  // Enter sends — but never while an IME composition (注音/拼音) is in progress.
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Enter' || e.shiftKey) return;
    if (composing.current || e.nativeEvent.isComposing || (e.nativeEvent as any).keyCode === 229) return;
    e.preventDefault();
    send();
  }

  return (
    <div className="h-full flex flex-col">
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && <p className="opacity-50 text-sm">{t('chat.empty')}</p>}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[78%] px-3 py-2 rounded-2xl whitespace-pre-wrap leading-relaxed text-[15px] ${
              m.role === 'user' ? 'bg-pink-500/80 text-white rounded-br-sm' : 'bg-white/10 rounded-bl-sm'
            } ${m.streaming ? 'animate-pulse' : ''}`}>{m.text}</div>
          </div>
        ))}
        {talking && !messages[messages.length - 1]?.streaming && (
          <div className="text-xs opacity-60 pl-1">{t('chat.thinking')}</div>
        )}
      </div>
      {error && <div className="mx-4 mb-2 px-3 py-1.5 rounded bg-red-500/20 text-red-200 text-xs">{error}</div>}
      {!connected && <div className="mx-4 mb-2 px-3 py-1.5 rounded bg-amber-500/20 text-amber-200 text-xs">{t('chat.offline')}</div>}
      <div className="border-t border-white/10 p-3 flex gap-2 items-end">
        <textarea
          className="flex-1 resize-none rounded-xl bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-pink-400/60 text-[15px]"
          rows={2}
          placeholder={t('chat.placeholder')}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
        />
        <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={!draft.trim() || sending} onClick={send}>
          {t('chat.send')}
        </button>
      </div>
    </div>
  );
}
