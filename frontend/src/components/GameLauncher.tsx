import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { open } from '@tauri-apps/plugin-dialog'
import { Play, LoaderCircle, ExternalLink, Settings2 } from 'lucide-react'
import { useConfigStore } from '@/stores/configStore'
import { useGameStore } from '@/stores/gameStore'
import { useLauncherStore } from '@/stores/launcherStore'
import { PLATFORMS, platformInfo, isKnownDefaultStartUrl } from '@/lib/platforms'
import type { PlatformKind } from '@/types'
import { invoke } from '@/lib/tauri'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'

export function GameLauncher({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const config = useConfigStore(s => s.config)
  const setConfig = useConfigStore(s => s.setConfig)
  const game = useGameStore(s => s.game)
  const { running, busy, error, refresh, launch } = useLauncherStore()
  const [changing, setChanging] = useState(false)
  const [localError, setLocalError] = useState('')
  const [pathOpen, setPathOpen] = useState(false)
  const [path, setPath] = useState('')
  useEffect(() => { void refresh(); const timer = setInterval(refresh, 3000); return () => clearInterval(timer) }, [refresh])
  if (!config) return null
  const inGame = !!game && !game.is_done
  const zhangxin = config.platform.kind === 'Zhangxin'
  const amatsuki = config.platform.kind === 'Amatsuki'
  const native = zhangxin || amatsuki || config.platform.kind === 'RiichiCity'
  const select = async (kind: PlatformKind) => {
    if (kind === config.platform.kind || inGame || changing || busy) return
    setChanging(true); setLocalError('')
    const info = platformInfo(kind)
    const next = { ...config, platform: { kind }, capture: { ...config.capture,
      mode: (!info.supportsChromium ? 'mitm' : config.capture.mode) as 'mitm' | 'chromium',
      chromium: { ...config.capture.chromium, start_url: isKnownDefaultStartUrl(config.capture.chromium.start_url) ? info.defaultStartUrl : config.capture.chromium.start_url },
    }, proxy: { ...config.proxy, enabled: true }, autoplay: (kind === 'Zhangxin' || kind === 'Amatsuki') ? { ...config.autoplay, enabled: false } : config.autoplay }
    try { await invoke('update_config', { newConfig: next }); setConfig(next); await refresh() }
    catch (e) { setLocalError(String(e)) } finally { setChanging(false) }
  }
  const configure = async () => {
    if (!native) { setLocalError('请在设置 → 封包捕获中指定浏览器路径。'); return }
    setPath((amatsuki ? config.proxy.amatsuki : zhangxin ? config.proxy.zhangxinplus : config.proxy.riichicity_unlock)?.client_path ?? ''); setPathOpen(true)
  }
  const savePath = async () => {
    setChanging(true); setLocalError('')
    try {
      const previous = config.proxy.riichicity_unlock ?? { enabled: false, executable: '', ca_path: '', client_path: '', injector_path: '' }
      const next = { ...config, proxy: { ...config.proxy, ...(amatsuki ? { amatsuki: { client_path: path } } : zhangxin ? { zhangxinplus: { client_path: path } } : { riichicity_unlock: { ...previous, client_path: path } }) } }
      await invoke('update_config', { newConfig: next }); setConfig(next); setPathOpen(false); await launch()
    } catch (e) { setLocalError(String(e)) } finally { setChanging(false) }
  }
  const start = async () => {
    setLocalError(''); await launch()
    if (useLauncherStore.getState().error.includes(amatsuki ? '未找到天月客户端' : zhangxin ? '未找到掌心客户端' : '未找到一番街客户端')) void configure()
  }
  return <div className="flex flex-col gap-2 min-w-0">
    <div className="flex flex-wrap items-center gap-2">
      {!compact && <select aria-label="启动游戏平台" value={config.platform.kind} disabled={busy || changing || inGame}
        title={inGame ? '对局结束后可切换平台' : '选择游戏平台'}
        onChange={e => void select(e.target.value as PlatformKind)}
        className="h-9 max-w-48 rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50">
        {PLATFORMS.map(p => <option key={p.kind} value={p.kind}>{t(p.labelKey)}</option>)}
      </select>}
      <Button size="sm" onClick={() => void start()} disabled={busy || changing} className="gap-1.5">
        {busy || changing ? <LoaderCircle className="size-4 animate-spin" /> : running ? <ExternalLink className="size-4" /> : <Play className="size-4" />}
        {changing ? '正在切换…' : busy ? '正在启动…' : running ? '返回游戏' : '启动游戏'}
      </Button>
      {!compact && native && <Button size="icon" variant="ghost" aria-label="配置游戏路径" disabled={busy || changing || inGame} onClick={() => void configure()}><Settings2 className="size-4" /></Button>}
    </div>
    {(error || localError) && <div className="max-w-md text-xs text-destructive" role="alert">{localError || error} <button className="underline" onClick={() => void configure()}>配置路径</button></div>}
    <Dialog open={pathOpen} onOpenChange={setPathOpen}><DialogContent>
      <DialogHeader><DialogTitle>{amatsuki ? '天月麻将游戏路径' : zhangxin ? '掌心麻将游戏路径' : '一番街游戏路径'}</DialogTitle><DialogDescription>{amatsuki ? '选择天月安装目录中的 mahjongP.exe。AI 接入无需设置代理或安装装扮插件。' : zhangxin ? '选择安装目录中的 zhangxinmj.exe。本地装扮无需设置代理。' : '选择 Game 文件夹中的 Mahjong-JP.exe。启动游戏时请保持 Proxifier 运行。'}</DialogDescription></DialogHeader>
      <Label htmlFor="game-client-path">游戏程序</Label>
      <div className="flex gap-2"><Input id="game-client-path" value={path} onChange={e => setPath(e.target.value)} /><Button variant="outline" onClick={async () => { const p = await open({ multiple: false, filters: [{ name: '游戏程序', extensions: ['exe'] }] }); if (typeof p === 'string') setPath(p) }}>浏览</Button></div>
      <Button onClick={() => void savePath()} disabled={changing || !path.trim()}>保存并启动</Button>
    </DialogContent></Dialog>
  </div>
}
