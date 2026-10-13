// Conversation state fed by the 556d hub WebSocket. Every window shares the same stream, so
// the office chat, the avatar bubble and (later) other clients always agree.
import { create } from 'zustand';
import { BASE } from './api';

export type Msg = { id: string; role: 'user' | 'assistant'; text: string; ts?: number; streaming?: boolean; source?: string };

type State = {
  messages: Msg[];
  talking: boolean;
  connected: boolean;
  error: string | null;
  selected: string;                          // companion the windows are on (roster selection)
  selectedName: string;                      // her display name
  avatarUrl: string | null;                  // her model (avatar follows the chat window)
  bubble: { text: string } | null;           // avatar speech bubble (bridge 'message' events)
  motion: { name: string; n: number } | null; // last requested motion (bridge 'motion' events)
  lastReply: { n: number; text: string; status: string; source?: string } | null; // her latest completed reply (voice loop waits on it)
  speaking: { url: string; n: number; playing: boolean } | null; // speak_audio: the avatar lip-syncs / plays it
  setHistory(msgs: Msg[]): void;
  setSelected(name: string, displayName?: string, avatarUrl?: string | null): void;
  connect(): void;
};

let bubbleTimer: ReturnType<typeof setTimeout> | null = null;

let socket: WebSocket | null = null;
let seq = 0;
const nextId = () => `m${Date.now()}-${seq++}`;

export const useStore = create<State>((set, get) => ({
  messages: [],
  talking: false,
  connected: false,
  error: null,
  selected: '',
  selectedName: '',
  avatarUrl: null,
  bubble: null,
  motion: null,
  lastReply: null,
  speaking: null,

  setHistory(msgs) { set({ messages: msgs }); },
  setSelected(name, displayName, avatarUrl) {
    const cur = get();
    if (name !== cur.selected) set({ selected: name, messages: [], talking: false, error: null, bubble: null });
    set({ selectedName: displayName ?? cur.selectedName, ...(avatarUrl !== undefined ? { avatarUrl } : {}) });
  },

  connect() {
    if (socket) return;
    const open = () => {
      socket = new WebSocket(BASE.replace(/^http/, 'ws') + '/ws');
      socket.onopen = () => set({ connected: true, error: null });
      socket.onclose = () => { set({ connected: false }); socket = null; setTimeout(open, 2000); };
      socket.onerror = () => { /* onclose follows */ };
      socket.onmessage = (e) => {
        let ev: any;
        try { ev = JSON.parse(e.data); } catch { return; }
        const { messages, selected } = get();
        // roster / selection events are global; conversation events belong to one companion
        if (ev.type === 'companion.selected') {
          get().setSelected(ev.companion, ev.display_name, ev.avatar_model_url ? BASE + ev.avatar_model_url : null);
          return;
        }
        if (ev.type === 'companion.lifecycle') return;
        if (ev.companion && selected && ev.companion !== selected) return;
        switch (ev.type) {
          case 'chat.user':
            set({ messages: [...messages, { id: nextId(), role: 'user', text: ev.text, ts: Date.now() / 1000, source: ev.source }], error: null });
            break;
          case 'chat.delta': {
            const last = messages[messages.length - 1];
            if (last && last.role === 'assistant' && last.streaming) {
              set({ messages: [...messages.slice(0, -1), { ...last, text: last.text + ev.text }] });
            } else {
              set({ messages: [...messages, { id: nextId(), role: 'assistant', text: ev.text, streaming: true }] });
            }
            break;
          }
          case 'chat.complete': {
            set({ lastReply: { n: Date.now(), text: ev.text ?? '', status: ev.status ?? 'stop', source: ev.source } });
            const last = messages[messages.length - 1];
            if (last && last.role === 'assistant' && last.streaming) {
              set({ messages: [...messages.slice(0, -1), { ...last, text: ev.text || last.text, streaming: false, ts: Date.now() / 1000, source: ev.source ?? last.source }] });
            } else if (ev.text) {
              set({ messages: [...messages, { id: nextId(), role: 'assistant', text: ev.text, ts: Date.now() / 1000, source: ev.source }] });
            }
            break;
          }
          case 'chat.error':
            set({ error: ev.message || 'error' });
            break;
          case 'companion.state':
            set({ talking: !!ev.talking });
            break;
          // avatar bridge events (same hub)
          case 'message': {
            if (bubbleTimer) clearTimeout(bubbleTimer);
            set({ bubble: { text: ev.text } });
            bubbleTimer = setTimeout(() => set({ bubble: null }), ev.duration || 5000);
            break;
          }
          case 'motion':
            set({ motion: { name: ev.name, n: Date.now() } });
            break;
          case 'speak_audio': {
            const cur = get().speaking;
            if (ev.action === 'start' && ev.audio_url) set({ speaking: { url: ev.audio_url, n: Date.now(), playing: false } });
            else if (ev.action === 'playing') { if (cur) set({ speaking: { ...cur, playing: true } }); }
            else set({ speaking: null });
            break;
          }
          case 'emotion':
            if (ev.motion) set({ motion: { name: ev.motion, n: Date.now() } });
            break;
        }
      };
    };
    open();
  },
}));
