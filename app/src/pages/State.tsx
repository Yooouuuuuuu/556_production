import { useEffect, useState } from 'react';
import { api, PsycheView, PsycheInstance } from '../api';
import { t } from '../i18n';

// 狀態 tab: how she is right now, read from her psyche.db (the engine inside her process writes it;
// 556d only reads). Words first, numbers small: the same material her state block is made of.

const EMOTION_ZH: Record<string, string> = {
  joy: '開心', distress: '難過', hope: '期待', fear: '擔心', satisfaction: '滿足', disappointment: '失望',
  relief: '鬆了口氣', gratitude: '感激', anger: '生氣', pride: '得意', shame: '不好意思', liking: '喜歡',
  disliking: '反感', happy_for: '替對方高興', sorry_for: '替對方難過', longing: '想念', hurt: '委屈',
};
const OCTANTS: Record<string, string> = {
  '1,1,1': '興致勃勃', '1,1,-1': '撒嬌黏人', '1,-1,1': '自在', '1,-1,-1': '溫和乖巧',
  '-1,1,1': '不爽', '-1,1,-1': '不安', '-1,-1,1': '冷淡', '-1,-1,-1': '悶',
};
const word = (x: number) => (x < 0.2 ? '' : x < 0.45 ? '有點' : x < 0.7 ? '蠻' : '很');
const energyWord = (e: number) => (e >= 0.75 ? '精神很好' : e >= 0.55 ? '精神還不錯' : e >= 0.35 ? '有點累' : '很累');
const intensityNow = (i: PsycheInstance, now: number) => i.intensity0 * Math.pow(0.5, Math.max(0, now - i.born_at) / 3600 / Math.max(1e-6, i.half_life_h));
const ago = (ts: number, now: number) => {
  const m = Math.max(0, Math.round((now - ts) / 60));
  return m < 1 ? '剛剛' : m < 60 ? `${m} 分鐘前` : m < 1440 ? `${Math.round(m / 60)} 小時前` : `${Math.round(m / 1440)} 天前`;
};

export function State() {
  const [v, setV] = useState<PsycheView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now() / 1000);

  useEffect(() => {
    let alive = true;
    const load = () => api.psyche().then((r) => { if (alive) { setV(r); setErr(null); setNow(Date.now() / 1000); } }).catch((e) => alive && setErr(String(e)));
    load();
    const id = setInterval(load, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (err) return <div className="p-4 text-sm text-red-300">{err}</div>;
  if (!v) return <div className="p-4 text-sm opacity-60">…</div>;
  if (!v.exists) return <div className="p-4 text-sm opacity-60">{t('state.no_engine')}</div>;

  const snap = v.snapshot;
  const mood = snap?.mood ?? [0, 0, 0];
  const key = mood.map((x) => (x >= 0 ? 1 : -1)).join(',');
  const strength = Math.min(1, Math.sqrt(mood[0] ** 2 + mood[1] ** 2 + mood[2] ** 2) / Math.sqrt(3));
  const moodWord = strength < 0.2 ? '平靜' : `${word(strength)}${OCTANTS[key]}`;
  const active = (v.instances ?? []).filter((i) => i.resolved_at == null).map((i) => ({ ...i, now: intensityNow(i, now) })).filter((i) => i.now >= 0.02).sort((a, b) => b.now - a.now);
  const loops = (v.loops ?? []).filter((l) => l.state !== 'closed');

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 text-sm">
      <div className="flex items-center gap-3 text-xs opacity-60">
        <span>{v.running ? t('state.running') : t('state.stopped')}</span>
        {v.snapshot_at ? <span>{t('state.snapshot_at')} {ago(v.snapshot_at, now)}</span> : null}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-white/5 p-3">
          <div className="text-xs opacity-60">{t('state.energy')}</div>
          <div className="text-lg">{snap ? energyWord(snap.energy) : '—'}</div>
          {snap && <div className="h-1 mt-2 rounded bg-white/10"><div className="h-1 rounded bg-pink-400/70" style={{ width: `${Math.round(snap.energy * 100)}%` }} /></div>}
        </div>
        <div className="rounded-lg bg-white/5 p-3">
          <div className="text-xs opacity-60">{t('state.mood')}</div>
          <div className="text-lg">{snap ? moodWord : '—'}</div>
          {snap && <div className="text-xs opacity-50 mt-1">P {mood[0].toFixed(2)} · A {mood[1].toFixed(2)} · D {mood[2].toFixed(2)} · 正 {snap.affect.pos.toFixed(2)} 負 {snap.affect.neg.toFixed(2)}</div>}
        </div>
      </div>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.feelings')}</h3>
        {active.length === 0 ? <div className="opacity-50">{t('state.none')}</div> : (
          <ul className="space-y-1">
            {active.map((i) => (
              <li key={i.id} className="flex gap-2 items-baseline">
                <span className="shrink-0">{word(i.now) || '一點'}{EMOTION_ZH[i.type] ?? i.type}</span>
                <span className="opacity-70 flex-1">{i.cause}</span>
                <span className="text-xs opacity-40 shrink-0">{ago(i.born_at, now)}{i.resolved_by ? ` · ${i.resolved_by}` : ''}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.loops')}</h3>
        {loops.length === 0 ? <div className="opacity-50">{t('state.none')}</div> : (
          <ul className="space-y-1">{loops.map((l) => <li key={l.id}>{l.what}{l.cue_time ? <span className="text-xs opacity-50"> · {l.cue_time.replace('T', ' ')}</span> : null}</li>)}</ul>
        )}
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.events')}</h3>
        <ul className="space-y-1">
          {(v.events ?? []).slice(0, 30).map((e) => {
            const p = e.payload ?? {};
            const text = e.kind === 'turn' ? `💬 ${String(p.user ?? '').slice(0, 80)}`
              : e.kind === 'appraisal_applied' ? `✦ ${(p.events ?? []).join('、') || '（沒有事件）'}${(p.born ?? []).length ? ` → ${p.born.length} 個情緒` : ''}`
              : e.kind === 'start' ? `▶ 開始（補了 ${p.gap_ticks ?? 0} 分鐘）` : e.kind === 'stop' ? '■ 停止' : e.kind;
            return <li key={e.id} className="flex gap-2"><span className="text-xs opacity-40 shrink-0 w-20">{ago(e.at, now)}</span><span className="opacity-80 truncate">{text}</span></li>;
          })}
        </ul>
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.appraisals')}</h3>
        <ul className="space-y-1">
          {(v.appraisals ?? []).slice(0, 10).map((a) => {
            const evs = (a.data?.events ?? []) as { event_kind: string; cause: string; v: number; R: number }[];
            return (
              <li key={a.id} className="flex gap-2">
                <span className="text-xs opacity-40 shrink-0 w-20">{ago(a.at, now)}</span>
                <span className={`flex-1 truncate ${a.error ? 'text-red-300' : 'opacity-80'}`}>
                  {a.error ? a.error : evs.length ? evs.map((e) => `${e.event_kind}（${e.cause}）`).join('；') : '（沒有事件）'}
                </span>
                <span className="text-xs opacity-40 shrink-0">{Math.round(a.ms / 1000)} s{a.applied_tick == null && !a.error ? ' · 待套用' : ''}</span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
