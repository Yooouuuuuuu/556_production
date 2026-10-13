import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useStore } from '../store';
import { t } from '../i18n';
import { PushToTalk } from '../voice/recorder';
import { useVoice } from '../voice/loop';

// The office chat: last X turns from /api/history, live updates from the hub, IME-safe composer.
export function Chat() {
  const { messages, talking, connected, error, setHistory, connect, selected, setHandsFree, setProactiveSpeak } = useStore();
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const voice = useVoice();
  const ptt = useRef(new PushToTalk());
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceOk, setVoiceOk] = useState({ stt: false, tts: false });

  useEffect(() => {
    connect();
    api.voice().then((v) => setVoiceOk({ stt: v.voice.stt.kind !== 'none', tts: v.voice.tts.kind !== 'none' })).catch(() => {});
    api.psycheSettings().then((r) => setProactiveSpeak((r.settings?.proactive?.speak as any) ?? 'follow')).catch(() => {});
    api.history().then((h) => setHistory(h.messages.map((m, i) => ({ id: `h${i}`, role: m.role, text: m.text, ts: m.ts, source: m.source }))))
      .catch(() => { /* backend not up yet; the header shows the status */ });
  }, [selected]);

  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight }); }, [messages, talking]);
  useEffect(() => { setHandsFree(voice.handsfree); }, [voice.handsfree]);

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

  // Mode 1: press to record, press again to stop; the transcript lands in the composer.
  async function toggleRecord() {
    try {
      if (recording) {
        setRecording(false);
        setTranscribing(true);
        const blob = await ptt.current.stop();
        const r = await api.transcribe(blob);
        if (r.text.trim()) setDraft((d) => (d.trim() ? d.trimEnd() + ' ' : '') + r.text.trim());
      } else {
        await ptt.current.start();
        setRecording(true);
      }
    } catch (e) {
      setRecording(false);
      useStore.setState({ error: String(e) });
    } finally {
      setTranscribing(false);
    }
  }

  // Mode 2: conversation mode — the mic stays open, the text box is locked.
  function toggleHandsFree() {
    if (voice.handsfree) voice.stop();
    else voice.start().catch((e) => useStore.setState({ error: String(e) }));
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
        {messages.length === 0 && <p className="opacity-50 text-sm">{selected ? t('chat.empty') : t('chat.no_companion')}</p>}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[78%] px-3 py-2 rounded-2xl whitespace-pre-wrap leading-relaxed text-[15px] ${
              m.role === 'user' ? 'bg-pink-500/80 text-white rounded-br-sm' : 'bg-white/10 rounded-bl-sm'
            } ${m.streaming ? 'animate-pulse' : ''}`}>
              {m.source && m.source !== 'app' && <span className="block text-[10px] uppercase tracking-wider opacity-60 mb-0.5">{m.source === 'event' ? t('chat.badge_event') : m.source}</span>}
              {m.text}
            </div>
          </div>
        ))}
        {talking && !messages[messages.length - 1]?.streaming && (
          <div className="text-xs opacity-60 pl-1">{t('chat.thinking')}</div>
        )}
      </div>
      {error && <div className="mx-4 mb-2 px-3 py-1.5 rounded bg-red-500/20 text-red-200 text-xs">{error}</div>}
      {!connected && <div className="mx-4 mb-2 px-3 py-1.5 rounded bg-amber-500/20 text-amber-200 text-xs">{t('chat.offline')}</div>}
      {voice.handsfree && (
        <div className="mx-4 mb-2 px-3 py-1.5 rounded bg-pink-500/15 text-pink-100 text-xs flex gap-2 items-center">
          <span className={voice.phase === 'listening' ? 'animate-pulse' : ''}>{t('chat.phase.' + voice.phase)}</span>
          {voice.queue > 0 && <span className="opacity-70">· {t('chat.queued').replace('{n}', String(voice.queue))}</span>}
          {voice.last && <span className="opacity-70 truncate">· {voice.last}</span>}
          {voice.error && <span className="text-red-300 truncate">· {voice.error}</span>}
        </div>
      )}
      <div className="border-t border-white/10 p-3 flex gap-2 items-end">
        <textarea
          className="flex-1 resize-none rounded-xl bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-pink-400/60 text-[15px] disabled:opacity-50"
          rows={2}
          disabled={voice.handsfree}
          placeholder={voice.handsfree ? t('chat.handsfree_placeholder') : t('chat.placeholder')}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
        />
        <button
          className={`px-3 py-2 rounded-xl disabled:opacity-40 ${recording ? 'bg-red-500/80 text-white animate-pulse' : 'bg-white/10 hover:bg-white/20'}`}
          disabled={!voiceOk.stt || voice.handsfree || transcribing}
          title={voiceOk.stt ? (recording ? t('chat.recording') : t('chat.record')) : t('chat.voice_off')}
          onClick={toggleRecord}
        >
          {transcribing ? '…' : recording ? '■' : '🎙'}
        </button>
        <button
          className={`px-3 py-2 rounded-xl text-sm disabled:opacity-40 ${voice.handsfree ? 'bg-pink-500/80 text-white' : 'bg-white/10 hover:bg-white/20'}`}
          disabled={!voiceOk.stt || !voiceOk.tts}
          title={voiceOk.stt && voiceOk.tts ? '' : t('chat.voice_off')}
          onClick={toggleHandsFree}
        >
          {voice.handsfree ? t('chat.handsfree_stop') : t('chat.handsfree')}
        </button>
        <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={!draft.trim() || sending || voice.handsfree} onClick={send}>
          {t('chat.send')}
        </button>
      </div>
    </div>
  );
}
