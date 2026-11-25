import { useCallback, useEffect, useRef, useState } from 'react'
import { pickShow } from '@/lib/botShow'
import { invoke, listen } from '@/lib/tauri'
import type { AppConfig, BotResponse, BotStatus, MjaiEvent, OverlayConfig, ShowMeta, Snapshot } from '@/types'

export type ArcherReadiness = {
  state: 'checking' | 'ready' | 'error' | 'disabled' | 'in_game'
  message: string
  code?: string | null
  models: Array<{ players: number; name: string; available: boolean }>
  elapsed_ms: number
}

export function useOverlayShow(setConfig: (config: OverlayConfig) => void) {
  const [show, setShow] = useState<ShowMeta | null>(null)
  const [readiness, setReadiness] = useState<ArcherReadiness | null>(null)
  const refreshRef = useRef<(force?: boolean) => void>(() => {})

  useEffect(() => {
    const unlistens: Array<() => void> = []
    let cancelled = false
    let inGame = false
    let selected = false
    let revision = 0
    let pending = 0

    const refresh = async (force = false) => {
      if (cancelled || inGame) return
      const ticket = ++revision
      pending++
      try {
        const config = await invoke<AppConfig>('get_config')
        if (cancelled || inGame || ticket !== revision) return
        setConfig(config.overlay)
        selected = config.bot.enabled &&
          (config.bot.active_3p === 'archer-api' || config.bot.active_4p === 'archer-api')
        if (!selected) {
          setReadiness(null)
          return
        }
        setReadiness({ state: 'checking', message: '正在检查 Archer 连接…', models: [], elapsed_ms: 0 })
        const result = await invoke<ArcherReadiness>('get_archer_readiness', { force })
        if (cancelled || inGame || ticket !== revision) return
        if (result.state === 'in_game') {
          inGame = true
          setReadiness(null)
        } else {
          setReadiness(result.state === 'disabled' ? null : result)
        }
      } catch {
        if (!cancelled && !inGame && ticket === revision && selected) {
          setReadiness({ state: 'error', message: '无法检查 Archer 连接，请重试', models: [], elapsed_ms: 0 })
        }
      } finally {
        pending--
      }
    }
    refreshRef.current = (force) => { void refresh(force) }

    const startGame = () => {
      inGame = true
      revision++
      setReadiness(null)
      setShow(null)
    }
    const endGame = () => {
      inGame = false
      revision++
      setShow(null)
      setReadiness(null)
      void refresh()
    }
    const subscribe = async <T,>(name: string, callback: (event: T) => void) => {
      const unlisten = await listen<T>(name, (event) => { if (!cancelled) callback(event) })
      if (cancelled) unlisten()
      else unlistens.push(unlisten)
    }
    void Promise.all([
      subscribe<BotResponse>('bot-response', (response) => {
        if (!inGame) return
        const next = pickShow(response.meta)
        if (next) setShow(next)
      }),
      subscribe<MjaiEvent>('mjai-event', (event) => {
        if (event.type === 'start_game' || event.type === 'start_kyoku') startGame()
        else if (event.type === 'end_game') endGame()
      }),
      subscribe<BotStatus>('bot-status', (status) => {
        if ((status.state === 'ready' || status.state === 'loading') && !inGame) startGame()
        else if (status.state === 'stopped' && inGame) endGame()
      }),
      subscribe<null>('bot-config-changed', () => {
        if (!inGame) {
          setShow(null)
          void refresh(true)
        }
      }),
      subscribe<OverlayConfig>('overlay-config', setConfig),
    ]).then(async () => {
      const ticket = revision
      const snapshot = await invoke<Snapshot>('get_status').catch(() => null)
      if (cancelled || ticket !== revision) return
      const status = snapshot?.bot_status.state
      if (status === 'ready' || status === 'loading') startGame()
      else void refresh()
    }).catch(() => {})

    // Only free checks while idle; in-game suggestions take priority.
    const timer = window.setInterval(() => {
      if (!pending && !inGame) void refresh()
    }, 60_000)
    return () => {
      cancelled = true
      revision++
      window.clearInterval(timer)
      refreshRef.current = () => {}
      unlistens.forEach((unlisten) => unlisten())
    }
  }, [setConfig])

  const recheck = useCallback(() => refreshRef.current(true), [])
  return { show, readiness, recheck }
}
