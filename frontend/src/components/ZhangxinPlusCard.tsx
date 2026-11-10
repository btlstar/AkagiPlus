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
    catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true
    void invoke<string>('zhangxinplus', { action: 'status' })
      .then(raw => { if (active) setResult(JSON.parse(raw) as Status) })
      .catch(e => { if (active) setError(String(e)) })
      .finally(() => { if (active) setBusy(false) })
    void refresh()
    return () => { active = false }
  }, [refresh])
  return <Card>
    <CardHeader><CardTitle>{t('platform.plugin_title', { game: t('platform.zhangxin'), plugin: 'ZhangxinPlus' })}</CardTitle></CardHeader>
    <CardContent className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t('platform.zhangxin_cosmetics')}</p>
      <p className="text-sm" role="status">{busy ? '正在处理…' : result?.message ?? '正在检查…'}</p>
      {result?.runtime && <p className="text-xs text-muted-foreground">上次游戏运行：已处理 {result.runtime.reads} 次读取、{result.runtime.writes} 次本地选择；AI 消息 {result.runtime.ai_frames ?? 0} 条。</p>}
      {result?.runtime?.ai_error && <p role="alert" className="text-sm text-destructive">本地 AI 消息写入失败：{result.runtime.ai_error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || running || launching} onClick={() => void act('install')}>安装 / 更新 ZhangxinPlus</Button>
        <Button variant="outline" disabled={busy || running || launching} onClick={() => void act('restore')}>还原游戏文件</Button>
        <Button variant="ghost" disabled={busy || launching} onClick={() => void act('status')}>刷新状态</Button>
      </div>
      {(running || launching) && <p className="text-xs text-muted-foreground">请先退出掌心，再安装或还原插件。</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <p className="text-xs text-muted-foreground">{t('platform.zhangxin_install_hint')}</p>
      <p className="text-xs text-muted-foreground">{t('platform.zhangxin_limits')}</p>
    </CardContent>
  </Card>
}
