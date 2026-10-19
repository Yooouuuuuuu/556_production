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
  context_turns: number;
};

// 設定 → 全域 → 模型連線 (home/models.json). Keys never come back: api_key is write-only, api_key_set says one is stored.
export type Endpoint = { method: string; base_url: string; api_key?: string; model: string };
export type Use = Endpoint & { use: 'master' | 'custom' };
export type EmbedderConn = { kind: string; exe: string; file: string; port: number; base_url: string; api_key?: string; model: string; dims: number };
export type Connections = { master: Endpoint; chat: Use; memory: Use; soul: Use; embedder: EmbedderConn; timezone: string };
export type ConnectionsView = { exists: boolean; connections: any; missing: string[]; restart_required?: boolean; embedder_status?: { kind: string; local_running: boolean; port: number } };

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
export type PsycheLoop = { id: string; what: string; origin: string; cue_time: string | null; importance: number; state: string; created_at: number; closed_at: number | null;
  ask?: string | null; asking?: string | null; answer?: string | null; tries?: number | null; fails?: number | null; why?: string | null; outcome?: string | null };
export type PsycheEvent = { id: number; at: number; kind: string; counterpart: string; payload: any };
export type PsycheAppraisal = { id: number; at: number; turn_id: string; platform: string; data: any; error: string | null; ms: number; applied_tick: number | null };
export type PsycheView = { companion: string; exists: boolean; running?: boolean; snapshot_at?: number;
  snapshot?: { tick: number; t: number; affect: { pos: number; neg: number; ar: number }; mood: number[]; energy: number;
    activity?: string; needs?: Record<string, number>; contact?: Record<string, any>; sleep?: Record<string, any>; last_block?: { text?: string; strategy?: string };
    rel?: Record<string, any>; rel_words?: Record<string, string>; ledger?: Record<string, any[]>; others?: Record<string, any>; last_strategy?: Record<string, string> };
  inter_agent_visibility?: boolean;
  instances?: PsycheInstance[]; loops?: PsycheLoop[]; events?: PsycheEvent[]; appraisals?: PsycheAppraisal[];
  checks?: { id: number; at: number; platform: string; hits: Record<string, string[]>; excerpt: string }[]; checks_total?: number };
export type PsycheSettings = Record<string, any>;
export type RelayConversation = { counterpart: string; session_id: string; last_ts: number; messages: { role: string; text: string; ts: number }[] };

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
  // her conversations with the other characters (read-only; shown when 主動 → inter_agent_visibility)
  relayLog: () => get<{ companion: string; conversations: RelayConversation[]; names: Record<string, string> }>('/api/relay/log'),
  psycheCommand: async (op: 'close_loop' | 'add_loop' | 'life_event' | 'feedback', payload: Record<string, any>) => {
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
  connections: () => get<ConnectionsView>('/api/connections'),
  updateConnections: async (c: Connections) => {
    const r = await fetch(BASE + '/api/connections', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(c) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<ConnectionsView & { restart_required: boolean }>;
  },
  probeConnection: async (body: { base_url: string; api_key?: string; job?: string }) => {
    const r = await fetch(BASE + '/api/connections/probe', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ ok: boolean; models: string[]; error?: string }>;
  },
  updateSettings: async (patch: Partial<Settings>) => {
    const r = await fetch(BASE + '/api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ settings: Settings; restart_required: boolean; reembed_required: boolean }>;
  },
  restartHermes: () => fetch(BASE + '/api/restart-hermes', { method: 'POST' }),
  // voice connectors: global, or one character's override (+ the effective config) with `companion`
  voice: (companion?: string) => get<{ voice: VoiceConfig; effective?: VoiceConfig; kinds: string[]; companion?: string }>('/api/voice' + (companion ? `?companion=${encodeURIComponent(companion)}` : '')),
  config: () => get<{ knobs: Knob[]; companion: string }>('/api/config'),
  updateConfig: async (patch: Record<string, any>) => {
    const r = await fetch(BASE + '/api/config', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ effects: Record<string, boolean>; errors: string[] }>;
  },
  updateVoice: async (patch: Partial<VoiceConfig>, companion?: string) => {
    const r = await fetch(BASE + '/api/voice' + (companion ? `?companion=${encodeURIComponent(companion)}` : ''), { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(await errorOf(r));
    return r.json() as Promise<{ voice: VoiceConfig; effective?: VoiceConfig }>;
  },
  testVoice: async (text?: string, companion?: string) => {
    const r = await fetch(BASE + '/api/voice/test' + (companion ? `?companion=${encodeURIComponent(companion)}` : ''), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) });
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

// The create-character page: packages under characters/<id> (describe/ in the person's words, profile.json,
// the generated SOUL and files) and the soul skill run as a 556d job. See docs/prompt/prompt.md §2.9.
export type CharPackage = { id: string; display_name: string; avatar_model: string; describe_filled: number; describe_total: number; phases: string[]; has_soul: boolean; installed: boolean; running: boolean; job_kind: string; lock: any; stale: string[] };
export type CharJob = { running: boolean; kind: string; phase: string; model: string; started_at: number | null; exit_code: number; error: string; log: string };
export type CharProfile = { pronoun?: string; closeness?: string | null; scratch?: boolean; simple?: { who?: string; talk?: string; refuses?: string } | null; big5?: Record<string, number | null>; constants?: Record<string, number | null>; thinking?: Record<string, number | null>; choices?: Record<string, string | null>; schedule?: any; proposed?: { big5?: Record<string, number | null>; constants?: Record<string, number | null>; thinking?: Record<string, number | null>; choices?: Record<string, string | null>; evidence?: Record<string, string>; model?: string; at?: string } | null };
export type CharDetail = { character: CharPackage; describe: Record<string, string>; profile: CharProfile | null; build: Record<string, any>; check: string; verify: string; soul: string; seeds: number; people: string[]; job: CharJob };

async function send<T>(path: string, method: 'POST' | 'PUT', body?: any): Promise<T> {
  const r = await fetch(BASE + path, { method, headers: { 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!r.ok) throw new Error(await errorOf(r));
  return r.json() as Promise<T>;
}

export const chars = {
  list: () => get<{ characters: CharPackage[]; template: Record<string, string>; model: string; models: string[]; phases: string[] }>('/api/characters'),
  create: (body: { id: string; display_name: string; pronoun: string; avatar?: string; from_example: boolean }) => send<{ character: CharPackage; output: string }>('/api/characters', 'POST', body),
  detail: (id: string) => get<CharDetail>(`/api/characters/${encodeURIComponent(id)}`),
  saveDescribe: (id: string, files: Record<string, string>) => send<{ saved: number; character: CharPackage }>(`/api/characters/${encodeURIComponent(id)}/describe`, 'PUT', { files }),
  saveProfile: (id: string, profile: Partial<CharProfile>) => send<{ profile: CharProfile }>(`/api/characters/${encodeURIComponent(id)}/profile`, 'PUT', { profile }),
  simple: (id: string, force = false) => send<{ started: boolean; job: CharJob }>(`/api/characters/${encodeURIComponent(id)}/simple`, 'POST', { force }),
  run: (id: string, body: { phase: string; from?: string; model?: string; yes?: boolean; force?: boolean }) => send<{ started: boolean; job: CharJob }>(`/api/characters/${encodeURIComponent(id)}/run`, 'POST', body),
  install: (id: string, force = false) => send<{ started: boolean; job: CharJob }>(`/api/characters/${encodeURIComponent(id)}/install`, 'POST', { force }),
  job: (id: string) => get<{ job: CharJob }>(`/api/characters/${encodeURIComponent(id)}/job`),
};
