// 556d client: the ONLY backend the renderer talks to (hub architecture).
export const BASE = 'http://127.0.0.1:55600';

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export type Settings = {
  companion_name: string;
  your_name: string;
  reply_language: string;
  mirror_to_telegram: boolean;
  avatar_model: string;
  show_avatar_on_start: boolean;
  memory_language: string;
  model_lane: string;
  context_turns: number;
  embedder_model: string;
};

export type MemoryItem = {
  id: number; text: string; tags: string[]; archived: number; superseded: boolean;
  archive_reason: string | null; created_at: number; updated_at: number; layer: 'long' | 'short';
};
export type MemoryStats = {
  memories: number; short: number; archived: number; superseded: number; tags: number;
  owner_alive: boolean; pending_commands: number; file_bytes: number; path: string;
};
export type MemoryTag = { tag: string; count: number };
export type VoiceProvider = { kind: string; base_url: string; api_key?: string; api_key_set?: boolean; model: string; voice?: string; format?: string; language?: string };
export type ToolExtension = { key: string; label: string; help: string; toolsets: string[]; acts_in_world: boolean; enabled: boolean };
export type VoiceHandsFree = { threshold: number; min_silence_ms: number; pre_roll_s: number; grace_s: number; min_turn_s: number; max_turn_s: number; echo_guard: boolean; spoken_style: string };
export type VoiceConfig = { tts: VoiceProvider; stt: VoiceProvider; handsfree?: VoiceHandsFree };
export type Knob = { key: string; group: string; label: string; help: string; type: string; options?: string[]; scope: string; dev: boolean; effect: string; value: any; set?: boolean };
export type CompanionInfo = {
  name: string; display_name: string; avatar_model: string; active: boolean; hermes_connected: boolean;
  stopping: boolean; api_port: number; channels: string[]; gateway: boolean; dir: string;
};

// Error text of a failed response: the hub's {"error"} JSON, else the raw body (an old daemon
// answers unknown routes with Go's plain "404 page not found").
async function errorOf(r: Response): Promise<string> {
  const body = await r.text();
  try { return JSON.parse(body).error || `HTTP ${r.status}`; } catch { return `HTTP ${r.status}: ${body.slice(0, 120).trim()}`; }
}

export type PsycheInstance = { id: string; born_at: number; type: string; target: string; cause: string; intensity0: number; half_life_h: number; stack_key: string; loop_id: string | null; resolved_at: number | null; resolved_by: string | null };
export type PsycheLoop = { id: string; what: string; origin: string; cue_time: string | null; importance: number; state: string; created_at: number; closed_at: number | null };
export type PsycheEvent = { id: number; at: number; kind: string; counterpart: string; payload: any };
export type PsycheAppraisal = { id: number; at: number; turn_id: string; platform: string; data: any; error: string | null; ms: number; applied_tick: number | null };
export type PsycheView = { companion: string; exists: boolean; running?: boolean; snapshot_at?: number;
  snapshot?: { tick: number; t: number; affect: { pos: number; neg: number; ar: number }; mood: number[]; energy: number;
    activity?: string; needs?: Record<string, number>; contact?: Record<string, any>; sleep?: Record<string, any>; last_block?: { text?: string } };
  instances?: PsycheInstance[]; loops?: PsycheLoop[]; events?: PsycheEvent[]; appraisals?: PsycheAppraisal[];
  checks?: { id: number; at: number; platform: string; hits: Record<string, string[]>; excerpt: string }[]; checks_total?: number };
export type PsycheSettings = Record<string, any>;

export const api = {
  // 狀態: her inner state, read-only from psyche.db
  psyche: () => get<PsycheView>('/api/psyche'),
  psycheSettings: () => get<{ companion: string; exists: boolean; settings: PsycheSettings }>('/api/psyche/settings'),
  updatePsycheSettings: async (patch: PsycheSettings) => {
    const r = await fetch(BASE + '/api/psyche/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ settings: PsycheSettings; restart_required: boolean }>;
  },
  // a command for the engine (single writer): queued in psyche.db, drained on her next tick
  psycheCommand: async (op: 'close_loop' | 'add_loop' | 'life_event', payload: Record<string, any>) => {
    const r = await fetch(BASE + '/api/psyche/command', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ op, payload }) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ id: number; queued: boolean }>;
  },
  memory: (p: { q?: string; tag?: string; archived?: boolean; limit?: number; layer?: 'long' | 'short' } = {}) => {
    const qs = new URLSearchParams();
    if (p.layer) qs.set('layer', p.layer);
    if (p.q) qs.set('q', p.q);
    if (p.tag) qs.set('tag', p.tag);
    if (p.archived) qs.set('archived', '1');
    if (p.limit) qs.set('limit', String(p.limit));
    const s = qs.toString();
    return get<{ exists: boolean; stats?: MemoryStats; tags?: MemoryTag[]; memories: MemoryItem[] }>(`/api/memory${s ? `?${s}` : ''}`);
  },
  // delete-only by design: goes through the KeepsakeDB command queue to the owning Hermes process
  deleteMemory: async (ids: number[], reason: string) => {
    const r = await fetch(BASE + '/api/memory/delete', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ids, reason }) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ status: 'done' | 'queued' | 'error'; count: number; command_id: number }>;
  },
  companion: () => get<{ name: string; profile: string; active: boolean; avatar_model_url: string; hermes_connected: boolean; channels?: string[] }>('/api/companion'),
  companions: () => get<{ companions: CompanionInfo[]; selected: string }>('/api/companions'),
  companionAction: async (name: string, action: 'start' | 'stop') => {
    const r = await fetch(`${BASE}/api/companions/${encodeURIComponent(name)}/${action}`, { method: 'POST' });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ companion: CompanionInfo }>;
  },
  select: async (name: string) => {
    const r = await fetch(BASE + '/api/selected', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ selected: string; companion: CompanionInfo }>;
  },
  history: (limit?: number) => get<{ turns: number; messages: { role: 'user' | 'assistant'; text: string; ts?: number; source?: string }[] }>(`/api/history${limit ? `?limit=${limit}` : ''}`),
  settings: () => get<{ settings: Settings }>('/api/settings'),
  updateSettings: async (patch: Partial<Settings>) => {
    const r = await fetch(BASE + '/api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ settings: Settings; restart_required: boolean; reembed_required: boolean }>;
  },
  restartHermes: () => fetch(BASE + '/api/restart-hermes', { method: 'POST' }),
  voice: () => get<{ voice: VoiceConfig; kinds: string[] }>('/api/voice'),
  config: () => get<{ knobs: Knob[]; companion: string }>('/api/config'),
  updateConfig: async (patch: Record<string, any>) => {
    const r = await fetch(BASE + '/api/config', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ effects: Record<string, boolean>; errors: string[] }>;
  },
  updateVoice: async (patch: Partial<VoiceConfig>) => {
    const r = await fetch(BASE + '/api/voice', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ voice: VoiceConfig }>;
  },
  testVoice: async (text?: string) => {
    const r = await fetch(BASE + '/api/voice/test', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ tts: { ok: boolean; ms?: number; bytes?: number; error?: string; audio_data_url?: string }; stt: { ok: boolean; ms?: number; text?: string; error?: string } }>;
  },
  models: () => get<{ models: { name: string; models: string[] }[] }>('/api/models'),
  // Fire-and-forget send: the reply arrives through the hub WebSocket, never through this response.
  send: async (text: string, client: string, voice = false) => {
    const r = await fetch(BASE + '/api/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'X-556-Client': client, ...(voice ? { 'X-556-Voice': '1' } : {}) },
      body: JSON.stringify({ model: '556', stream: false, messages: [{ role: 'user', content: text }] }),
    });
    if (!r.ok) throw new Error(`send: HTTP ${r.status}`);
  },
  // voice modes: one recorded turn -> text; one reply -> cached audio (+ speak_audio for the avatar)
  transcribe: async (blob: Blob, lang?: string) => {
    const r = await fetch(BASE + '/api/voice/transcribe' + (lang ? `?lang=${encodeURIComponent(lang)}` : ''), { method: 'POST', headers: { 'content-type': blob.type || 'audio/webm' }, body: blob });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ text: string; ms: number }>;
  },
  speak: async (text: string) => {
    const r = await fetch(BASE + '/api/voice/speak', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ audio_url: string; text: string; ms: number; bytes: number }>;
  },
  speakEnd: () => fetch(BASE + '/api/voice/speak', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action: 'end' }) }).then(() => undefined),
  speakPlaying: () => fetch(BASE + '/api/voice/speak', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action: 'playing' }) }).then(() => undefined),
  // tools: baseline memory + extensions per character; a restart applies changes
  tools: () => get<{ companion: string; baseline: string[]; configured: boolean; extensions: ToolExtension[] }>('/api/tools'),
  setTool: async (key: string, enabled: boolean) => {
    const r = await fetch(BASE + '/api/tools', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ key, enabled }) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ extensions: ToolExtension[]; toolsets: string[]; restart_required: boolean }>;
  },
};

// Exposed by electron/preload.ts
declare global {
  interface Window {
    desktop?: { toggleAvatar(): void; dragStart(x: number, y: number): void; dragEnd(): void };
  }
}
