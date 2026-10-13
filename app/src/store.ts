// Conversation state fed by the 556d hub WebSocket. Every window shares the same stream, so
// the office chat, the avatar bubble and (later) other clients always agree.
import { create } from 'zustand';
import { BASE } from './api';

export type Msg = { id: string; role: 'user' | 'assistant'; text: string; ts?: number; streaming?: boolean };

type State = {
  messages: Msg[];
  talking: boolean;
  connected: boolean;
  error: string | null;
  bubble: { text: string } | null;           // avatar speech bubble (bridge 'message' events)
  motion: { name: string; n: number } | null; // last requested motion (bridge 'motion' events)
  setHistory(msgs: Msg[]): void;
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
  bubble: null,
  motion: null,

  setHistory(msgs) { set({ messages: msgs }); },

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
        const { messages } = get();
        switch (ev.type) {
          case 'chat.user':
            set({ messages: [...messages, { id: nextId(), role: 'user', text: ev.text, ts: Date.now() / 1000 }], error: null });
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
            const last = messages[messages.length - 1];
            if (last && last.role === 'assistant' && last.streaming) {
              set({ messages: [...messages.slice(0, -1), { ...last, text: ev.text || last.text, streaming: false, ts: Date.now() / 1000 }] });
            } else if (ev.text) {
              set({ messages: [...messages, { id: nextId(), role: 'assistant', text: ev.text, ts: Date.now() / 1000 }] });
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
          case 'emotion':
            if (ev.motion) set({ motion: { name: ev.motion, n: Date.now() } });
            break;
        }
      };
    };
    open();
  },
}));
