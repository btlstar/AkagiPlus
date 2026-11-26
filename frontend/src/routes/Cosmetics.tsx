import { useTranslation } from 'react-i18next'
import { AmatsukiStyleCard } from '@/components/AmatsukiStyleCard'
import { ZhangxinPlusCard } from '@/components/ZhangxinPlusCard'
import { RiichiCityLocalCard } from '@/components/RiichiCityLocalCard'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { invoke } from '@/lib/tauri'
import { useConfigStore } from '@/stores/configStore'
import type { AppConfig, MajsoulMaxConfig, MajsoulMaxStatus } from '@/types'

const defaults: MajsoulMaxConfig = {
  enabled: false, python: '.venv/Scripts/python.exe',
  worker: 'plugins/majsoulmax/worker.py', data_dir: '.local/majsoulmax',
}
const phases = ['disabled', 'stopped', 'starting', 'ready', 'failed']

export function Cosmetics() {
  const { t } = useTranslation()
  const config = useConfigStore((s) => s.config)
  const setConfig = useConfigStore((s) => s.setConfig)
  const [draft, setDraft] = useState<MajsoulMaxConfig>(defaults)
  const [status, setStatus] = useState<MajsoulMaxStatus | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!config) invoke<AppConfig>('get_config').then(setConfig).catch(() => {})
  }, [config, setConfig])
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(config?.proxy.majsoulmax ?? defaults)
  }, [config])
  useEffect(() => {
    let alive = true
    const refresh = () => invoke<MajsoulMaxStatus>('get_majsoulmax_status')
      .then((s) => { if (alive) setStatus(s) }).catch(() => {})
    void refresh()
    const timer = setInterval(refresh, 2000)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  const save = async () => {
    if (!config) return
    setSaving(true); setError('')
    const next: AppConfig = {
      ...config,
      proxy: { ...config.proxy, enabled: draft.enabled ? true : config.proxy.enabled, majsoulmax: draft },
      capture: draft.enabled ? { ...config.capture, mode: 'mitm' } : config.capture,
    }
    try {
      await invoke('update_config', { newConfig: next })
      setConfig(next)
      toast.success(t('cosmetics.saved'), { description: t('cosmetics.relogin') })
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }
  const supported = config?.platform.kind === 'Majsoul'
  return (
    <div className="p-6 max-w-4xl flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">{t('cosmetics.title')}</h1>
        <p className="text-sm text-muted-foreground mt-2">{t('cosmetics.intro')}</p>
      </header>
      {config?.platform.kind === 'Amatsuki' ? <AmatsukiStyleCard /> : config?.platform.kind === 'Zhangxin' ? <ZhangxinPlusCard /> : config?.platform.kind === 'RiichiCity' ? <RiichiCityLocalCard /> : <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div><CardTitle>{t('platform.plugin_title', { game: t('platform.majsoul'), plugin: 'MajsoulMax-rs' })}</CardTitle><p className="text-xs text-muted-foreground mt-2">MajsoulMax-rs 0.7.0</p></div>
          <Switch aria-label={t('cosmetics.enable', { plugin: 'MajsoulMax' })} checked={draft.enabled} disabled={!supported || saving}
            onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} />
        </CardHeader>
        <CardContent className="grid gap-5">
          {!supported && <p className="text-sm text-muted-foreground">{t('cosmetics.select_majsoul')}</p>}
          <p className="text-sm text-muted-foreground">{t('cosmetics.majsoul_help')}</p>
          {config?.capture.mode !== 'mitm' && <p className="text-sm text-amber-500">{t('cosmetics.mitm')}</p>}
          <div className="flex items-center gap-2 text-sm" role="status">
            <span className={`size-2 rounded-full ${status?.phase === 'ready' ? 'bg-emerald-500' : status?.phase === 'failed' ? 'bg-red-500' : 'bg-muted-foreground'}`} />
            <span>{status ? phases.includes(status.phase) ? t('cosmetics.' + status.phase) : status.phase : t('cosmetics.disconnected')}</span>
            {status?.phase === 'ready' && <span className="text-muted-foreground">{t('cosmetics.processed', { count: status.modified })}</span>}
          </div>
          <p className="text-xs text-muted-foreground">{t('cosmetics.browser')}</p>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">{t('cosmetics.paths')}</summary>
            <div className="grid gap-4 mt-4">
              {([['python', 'Python'], ['worker', t('cosmetics.worker')], ['data_dir', t('cosmetics.data_dir')]] as const).map(([key, label]) => (
                <div className="grid gap-2" key={key}><Label htmlFor={`majsoulmax-${key}`}>{label}</Label>
                  <Input id={`majsoulmax-${key}`} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
                </div>
              ))}
              {status?.snapshot && <span className="text-xs text-muted-foreground">{t('cosmetics.snapshot', { value: status.snapshot })}</span>}
            </div>
          </details>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="flex items-center justify-between gap-4">
            <Button variant="outline" asChild><Link to="/logs">{t('cosmetics.diagnostics')}</Link></Button>
            <Button onClick={save} disabled={!supported || saving}>{saving ? t('common.saving') : t('cosmetics.save_settings')}</Button>
          </div>
          <p className="text-xs text-muted-foreground">{t('cosmetics.majsoul_hint')}</p>
        </CardContent>
      </Card>}
    </div>
  )
}
