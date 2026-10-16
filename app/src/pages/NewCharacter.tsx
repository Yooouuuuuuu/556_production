import { useEffect, useRef, useState } from 'react';
import { chars, CharDetail, CharPackage, CharProfile } from '../api';
import { t } from '../i18n';

// 設定 → 角色 → 新角色: the soul skill behind 556d (docs/prompt/prompt.md §2.9). One page, four sections for the
// selected package: 描述 (ten boxes in your own words), 產生 (the skill, phase by phase or all at once, its log live),
// 確認 (the proposed numbers and choices with the skill's evidence; you confirm or move them), 結果 (the SOUL, the
// checks, the blind read-back, install). The LLM runs only here, under your eyes; the files are written by code.

const STEMS = ['01-她是誰', '02-背景', '03-發生過的事', '04-說話的方式', '05-怎麼想', '06-跟人相處', '07-喜好', '08-立場', '09-身邊的人', '10-其他'];
const PHASES = ['intake', 'structure', 'thinking', 'voice', 'reactions', 'parts', 'assemble', 'verify'];
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

const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-pink-400/60 text-sm';
const label = 'block text-xs opacity-70 mb-1';
const btn = 'px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/20 disabled:opacity-40';
const primary = 'px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40 text-sm';

export function NewCharacter({ onBack }: { onBack(): void }) {
  const [list, setList] = useState<CharPackage[]>([]);
  const [template, setTemplate] = useState<Record<string, string>>({});
  const [models, setModels] = useState<string[]>(['gemini', 'claude']);
  const [id, setId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CharDetail | null>(null);
  const [describe, setDescribe] = useState<Record<string, string>>({});
  const [profile, setProfile] = useState<CharProfile | null>(null);
  const [model, setModel] = useState('gemini');
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ id: '', display_name: '', pronoun: '她', from_example: false });
  const [thenRest, setThenRest] = useState(false); // 「全部」: after a clean intake, continue from structure
  const logRef = useRef<HTMLPreElement>(null);

  const refreshList = () => chars.list().then((r) => { setList(r.characters); setTemplate(r.template); if (r.models?.length) setModels(r.models); }).catch((e) => setNotice({ kind: 'err', text: String(e) }));
  const load = (cid: string) => chars.detail(cid).then((d) => { setDetail(d); setDescribe(d.describe); setProfile(d.profile); }).catch((e) => setNotice({ kind: 'err', text: String(e) }));

  useEffect(() => { refreshList(); }, []);
  useEffect(() => { if (id) { setDetail(null); load(id); } }, [id]);

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
      const r = await chars.create({ id: form.id.trim(), display_name: form.display_name.trim(), pronoun: form.pronoun, from_example: form.from_example });
      await refreshList();
      setId(r.character.id);
      setForm({ id: '', display_name: '', pronoun: '她', from_example: false });
    } catch (e) { setNotice({ kind: 'err', text: String(e) }); } finally { setBusy(false); }
  }
  async function saveDescribe() {
    if (!id) return;
    setBusy(true); setNotice(null);
    try { await chars.saveDescribe(id, describe); setNotice({ kind: 'ok', text: t('newchar.saved') }); await load(id); refreshList(); }
    catch (e) { setNotice({ kind: 'err', text: String(e) }); } finally { setBusy(false); }
  }
  async function run(phase: string, yes: boolean, force = false, from?: string) {
    if (!id) return;
    setNotice(null);
    try { const r = await chars.run(id, { phase, from, model, yes, force }); setDetail((d) => (d ? { ...d, job: r.job } : d)); }
    catch (e) { setNotice({ kind: 'err', text: String(e) }); }
  }
  function runAll() { setThenRest(true); run('intake', false); }
  function continueThin() { run('structure', true, false, 'structure'); }
  async function saveProfile() {
    if (!id || !profile) return;
    setBusy(true); setNotice(null);
    try {
      const r = await chars.saveProfile(id, { pronoun: profile.pronoun, big5: profile.big5, constants: profile.constants, thinking: profile.thinking, choices: profile.choices });
      setProfile(r.profile); setNotice({ kind: 'ok', text: t('newchar.saved') });
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

  return (
    <div className="h-full overflow-y-auto p-5 max-w-3xl space-y-5">
      <div className="flex items-center gap-3">
        <button className="text-sm opacity-70 hover:opacity-100" onClick={onBack}>{t('character.back')}</button>
        <h1 className="text-lg font-semibold">{t('newchar.title')}</h1>
      </div>
      <p className="text-xs opacity-60">{t('newchar.note')}</p>
      {notice && <p className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : 'text-green-300'}`}>{notice.text}</p>}

      {/* packages + create */}
      <section className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {list.map((c) => (
            <button key={c.id} className={`px-3 py-1.5 rounded-lg text-sm ${c.id === id ? 'bg-pink-500/40' : 'bg-white/5 hover:bg-white/10'}`} onClick={() => setId(c.id)}>
              {c.display_name || c.id} <span className="opacity-50 text-xs">{c.id}</span>
              <span className="opacity-60 text-xs ml-1">{c.describe_filled}/{c.describe_total}{c.has_soul ? (c.lock ? ' · SOUL' : ' · ' + t('newchar.handwritten')) : ''}{c.installed ? ' · ' + t('newchar.installed_tag') : ''}{c.running ? ' · ' + t('newchar.running') : ''}</span>
            </button>
          ))}
        </div>
        <details className="rounded-xl bg-white/5 p-3" open={list.length === 0}>
          <summary className="cursor-pointer text-sm">{t('newchar.create')}</summary>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div><label className={label}>{t('newchar.id')}</label><input className={field} value={form.id} placeholder="lin" onChange={(e) => setForm({ ...form, id: e.target.value.toLowerCase() })} /></div>
            <div><label className={label}>{t('newchar.display')}</label><input className={field} value={form.display_name} placeholder="阿凜" onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></div>
            <div><label className={label}>{t('newchar.pronoun')}</label>
              <select className={field} value={form.pronoun} onChange={(e) => setForm({ ...form, pronoun: e.target.value })}><option value="她">她</option><option value="他">他</option></select></div>
            <label className="flex items-center gap-2 text-sm mt-5"><input type="checkbox" checked={form.from_example} onChange={(e) => setForm({ ...form, from_example: e.target.checked })} />{t('newchar.from_example')}</label>
          </div>
          <button className={`${primary} mt-3`} disabled={busy || !form.id.trim() || !form.display_name.trim()} onClick={create}>{t('newchar.create_go')}</button>
        </details>
      </section>

      {id && detail && (
        <>
          {/* 描述 */}
          <section className="space-y-3">
            <h2 className="font-semibold">{t('newchar.describe')} <span className="text-xs opacity-50 font-normal">{cur?.display_name} · {id}</span></h2>
            <p className="text-xs opacity-60">{t('newchar.describe_note')}</p>
            {STEMS.map((stem) => (
              <div key={stem}>
                <label className={label}>{stem.slice(3)}</label>
                <textarea className={`${field} min-h-[72px]`} rows={3} value={describe[stem] ?? ''} placeholder={template[stem] || ''} onChange={(e) => setDescribe({ ...describe, [stem]: e.target.value })} />
              </div>
            ))}
            <button className={primary} disabled={busy || running} onClick={saveDescribe}>{t('newchar.save')}</button>
          </section>

          {/* 產生 */}
          <section className="space-y-3">
            <h2 className="font-semibold">{t('newchar.generate')}</h2>
            <p className="text-xs opacity-60">{t('newchar.generate_note')}</p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm">{t('newchar.model')}</label>
              <select className={`${field} w-auto`} value={model} onChange={(e) => setModel(e.target.value)}>{models.map((m) => <option key={m} value={m}>{m}</option>)}</select>
              <button className={primary} disabled={running} onClick={runAll}>{t('newchar.run_all')}</button>
              <button className={btn} disabled={running || !detail.character.phases.includes('intake')} onClick={continueThin} title={t('newchar.continue_note')}>{t('newchar.continue')}</button>
            </div>
            <div className="flex flex-wrap gap-2">
              {PHASES.map((ph) => (
                <button key={ph} className={`${btn} ${detail.character.phases.includes(ph) ? 'ring-1 ring-green-400/40' : ''}`} disabled={running} onClick={() => run(ph, true)}>
                  {t('newchar.phase.' + ph)}
                </button>
              ))}
              <button className={btn} disabled={running || !detail.check || detail.check.includes('通過')} onClick={() => run('assemble', true, true)} title={t('newchar.force_note')}>{t('newchar.force')}</button>
            </div>
            {(running || jobDone) && (
              <div className="rounded-xl bg-black/30 p-3 text-xs space-y-1">
                <div className="opacity-70">
                  {running ? `${t('newchar.running')} · ${detail.job.kind} ${detail.job.phase || ''} ${detail.job.model || ''}` : `${t('newchar.finished')} · ${detail.job.kind} · exit ${detail.job.exit_code}${detail.job.error ? ' · ' + detail.job.error : ''}`}
                </div>
                <pre ref={logRef} className="max-h-56 overflow-y-auto whitespace-pre-wrap leading-relaxed">{detail.job.log || '…'}</pre>
              </div>
            )}
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

          {/* 確認 */}
          <section className="space-y-3">
            <h2 className="font-semibold">{t('newchar.confirm')}</h2>
            <p className="text-xs opacity-60">{t('newchar.confirm_note')}{profile?.proposed?.model ? ` · ${profile.proposed.model} · ${profile.proposed.at}` : ''}</p>
            {!profile?.proposed && <p className="text-sm opacity-60">{t('newchar.no_proposals')}</p>}
            {profile && (
              <div className="space-y-3">
                <div className="grid gap-2">
                  {METERS.map((k) => (
                    <div key={k} className="rounded-lg bg-white/5 p-2">
                      <div className="flex items-center gap-3 text-sm">
                        <span className="w-44">{t('newchar.meter.' + k)}</span>
                        <input type="range" min={0} max={1} step={0.05} className="flex-1" value={profile.thinking?.[k] ?? proposed('thinking', k) ?? 0.5} onChange={(e) => num('thinking', k, Number(e.target.value))} />
                        <span className="w-10 text-right tabular-nums">{(profile.thinking?.[k] ?? proposed('thinking', k) ?? 0.5).toFixed(2)}</span>
                        {profile.thinking?.[k] == null && <span className="text-xs text-amber-300">{t('newchar.unconfirmed')}</span>}
                      </div>
                      {evidence(k) && <div className="text-xs opacity-60 mt-1">{evidence(k)}</div>}
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.keys(CHOICES).map((k) => (
                    <div key={k} className="rounded-lg bg-white/5 p-2">
                      <label className={label}>{t('newchar.choice.' + k)}</label>
                      <select className={field} value={profile.choices?.[k] ?? profile.proposed?.choices?.[k] ?? ''} onChange={(e) => choice(k, e.target.value)}>
                        {CHOICES[k].map((o) => <option key={o} value={o}>{o ? t('newchar.opt.' + o) : '—'}</option>)}
                      </select>
                      {evidence(k) && <div className="text-xs opacity-60 mt-1">{evidence(k)}</div>}
                    </div>
                  ))}
                </div>
                <details className="rounded-lg bg-white/5 p-2">
                  <summary className="cursor-pointer text-sm">{t('newchar.personality')}</summary>
                  <div className="grid gap-2 mt-2">
                    {BIG5.map((k) => (
                      <div key={k} className="flex items-center gap-3 text-sm">
                        <span className="w-44">{t('newchar.big5.' + k)}</span>
                        <input type="range" min={0} max={1} step={0.05} className="flex-1" value={profile.big5?.[k] ?? proposed('big5', k) ?? 0.5} onChange={(e) => num('big5', k, Number(e.target.value))} />
                        <span className="w-10 text-right tabular-nums">{(profile.big5?.[k] ?? proposed('big5', k) ?? 0.5).toFixed(2)}</span>
                      </div>
                    ))}
                    {CONSTANTS.map((k) => (
                      <div key={k} className="flex items-center gap-3 text-sm">
                        <span className="w-44">{t('newchar.const.' + k)}</span>
                        <input type="range" min={k === 'chronotype' ? -1 : 0} max={1} step={0.05} className="flex-1" value={profile.constants?.[k] ?? proposed('constants', k) ?? (k === 'chronotype' ? 0 : 0.5)} onChange={(e) => num('constants', k, Number(e.target.value))} />
                        <span className="w-10 text-right tabular-nums">{(profile.constants?.[k] ?? proposed('constants', k) ?? (k === 'chronotype' ? 0 : 0.5)).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </details>
                <div className="flex gap-2">
                  <button className={btn} disabled={!profile.proposed} onClick={acceptProposals}>{t('newchar.accept_all')}</button>
                  <button className={primary} disabled={busy} onClick={saveProfile}>{t('newchar.save')}</button>
                </div>
              </div>
            )}
          </section>

          {/* 結果 */}
          <section className="space-y-3">
            <h2 className="font-semibold">{t('newchar.result')}</h2>
            {detail.character.stale?.length > 0 && (
              <p className="text-sm text-amber-300">{t('newchar.stale').replace('{what}', detail.character.stale.join('、'))}</p>
            )}
            {detail.check && <pre className="rounded-lg bg-white/5 p-3 text-xs whitespace-pre-wrap">{detail.check}</pre>}
            {detail.verify && <pre className="rounded-lg bg-white/5 p-3 text-xs whitespace-pre-wrap max-h-64 overflow-y-auto">{detail.verify}</pre>}
            {detail.soul ? (
              <>
                <div className="text-xs opacity-60">{t('newchar.soul_stats').replace('{chars}', String(detail.soul.length)).replace('{seeds}', String(detail.seeds)).replace('{people}', detail.people.join('、') || '—')}</div>
                <pre className="rounded-lg bg-white/5 p-3 text-sm whitespace-pre-wrap max-h-[28rem] overflow-y-auto leading-relaxed">{detail.soul}</pre>
                <div className="flex items-center gap-3">
                  <button className={primary} disabled={running} onClick={install}>{detail.character.installed ? t('newchar.reinstall') : t('newchar.install')}</button>
                  <span className="text-xs opacity-60">{detail.character.installed ? t('newchar.installed_note') : t('newchar.install_note')}</span>
                </div>
              </>
            ) : <p className="text-sm opacity-60">{t('newchar.no_soul')}</p>}
          </section>
        </>
      )}
    </div>
  );
}
