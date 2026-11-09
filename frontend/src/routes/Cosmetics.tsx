import { ZhangxinPlusCard } from '@/components/ZhangxinPlusCard'
import { RiichiCityLocalCard } from '@/components/RiichiCityLocalCard'
import { useEffect, useState } from 'react'
import { RiichiCityUnlockCard } from './RiichiCityUnlockCard'
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
const phases: Record<string, string> = {
  disabled: '未启用', stopped: '捕获已停止', starting: '正在加载', ready: '已就绪', failed: '已暂停，请检查诊断',
}

export function Cosmetics() {
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
      toast.success('装扮设置已保存', { description: '捕获会重新启动，请重新登录游戏加载装扮。' })
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }
  const supported = config?.platform.kind === 'Majsoul'
  return (
    <div className="p-6 max-w-4xl flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">装扮</h1>
        <p className="text-sm text-muted-foreground mt-2">为各平台提供独立的装扮扩展。</p>
      </header>
      {config?.platform.kind === 'Amatsuki' ? <Card><CardHeader><CardTitle>AmatsukiStyle · 天月本地装扮</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">天月装扮目前使用独立的 AmatsukiStyle 开发版，请单独启动工具。AkagiPlus 的天月 AI 接入可独立使用。</CardContent></Card> : config?.platform.kind === 'Zhangxin' ? <ZhangxinPlusCard /> : config?.platform.kind === 'RiichiCity' ? <><RiichiCityLocalCard /><details className="text-sm"><summary className="cursor-pointer text-muted-foreground mb-4">可选：外部 RiichiCityUnlock</summary><RiichiCityUnlockCard /></details></> : <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div><CardTitle>雀魂 · MajsoulMax</CardTitle><p className="text-xs text-muted-foreground mt-2">MajsoulMax</p></div>
          <Switch aria-label="启用 MajsoulMax" checked={draft.enabled} disabled={!supported || saving}
            onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} />
        </CardHeader>
        <CardContent className="grid gap-5">
          {!supported && <p className="text-sm text-muted-foreground">请先在设置中选择雀魂平台。</p>}
          <p className="text-sm text-muted-foreground">启用后，在游戏内选择角色、皮肤与装扮；选择会保存在本机。</p>
          {config?.capture.mode !== 'mitm' && <p className="text-sm text-amber-500">保存并启用 MajsoulMax 将切换到 MITM 捕获。</p>}
          <div className="flex items-center gap-2 text-sm" role="status">
            <span className={`size-2 rounded-full ${status?.phase === 'ready' ? 'bg-emerald-500' : status?.phase === 'failed' ? 'bg-red-500' : 'bg-muted-foreground'}`} />
            <span>{status ? phases[status.phase] ?? status.phase : '尚未连接程序'}</span>
            {status?.phase === 'ready' && <span className="text-muted-foreground">已处理 {status.modified} 条装扮消息</span>}
          </div>
          <p className="text-xs text-muted-foreground">在「总览」或「对局」页点击「启动游戏」，打开专用游戏浏览器。</p>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">插件路径</summary>
            <div className="grid gap-4 mt-4">
              {([['python', 'Python'], ['worker', 'MajsoulMax 入口'], ['data_dir', '私人装扮配置目录']] as const).map(([key, label]) => (
                <div className="grid gap-2" key={key}><Label htmlFor={`majsoulmax-${key}`}>{label}</Label>
                  <Input id={`majsoulmax-${key}`} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
                </div>
              ))}
              {status?.snapshot && <span className="text-xs text-muted-foreground">资源快照：{status.snapshot}</span>}
            </div>
          </details>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="flex items-center justify-between gap-4">
            <Button variant="outline" asChild><Link to="/logs">查看诊断</Link></Button>
            <Button onClick={save} disabled={!supported || saving}>{saving ? '保存中…' : '保存设置'}</Button>
          </div>
          <p className="text-xs text-muted-foreground">保存会重启捕获，请在对局结束后修改。关闭 MajsoulMax 后重新登录，游戏将恢复原始装扮。</p>
        </CardContent>
      </Card>}
    </div>
  )
}
