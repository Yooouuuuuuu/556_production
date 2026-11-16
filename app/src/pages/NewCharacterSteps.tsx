import { useState } from 'react';
import { CharDetail, CharProfile, LifeSample, LifeSpec } from '../api';
import { t } from '../i18n';
import { LifeEditor, lifeFromStructure, sampleSpec } from './NewCharacter';

// Steps 3 (日子) and 5 (確認) of the new-character page, redrawn on the design canvas's rule (0.13.x): what can be
// pressed has a border or a fill and changes on hover — a solid button for the one main action, outlined buttons whose
// label is a verb, a row of boxes for one-of-several (never a dropdown), sliders with words at both ends; what is only
// read has neither — a status is a dot and a word, an explanation is small pale text, a card's background only groups.

const primary = 'px-5 py-2.5 rounded-xl bg-accent text-accent-ink font-bold hover:bg-accent/90 disabled:opacity-40';
const outline = 'px-4 py-2 rounded-xl border border-ink/35 text-ink hover:bg-white/10 disabled:opacity-30';
const card = 'rounded-2xl bg-panel p-5';
const input = 'rounded-lg border border-ink/25 bg-[#110e0c] px-3 py-2 text-ink';

function Dot({ tone, children }: { tone: 'ok' | 'warn' | 'muted'; children: React.ReactNode }) {
  const c = tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : 'text-muted';
  const b = tone === 'ok' ? 'bg-ok' : tone === 'warn' ? 'bg-warn' : 'bg-muted';
  return <span className={`inline-flex items-center gap-1.5 text-sm ${c}`}><span aria-hidden="true" className={`w-2 h-2 rounded-full ${b}`} />{children}</span>;
}

export function Segments<T extends string>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T | null | undefined; onChange(v: T): void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap border border-ink/35 rounded-xl overflow-hidden">
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <button key={o.value} type="button" role="radio" aria-checked={on} onClick={() => onChange(o.value)}
            className={`px-4 py-2 text-sm ${i ? 'border-l border-ink/20' : ''} ${on ? 'bg-accent text-accent-ink font-bold' : 'hover:bg-white/10'}`}>{o.label}</button>
        );
      })}
    </div>
  );
}

const hhmm = (h?: number) => {
  if (h == null || !Number.isFinite(h)) return '—';
  const x = ((h % 24) + 24) % 24;
  return `${String(Math.floor(x)).padStart(2, '0')}:${String(Math.round((x % 1) * 60)).padStart(2, '0')}`;
};
const blocks = (b?: number[][]) => (b || []).map((x) => `${hhmm(x[0])}–${hhmm(x[1])}`).join('、') || '—';

// a 24-hour bar: sleep (blue), busy (apricot), her own time (green)
function DayBar({ life }: { life: LifeSpec }) {
  const s = life.schedule || {};
  const seg = (a: number, b: number, cls: string, k: string) => {
    const out: JSX.Element[] = [];
    const add = (x: number, y: number, kk: string) => out.push(<div key={kk} className={`absolute top-0 bottom-0 ${cls}`} style={{ left: `${(x / 24) * 100}%`, width: `${((y - x) / 24) * 100}%` }} />);
    const A = ((a % 24) + 24) % 24, B = ((b % 24) + 24) % 24;
    if (b - a >= 24) add(0, 24, k); else if (A <= B) add(A, B, k); else { add(A, 24, k + 'a'); add(0, B, k + 'b'); }
    return out;
  };
  const bed = s.bedtime ?? 23.5, wake = s.wake ?? 7.5;
  return (
    <div className="space-y-1.5">
      <div className="relative h-8 rounded-lg bg-panel2 overflow-hidden">
        {seg(bed, wake < bed ? wake + 24 : wake, 'bg-[rgba(120,140,200,0.4)]', 'sleep')}
        {(s.hobby || []).flatMap((x, i) => seg(x[0], x[1], 'bg-ok/35', 'h' + i))}
        {life.busyness_mode !== 'none' && (s.work || []).flatMap((x, i) => seg(x[0], x[1], 'bg-accent/60', 'w' + i))}
      </div>
      <div className="flex justify-between text-[11px] text-muted"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>
      <div className="flex gap-4 text-xs text-muted"><span>{t('newchar.day_legend_sleep')}</span><span>{t('newchar.day_legend_busy')}</span><span>{t('newchar.day_legend_own')}</span></div>
    </div>
  );
}

function DayReadOnly({ life }: { life: LifeSpec }) {
  const s = life.schedule || {};
  const pj = (life.projects || [])[0];
  return (
    <div className="space-y-5">
      <DayBar life={life} />
      <dl className="grid grid-cols-[auto_1fr_auto_1fr] gap-x-5 gap-y-2 text-sm">
        <dt className="text-muted">{t('newchar.life_wake')}</dt><dd>{hhmm(s.wake)}</dd>
        <dt className="text-muted">{t('newchar.life_bedtime')}</dt><dd>{hhmm(s.bedtime)}</dd>
        <dt className="text-muted">{t('newchar.life_busy')}</dt><dd>{blocks(s.work)}</dd>
        <dt className="text-muted">{t('newchar.day_own')}</dt><dd>{blocks(s.hobby)}</dd>
      </dl>
      <div className="space-y-1">
        <div className="text-sm font-bold">{t('newchar.life_project')}</div>
        <div className="text-sm text-soft">{pj ? `${pj.title}${pj.stage ? '　·　' + pj.stage : ''}` : t('newchar.day_none')}</div>
      </div>
      <div className="space-y-1">
        <div className="text-sm font-bold">{t('newchar.life_events')}</div>
        {(life.small_events || []).length === 0 && <div className="text-sm text-soft">{t('newchar.day_none')}</div>}
        {(life.small_events || []).map((e, i) => (
          <div key={i} className="flex gap-3 py-1.5 border-t border-white/5 text-sm">
            <span className={`w-14 text-xs ${e.kind === 'unwell' ? 'text-red-300' : (e.v ?? 0) < 0 ? 'text-warn' : 'text-ok'}`}>{e.kind === 'unwell' ? t('newchar.day_unwell') : (e.v ?? 0) < 0 ? t('newchar.day_bad') : t('newchar.day_good')}</span>
            <span>{e.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

type Src = 'describe' | 'sample' | 'custom';

export function LifeStep({ profile, setProfile, detail, samples, onNext }: {
  profile: CharProfile; setProfile(p: CharProfile): void; detail: CharDetail; samples: LifeSample[]; onNext(): void;
}) {
  const draft = lifeFromStructure(detail.build?.structure?.life);
  const [src, setSrc] = useState<Src>(profile.life ? 'custom' : 'describe');
  const [sampleId, setSampleId] = useState<string>('');
  const [key, setKey] = useState(0);

  function pick(next: Src) {
    if (next === src) return;
    if (next === 'describe') { setProfile({ ...profile, life: null }); }
    if (next === 'custom') { setProfile({ ...profile, life: profile.life ?? draft ?? { schedule: {}, projects: [], small_events: [] } }); setKey((k) => k + 1); }
    if (next === 'sample') {
      const sm = samples.find((x) => x.id === sampleId) ?? samples[0];
      if (sm && (profile.life || draft) && !window.confirm(t('newchar.life_sample_confirm'))) return;
      if (sm) { setSampleId(sm.id); setProfile({ ...profile, life: sampleSpec(sm) }); }
    }
    setSrc(next);
  }
  const sources: { id: Src; title: string; note: string }[] = [
    { id: 'describe', title: t('newchar.day_src_describe'), note: t('newchar.day_src_describe_note') },
    { id: 'sample', title: t('newchar.day_src_sample'), note: t('newchar.day_src_sample_note') },
    { id: 'custom', title: t('newchar.day_src_custom'), note: t('newchar.day_src_custom_note') },
  ];
  const shown: LifeSpec | null = src === 'describe' ? draft : profile.life ?? null;

  return (
    <section className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-xl font-bold mb-1">{t('newchar.day_title')}</h2>
        <p className="text-sm text-muted">{t('newchar.day_sub')}</p>
      </div>
      <div role="radiogroup" aria-label={t('newchar.day_title')} className="grid grid-cols-3 gap-3.5">
        {sources.map((o) => {
          const on = o.id === src;
          return (
            <button key={o.id} type="button" role="radio" aria-checked={on} onClick={() => pick(o.id)}
              className={`flex flex-col gap-2 p-4 rounded-2xl text-left ${on ? 'bg-accent text-accent-ink border-2 border-accent' : 'border border-ink/35 hover:bg-white/5'}`}>
              <span className="flex items-center gap-2.5 font-bold"><span aria-hidden="true" className={`w-3.5 h-3.5 rounded-full box-border ${on ? 'bg-accent-ink border-4 border-ink' : 'border-2 border-ink/60'}`} />{o.title}</span>
              <span className="text-[13px] leading-relaxed opacity-85">{o.note}</span>
            </button>
          );
        })}
      </div>

      {src === 'sample' && (
        <Segments label={t('newchar.day_src_sample')} value={sampleId} options={samples.map((s) => ({ value: s.id, label: s.name }))}
          onChange={(id) => { const sm = samples.find((x) => x.id === id); if (sm) { setSampleId(id); setProfile({ ...profile, life: sampleSpec(sm) }); } }} />
      )}

      <div className={card}>
        <div className="flex items-baseline gap-3 mb-4">
          <h3 className="text-base font-bold">{t('newchar.day_shape')}</h3>
          <span className="text-sm text-muted">{src === 'describe' ? t('newchar.day_ro_describe') : src === 'sample' ? t('newchar.day_ro_sample') : t('newchar.day_editable')}</span>
        </div>
        {src === 'custom' && profile.life ? (
          <div className="space-y-5">
            <DayBar life={profile.life} />
            <LifeEditor key={key} life={profile.life} onChange={(next) => setProfile({ ...profile, life: next })} />
          </div>
        ) : shown ? <DayReadOnly life={shown} /> : <p className="text-sm text-soft">{t('newchar.day_no_draft')}</p>}
      </div>

      <button type="button" className={outline} onClick={onNext}>{t('newchar.day_next')}</button>
    </section>
  );
}

// ---- 5 確認
const METER_ENDS: Record<string, [string, string, string]> = {
  rationality: ['newchar.q.rationality', 'newchar.end.rationality_lo', 'newchar.end.rationality_hi'],
  experientiality: ['newchar.q.experientiality', 'newchar.end.experientiality_lo', 'newchar.end.experientiality_hi'],
  promotion: ['newchar.q.promotion', 'newchar.end.promotion_lo', 'newchar.end.promotion_hi'],
  prevention: ['newchar.q.prevention', 'newchar.end.prevention_lo', 'newchar.end.prevention_hi'],
  maximizing: ['newchar.q.maximizing', 'newchar.end.maximizing_lo', 'newchar.end.maximizing_hi'],
};

function Slider({ value, proposal, lo, hi, min = 0, max = 1, onChange, label }: { value: number; proposal?: number | null; lo: string; hi: string; min?: number; max?: number; onChange(v: number): void; label: string }) {
  const pct = (x: number) => ((x - min) / (max - min)) * 100;
  return (
    <div className="flex items-center gap-3.5">
      <span className="w-24 text-[13px] text-soft">{lo}</span>
      <div className="flex-1 relative pb-3">
        <input type="range" aria-label={label} min={min} max={max} step={0.05} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[#e07b45] cursor-grab" />
        {proposal != null && <span aria-hidden="true" className="absolute top-5 text-[10px] text-muted -translate-x-1/2" style={{ left: `${pct(proposal)}%` }}>▲</span>}
      </div>
      <span className="w-24 text-[13px] text-soft text-right">{hi}</span>
      <span className="w-10 text-right text-sm tabular-nums">{value.toFixed(2)}</span>
    </div>
  );
}

const CHOICE_Q: Record<string, string> = { medium_primary: 'newchar.q.medium_primary', medium_secondary: 'newchar.q.medium_secondary', first_look: 'newchar.q.first_look', contradiction: 'newchar.q.contradiction', cause: 'newchar.q.cause' };

export function ConfirmStep({ profile, setProfile, meters, choices, big5, constants, onNext }: {
  profile: CharProfile; setProfile(p: CharProfile): void; meters: string[]; choices: Record<string, string[]>; big5: string[]; constants: string[]; onNext(): void;
}) {
  const [advanced, setAdvanced] = useState(false);
  const prop = profile.proposed;
  const ev = (k: string) => prop?.evidence?.[k];
  const pVal = (g: 'thinking' | 'big5' | 'constants', k: string) => (prop?.[g]?.[k] ?? null) as number | null;
  const cur = (g: 'thinking' | 'big5' | 'constants', k: string, dflt = 0.5) => (profile[g]?.[k] ?? pVal(g, k) ?? dflt) as number;
  const setNum = (g: 'thinking' | 'big5' | 'constants', k: string, v: number) => setProfile({ ...profile, [g]: { ...(profile[g] || {}), [k]: v } });
  const changed = (g: 'thinking' | 'big5' | 'constants', k: string) => profile[g]?.[k] != null && pVal(g, k) != null && Math.abs((profile[g]![k] as number) - (pVal(g, k) as number)) > 0.001;
  function backToProposals() {
    if (!prop) return;
    setProfile({ ...profile, thinking: { ...(prop.thinking || {}) }, choices: { ...(prop.choices || {}) }, big5: { ...(prop.big5 || {}) }, constants: { ...(prop.constants || {}) } });
  }

  if (!prop) return <p className="text-sm text-soft">{t('newchar.no_proposals')}</p>;

  return (
    <section className="space-y-6 max-w-4xl">
      <div className="flex items-start gap-5">
        <div className="flex-1">
          <h2 className="text-xl font-bold mb-1">{t('newchar.cf_title')}</h2>
          <p className="text-sm text-muted leading-relaxed">{t('newchar.cf_sub')}</p>
        </div>
        <button type="button" className={outline} onClick={backToProposals}>{t('newchar.cf_all_back')}</button>
      </div>

      <div className="space-y-3">
        <h3 className="text-base font-bold">{t('newchar.cf_thinking')}</h3>
        {meters.map((k) => {
          const ch = changed('thinking', k);
          return (
            <div key={k} className={`${card} space-y-3 ${ch ? 'outline outline-1 outline-warn/40' : ''}`}>
              <div className="flex items-center gap-3">
                <span className="font-bold">{t(METER_ENDS[k][0])}</span>
                <span className="ml-auto">{ch ? <Dot tone="warn">{t('newchar.cf_changed')}</Dot> : <Dot tone="ok">{t('newchar.cf_using')}</Dot>}</span>
                {ch && <button type="button" className="px-3 py-1 rounded-lg border border-ink/35 text-xs hover:bg-white/10" onClick={() => setNum('thinking', k, pVal('thinking', k) as number)}>{t('newchar.cf_back')}</button>}
              </div>
              <Slider label={t(METER_ENDS[k][0])} value={cur('thinking', k)} proposal={pVal('thinking', k)} lo={t(METER_ENDS[k][1])} hi={t(METER_ENDS[k][2])} onChange={(v) => setNum('thinking', k, v)} />
              {ev(k) && <p className="text-[13px] text-muted">{t('newchar.cf_evidence')}{ev(k)}</p>}
            </div>
          );
        })}
      </div>

      <div className="space-y-3">
        <h3 className="text-base font-bold">{t('newchar.cf_habits')}</h3>
        <div className={`${card} space-y-5`}>
          {Object.keys(choices).map((k) => {
            const v = (profile.choices?.[k] ?? prop.choices?.[k] ?? '') as string;
            const pv = prop.choices?.[k];
            return (
              <div key={k} className="space-y-2">
                <div className="font-bold">{t(CHOICE_Q[k])}</div>
                <Segments label={t(CHOICE_Q[k])} value={v} options={choices[k].map((o) => ({ value: o, label: o ? t('newchar.opt.' + o) : t('newchar.opt_none') }))}
                  onChange={(o) => setProfile({ ...profile, choices: { ...(profile.choices || {}), [k]: o || null } })} />
                <div className="text-[13px] text-muted">{t('newchar.cf_proposal')}{pv ? t('newchar.opt.' + pv) : t('newchar.opt_none')}{ev(k) ? ' · ' + ev(k) : ''}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className={`${card} flex items-center gap-4`}>
        <div className="flex-1 space-y-1">
          <div className="font-bold">{t('newchar.scratch')}</div>
          <div className="text-[13px] text-muted">{t('newchar.scratch_note')}</div>
        </div>
        <button type="button" role="switch" aria-checked={!!profile.scratch} aria-label={t('newchar.scratch')} onClick={() => setProfile({ ...profile, scratch: !profile.scratch })}
          className={`relative w-13 h-7.5 rounded-full border ${profile.scratch ? 'bg-accent border-accent' : 'bg-panel2 border-ink/35'}`} style={{ width: 52, height: 30 }}>
          <span className="absolute top-1 w-5 h-5 rounded-full bg-ink transition-all" style={{ left: profile.scratch ? 26 : 4 }} />
        </button>
        <span className="w-6 text-sm text-muted">{profile.scratch ? t('newchar.on') : t('newchar.off')}</span>
      </div>

      <button type="button" className={outline} aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>{advanced ? '▾ ' : '▸ '}{t('newchar.cf_advanced')}</button>
      {advanced && (
        <div className={`${card} space-y-3`}>
          {big5.map((k) => (
            <div key={k} className="space-y-1">
              <div className="text-sm font-bold">{t('newchar.big5.' + k)}</div>
              <Slider label={t('newchar.big5.' + k)} value={cur('big5', k)} proposal={pVal('big5', k)} lo={t('newchar.end.low')} hi={t('newchar.end.high')} onChange={(v) => setNum('big5', k, v)} />
            </div>
          ))}
          {constants.map((k) => (
            <div key={k} className="space-y-1">
              <div className="text-sm font-bold">{t('newchar.const.' + k)}</div>
              <Slider label={t('newchar.const.' + k)} min={k === 'chronotype' ? -1 : 0} value={cur('constants', k, k === 'chronotype' ? 0 : 0.5)} proposal={pVal('constants', k)}
                lo={k === 'chronotype' ? t('newchar.end.early') : t('newchar.end.low')} hi={k === 'chronotype' ? t('newchar.end.night') : t('newchar.end.high')} onChange={(v) => setNum('constants', k, v)} />
            </div>
          ))}
        </div>
      )}

      <button type="button" className={outline} onClick={onNext}>{t('newchar.next_step')}</button>
    </section>
  );
}
