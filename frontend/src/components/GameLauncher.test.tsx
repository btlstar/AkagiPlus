import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { GameLauncher } from './GameLauncher'
import { useConfigStore } from '@/stores/configStore'
import { useLauncherStore } from '@/stores/launcherStore'
import { useGameStore } from '@/stores/gameStore'
import { invoke } from '@/lib/tauri'
import type { AppConfig, GameStateSnapshot } from '@/types'
vi.mock('@/lib/tauri', () => ({ invoke: vi.fn() }))
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn() }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
const config = { platform: { kind: 'Majsoul' }, proxy: { enabled: true }, capture: { mode: 'mitm', chromium: { start_url: 'https://game.maj-soul.com/1/' } } } as AppConfig
beforeEach(() => {
  vi.clearAllMocks()
  useConfigStore.setState({ config })
  useGameStore.setState({ game: null })
  useLauncherStore.setState({ running: false, busy: false, error: '' })
  vi.mocked(invoke).mockResolvedValue({ running: false, client_path: '' })
})
describe('GUI game launch', () => {
  it('shares one pending launch across both entry points', async () => {
    let finish!: (value: unknown) => void
    vi.mocked(invoke).mockImplementation(cmd => cmd === 'launch_game' ? new Promise(resolve => { finish = resolve }) : Promise.resolve({ running: false, client_path: '' }))
    render(<><GameLauncher /><GameLauncher compact /></>)
    fireEvent.click(screen.getAllByRole('button', { name: '启动游戏' })[0])
    expect(screen.getAllByRole('button', { name: '正在启动…' }).every(b => (b as HTMLButtonElement).disabled)).toBe(true)
    await useLauncherStore.getState().launch()
    expect(vi.mocked(invoke).mock.calls.filter(([cmd]) => cmd === 'launch_game')).toHaveLength(1)
    finish({ running: true, client_path: '' })
    await waitFor(() => expect(screen.getAllByRole('button', { name: '返回游戏' })).toHaveLength(2))
  })
  it('disables platform changes during a match', () => {
    useGameStore.setState({ game: { is_done: false } as GameStateSnapshot })
    render(<GameLauncher />)
    expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(true)
  })
  it('shares saved platform and selects native capture for RiichiCity', async () => {
    render(<GameLauncher />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'RiichiCity' } })
    await waitFor(() => expect(useConfigStore.getState().config?.platform.kind).toBe('RiichiCity'))
    expect(vi.mocked(invoke).mock.calls.some(([cmd, args]) => cmd === 'update_config' && (args?.newConfig as AppConfig).capture.mode === 'mitm')).toBe(true)
  })
  it('shows path configuration after missing native client', async () => {
    useConfigStore.setState({ config: { ...config, platform: { kind: 'RiichiCity' } } })
    vi.mocked(invoke).mockImplementation(cmd => cmd === 'launch_game' ? Promise.reject('未找到一番街客户端，请选择游戏。') : Promise.resolve({ running: false, client_path: '' }))
    render(<GameLauncher />)
    fireEvent.click(screen.getByRole('button', { name: '启动游戏' }))
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByLabelText('游戏程序')).toBeTruthy()
  })
  it.each(['Zhangxin', 'Amatsuki'] as const)('selects %s without retaining automatic play', async (kind) => {
    useConfigStore.setState({ config: { ...config, autoplay: { enabled: true } } as AppConfig })
    render(<GameLauncher />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: kind } })
    await waitFor(() => expect(useConfigStore.getState().config?.platform.kind).toBe(kind))
    expect(useConfigStore.getState().config?.autoplay.enabled).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: '配置游戏路径' }))
    expect(await screen.findByText(kind === 'Amatsuki' ? '天月麻将游戏路径' : '掌心麻将游戏路径')).toBeTruthy()
  })

})
