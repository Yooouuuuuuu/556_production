import { useEffect, useState } from 'react';
import { api, CompanionInfo, Settings as S } from '../api';
import { ToolsSettings } from './ToolsSettings';
import { ProactiveSettings } from './ProactiveSettings';
import { DevSettings } from './DevSettings';
import { VoiceSettings } from './VoiceSettings';
import { t } from '../i18n';

// One character's page (設定 → 角色 → a character): everything that belongs to that character alone —
// name and Live2D model (companion.json), memory language and context window (kokoro.json /
// config.yaml), abilities (platform toolsets), 主動 (psyche.json), its own voice (profile voice.json
// over the global connectors), the channel accounts (.env) and, behind the developer toggle, the
// model and memory-engine knobs of its own config files. 556d edits the character on stage, so the
// list switches the stage to this character before opening the page.
export function Character({ info, onBack }: { info: CompanionInfo; onBack(): void }) {
  const [s, setS] = useState<S | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [dev, setDev] = useState<boolean>(() => { try { return localStorage.getItem('556.dev') === '1'; } catch { return false; } });
  const toggleDev = (on: boolean) => { setDev(on); try { localStorage.setItem('556.dev', on ? '1' : '0'); } catch { /* ignore */ } };

  useEffect(() => {
    setS(null);
    api.settings().then((r) => setS(r.settings)).catch((e) => setNotice({ kind: 'err', text: String(e) }));
    api.models().then((r) => setModels(r.models.flatMap((m) => m.models))).catch(() => {});
  }, [info.name]);

  const set = <K extends keyof S>(k: K, v: S[K]) => s && setS({ ...s, [k]: v });

  async function save() {
    if (!s) return;
    setSaving(true);
    setNotice(null);
    try {
      const r = await api.updateSettings({ companion_name: s.companion_name, avatar_model: s.avatar_model, memory_language: s.memory_language, context_turns: s.context_turns });
      setS(r.settings);
      setRestartNeeded(r.restart_required);
      setNotice({
        kind: r.reembed_required ? 'warn' : 'ok',
        text: r.reembed_required ? t('settings.saved_reembed') : r.restart_required ? t('settings.saved_restart') : t('settings.saved'),
      });
    } catch (e) {
      setNotice({ kind: 'err', text: String(e) });
    } finally {
      setSaving(false);
    }
  }

  async function restart() {
    await api.restartHermes();
    setRestartNeeded(false);
    setNotice({ kind: 'ok', text: t('settings.restarting') });
  }

  const status = info.active ? (info.stopping ? t('roster.stopping') : info.hermes_connected ? t('roster.active') : t('roster.starting')) : t('roster.inactive');
  const field = 'w-full rounded-lg bg-white/5 px-3 py-2 outline-none focus:ring-1 focus:ring-pink-400/60';
  const label = 'block text-xs opacity-70 mb-1';

  return (
    <div className="h-full overflow-y-auto p-5 max-w-2xl space-y-5">
      <div className="flex items-center gap-3">
        <button className="text-sm opacity-70 hover:opacity-100" onClick={onBack}>{t('character.back')}</button>
        <h2 className="font-semibold text-lg">{info.display_name || info.name}</h2>
        <span className="text-xs opacity-50">{info.name}</span>
        <span className={`w-2.5 h-2.5 rounded-full ${info.active ? (info.hermes_connected ? 'bg-green-400' : 'bg-amber-400') : 'bg-white/20'}`} />
        <span className="text-xs opacity-60">{status}</span>
      </div>
      <p className="text-xs opacity-60">{t('character.note')}</p>

      {s && (
        <>
          <section className="space-y-3">
            <h2 className="font-semibold">{t('character.basic')}</h2>
            <div>
              <label className={label}>{t('settings.companion_name')}</label>
              <input className={field} value={s.companion_name} placeholder={t('settings.unnamed')} onChange={(e) => set('companion_name', e.target.value)} />
            </div>
            <div>
              <label className={label}>{t('settings.avatar_model')}</label>
              <select className={field} value={s.avatar_model} onChange={(e) => set('avatar_model', e.target.value)}>
                {[s.avatar_model, ...models.filter((m) => m !== s.avatar_model)].map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="font-semibold">{t('settings.memory')}</h2>
            <div>
              <label className={label}>{t('settings.memory_language')}</label>
              <select className={field} value={s.memory_language} onChange={(e) => set('memory_language', e.target.value)}>
                <option value="zh-TW">繁體中文 (zh-TW)</option>
                <option value="en">English (en)</option>
              </select>
              <p className="text-xs opacity-60 mt-1">{t('settings.memory_language_note')}</p>
            </div>
            <div>
              <label className={label}>{t('settings.context_turns')}</label>
              <input className={field} type="number" min={2} max={200} value={s.context_turns} onChange={(e) => set('context_turns', Number(e.target.value))} />
            </div>
          </section>

          <div className="flex items-center gap-3">
            <button className="px-4 py-2 rounded-xl bg-pink-500/80 hover:bg-pink-500 text-white disabled:opacity-40" disabled={saving} onClick={save}>{t('settings.save')}</button>
            {restartNeeded && <button className="px-4 py-2 rounded-xl bg-amber-500/70 hover:bg-amber-500 text-white" onClick={restart}>{t('settings.restart')}</button>}
            {notice && <span className={`text-sm ${notice.kind === 'err' ? 'text-red-300' : notice.kind === 'warn' ? 'text-amber-300' : 'text-green-300'}`}>{notice.text}</span>}
          </div>
        </>
      )}

      <ToolsSettings onChanged={() => setRestartNeeded(true)} />
      <ProactiveSettings onChanged={() => setRestartNeeded(true)} />
      <VoiceSettings companion={info.name} />

      <section className="space-y-3">
        <h2 className="font-semibold">{t('character.channels')}</h2>
        <p className="text-xs opacity-60">{t('character.channels_note')}</p>
        <DevSettings groups={['channels']} tone="plain" onRestart={restart} />
      </section>

      <label className="flex items-center gap-2 text-sm opacity-80">
        <input type="checkbox" checked={dev} onChange={(e) => toggleDev(e.target.checked)} />
        {t('dev.toggle')}
      </label>
      {dev && <DevSettings groups={['model', 'memory']} onRestart={restart} />}
    </div>
  );
}
