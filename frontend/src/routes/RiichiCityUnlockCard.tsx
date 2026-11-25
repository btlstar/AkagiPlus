import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { invoke } from '@/lib/tauri'
import { useConfigStore } from '@/stores/configStore'
import type { AppConfig, RiichiCityUnlockConfig } from '@/types'

const defaults: RiichiCityUnlockConfig = { enabled: false, executable: '', ca_path: '', client_path: '', injector_path: '' }
const phases = ['disabled', 'starting', 'ready', 'failed', 'stopped']
export function RiichiCityUnlockCard() {
  const { t } = useTranslation()
  const config = useConfigStore((s) => s.config)
  const setConfig = useConfigStore((s) => s.setConfig)
  const [draft, setDraft] = useState(defaults)
  const [phase, setPhase] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(config?.proxy.riichicity_unlock ?? defaults)
  }, [config])
  useEffect(() => {
    let alive = true
    const refresh = () => invoke<{ phase: string }>('get_riichicity_unlock_status').then((s) => { if (alive) setPhase(s.phase) }).catch(() => {})
    void refresh()
    const timer = setInterval(refresh, 2000)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  const save = async () => {
    if (!config) return
    setSaving(true); setError('')
    const next: AppConfig = { ...config,
      capture: draft.enabled ? { ...config.capture, mode: 'mitm' } : config.capture,
      proxy: { ...config.proxy, enabled: draft.enabled ? true : config.proxy.enabled, riichicity_unlock: draft },
    }
    try {
      await invoke('update_config', { newConfig: next }); setConfig(next)
      toast.success(t('cosmetics.saved'), { description: t('cosmetics.external_launch') })
    } catch (e) { setError(String(e)) } finally { setSaving(false) }
  }
  const browse = async (key: keyof Omit<RiichiCityUnlockConfig, 'enabled'>) => {
    try {
      const selected = await open({ multiple: false, directory: false })
      if (typeof selected === 'string') setDraft((prev) => ({ ...prev, [key]: selected }))
    } catch (e) { setError(String(e)) }
  }
  return <Card>
    <CardHeader className="flex flex-row items-center justify-between gap-4">
      <div><CardTitle>{t('platform.plugin_title', { game: t('platform.riichi_city'), plugin: 'RiichiCityUnlock' })}</CardTitle><p className="text-xs text-muted-foreground mt-2">{t('cosmetics.external')}</p></div>
      <Switch aria-label={t('cosmetics.enable', { plugin: 'RiichiCityUnlock' })} checked={draft.enabled} disabled={saving}
        onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} />
    </CardHeader>
    <CardContent className="grid gap-5">
      <p className="text-sm text-muted-foreground">{t('cosmetics.external_help')}</p>
      <p className="text-sm" role="status">{phase ? phases.includes(phase) ? t('cosmetics.' + phase) : phase : t('cosmetics.idle')}</p>
      {([['executable', t('cosmetics.executable'), 'RiichiCityUnlock.exe'],
         ['client_path', t('launcher.program'), t('cosmetics.auto_client')],
         ['injector_path', t('cosmetics.injector'), 'proxinjector-cli.exe'],
         ['ca_path', t('cosmetics.ca'), t('cosmetics.auto_ca')]] as const).map(([key, label, placeholder]) =>
        <div className="grid gap-2" key={key}><Label htmlFor={`rcu-${key}`}>{label}</Label>
          <div className="flex gap-2"><Input id={`rcu-${key}`} value={draft[key]} placeholder={placeholder}
            onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
            <Button variant="outline" onClick={() => browse(key)}>{t('launcher.browse')}</Button></div>
        </div>)}
      <p className="text-xs text-muted-foreground">{t('cosmetics.external_launch')}</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end"><Button disabled={saving} onClick={save}>{saving ? t('common.saving') : t('cosmetics.save_settings')}</Button></div>
      <p className="text-xs text-muted-foreground">{t('cosmetics.external_hint')}</p>
    </CardContent>
  </Card>
}
