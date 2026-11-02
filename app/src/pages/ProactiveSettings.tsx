import { useEffect, useState } from 'react';
import { api, PsycheSettings } from '../api';
import { t } from '../i18n';

// 主動 — how and when she may speak first, her busyness, and her personality (psyche.json in her
// profile). The gates (enabled, no-disturb, caps, speak) apply at her next tick; personality,
// constants and the schedule apply at her next start, like everything else that shapes the dynamics.
const BIG5: [string, string][] = [['openness', '開放性'], ['conscientiousness', '盡責性'], ['extraversion', '外向性'], ['agreeableness', '親和性'], ['neuroticism', '神經質']];
const CONSTS: [string, string][] = [['self_esteem_stability', '自尊穩定'], ['expressiveness', '表達外放'], ['humor_coping', '幽默調節'], ['clinginess_cap', '黏人度上限'], ['tsundere_tendency', '傲嬌'], ['assertiveness', '主見']];

// the five thinking meters (psyche.json `thinking`) with the engine's Big Five defaults for a blank slider
const THINKING: [string, (b5: Record<string, number>) => number][] = [
  ['rationality', (b5) => Number(b5.conscientiousness ?? 0.5)], ['experientiality', () => 0.5],
  ['promotion', (b5) => Number(b5.extraversion ?? 0.5)], ['prevention', (b5) => Number(b5.neuroticism ?? 0.5)], ['maximizing', () => 0.5],
];

export function ProactiveSettings({ onChanged }: { onChanged(): void }) {
  const [s, setS] = useState<PsycheSettings | null>(null);
  const [exists, setExists] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [showPersonality, setShowPersonality] = useState(false);
  const [showThinking, setShowThinking] = useState(false);

  useEffect(() => {
    api.psycheSettings().then((r) => { setExists(r.exists); setS(r.settings ?? {}); }).catch((e) => setNotice(String(e)));
  }, []);

  if (!s) return null;
  const p = s.proactive ?? {};
  const life = s.life ?? {};
  const ch = s.character ?? {};
  const b5 = ch.big5 ?? {};
  const nd = (p.no_disturb && p.no_disturb[0]) || [23, 8];
  const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-accent/60';
  const label = 'block text-xs opacity-70 mb-1';
  const setP = (k: string, v: any) => setS({ ...s, proactive: { ...p, [k]: v } });
  const setCh = (k: string, v: number) => setS({ ...s, character: { ...ch, [k]: v } });
  const setChAny = (k: string, v: any) => setS({ ...s, character: { ...ch, [k]: v } });
  const setB5 = (k: string, v: number) => setS({ ...s, character: { ...ch, big5: { ...b5, [k]: v } } });

  async function save() {
    if (!s) return;
    setSaving(true);
    setNotice(null);
    try {
      const patch: PsycheSettings = {
        proactive: { enabled: p.enabled !== false, no_disturb: [[Number(nd[0]), Number(nd[1])]], daily_cap: Number(p.daily_cap ?? 3),
          usage_threshold_min: Number(p.usage_threshold_min ?? 90), min_gap_min: Number(p.min_gap_min ?? 90), speak: p.speak ?? 'follow',
          inter_agent: p.inter_agent !== false, inter_agent_turn_cap: Number(p.inter_agent_turn_cap ?? 6), inter_agent_visibility: p.inter_agent_visibility !== false },
        life: { busyness_mode: life.busyness_mode ?? 'work' },
        cares_about: s.cares_about ?? [],
        character: ch,
        thinking: s.thinking ?? {},
      };
      const r = await api.updatePsycheSettings(patch);
      setS(r.settings);
      setNotice(r.restart_required ? t('settings.saved_restart') : t('proactive.saved'));
      if (r.restart_required) onChanged();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setSaving(false);
    }
  }

  const slider = (k: string, zh: string, v: number, set: (x: number) => void, min = 0, max = 1) => (
    <label key={k} className="flex items-center gap-2 text-sm">
      <span className="w-20 opacity-80">{zh}</span>
      <input type="range" min={min} max={max} step={0.05} value={v} onChange={(e) => set(Number(e.target.value))} className="flex-1" />
      <span className="w-10 text-right text-xs opacity-60">{v.toFixed(2)}</span>
    </label>
  );

  return (
    <section className="space-y-3">
      <h2 className="font-semibold">{t('settings.proactive')}</h2>
      {!exists && <p className="text-xs text-amber-300">{t('proactive.no_file')}</p>}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={p.enabled !== false} onChange={(e) => setP('enabled', e.target.checked)} />
        {t('proactive.enabled')}
      </label>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label}>{t('proactive.no_disturb')}</label>
          <div className="flex items-center gap-2">
            <input className={field} type="number" min={0} max={24} step={0.5} value={nd[0]} onChange={(e) => setP('no_disturb', [[Number(e.target.value), Number(nd[1])]])} />
            <span className="opacity-60">→</span>
            <input className={field} type="number" min={0} max={24} step={0.5} value={nd[1]} onChange={(e) => setP('no_disturb', [[Number(nd[0]), Number(e.target.value)]])} />
          </div>
          <p className="text-xs opacity-60 mt-1">{t('proactive.no_disturb_note')}</p>
        </div>
        <div>
          <label className={label}>{t('proactive.speak')}</label>
          <select className={field} value={p.speak ?? 'follow'} onChange={(e) => setP('speak', e.target.value)}>
            <option value="follow">{t('proactive.speak_follow')}</option>
            <option value="always">{t('proactive.speak_always')}</option>
            <option value="never">{t('proactive.speak_never')}</option>
          </select>
        </div>
        <div>
          <label className={label}>{t('proactive.daily_cap')}</label>
          <input className={field} type="number" min={0} max={20} value={p.daily_cap ?? 3} onChange={(e) => setP('daily_cap', Number(e.target.value))} />
        </div>
        <div>
          <label className={label}>{t('proactive.usage')}</label>
          <input className={field} type="number" min={0} max={1440} value={p.usage_threshold_min ?? 90} onChange={(e) => setP('usage_threshold_min', Number(e.target.value))} />
        </div>
        <div>
          <label className={label}>{t('proactive.min_gap')}</label>
          <input className={field} type="number" min={0} max={1440} value={p.min_gap_min ?? 90} onChange={(e) => setP('min_gap_min', Number(e.target.value))} />
        </div>
        <div>
          <label className={label}>{t('proactive.busyness')}</label>
          <select className={field} value={life.busyness_mode ?? 'work'} onChange={(e) => setS({ ...s, life: { ...life, busyness_mode: e.target.value } })}>
            <option value="work">{t('proactive.busy_work')}</option>
            <option value="hobby">{t('proactive.busy_hobby')}</option>
            <option value="none">{t('proactive.busy_none')}</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 items-end">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p.inter_agent !== false} onChange={(e) => setP('inter_agent', e.target.checked)} />{t('proactive.inter_agent')}</label>
        <div><label className={label}>{t('proactive.turn_cap')}</label><input className={field} type="number" min={1} max={30} value={p.inter_agent_turn_cap ?? 6} onChange={(e) => setP('inter_agent_turn_cap', Number(e.target.value))} /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p.inter_agent_visibility !== false} onChange={(e) => setP('inter_agent_visibility', e.target.checked)} />{t('proactive.visibility')}</label>
      </div>
      <div>
        <label className={label}>{t('proactive.cares')}</label>
        <textarea className={field} rows={3} value={(s.cares_about ?? []).join('\n')}
          onChange={(e) => setS({ ...s, cares_about: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean) })} />
        <p className="text-xs opacity-60 mt-1">{t('proactive.cares_note')}</p>
      </div>
      <button className="text-xs opacity-70 hover:opacity-100" onClick={() => setShowPersonality(!showPersonality)}>
        {showPersonality ? '▾' : '▸'} {t('proactive.personality')} <span className="opacity-60">({t('proactive.personality_note')})</span>
      </button>
      {showPersonality && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          {BIG5.map(([k, zh]) => slider(k, zh, Number(b5[k] ?? 0.5), (v) => setB5(k, v)))}
          {CONSTS.map(([k, zh]) => slider(k, zh, Number(ch[k] ?? 0.5), (v) => setCh(k, v)))}
          {slider('chronotype', '晨型／夜型', Number(ch.chronotype ?? 0), (v) => setCh('chronotype', v), -1, 1)}
          {slider('rumination', t('proactive.rumination'), Number(ch.rumination ?? b5.neuroticism ?? 0.4), (v) => setCh('rumination', v))}
        </div>
      )}
      <button className="text-xs opacity-70 hover:opacity-100" onClick={() => setShowThinking(!showThinking)}>
        {showThinking ? '▾' : '▸'} {t('proactive.thinking')} <span className="opacity-60">({t('proactive.thinking_note')})</span>
      </button>
      {showThinking && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          {THINKING.map(([k, def]) => slider(k, t('newchar.meter.' + k), Number((s.thinking ?? {})[k] ?? def(b5)), (v) => setS({ ...s, thinking: { ...(s.thinking ?? {}), [k]: v } })))}
        </div>
      )}
      <div className="space-y-1">
        <div className="text-xs opacity-70">{t('proactive.memory_title')}</div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ch.forgets !== false} onChange={(e) => setChAny('forgets', e.target.checked)} />{t('proactive.forgets')}</label>
        {ch.forgets !== false && slider('memory_reliability', t('proactive.forget_rate'), Number(ch.memory_reliability ?? 0.8), (v) => setChAny('memory_reliability', v), 0, 1)}
        <p className="text-xs opacity-60">{t('proactive.forget_note')}</p>
      </div>
      <div className="flex items-center gap-3">
        <button className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-sm disabled:opacity-40" disabled={saving} onClick={save}>{t('proactive.save')}</button>
        {notice && <span className="text-xs opacity-80">{notice}</span>}
      </div>
    </section>
  );
}
