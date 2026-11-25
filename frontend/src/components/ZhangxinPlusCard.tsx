import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { invoke } from '@/lib/tauri'
import { useLauncherStore } from '@/stores/launcherStore'

type Status = { status: string; message: string; runtime?: { reads: number; writes: number; ai_frames?: number; ai_error?: string } }
export function ZhangxinPlusCard() {
  const { t } = useTranslation()
  const [result, setResult] = useState<Status | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const running = useLauncherStore(s => s.running)
  const launching = useLauncherStore(s => s.busy)
  const refresh = useLauncherStore(s => s.refresh)
  const act = async (action: 'status' | 'install' | 'restore') => {
    setBusy(true); setError('')
    try { setResult(JSON.parse(await invoke<string>('zhangxinplus', { action })) as Status) }
    catch (e) { setResult(null); setError(String(e)) } finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true
    void invoke<string>('zhangxinplus', { action: 'status' })
      .then(raw => { if (active) setResult(JSON.parse(raw) as Status) })
      .catch(e => { if (active) { setResult(null); setError(String(e)) } })
      .finally(() => { if (active) setBusy(false) })
    void refresh()
    return () => { active = false }
  }, [refresh])
  return <Card>
    <CardHeader><CardTitle>{t('platform.plugin_title', { game: t('platform.zhangxin'), plugin: 'ZhangxinPlus' })}</CardTitle></CardHeader>
    <CardContent className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t('platform.zhangxin_cosmetics')}</p>
      <p className="text-sm" role="status">{busy ? t('cosmetics.working') : error ? t('cosmetics.check_failed') : result ? t('cosmetics.' + result.status, { defaultValue: result.message }) : t('cosmetics.checking')}</p>
      {result?.runtime && <p className="text-xs text-muted-foreground">{t('cosmetics.last_run', { reads: result.runtime.reads, writes: result.runtime.writes, frames: result.runtime.ai_frames ?? 0 })}</p>}
      {result?.runtime?.ai_error && <p role="alert" className="text-sm text-destructive">{t('cosmetics.ai_error', { error: result.runtime.ai_error })}</p>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || running || launching} onClick={() => void act('install')}>{t('cosmetics.install')} ZhangxinPlus</Button>
        <Button variant="outline" disabled={busy || running || launching} onClick={() => void act('restore')}>{t('cosmetics.restore')}</Button>
        <Button variant="ghost" disabled={busy || launching} onClick={() => void act('status')}>{t('cosmetics.refresh')}</Button>
      </div>
      {(running || launching) && <p className="text-xs text-muted-foreground">{t('cosmetics.quit', { game: t('platform.zhangxin') })}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <p className="text-xs text-muted-foreground">{t('platform.zhangxin_install_hint')}</p>
      <p className="text-xs text-muted-foreground">{t('platform.zhangxin_limits')}</p>
    </CardContent>
  </Card>
}
