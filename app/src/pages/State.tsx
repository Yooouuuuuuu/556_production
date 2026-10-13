import { useEffect, useState } from 'react';
import { api, PsycheView, PsycheInstance } from '../api';
import { t } from '../i18n';

// 狀態 tab: how she is right now, read from her psyche.db (the engine inside her process writes it;
// 556d only reads). Words first, numbers small: the same material her state block is made of.
// The few things you can do here (close a loop, add a reminder or a life event) are commands the
// engine drains on its next tick — 556d never writes her state itself.

const EMOTION_ZH: Record<string, string> = {
  joy: '開心', distress: '難過', hope: '期待', fear: '擔心', satisfaction: '滿足', disappointment: '失望',
  relief: '鬆了口氣', gratitude: '感激', anger: '生氣', pride: '得意', shame: '不好意思', liking: '喜歡',
  disliking: '反感', happy_for: '替對方高興', sorry_for: '替對方難過', longing: '想念', hurt: '委屈',
};
const OCTANTS: Record<string, string> = {
  '1,1,1': '興致勃勃', '1,1,-1': '撒嬌黏人', '1,-1,1': '自在', '1,-1,-1': '溫和乖巧',
  '-1,1,1': '不爽', '-1,1,-1': '不安', '-1,-1,1': '冷淡', '-1,-1,-1': '悶',
};
const ACTIVITY_ZH: Record<string, string> = { sleep: '在睡覺', lying: '躺在床上', woken: '被吵醒', work: '在工作', hobby: '在弄自己的事', meal: '在吃飯', rest: '在休息', chat: '在聊天' };
const NEEDS_ZH: Record<string, string> = { affiliation_person: '想找你', affiliation_general: '想有人陪', competence: '想有進展', autonomy: '想自己決定', certainty: '想知道結果', novelty: '想有新鮮事' };
const PHASE_ZH: Record<string, string> = { ok: '', protest: '想找你', despair: '悶著', detachment: '疏離' };
const word = (x: number) => (x < 0.2 ? '' : x < 0.45 ? '有點' : x < 0.7 ? '蠻' : '很');
const energyWord = (e: number, a?: string) => (a === 'sleep' ? '在睡覺' : a === 'woken' ? '很睏' : e >= 0.75 ? '精神很好' : e >= 0.55 ? '精神還不錯' : e >= 0.35 ? '有點累' : '很累');
const intensityNow = (i: PsycheInstance, now: number) => i.intensity0 * Math.pow(0.5, Math.max(0, now - i.born_at) / 3600 / Math.max(1e-6, i.half_life_h));
const ago = (ts: number, now: number) => {
  const m = Math.max(0, Math.round((now - ts) / 60));
  return m < 1 ? '剛剛' : m < 60 ? `${m} 分鐘前` : m < 1440 ? `${Math.round(m / 60)} 小時前` : `${Math.round(m / 1440)} 天前`;
};

function eventText(e: { kind: string; payload: any }): string {
  const p = e.payload ?? {};
  switch (e.kind) {
    case 'turn': return `💬 ${String(p.user ?? '').slice(0, 80)}`;
    case 'appraisal_applied': return `✦ ${(p.events ?? []).join('、') || '（沒有事件）'}${(p.born ?? []).length ? ` → ${p.born.length} 個情緒` : ''}`;
    case 'proactive_fired': return `📣 想開口：${p.kind}${p.what ? `（${p.what}）` : ''}`;
    case 'sent': return `📣 她說了：${String(p.text ?? '').slice(0, 80)}`;
    case 'silent': return '📣 想了想，沒有打擾';
    case 'send_failed': return `📣 沒送出去（${p.why ?? ''}）`;
    case 'reply_timeout': return `⏳ 等不到回覆（第 ${p.unanswered} 則）`;
    case 'sleep': return `🌙 ${p.what === 'fell_asleep' ? '睡著了' : p.what === 'woke_up' ? '醒了' : '被訊息吵醒'}`;
    case 'life': return `🍃 ${p.text ?? ''}`;
    case 'rumination': return `🔁 又想起：${EMOTION_ZH[p.type] ?? p.type}`;
    case 'loop_due': return `⏰ 到了：${p.what ?? ''}`;
    case 'start': return `▶ 開始（補了 ${p.gap_ticks ?? 0} 分鐘）`;
    case 'stop': return '■ 停止';
    default: return e.kind;
  }
}

export function State() {
  const [v, setV] = useState<PsycheView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now() / 1000);
  const [showBlock, setShowBlock] = useState(false);
  const [remind, setRemind] = useState({ what: '', when: '' });
  const [life, setLife] = useState({ text: '', bad: false });
  const [busy, setBusy] = useState(false);

  const load = () => api.psyche().then((r) => { setV(r); setErr(null); setNow(Date.now() / 1000); }).catch((e) => setErr(String(e)));
  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  async function command(op: 'close_loop' | 'add_loop' | 'life_event', payload: Record<string, any>) {
    setBusy(true);
    try { await api.psycheCommand(op, payload); setTimeout(load, 1500); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  if (err) return <div className="p-4 text-sm text-red-300">{err}</div>;
  if (!v) return <div className="p-4 text-sm opacity-60">…</div>;
  if (!v.exists) return <div className="p-4 text-sm opacity-60">{t('state.no_engine')}</div>;

  const snap = v.snapshot;
  const mood = snap?.mood ?? [0, 0, 0];
  const key = mood.map((x) => (x >= 0 ? 1 : -1)).join(',');
  const strength = Math.min(1, Math.sqrt(mood[0] ** 2 + mood[1] ** 2 + mood[2] ** 2) / Math.sqrt(3));
  const moodWord = strength < 0.2 ? '平靜' : `${word(strength)}${OCTANTS[key]}`;
  const active = (v.instances ?? []).filter((i) => i.resolved_at == null).map((i) => ({ ...i, now: intensityNow(i, now) })).filter((i) => i.now >= 0.02).sort((a, b) => b.now - a.now);
  const loops = (v.loops ?? []).filter((l) => l.state !== 'closed' && l.state !== 'expired');
  const needs = snap?.needs ?? {};
  const contact = snap?.contact ?? {};
  const blockText = snap?.last_block?.text ?? '';
  const card = 'rounded-lg bg-white/5 p-3';

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 text-sm">
      <div className="flex items-center gap-3 text-xs opacity-60">
        <span>{v.running ? t('state.running') : t('state.stopped')}</span>
        {v.snapshot_at ? <span>{t('state.snapshot_at')} {ago(v.snapshot_at, now)}</span> : null}
        {typeof v.checks_total === 'number' && v.checks_total > 0 && <span>· {t('state.checks')} {v.checks_total}</span>}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className={card}>
          <div className="text-xs opacity-60">{t('state.doing')}</div>
          <div className="text-lg">{snap?.activity ? ACTIVITY_ZH[snap.activity] ?? snap.activity : '—'}</div>
          <div className="text-xs opacity-50 mt-1">{snap ? energyWord(snap.energy, snap.activity) : ''}{snap?.sleep?.debt > 0.2 ? ' · 睡眠不足' : ''}</div>
        </div>
        <div className={card}>
          <div className="text-xs opacity-60">{t('state.mood')}</div>
          <div className="text-lg">{snap ? moodWord : '—'}</div>
          {snap && <div className="text-xs opacity-50 mt-1">正 {snap.affect.pos.toFixed(2)} · 負 {snap.affect.neg.toFixed(2)} · P {mood[0].toFixed(2)} A {mood[1].toFixed(2)}</div>}
        </div>
        <div className={card}>
          <div className="text-xs opacity-60">{t('state.contact')}</div>
          <div className="text-lg">{PHASE_ZH[contact.phase] || '還好'}</div>
          <div className="text-xs opacity-50 mt-1">
            {contact.last_turn_at ? `上次聊天 ${ago(contact.last_turn_at, now)}` : '還沒聊過'}
            {contact.awaiting_since ? ' · 等你回' : ''}{contact.unanswered ? ` · 未回 ${contact.unanswered}` : ''} · 今天主動 {contact.proactive_today ?? 0}
          </div>
        </div>
      </div>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.needs')}</h3>
        <div className="grid grid-cols-3 gap-x-4 gap-y-1">
          {Object.entries(NEEDS_ZH).map(([k, zh]) => {
            const x = Math.max(0, Math.min(1, Number(needs[k] ?? 0)));
            return (
              <div key={k} className="flex items-center gap-2 text-xs">
                <span className="w-20 opacity-70">{zh}</span>
                <div className="flex-1 h-1 rounded bg-white/10"><div className="h-1 rounded bg-pink-400/70" style={{ width: `${Math.round(x * 100)}%` }} /></div>
              </div>
            );
          })}
        </div>
      </section>

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
          <ul className="space-y-1">
            {loops.map((l) => (
              <li key={l.id} className="flex gap-2 items-baseline">
                <span className="flex-1">{l.what}{l.cue_time ? <span className="text-xs opacity-50"> · {l.cue_time.replace('T', ' ')}</span> : null}<span className="text-xs opacity-40"> · {l.state}</span></span>
                <button className="text-xs opacity-60 hover:opacity-100 disabled:opacity-30" disabled={busy} onClick={() => command('close_loop', { loop: l.id })}>{t('state.close_loop')}</button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2 flex gap-2 items-center text-xs">
          <input className="flex-1 rounded bg-white/5 px-2 py-1 outline-none" placeholder={t('state.remind_placeholder')} value={remind.what} onChange={(e) => setRemind({ ...remind, what: e.target.value })} />
          <input className="rounded bg-white/5 px-2 py-1 outline-none" type="datetime-local" value={remind.when} onChange={(e) => setRemind({ ...remind, when: e.target.value })} />
          <button className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 disabled:opacity-30" disabled={busy || !remind.what.trim() || !remind.when}
            onClick={() => { command('add_loop', { what: remind.what.trim(), cue_time: remind.when.slice(0, 16), importance: 0.8 }); setRemind({ what: '', when: '' }); }}>{t('state.remind_add')}</button>
        </div>
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.life')}</h3>
        <div className="flex gap-2 items-center text-xs">
          <input className="flex-1 rounded bg-white/5 px-2 py-1 outline-none" placeholder={t('state.life_placeholder')} value={life.text} onChange={(e) => setLife({ ...life, text: e.target.value })} />
          <label className="flex items-center gap-1 opacity-80"><input type="checkbox" checked={life.bad} onChange={(e) => setLife({ ...life, bad: e.target.checked })} />{t('state.life_bad')}</label>
          <button className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 disabled:opacity-30" disabled={busy || !life.text.trim()}
            onClick={() => { command('life_event', { text: life.text.trim(), v: life.bad ? -0.4 : 0.3, R: 0.4, share: true }); setLife({ text: '', bad: false }); }}>{t('state.life_add')}</button>
        </div>
        {(v.snapshot as any)?.share_backlog?.length ? <div className="text-xs opacity-60 mt-1">{t('state.share')}: {(v.snapshot as any).share_backlog.map((s: any) => s.what).join('、')}</div> : null}
      </section>

      <section>
        <button className="text-xs opacity-60 hover:opacity-100" onClick={() => setShowBlock(!showBlock)}>{showBlock ? '▾' : '▸'} {t('state.block')}</button>
        {showBlock && <pre className="mt-1 text-xs whitespace-pre-wrap opacity-80 bg-white/5 rounded p-2">{blockText || t('state.none')}</pre>}
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.events')}</h3>
        <ul className="space-y-1">
          {(v.events ?? []).slice(0, 40).map((e) => (
            <li key={e.id} className="flex gap-2"><span className="text-xs opacity-40 shrink-0 w-20">{ago(e.at, now)}</span><span className="opacity-80 truncate">{eventText(e)}</span></li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide opacity-60 mb-2">{t('state.appraisals')}</h3>
        <ul className="space-y-1">
          {(v.appraisals ?? []).slice(0, 10).map((a) => {
            const evs = (a.data?.events ?? []) as { event_kind: string; cause: string }[];
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
