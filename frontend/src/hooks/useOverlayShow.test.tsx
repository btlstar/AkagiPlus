import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AppConfig } from '@/types'

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  handlers: new Map<string, (event: unknown) => void>(),
  unlisten: vi.fn(),
}))
vi.mock('@/lib/tauri', () => ({
  invoke: mocks.invoke,
  listen: vi.fn(async (name: string, callback: (event: unknown) => void) => {
    mocks.handlers.set(name, callback)
    return mocks.unlisten
  }),
}))
import { useOverlayShow, type ArcherReadiness } from './useOverlayShow'

const ready: ArcherReadiness = {
  state: 'ready', message: '连接正常', models: [
    { players: 4, name: 'R260706', available: true },
    { players: 3, name: 'NH260304', available: true },
  ], elapsed_ms: 123,
}
const config = (name = 'archer-api') => ({
  bot: { enabled: true, active_4p: name, active_3p: name },
  overlay: { enabled: true, top_n: 3, opacity: 0.95, always_on_top: true },
}) as AppConfig
const suggestion = { title: 'Archer · R260706', items: [{ label: '打牌', pais: ['P'], value: '100.0%' }] }
let currentConfig: AppConfig
let status = 'idle'
let probe: () => Promise<ArcherReadiness>
const setConfig = vi.fn()
const emit = (name: string, event: unknown) => act(() => mocks.handlers.get(name)?.(event))
const count = () => mocks.invoke.mock.calls.filter(([name]) => name === 'get_archer_readiness').length

beforeEach(() => {
  vi.clearAllMocks()
  mocks.handlers.clear()
  currentConfig = config()
  status = 'idle'
  probe = async () => ready
  mocks.invoke.mockImplementation(async (command: string) => {
    if (command === 'get_config') return currentConfig
    if (command === 'get_status') return { bot_status: { state: status } }
    if (command === 'get_archer_readiness') return probe()
    throw new Error(command)
  })
})
afterEach(() => vi.useRealTimers())

describe('idle Archer connection display', () => {
  it('automatically checks selected Archer and loads overlay settings', async () => {
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(result.current.readiness?.state).toBe('ready'))
    expect(count()).toBe(1)
    expect(setConfig).toHaveBeenCalledWith(currentConfig.overlay)
    expect(mocks.invoke).toHaveBeenCalledWith('get_archer_readiness', { force: false })
  })
  it('does not query Archer for another selected engine', async () => {
    currentConfig = config('native')
    renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(setConfig).toHaveBeenCalled())
    expect(count()).toBe(0)
  })
  it('a slow connection result cannot overwrite a real game suggestion', async () => {
    let finish!: (value: ArcherReadiness) => void
    probe = () => new Promise((resolve) => { finish = resolve })
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(result.current.readiness?.state).toBe('checking'))
    emit('mjai-event', { type: 'start_game' })
    emit('bot-response', { type: 'dahai', meta: { show: suggestion } })
    await act(async () => finish(ready))
    expect(result.current.show).toEqual(suggestion)
    expect(result.current.readiness).toBeNull()
  })
  it('restores readiness after the game and ignores late boundary displays', async () => {
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(result.current.readiness?.state).toBe('ready'))
    emit('mjai-event', { type: 'start_game' })
    emit('bot-response', { type: 'dahai', meta: { show: suggestion } })
    emit('mjai-event', { type: 'end_game' })
    emit('bot-response', { type: 'none', meta: { show: { items: [{ label: '等待新的决策' }] } } })
    await waitFor(() => expect(result.current.readiness?.state).toBe('ready'))
    expect(result.current.show).toBeNull()
    expect(count()).toBe(2)
  })
  it.each(['archer-api', 'native'])('opens during a %s game without a pre-game query', async (name) => {
    currentConfig = config(name)
    status = 'ready'
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith('get_status'))
    await act(async () => {})
    emit('bot-response', { type: 'dahai', meta: { show: suggestion } })
    expect(result.current.show).toEqual(suggestion)
    expect(count()).toBe(0)
  })
  it('refreshes idle configuration changes but stops checks in games', async () => {
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(result.current.readiness?.state).toBe('ready'))
    emit('bot-config-changed', null)
    await waitFor(() => expect(count()).toBe(2))
    expect(mocks.invoke).toHaveBeenCalledWith('get_archer_readiness', { force: true })
    emit('mjai-event', { type: 'start_game' })
    emit('bot-config-changed', null)
    await act(async () => {})
    expect(count()).toBe(2)
  })
  it('only performs periodic free checks while idle', async () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(result.current.readiness?.state).toBe('ready')
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
    expect(count()).toBe(2)
    emit('mjai-event', { type: 'start_game' })
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000) })
    expect(count()).toBe(2)
  })
  it('allows retrying a failed connection check', async () => {
    probe = async () => ({ ...ready, state: 'error', message: '无法连接' })
    const { result } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(result.current.readiness?.state).toBe('error'))
    probe = async () => ready
    act(() => result.current.recheck())
    await waitFor(() => expect(result.current.readiness?.state).toBe('ready'))
    expect(mocks.invoke).toHaveBeenCalledWith('get_archer_readiness', { force: true })
  })
  it('releases event listeners and prevents idle work after closing', async () => {
    const { result, unmount } = renderHook(() => useOverlayShow(setConfig))
    await waitFor(() => expect(result.current.readiness?.state).toBe('ready'))
    unmount()
    expect(mocks.unlisten).toHaveBeenCalledTimes(5)
    const before = count()
    emit('bot-config-changed', null)
    await act(async () => {})
    expect(count()).toBe(before)
  })
})
