import { useEffect, useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { invoke } from '@/lib/tauri'
import { useLauncherStore } from '@/stores/launcherStore'
type Result = { status: string; message: string }
export function RiichiCityLocalCard() {
  const [status, setStatus] = useState('正在检查…')
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
      setStatus(result.message)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true
    void invoke<string>('riichicity_local', { action: 'status' })
      .then(raw => { if (active) setStatus((JSON.parse(raw) as Result).message) })
      .catch(e => { if (active) setError(String(e)) })
      .finally(() => { if (active) setBusy(false) })
    void refresh()
    return () => { active = false }
  }, [refresh])
  return <Card>
    <CardHeader><CardTitle>一番街 · 本地装扮</CardTitle></CardHeader>
    <CardContent className="grid gap-4">
      <p className="text-sm text-muted-foreground">直接在游戏内选择角色、皮肤、头像和装扮方案。首次使用需安装补丁，之后正常启动游戏即可。</p>
      <p className="text-sm" role="status">{busy ? '正在处理…' : status}</p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || running || launching} onClick={() => void act('install')}>安装 / 更新</Button>
        <Button variant="outline" disabled={busy || running || launching} onClick={() => void act('restore')}>还原游戏文件</Button>
        <Button variant="ghost" disabled={busy || launching} onClick={() => void act('status')}>刷新状态</Button>
      </div>
      {(running || launching) && <p className="text-xs text-muted-foreground">请先正常退出一番街，再安装或还原补丁。</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <p className="text-xs text-muted-foreground">只支持已适配的客户端版本。操作前校验并备份原文件；游戏更新后请勿强行覆盖。安全模式若包含自己，会将对局皮肤显示为默认。</p>
    </CardContent>
  </Card>
}
