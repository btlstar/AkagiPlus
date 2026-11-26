import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { invoke } from '@/lib/tauri'
import { useLauncherStore } from '@/stores/launcherStore'
type Result = { status: string; message: string; available_version?: number }
export function RiichiCityLocalCard() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<Result | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const running = useLauncherStore(s => s.running)
  const launching = useLauncherStore(s => s.busy)
  const refresh = useLauncherStore(s => s.refresh)
  const act = async (action: 'status' | 'install' | 'restore') => {
    setBusy(true); setError('')
    try {
      const raw = await invoke<string>('riichicity_local', { action })
      const result = JSON.parse(raw) as Result
      setStatus(result)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true
    void invoke<string>('riichicity_local', { action: 'status' })
      .then(raw => { if (active) setStatus(JSON.parse(raw) as Result) })
      .catch(e => { if (active) setError(String(e)) })
      .finally(() => { if (active) setBusy(false) })
    void refresh()
    return () => { active = false }
  }, [refresh])
  return <Card>
    <CardHeader><CardTitle>{t('platform.plugin_title', { game: t('platform.riichi_city'), plugin: 'RiichiCityStyle' })}</CardTitle></CardHeader>
    <CardContent className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t('cosmetics.riichi_help')}</p>
      <p className="text-sm" role="status">{busy ? t('cosmetics.working') : status ? t('cosmetics.' + status.status, { defaultValue: status.message }) : t('cosmetics.checking')}{!busy && status?.available_version ? ` · v${status.available_version}` : ''}</p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || running || launching} onClick={() => void act('install')}>{t('cosmetics.install')}</Button>
        <Button variant="outline" disabled={busy || running || launching} onClick={() => void act('restore')}>{t('cosmetics.restore')}</Button>
        <Button variant="ghost" disabled={busy || launching} onClick={() => void act('status')}>{t('cosmetics.refresh')}</Button>
      </div>
      {(running || launching) && <p className="text-xs text-muted-foreground">{t('cosmetics.quit', { game: t('platform.riichi_city') })}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <p className="text-xs text-muted-foreground">{t('cosmetics.riichi_hint')}</p>
    </CardContent>
  </Card>
}
