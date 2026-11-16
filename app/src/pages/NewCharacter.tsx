import { useEffect, useRef, useState } from 'react';
import { chars, CharDetail, CharPackage, CharProfile, LifeSample, LifeSpec } from '../api';
import { t } from '../i18n';
import { ConfirmStep, LifeStep } from './NewCharacterSteps';

// 名單 → ＋ 新角色: the soul skill behind 556d (docs/prompt/prompt.md §2.9). One page, four sections for the
// selected package: 描述 (ten boxes in your own words), 產生 (the skill, phase by phase or all at once, its log live),
// 確認 (the proposed numbers and choices with the skill's evidence; you confirm or move them), 結果 (the SOUL, the
// checks, the blind read-back, install). The LLM runs only here, under your eyes; the files are written by code.

const STEMS = ['01-她是誰', '02-背景', '03-發生過的事', '04-說話的方式', '05-怎麼想', '06-跟人相處', '07-喜好', '08-立場', '09-身邊的人', '10-其他'];
const PHASES = ['intake', 'structure', 'thinking', 'voice', 'reactions', 'parts', 'assemble', 'verify'];
const CLOSENESS = ['剛認識', '還不算熟', '朋友', '很熟', '很親近']; // the bands of tools/soul_writer.py CLOSENESS
const METERS = ['rationality', 'experientiality', 'promotion', 'prevention', 'maximizing'];
const BIG5 = ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism'];
const CONSTANTS = ['self_esteem_stability', 'expressiveness', 'humor_coping', 'clinginess_cap', 'tsundere_tendency', 'assertiveness', 'chronotype'];
const CHOICES: Record<string, string[]> = {
  medium_primary: ['inner_dialogic', 'inner_condensed', 'imagery', 'felt', 'sound', 'unsymbolized'],
  medium_secondary: ['', 'inner_dialogic', 'inner_condensed', 'imagery', 'felt', 'sound', 'unsymbolized'],
  first_look: ['thing', 'people', 'scene'],
  contradiction: ['hold_both', 'pick_one'],
  cause: ['person', 'situation'],
};

const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-accent/60 text-sm';
const label = 'block text-xs opacity-70 mb-1';
const btn = 'px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/20 disabled:opacity-40';
const primary = 'px-4 py-2 rounded-xl bg-accent hover:bg-accent/90 text-accent-ink font-medium disabled:opacity-40 text-sm';

// 日子與作息: a compact editor over the engine's own shape (psyche.json `life`, docs/inner-life §14). Hours are decimal
// local hours; busy and meal blocks read "9.5-12.5, 14-18"; small events are one per line with a leading + (good),
// - (bad) or ! (unwell). What is saved into profile.json `life` is the full engine shape, so the skill writes it as is.
const blocksText = (b?: number[][]) => (b || []).map((x) => `${x[0]}-${x[1]}`).join(', ');
const parseBlocks = (s: string): number[][] =>
  s.split(/[,，]/).map((x) => x.trim()).filter(Boolean)
    .map((x) => x.split(/[-–~]/).map((n) => Number(n.trim())))
    .filter((p) => p.length === 2 && p.every((n) => Number.isFinite(n)));
const eventsText = (ev?: LifeSpec['small_events']) => (ev || []).map((e) => `${e.kind === 'unwell' ? '!' : (e.v ?? 0) < 0 ? '-' : '+'} ${e.text}`).join('\n');
const parseEvents = (s: string): NonNullable<LifeSpec['small_events']> => {
  const out: NonNullable<LifeSpec['small_events']> = [];
  for (const raw of s.split('\n')) {
    const l = raw.trim();
    if (!l) continue;
    const m = l.match(/^([+\-!！＋－])\s*(.*)$/);
    const sign = m ? m[1] : '+';
    const text = (m ? m[2] : l).trim();
    if (!text) continue;
    if (sign === '!' || sign === '！') out.push({ text, v: -0.4, R: 0.4, p: 0.05, kind: 'unwell', share: true });
    else if (sign === '-' || sign === '－') out.push({ text, v: -0.3, R: 0.3, p: 0.1, kind: 'life', share: true });
    else out.push({ text, v: 0.3, R: 0.3, p: 0.1, kind: 'life', share: true });
  }
  return out;
};
// the structure phase's draft of her day (build/structure.json `life`: wake, bedtime, busy, busyness_mode, project, small_events) → the engine shape
export function lifeFromStructure(st: any): LifeSpec | null {
  if (!st || typeof st !== 'object') return null;
  const out: LifeSpec = {};
  const sched: NonNullable<LifeSpec['schedule']> = {};
  if (typeof st.wake === 'number') sched.wake = st.wake;
  if (typeof st.bedtime === 'number') sched.bedtime = st.bedtime;
  if (Array.isArray(st.busy)) sched.work = st.busy.filter((p: any) => Array.isArray(p) && p.length === 2).map((p: any) => [Number(p[0]), Number(p[1])]);
  if (Array.isArray(st.own)) sched.hobby = st.own.filter((p: any) => Array.isArray(p) && p.length === 2).map((p: any) => [Number(p[0]), Number(p[1])]);
  if (Object.keys(sched).length) out.schedule = sched;
  if (['work', 'hobby', 'none'].includes(st.busyness_mode)) out.busyness_mode = st.busyness_mode;
  if (st.project && typeof st.project.title === 'string' && st.project.title.trim()) out.projects = [{ title: st.project.title.trim(), stage: (st.project.stage || '進行中').trim(), difficulty: 0.5, progress: 0 }];
  if (Array.isArray(st.small_events)) {
    const ev = st.small_events.filter((e: any) => e && typeof e.text === 'string' && e.text.trim())
      .map((e: any) => ({ text: e.text.trim(), v: Math.max(-1, Math.min(1, Number(e.v) || 0)), R: 0.3, p: 0.1, kind: 'life', share: true }));
    if (ev.length) out.small_events = ev;
  }
  return Object.keys(out).length ? out : null;
}
export function sampleSpec(s: LifeSample): LifeSpec {
  const { id, name, note, ...spec } = s;
  void id; void name; void note;
  return spec;
}

export function LifeEditor({ life, onChange }: { life: LifeSpec; onChange(next: LifeSpec): void }) {
  // the design canvas's 日子 › 自己寫: times on a clock (never decimals), one row per kind of time with × and ＋ 加一段,
  // "which times count as busy" as boxes you can turn on together, small events with a 好事／壞事／不舒服 picker
  const s = life.schedule || {};
  const toClock = (h?: number) => { if (h == null || !Number.isFinite(h)) return ''; const x = ((h % 24) + 24) % 24; return `${String(Math.floor(x)).padStart(2, '0')}:${String(Math.round((x % 1) * 60)).padStart(2, '0')}`; };
  const fromClock = (v: string) => { const [hh, mm] = v.split(':').map(Number); return Number.isFinite(hh) ? hh + (Number.isFinite(mm) ? mm / 60 : 0) : 0; };
  const setS = (patch: Partial<NonNullable<LifeSpec['schedule']>>) => onChange({ ...life, schedule: { ...s, ...patch } });
  const timeBox = 'rounded-lg border border-ink/25 bg-[#110e0c] px-2.5 py-2 text-ink text-[15px]';
  const square = 'w-9 h-9 rounded-lg border border-ink/30 hover:bg-white/10';
  const outline = 'self-start px-3.5 py-1.5 rounded-lg border border-ink/35 text-sm hover:bg-white/10';
  const hours = (a: number, b: number) => { const d = ((b - a) % 24 + 24) % 24 || 24; return `${Math.floor(d)} ${t('newchar.de_hours')}${d % 1 ? ' ' + t('newchar.de_half') : ''}`; };
  type Key = 'work' | 'hobby' | 'meals';
  const rows: { key: Key; name: string; note: string; swatch: string; add: [number, number] }[] = [
    { key: 'work', name: t('newchar.de_work'), note: t('newchar.de_work_note'), swatch: 'bg-accent', add: [14, 18] },
    { key: 'hobby', name: t('newchar.day_own'), note: t('newchar.de_own_note'), swatch: 'bg-ok', add: [20, 22] },
    { key: 'meals', name: t('newchar.life_meals'), note: '', swatch: 'bg-soft', add: [12, 13] },
  ];
  const spans = (k: Key) => (s[k] || []) as number[][];
  const setSpan = (k: Key, i: number, j: 0 | 1, v: string) => {
    const next = spans(k).map((x) => [...x]);
    let h = fromClock(v);
    if (j === 1 && h <= next[i][0]) h += 24; // an end at or before the start runs past midnight (00:00 → 24:00)
    next[i][j] = h; setS({ [k]: next } as any);
  };
  const busy = life.busy_kinds ?? ['work'];
  const busyOpts: { v: 'work' | 'hobby' | 'meal'; label: string }[] = [{ v: 'work', label: t('newchar.de_work') }, { v: 'hobby', label: t('newchar.day_own') }, { v: 'meal', label: t('newchar.life_meals') }];
  const toggleBusy = (v: 'work' | 'hobby' | 'meal') => onChange({ ...life, busy_kinds: busy.includes(v) ? busy.filter((x) => x !== v) : [...busy, v] });
  const pj = (life.projects || [])[0] || { title: '', stage: '', difficulty: 0.5 };
  const setP = (patch: Partial<typeof pj>) => { const next = { ...pj, ...patch }; onChange({ ...life, projects: (next.title || '').trim() ? [{ difficulty: 0.5, progress: 0, ...next }] : [] }); };
  const events = life.small_events || [];
  const toneOf = (e: NonNullable<LifeSpec['small_events']>[number]) => (e.kind === 'unwell' ? 2 : (e.v ?? 0) < 0 ? 1 : 0);
  const setTone = (i: number, tone: number) => onChange({ ...life, small_events: events.map((e, j) => j !== i ? e : tone === 2 ? { ...e, v: -0.4, kind: 'unwell' } : tone === 1 ? { ...e, v: -0.3, kind: 'life' } : { ...e, v: 0.3, kind: 'life' }) });
  const setText = (i: number, text: string) => onChange({ ...life, small_events: events.map((e, j) => (j === i ? { ...e, text } : e)) });

  return (
    <div className="space-y-5">
      <div className="divide-y divide-white/8">
        <div className="flex gap-5 py-4">
          <div className="w-36 shrink-0"><div className="flex items-center gap-2 font-bold"><span className="w-3 h-3 rounded-sm bg-[rgba(120,140,200,0.7)]" />{t('newchar.de_sleep')}</div><div className="text-xs text-muted mt-1">{t('newchar.de_sleep_note')}</div></div>
          <div className="flex items-center gap-2.5">
            <input type="time" aria-label={t('newchar.life_bedtime')} className={timeBox} value={toClock(s.bedtime)} onChange={(e) => setS({ bedtime: fromClock(e.target.value) })} />
            <span className="text-muted">{t('newchar.de_to')}</span>
            <input type="time" aria-label={t('newchar.life_wake')} className={timeBox} value={toClock(s.wake)} onChange={(e) => setS({ wake: fromClock(e.target.value) })} />
            {s.bedtime != null && s.wake != null && <span className="text-xs text-muted">{hours(s.bedtime, s.wake)}</span>}
          </div>
        </div>
        {rows.map((r) => (
          <div key={r.key} className="flex gap-5 py-4">
            <div className="w-36 shrink-0"><div className="flex items-center gap-2 font-bold"><span className={`w-3 h-3 rounded-sm ${r.swatch}`} />{r.name}</div>{r.note && <div className="text-xs text-muted mt-1">{r.note}</div>}</div>
            <div className="flex-1 flex flex-col gap-2.5">
              {spans(r.key).length === 0 && <span className="text-sm text-muted">{t('newchar.day_none')}</span>}
              {spans(r.key).map((x, i) => (
                <div key={i} className="flex items-center gap-2.5">
                  <input type="time" aria-label={t('newchar.de_from')} className={timeBox} value={toClock(x[0])} onChange={(e) => setSpan(r.key, i, 0, e.target.value)} />
                  <span className="text-muted">{t('newchar.de_to')}</span>
                  <input type="time" aria-label={t('newchar.de_until')} className={timeBox} value={toClock(x[1])} onChange={(e) => setSpan(r.key, i, 1, e.target.value)} />
                  <span className="text-xs text-muted w-20">{hours(x[0], x[1])}</span>
                  <button type="button" aria-label={t('newchar.de_remove')} className={square} onClick={() => setS({ [r.key]: spans(r.key).filter((_, j) => j !== i) } as any)}>×</button>
                </div>
              ))}
              <button type="button" className={outline} onClick={() => setS({ [r.key]: [...spans(r.key), r.add] } as any)}>＋ {t('newchar.de_add_span')}</button>
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <div className="font-bold">{t('newchar.de_busy_q')}</div>
        <div role="group" aria-label={t('newchar.de_busy_q')} className="inline-flex flex-wrap gap-2">
          {busyOpts.map((o) => {
            const on = busy.includes(o.v);
            return (
              <button key={o.v} type="button" role="checkbox" aria-checked={on} onClick={() => toggleBusy(o.v)}
                className={`px-4 py-2 rounded-xl text-sm border ${on ? 'bg-accent text-accent-ink border-accent font-bold' : 'border-ink/35 hover:bg-white/10'}`}>{on ? '✓ ' : ''}{o.label}</button>
            );
          })}
        </div>
        <div className="text-[13px] text-muted">{t('newchar.de_busy_note')}</div>
      </div>

      <div className="space-y-2">
        <div className="font-bold">{t('newchar.life_project')}</div>
        <div className="flex gap-3">
          <label className="flex-1 flex flex-col gap-1.5 text-[13px] text-soft">{t('newchar.de_what')}<input className={timeBox} value={pj.title || ''} onChange={(e) => setP({ title: e.target.value })} /></label>
          <label className="w-80 flex flex-col gap-1.5 text-[13px] text-soft">{t('newchar.life_stage')}<input className={timeBox} value={pj.stage || ''} onChange={(e) => setP({ stage: e.target.value })} /></label>
        </div>
      </div>

      <div className="space-y-2.5">
        <div className="flex items-baseline gap-3"><span className="font-bold">{t('newchar.life_events')}</span><span className="text-[13px] text-muted">{t('newchar.de_events_note')}</span></div>
        {events.map((e, i) => (
          <div key={i} className="flex items-center gap-2.5">
            <div role="radiogroup" aria-label={t('newchar.de_tone')} className="inline-flex border border-ink/30 rounded-lg overflow-hidden text-[13px]">
              {[t('newchar.day_good'), t('newchar.day_bad'), t('newchar.day_unwell')].map((label, k) => (
                <button key={k} type="button" role="radio" aria-checked={toneOf(e) === k} onClick={() => setTone(i, k)}
                  className={`px-2.5 py-1.5 ${k ? 'border-l border-ink/20' : ''} ${toneOf(e) === k ? 'bg-accent text-accent-ink font-bold' : 'hover:bg-white/10'}`}>{label}</button>
              ))}
            </div>
            <input aria-label={t('newchar.life_events')} className={`${timeBox} flex-1`} value={e.text} onChange={(ev) => setText(i, ev.target.value)} />
            <button type="button" aria-label={t('newchar.de_remove')} className={square} onClick={() => onChange({ ...life, small_events: events.filter((_, j) => j !== i) })}>×</button>
          </div>
        ))}
        <button type="button" className={outline} onClick={() => onChange({ ...life, small_events: [...events, { text: '', v: 0.3, R: 0.3, p: 0.1, kind: 'life', share: true }] })}>＋ {t('newchar.de_add_event')}</button>
      </div>
    </div>
  );
}

// The new-character page (0.13.0): a package picker, then five steps across the top — 描述 · 關係 · 產生 · 確認 · 結果 —
// one step on the left, the package card on the right. 描述 shows ONE box at a time (its title, what to write, the
// input) with the ten titles listed on the right, each marked filled or empty; the hint is text above the box, never
// a placeholder that vanishes as you type. A save bar at the bottom names what is typed but not saved.
type Step = 'describe' | 'relation' | 'life' | 'generate' | 'confirm' | 'result';
const STEPS: { key: Step; label: string }[] = [
  { key: 'describe', label: 'newchar.describe' }, { key: 'relation', label: 'newchar.relation' }, { key: 'life', label: 'newchar.life' },
  { key: 'generate', label: 'newchar.generate' }, { key: 'confirm', label: 'newchar.confirm' }, { key: 'result', label: 'newchar.result' },
];
const clock = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export function NewCharacter({ onBack, initialId }: { onBack(): void; initialId?: string | null }) {
  const [list, setList] = useState<CharPackage[]>([]);
  const [template, setTemplate] = useState<Record<string, string>>({});
  const [model, setModel] = useState('');
  const [lifeSamples, setLifeSamples] = useState<LifeSample[]>([]); // templates/life/*.json, served with the package list
  const [lifeKey, setLifeKey] = useState(0); // remounts the life editor when a sample / the draft / clear replaces its text
  const [id, setId] = useState<string | null>(initialId ?? null);
  const [step, setStep] = useState<Step>('describe');
  const [box, setBox] = useState(0); // which of the ten boxes the editor shows
  const [detail, setDetail] = useState<CharDetail | null>(null);
  const [describe, setDescribe] = useState<Record<string, string>>({});
  const [profile, setProfile] = useState<CharProfile | null>(null);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState('');
  const [rowMenu, setRowMenu] = useState<string | null>(null); // the 產生 row whose 只跑這步 is open
  const [form, setForm] = useState({ id: '', display_name: '', pronoun: '她' });
  const [thenRest, setThenRest] = useState(false); // 「全部」: after a clean intake, continue from structure
  const logRef = useRef<HTMLPreElement>(null);
  const describeDirty = useRef(false); // typed but not saved: a reload (a job ending) must not wipe it
  const relDirty = useRef(false); // the 關係 inputs (bar, shared past) typed but not saved — same rule

  const refreshList = () => chars.list().then((r) => { setList(r.characters); setTemplate(r.template); setModel(r.model || ''); setLifeSamples(r.life_samples || []); }).catch((e) => setNotice({ kind: 'err', text: String(e) }));
  const load = (cid: string) => chars.detail(cid).then((d) => {
    setDetail(d);
    if (!describeDirty.current) setDescribe(d.describe);
    setProfile((p) => (relDirty.current && p && d.profile ? { ...d.profile, closeness: p.closeness ?? null, shared_past: p.shared_past ?? '' } : d.profile));
  }).catch((e) => setNotice({ kind: 'err', text: String(e) }));
  // the 關係 inputs are inputs like the describe boxes: saved before a run, and with 儲存
  const saveRelation = async (cid: string) => {
    if (!relDirty.current || !profile) return;
    await chars.saveProfile(cid, { closeness: profile.closeness ?? null, shared_past: profile.shared_past ?? '' });
    relDirty.current = false;
  };

  // ---- autosave (0.13.x): no save buttons; whatever is typed is written a second after you stop, and always before a
  // step change or a run. Comparison is on a key-sorted copy (the server may return the same profile in another order).
  const stable = (v: any): string => JSON.stringify(v, (_k, x) => (x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x));
  const PROFILE_KEYS = ['pronoun', 'closeness', 'scratch', 'simple', 'big5', 'constants', 'thinking', 'choices', 'life', 'shared_past'] as const;
  const pick = (p: CharProfile | null | undefined) => Object.fromEntries(PROFILE_KEYS.map((k) => [k, (p as any)?.[k] ?? null]));
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'err'>('idle');
  const saving = useRef<Promise<void> | null>(null);
  const autosave = async (): Promise<void> => {
    if (saving.current) { await saving.current; }
    if (!id || !detail || !profile) return;
    const descDirty = STEMS.some((st) => (describe[st] ?? '') !== (detail.describe[st] ?? ''));
    const profDirty = stable(pick(profile)) !== stable(pick(detail.profile));
    if (!descDirty && !profDirty) return;
    const job = (async () => {
      setSaveState('saving');
      try {
        const snapDescribe = { ...describe };
        if (descDirty) await chars.saveDescribe(id, snapDescribe);
        let saved = detail.profile;
        if (profDirty) saved = (await chars.saveProfile(id, pick(profile) as any)).profile;
        const fresh = await chars.detail(id);
        describeDirty.current = false; relDirty.current = false;
        setDetail((d) => (d ? { ...d, character: fresh.character, build: fresh.build, describe: descDirty ? snapDescribe : d.describe, profile: saved } : d));
        setSavedAt(clock()); setSaveState('saved');
      } catch (e) { setSaveState('err'); setNotice({ kind: 'err', text: String(e) }); }
    })();
    saving.current = job;
    try { await job; } finally { saving.current = null; }
  };
  useEffect(() => { const h = setTimeout(() => { autosave(); }, 1000); return () => clearTimeout(h); }, [describe, profile]);
  const go = async (next: Step) => { await autosave(); setStep(next); };

  useEffect(() => { refreshList(); }, []);
  useEffect(() => { if (id) { setDetail(null); describeDirty.current = false; relDirty.current = false; setStep('describe'); setBox(0); load(id); } }, [id]);

  // follow a running job: poll its log, reload the package when it ends
  const running = !!detail?.job?.running;
  useEffect(() => {
    if (!id || !running) return;
    const tick = setInterval(async () => {
      try {
        const { job } = await chars.job(id);
        setDetail((d) => (d ? { ...d, job } : d));
        if (!job.running) {
          await load(id); refreshList();
          if (thenRest && job.kind === 'run' && job.phase === 'intake') {
            setThenRest(false);
            if (job.exit_code === 0) await run('structure', true, false, 'structure');
            else setNotice({ kind: 'err', text: t('newchar.thin') });
          }
        }
      } catch { /* backend hiccup: keep polling */ }
    }, 2000);
    return () => clearInterval(tick);
  }, [id, running]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [detail?.job?.log]);

  async function create() {
    setBusy(true); setNotice(null);
    try {
      const r = await chars.create({ id: form.id.trim(), display_name: form.display_name.trim(), pronoun: form.pronoun });
      await refreshList();
      setId(r.character.id);
      setForm({ id: '', display_name: '', pronoun: '她' });
    } catch (e) { setNotice({ kind: 'err', text: String(e) }); } finally { setBusy(false); }
  }
  async function saveInputs() {
    if (!id) return;
    setBusy(true); setNotice(null);
    try {
      if (describeDirty.current) { await chars.saveDescribe(id, describe); describeDirty.current = false; }
      await saveRelation(id);
      setSavedAt(clock());
      await load(id); refreshList();
    } catch (e) { setNotice({ kind: 'err', text: String(e) }); } finally { setBusy(false); }
  }
  function discardInputs() {
    if (!detail) return;
    describeDirty.current = false; relDirty.current = false;
    setDescribe(detail.describe); setProfile(detail.profile);
  }
  async function run(phase: string, yes: boolean, force = false, from?: string) {
    if (!id) return;
    setNotice(null);
    try {
      await autosave(); // what is typed is what runs
      const r = await chars.run(id, { phase, from, yes, force }); setDetail((d) => (d ? { ...d, job: r.job } : d));
    } catch (e) { setNotice({ kind: 'err', text: String(e) }); }
  }
  function runAll() { setThenRest(true); run('intake', false); }
  async function runSimple() {
    if (!id || !profile) return;
    setBusy(true); setNotice(null);
    try {
      await chars.saveProfile(id, { pronoun: profile.pronoun, closeness: profile.closeness ?? null, scratch: !!profile.scratch, simple: profile.simple ?? null, big5: profile.big5, constants: profile.constants, thinking: profile.thinking, choices: profile.choices, life: profile.life ?? null, shared_past: profile.shared_past ?? '' });
      relDirty.current = false;
      const force = !!detail?.soul && !detail.character.phases.includes('assemble') ? confirm(t('newchar.simple_force')) : false;
      const r = await chars.simple(id, force);
      setDetail((d) => (d ? { ...d, job: r.job } : d));
    } catch (e) { setNotice({ kind: 'err', text: String(e) }); } finally { setBusy(false); }
  }
  const simpleBox = (k: 'who' | 'talk' | 'refuses', v: string) => profile && setProfile({ ...profile, simple: { ...(profile.simple || {}), [k]: v } });
  function continueThin() { run('structure', true, false, 'structure'); }
  async function saveProfile() {
    if (!id || !profile) return;
    setBusy(true); setNotice(null);
    try {
      const r = await chars.saveProfile(id, { pronoun: profile.pronoun, closeness: profile.closeness ?? null, scratch: !!profile.scratch, simple: profile.simple ?? null, big5: profile.big5, constants: profile.constants, thinking: profile.thinking, choices: profile.choices, life: profile.life ?? null, shared_past: profile.shared_past ?? '' });
      relDirty.current = false;
      setProfile(r.profile); setSavedAt(clock()); setNotice({ kind: 'ok', text: t('newchar.saved') });
    } catch (e) { setNotice({ kind: 'err', text: String(e) }); } finally { setBusy(false); }
  }
  async function install() {
    if (!id || !detail) return;
    setNotice(null);
    const stale = detail.character.stale?.length > 0;
    if (stale && !window.confirm(t('newchar.stale_install'))) return;
    try { const r = await chars.install(id, stale); setDetail((d) => (d ? { ...d, job: r.job } : d)); }
    catch (e) { setNotice({ kind: 'err', text: String(e) }); }
  }
  function acceptProposals() {
    if (!profile?.proposed) return;
    const p = profile.proposed;
    const fill = (cur: Record<string, any> | undefined, prop: Record<string, any> | undefined) => {
      const out = { ...(cur || {}) };
      for (const [k, v] of Object.entries(prop || {})) if (out[k] == null && v != null) out[k] = v;
      return out;
    };
    setProfile({ ...profile, big5: fill(profile.big5, p.big5), constants: fill(profile.constants, p.constants), thinking: fill(profile.thinking, p.thinking), choices: fill(profile.choices, p.choices) });
  }

  const num = (group: 'big5' | 'constants' | 'thinking', k: string, v: number) => profile && setProfile({ ...profile, [group]: { ...(profile[group] || {}), [k]: v } });
  const choice = (k: string, v: string) => profile && setProfile({ ...profile, choices: { ...(profile.choices || {}), [k]: v || null } });
  const evidence = (k: string) => profile?.proposed?.evidence?.[k];
  const proposed = (group: 'big5' | 'constants' | 'thinking', k: string) => profile?.proposed?.[group]?.[k];
  const intake = detail?.build?.intake;
  const jobDone = detail?.job && !detail.job.running && detail.job.started_at;
  const cur = list.find((c) => c.id === id);

  // what is typed but not saved, by name — the save bar reads this
  const dirtyBoxes = detail ? STEMS.filter((s) => (describe[s] ?? '') !== (detail.describe[s] ?? '')) : [];
  const dirtyRel = !!(detail && profile && detail.profile && ((profile.closeness ?? null) !== (detail.profile.closeness ?? null) || (profile.shared_past ?? '') !== (detail.profile.shared_past ?? '')));
  const dirtyNames = [...dirtyBoxes.map((s) => s.slice(3)), ...(dirtyRel ? [t('newchar.relation')] : [])];
  const filled = STEMS.filter((s) => (describe[s] ?? '').trim().length > 0).length;
  const stale = detail?.character.stale ?? [];
  const stem = STEMS[box];
  // a phase is done when its output exists and is not older than the phase before it; stale when the description
  // changed since, or an earlier phase ran after it; failed when the last job died in it
  const lastFailed = (() => {
    const j = detail?.job;
    if (!j || j.running || !j.exit_code) return '';
    const m = [...(j.log || '').matchAll(/== (\w+) ==/g)];
    return m.length ? m[m.length - 1][1] : '';
  })();
  // each changed input names the first phase that reads it (556d: describe/* → intake, profile.json:<phase> → that phase)
  const staleFrom = (k: string) => k.startsWith('describe/') ? 'intake' : k.startsWith('profile.json:') ? k.slice('profile.json:'.length) : 'assemble';
  const firstStale = stale.length ? Math.min(...stale.map((k) => PHASES.indexOf(staleFrom(k))).filter((n) => n >= 0)) : -1;
  const phaseState = (ph: string): 'done' | 'stale' | 'failed' | 'running' | 'todo' => {
    if (running && detail?.job?.log && [...detail.job.log.matchAll(/== (\w+) ==/g)].pop()?.[1] === ph) return 'running';
    if (ph === lastFailed) return 'failed';
    const times = detail?.character.phase_times || {};
    if (!times[ph]) return 'todo';
    const i = PHASES.indexOf(ph);
    for (let k = 0; k < i; k++) { const tk = times[PHASES[k]]; if (tk && tk > times[ph] + 2) return 'stale'; }
    return firstStale >= 0 && i >= firstStale ? 'stale' : 'done';
  };
  const nextPhase = PHASES.find((ph) => phaseState(ph) !== 'done') ?? null;
  const generated = !!detail?.character.phase_times && Object.keys(detail.character.phase_times).length > 0;
  const needRerun = generated && firstStale >= 0;
  const pill = (tone: 'ok' | 'warn' | 'plain', text: string) => <span className={`text-[11px] px-2 py-0.5 rounded-full ${tone === 'ok' ? 'bg-ok/15 text-ok' : tone === 'warn' ? 'bg-warn/15 text-warn' : 'bg-white/8 text-soft'}`}>{text}</span>;

  // ---- no package chosen: the list and the create form
  if (!id || !detail) {
    return (
      <div className="h-full overflow-y-auto p-5 max-w-3xl space-y-5">
        <p className="text-xs opacity-60">{t('newchar.note')}</p>
        {notice && <p className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : 'text-green-300'}`}>{notice.text}</p>}
        {id && !detail && <p className="text-sm opacity-60">{t('status.connecting')}</p>}
        <section className="space-y-2">
          {list.map((c) => (
            <button key={c.id} className="w-full text-left rounded-xl px-4 py-3 bg-white/5 hover:bg-white/10 flex items-center gap-3" onClick={() => setId(c.id)}>
              <span aria-hidden="true" className="w-9 h-9 rounded-full bg-accent/20 text-link inline-flex items-center justify-center font-bold">{[...(c.display_name || c.id)][0]}</span>
              <span className="font-medium">{c.display_name || c.id}</span>
              <span className="text-xs opacity-50">{c.id}</span>
              <span className="ml-auto flex gap-1.5">
                {pill('plain', `${c.describe_filled}/${c.describe_total}`)}
                {c.has_soul && pill('ok', c.lock ? 'SOUL' : t('newchar.handwritten'))}
                {c.installed && pill('ok', t('newchar.installed_tag'))}
                {c.stale?.length > 0 && pill('warn', t('newchar.stale_tag'))}
                {c.running && pill('warn', t('newchar.running_tag'))}
              </span>
            </button>
          ))}
        </section>
        <details className="rounded-xl bg-white/5 p-3" open={list.length === 0}>
          <summary className="cursor-pointer text-sm">{t('newchar.create')}</summary>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div><label className={label}>{t('newchar.id')}</label><input className={field} value={form.id} placeholder="lin" onChange={(e) => setForm({ ...form, id: e.target.value.toLowerCase() })} /></div>
            <div><label className={label}>{t('newchar.display')}</label><input className={field} value={form.display_name} placeholder={t("newchar.display")} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></div>
            <div><label className={label}>{t('newchar.pronoun')}</label>
              <select className={field} value={form.pronoun} onChange={(e) => setForm({ ...form, pronoun: e.target.value })}><option value="她">她</option><option value="他">他</option></select></div>
          </div>
          <button className={`${primary} mt-3`} disabled={busy || !form.id.trim() || !form.display_name.trim()} onClick={create}>{t('newchar.create_go')}</button>
        </details>
      </div>
    );
  }

  // ---- a package: five steps, one at a time, the package card beside it
  return (
    <div className="h-full flex flex-col">
      <div className="flex flex-wrap items-center gap-3 px-5 pt-3 pb-2">
        <button className="text-sm opacity-70 hover:opacity-100" onClick={() => setId(null)}>{t('newchar.back_list')}</button>
        <span className="font-semibold text-lg">{cur?.display_name || id}</span>
        <span className="text-xs opacity-50 font-mono">{id}</span>
        <span className="ml-auto text-xs text-muted">
          {saveState === 'saving' ? t('newchar.as_saving') : saveState === 'err' ? t('newchar.as_err') : savedAt ? t('newchar.as_saved').replace('{t}', savedAt) : ''}
          {detail.character.installed ? '　·　' + t('newchar.installed_tag') : ''}{running ? '　·　' + t('newchar.running_tag') : ''}
        </span>
      </div>
      <nav aria-label={t('newchar.title')} className="flex gap-1.5 px-5 pb-3">
        {STEPS.map((s, i) => {
          const mark = s.key === 'describe' ? (filled > 0 ? '✓' : '') : s.key === 'generate' ? (needRerun ? '•' : generated && !nextPhase ? '✓' : '') : s.key === 'result' ? (detail.character.installed && !needRerun ? '✓' : '') : '';
          const optional = s.key === 'relation' || s.key === 'life' || s.key === 'confirm';
          return (
            <button key={s.key} className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm ${step === s.key ? 'bg-accent text-accent-ink font-semibold' : 'bg-white/5 hover:bg-white/10'}`} onClick={() => go(s.key)}>
              <span className={`w-5 h-5 rounded-full inline-flex items-center justify-center text-[11px] ${step === s.key ? 'bg-black/15' : 'bg-white/10'}`}>{i + 1}</span>{t(s.label)}
              {mark === '✓' && <span className={step === s.key ? '' : 'text-ok'}>✓</span>}
              {mark === '•' && <span aria-label={t('newchar.gen_state.stale')} className="w-2 h-2 rounded-full bg-warn" />}
              {optional && <span className={`text-[11px] ${step === s.key ? 'opacity-70' : 'text-muted'}`}>{t('newchar.optional')}</span>}
            </button>
          );
        })}
      </nav>
      {notice && <p className={`px-5 pb-2 text-sm ${notice.kind === 'err' ? 'text-red-300' : 'text-green-300'}`}>{notice.text}</p>}

      <div className="flex-1 overflow-y-auto px-5 pb-5">
        <div className="flex gap-5 items-start">
          <main className="flex-1 min-w-0 space-y-5">
            {needRerun && step !== 'generate' && step !== 'result' && (
              <div className="flex items-center gap-3 rounded-xl border border-warn/40 px-4 py-2.5">
                <span className="inline-flex items-center gap-2 text-sm text-warn"><span aria-hidden="true" className="w-2 h-2 rounded-full bg-warn" />{t('newchar.rerun_hint').replace('{n}', String(firstStale + 1))}</span>
                <button className={`${btn} ml-auto`} onClick={() => go('generate')}>{t('newchar.go_generate')}</button>
              </div>
            )}

            {step === 'describe' && (
              <section className="rounded-2xl bg-panel border border-white/8 p-5 space-y-3">
                <div className="flex items-baseline gap-3 text-xs opacity-60"><span>{t('newchar.box_n').replace('{n}', String(box + 1))}</span><span className="ml-auto">{(describe[stem] ?? '').trim() ? `${[...(describe[stem] ?? '')].length} ${t('newchar.chars')}` : t('newchar.empty')}</span></div>
                <h2 className="text-xl font-bold">{stem.slice(3)}</h2>
                {template[stem] && <p className="text-sm leading-relaxed text-soft whitespace-pre-wrap">{template[stem]}</p>}
                <label className={label} htmlFor="box">{t('newchar.your_words')}</label>
                <textarea id="box" className={`${field} min-h-[180px] text-[15px] leading-relaxed`} rows={8} value={describe[stem] ?? ''} onChange={(e) => { describeDirty.current = true; setDescribe({ ...describe, [stem]: e.target.value }); }} />
                <div className="flex items-center gap-2">
                  <button className={btn} disabled={box === 0} onClick={() => setBox(box - 1)}>{t('newchar.prev_box')}</button>
                  {box < STEMS.length - 1
                    ? <button className={btn} onClick={() => setBox(box + 1)}>{t('newchar.next_box')}</button>
                    : <button className={btn} onClick={() => go('relation')}>{t('newchar.next_step')}</button>}
                  <span className="ml-auto text-xs opacity-60">{t('newchar.describe_note')}</span>
                </div>
              </section>
            )}

            {step === 'relation' && profile && (
              <section className="space-y-3">
                <p className="text-xs opacity-60">{t('newchar.relation_note')}</p>
                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-2xl bg-panel border border-white/8 p-4 space-y-3">
                    <label className={label}>{t('newchar.relation_bar')}</label>
                    <input type="range" min={0} max={4} step={1} className="w-full" value={Math.max(0, CLOSENESS.indexOf(profile.closeness || ''))} onChange={(e) => { relDirty.current = true; const i = Number(e.target.value); setProfile({ ...profile, closeness: CLOSENESS[i] }); }} />
                    <div className="flex justify-between text-[10px] opacity-50">{CLOSENESS.map((c) => <span key={c} className={c === (profile.closeness || CLOSENESS[0]) ? 'text-link font-bold opacity-100' : ''}>{c}</span>)}</div>
                    <p className="text-xs opacity-60">{t('newchar.relation_bar_hint')}</p>
                  </div>
                  <div className="rounded-2xl bg-panel border border-white/8 p-4 space-y-2">
                    <label className={label}>{t('newchar.relation_past')}</label>
                    <p className="text-xs opacity-60">{t('newchar.relation_past_hint')}</p>
                    <textarea className={`${field} min-h-[120px]`} rows={5} value={profile.shared_past ?? ''} onChange={(e) => { relDirty.current = true; setProfile({ ...profile, shared_past: e.target.value }); }} />
                  </div>
                </div>
                <button className={btn} onClick={() => go('life')}>{t('newchar.next_step')}</button>
              </section>
            )}

            {step === 'life' && profile && (
              <LifeStep profile={profile} setProfile={setProfile} detail={detail} samples={lifeSamples} onNext={() => go('generate')} />
            )}

            {step === 'generate' && (
              <section className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <button className={primary} disabled={running || !model} onClick={() => (nextPhase ? run('all', true, false, nextPhase) : runAll())}>
                    {nextPhase && nextPhase !== 'intake' ? t('newchar.gen_continue').replace('{n}', String(PHASES.indexOf(nextPhase) + 1)) : t('newchar.gen_all')}
                  </button>
                  {nextPhase && nextPhase !== 'intake' && <button className={btn} disabled={running || !model} onClick={runAll}>{t('newchar.gen_restart')}</button>}
                  {lastFailed === 'intake' && detail.job?.exit_code === 2 && <button className={btn} disabled={running || !model} onClick={continueThin} title={t('newchar.continue_note')}>{t('newchar.continue')}</button>}
                  <span className="text-xs text-muted">{t('newchar.model')}：{model || t('newchar.model_unset')}</span>
                </div>
                <p className="text-xs text-muted">{t('newchar.gen_note')}</p>
                <ol className="rounded-2xl border border-white/8 divide-y divide-white/8">
                  {PHASES.map((ph, i) => {
                    const st = phaseState(ph);
                    return (
                      <li key={ph} className="flex items-center gap-3 px-4 py-2.5">
                        <span aria-hidden="true" className={`w-2.5 h-2.5 rounded-full shrink-0 ${st === 'done' ? 'bg-ok' : st === 'stale' ? 'bg-warn' : st === 'failed' ? 'bg-red-400' : st === 'running' ? 'bg-accent animate-pulse' : 'bg-white/20'}`} />
                        <span className="w-6 text-sm text-muted tabular-nums">{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium">{t('newchar.phase.' + ph).replace(/^\d+\s*/, '')}</div>
                          <div className="text-xs text-muted">{t('newchar.gen_what.' + ph)}</div>
                        </div>
                        <span className={`text-xs w-24 text-right ${st === 'done' ? 'text-ok' : st === 'stale' ? 'text-warn' : st === 'failed' ? 'text-red-300' : 'text-muted'}`}>{t('newchar.gen_state.' + st)}{st === 'done' && detail.character.phase_times?.[ph] ? ' ' + new Date(detail.character.phase_times[ph] * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
                        {rowMenu === ph
                          ? <button className="px-3 py-1.5 rounded-lg text-sm border border-white/20 hover:bg-white/10 disabled:opacity-30" disabled={running || (!model && ph !== 'assemble')} onClick={() => { setRowMenu(null); run(ph, true); }}>{t('newchar.gen_run_one')}</button>
                          : <button aria-label={t('newchar.gen_more')} title={t('newchar.gen_more')} className="w-8 h-8 rounded-lg border border-white/15 hover:bg-white/10 text-muted" onClick={() => setRowMenu(ph)}>⋯</button>}
                      </li>
                    );
                  })}
                </ol>
                {detail.check && !detail.check.includes('通過') && (
                  <div className="flex items-center gap-3 text-xs text-muted">
                    <span>{t('newchar.force_note')}</span>
                    <button className="px-3 py-1.5 rounded-lg text-sm border border-white/20 hover:bg-white/10 disabled:opacity-30" disabled={running} onClick={() => run('assemble', true, true)}>{t('newchar.force')}</button>
                  </div>
                )}
                {(running || jobDone) && (
                  <div className="rounded-xl bg-black/30 p-3 text-xs space-y-1">
                    <div className="opacity-70">
                      {running ? `${t('newchar.running')} · ${detail.job.kind} ${detail.job.phase || ''} ${detail.job.model || ''}` : `${t('newchar.finished')} · ${detail.job.kind} · exit ${detail.job.exit_code}${detail.job.error ? ' · ' + detail.job.error : ''}`}
                    </div>
                    <pre ref={logRef} className="max-h-56 overflow-y-auto whitespace-pre-wrap leading-relaxed">{detail.job.log || '…'}</pre>
                  </div>
                )}
                <details className="rounded-xl bg-white/5 p-3">
                  <summary className="cursor-pointer text-sm">{t('newchar.simple')}</summary>
                  <p className="text-xs opacity-60 mt-2">{t('newchar.simple_note')}</p>
                  {profile && (
                    <div className="grid gap-2 mt-2">
                      <div><label className={label}>{t('newchar.simple_who')}</label><textarea className={`${field} min-h-[60px]`} rows={3} value={profile.simple?.who ?? ''} onChange={(e) => simpleBox('who', e.target.value)} /></div>
                      <div><label className={label}>{t('newchar.simple_talk')}</label><textarea className={`${field} min-h-[60px]`} rows={3} value={profile.simple?.talk ?? ''} onChange={(e) => simpleBox('talk', e.target.value)} /></div>
                      <div><label className={label}>{t('newchar.simple_refuses')}</label><textarea className={`${field} min-h-[60px]`} rows={3} value={profile.simple?.refuses ?? ''} onChange={(e) => simpleBox('refuses', e.target.value)} /></div>
                      <div><button className={primary} disabled={busy || running} onClick={runSimple}>{t('newchar.simple_go')}</button></div>
                    </div>
                  )}
                </details>
                {intake?.missing?.length > 0 && (
                  <div className="rounded-xl bg-amber-500/10 p-3 text-sm space-y-2">
                    <div className="font-medium">{t('newchar.intake_title')}</div>
                    {intake.missing.map((m: any, i: number) => (
                      <div key={i}>
                        <div className="opacity-80">{m.part}：{m.why}</div>
                        <ul className="list-disc ml-5 opacity-70">{(m.questions || []).map((q: string, j: number) => <li key={j}>{q}</li>)}</ul>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {step === 'confirm' && profile && (
              <ConfirmStep profile={profile} setProfile={setProfile} meters={METERS} choices={CHOICES} big5={BIG5} constants={CONSTANTS} onNext={() => go('result')} />
            )}

            {step === 'result' && (
              <section className="space-y-3">
                {needRerun && (
                  <div className="flex items-center gap-3 rounded-xl border border-warn/40 px-4 py-2.5">
                    <span className="inline-flex items-center gap-2 text-sm text-warn"><span aria-hidden="true" className="w-2 h-2 rounded-full bg-warn" />{t('newchar.result_stale').replace('{n}', String(firstStale + 1))}</span>
                    <button className={`${primary} ml-auto`} onClick={() => go('generate')}>{t('newchar.go_generate')}</button>
                  </div>
                )}
                {detail.check && <pre className="rounded-lg bg-white/5 p-3 text-xs whitespace-pre-wrap">{detail.check}</pre>}
                {detail.verify && <pre className="rounded-lg bg-white/5 p-3 text-xs whitespace-pre-wrap max-h-64 overflow-y-auto">{detail.verify}</pre>}
                {detail.soul ? (
                  <>
                    <div className="text-xs opacity-60">{t('newchar.soul_stats').replace('{chars}', String(detail.soul.length)).replace('{seeds}', String(detail.seeds)).replace('{people}', detail.people.join('、') || '—')}</div>
                    <pre className="rounded-lg bg-white/5 p-3 text-sm whitespace-pre-wrap max-h-[28rem] overflow-y-auto leading-relaxed">{detail.soul}</pre>
                    <div className="flex items-center gap-3">
                      <button className={needRerun ? btn : primary} disabled={running} onClick={install}>{detail.character.installed ? t('newchar.reinstall') : t('newchar.install')}</button>
                      <span className="text-xs opacity-60">{detail.character.installed ? t('newchar.installed_note') : t('newchar.install_note')}</span>
                    </div>
                  </>
                ) : <p className="text-sm opacity-60">{t('newchar.no_soul')}</p>}
              </section>
            )}
          </main>

          {/* the right column: the ten titles (on 描述) and the package card */}
          <aside className="w-[300px] shrink-0 sticky top-0 space-y-3">
            {step === 'describe' && (
              <div className="rounded-2xl bg-panel border border-white/8 p-2.5">
                <div className="flex items-baseline justify-between px-2 pb-2"><span className="text-sm font-semibold">{t('newchar.ten_boxes')}</span><span className="text-xs opacity-60">{t('newchar.filled').replace('{n}', String(filled))}</span></div>
                {STEMS.map((s, i) => {
                  const has = (describe[s] ?? '').trim().length > 0;
                  return (
                    <button key={s} className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm text-left ${i === box ? 'bg-accent/20' : 'hover:bg-white/5'}`} onClick={() => setBox(i)}>
                      <span className={`w-5 h-5 rounded-full inline-flex items-center justify-center text-[11px] ${has ? 'bg-ok/15 text-ok' : 'bg-white/8 text-muted'}`}>{i + 1}</span>
                      <span className="flex-1">{s.slice(3)}</span>
                      <span className={`text-xs ${has ? 'text-muted' : 'text-warn'}`}>{has ? `${[...(describe[s] ?? '')].length}` : t('newchar.empty')}</span>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="rounded-2xl bg-panel border border-white/8 p-4 space-y-2 text-sm">
              <div className="font-semibold">{t('newchar.package')}</div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                <dt className="opacity-60">{t('newchar.describe')}</dt><dd>{filled} / {STEMS.length}</dd>
                <dt className="opacity-60">SOUL</dt><dd>{detail.soul ? `${detail.soul.length} ${t('newchar.chars')}` : '—'}</dd>
                <dt className="opacity-60">{t('newchar.seeds_label')}</dt><dd>{detail.seeds}</dd>
                <dt className="opacity-60">{t('newchar.people_label')}</dt><dd>{detail.people.join('、') || '—'}</dd>
                <dt className="opacity-60">{t('newchar.install')}</dt><dd>{detail.character.installed ? t('newchar.installed_tag') : '—'}</dd>
              </dl>
              <div className="flex flex-wrap gap-1.5">
                {PHASES.map((ph) => {
                  const st = phaseState(ph);
                  return <span key={ph} className="flex items-center gap-1.5 text-[11px] text-muted w-[45%]"><span aria-hidden="true" className={`w-1.5 h-1.5 rounded-full ${st === 'done' ? 'bg-ok' : st === 'stale' ? 'bg-warn' : st === 'failed' ? 'bg-red-400' : 'bg-white/20'}`} />{t('newchar.phase.' + ph)}</span>;
                })}
              </div>
              {stale.length > 0 && <p className="text-xs opacity-60">{t('newchar.stale_hint')}</p>}
            </div>
          </aside>
        </div>
      </div>

    </div>
  );
}
