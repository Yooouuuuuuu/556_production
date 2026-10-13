// 556d client: the ONLY backend the renderer talks to (hub architecture).
export const BASE = 'http://127.0.0.1:55600';

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export type Settings = {
  companion_name: string;
  avatar_model: string;
  show_avatar_on_start: boolean;
  memory_language: string;
  model_lane: string;
  context_turns: number;
  embedder_model: string;
};

export const api = {
  companion: () => get<{ name: string; profile: string; avatar_model_url: string; hermes_connected: boolean }>('/api/companion'),
  history: (limit?: number) => get<{ turns: number; messages: { role: 'user' | 'assistant'; text: string; ts?: number }[] }>(`/api/history${limit ? `?limit=${limit}` : ''}`),
  settings: () => get<{ settings: Settings }>('/api/settings'),
  updateSettings: async (patch: Partial<Settings>) => {
    const r = await fetch(BASE + '/api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error((await r.json()).error || `HTTP ${r.status}`);
    return r.json() as Promise<{ settings: Settings; restart_required: boolean; reembed_required: boolean }>;
  },
  restartHermes: () => fetch(BASE + '/api/restart-hermes', { method: 'POST' }),
  models: () => get<{ models: { name: string; models: string[] }[] }>('/api/models'),
  // Fire-and-forget send: the reply arrives through the hub WebSocket, never through this response.
  send: async (text: string, client: string) => {
    const r = await fetch(BASE + '/api/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'X-556-Client': client },
      body: JSON.stringify({ model: '556', stream: false, messages: [{ role: 'user', content: text }] }),
    });
    if (!r.ok) throw new Error(`send: HTTP ${r.status}`);
  },
};

// Exposed by electron/preload.ts
declare global {
  interface Window {
    desktop?: { toggleAvatar(): void; dragStart(x: number, y: number): void; dragEnd(): void };
  }
}
