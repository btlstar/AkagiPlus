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
const phases: Record<string, string> = { '': '未启动', disabled: '未启用', starting: '正在启动', ready: '已就绪', failed: '启动失败，请查看诊断', stopped: '捕获已停止' }
export function RiichiCityUnlockCard() {
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
      toast.success('一番街装扮设置已保存', { description: '在总览点击「启动游戏」，程序会等待捕获就绪。' })
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
      <div><CardTitle>一番街 · RiichiCityUnlock</CardTitle><p className="text-xs text-muted-foreground mt-2">外部插件 · 实验性接入</p></div>
      <Switch aria-label="启用 RiichiCityUnlock" checked={draft.enabled} disabled={saving}
        onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} />
    </CardHeader>
    <CardContent className="grid gap-5">
      <p className="text-sm text-muted-foreground">保留原插件文件夹及个人配置。启用后由 AkagiPlus 管理启动，装扮和 AI 共用游戏捕获。</p>
      <p className="text-sm" role="status">{phases[phase] ?? phase}</p>
      {([['executable', 'RiichiCityUnlock 程序', '选择 RiichiCityUnlock.exe'],
         ['client_path', '游戏程序', '留空自动查找独立客户端 Mahjong-JP.exe'],
         ['injector_path', '进程代理工具', '选择 proxinjector-cli.exe'],
         ['ca_path', '插件公共 CA 证书', '留空使用用户目录 .mitmproxy/mitmproxy-ca-cert.pem']] as const).map(([key, label, placeholder]) =>
        <div className="grid gap-2" key={key}><Label htmlFor={`rcu-${key}`}>{label}</Label>
          <div className="flex gap-2"><Input id={`rcu-${key}`} value={draft[key]} placeholder={placeholder}
            onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
            <Button variant="outline" onClick={() => browse(key)}>浏览</Button></div>
        </div>)}
      <p className="text-xs text-muted-foreground">先保存，再从总览或对局页启动游戏。不要同时单独运行插件或旧版 Copilot 的一番街入口。</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end"><Button disabled={saving} onClick={save}>{saving ? '保存中…' : '保存设置'}</Button></div>
      <p className="text-xs text-muted-foreground">修改前先退出游戏。AI 模型仍在「机器人」中设置；自动操作默认保持关闭。</p>
    </CardContent>
  </Card>
}
