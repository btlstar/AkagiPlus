import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Cosmetics } from './Cosmetics'
import { useConfigStore } from '@/stores/configStore'
import type { AppConfig } from '@/types'
import { invoke } from '@/lib/tauri'
vi.mock('@/lib/tauri', () => ({ invoke: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

function makeConfig(over: {
  firstRunCompleted?: boolean
  platform?: AppConfig['platform']['kind']
  mode?: AppConfig['capture']['mode']
}): AppConfig {
  return {
    general: {
      first_run_completed: over.firstRunCompleted ?? false,
      developer_mode: false,
    },
    logging: { dir: '', level: 'info', all_level: 'warn' },
    platform: { kind: over.platform ?? 'Majsoul' },
    proxy: { enabled: true, addr: '127.0.0.1:23410', ca_dir: '', block_telemetry: true },
    bot: {
      enabled: true,
      active_4p: 'akagi-native',
      active_3p: 'akagi-native3p',
      auto_sync: false,
      dir: '',
      api: {
        enabled: false,
        base_url: '',
        key: '',
        model_4p: '',
        model_3p: '',
        proxy_enabled: false,
        proxy: '',
        react_timeout_ms: 3000,
      },
    },
    capture: {
      mode: over.mode ?? 'mitm',
      chromium: {
        executable: '',
        user_data_dir: '',
        start_url: 'https://game.maj-soul.com/1/',
        cft_channel: 'stable',
        force_cft: false,
        extra_args: [],
        block_telemetry: true,
      },
    },
    autoplay: {
      enabled: false,
      majsoul: {
        pre_click_delay_min_ms: 0,
        pre_click_delay_max_ms: 0,
        inter_click_delay_ms: [0, 0],
        hover_delay_ms: [0, 0],
        click_hold_ms: [0, 0],
        verify_input_ms: [0, 0],
        click_retries: 0,
        reload_after_failures: 0,
        dealer_first_discard_extra_delay_ms: [0, 0],
      },
      delay: {
        mode: 'legacy',
        min_delay_ms: [0, 0],
        min_button_delay_ms: [0, 0],
        distribution: 'uniform',
        lognormal: {},
        bank_on_long_thought: false,
        riichi_extra_ms: 0,
        kan_extra_ms: 0,
        safety_margin_ms: 0,
        bank_use_fraction: 0,
        bank_max_single_ms: 0,
        no_budget_cap_ms: 0,
      },
    },
    overlay: { enabled: true, top_n: 3, opacity: 1, always_on_top: true },
    network: { github_mirror_mode: 'auto', github_custom_mirror: '' },
  }
}

const base = makeConfig({ mode: 'chromium' })
const fixture: AppConfig = {
  ...base,
  proxy: { ...base.proxy, enabled: false, ca_dir: './ca' },
  capture: { ...base.capture, http: { record_all: false, bodies: true, max_body_bytes: 262144, static_assets: false } },
}

describe('MajsoulMax cosmetics settings', () => {
  beforeEach(() => {
    vi.mocked(invoke).mockReset()
    vi.mocked(invoke).mockImplementation(async (command) => {
      if (command === 'get_riichicity_unlock_status') return { phase: 'ready' }
      if (command === 'get_majsoulmax_status') return { phase: 'ready', modified: 3, snapshot: 'fixture' }
    })
    useConfigStore.setState({ config: structuredClone(fixture) })
  })
  it('enables MITM and preserves unrelated capture configuration', async () => {
    render(<MemoryRouter><Cosmetics /></MemoryRouter>)
    fireEvent.click(screen.getByRole('switch', { name: '启用 MajsoulMax' }))
    fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('update_config', {
      newConfig: {
        ...fixture,
        proxy: { ...fixture.proxy, enabled: true, majsoulmax: {
          enabled: true, python: '.venv/Scripts/python.exe', worker: 'plugins/majsoulmax/worker.py', data_dir: '.local/majsoulmax',
        } },
        capture: { ...fixture.capture, mode: 'mitm' },
      },
    }))
    expect(await screen.findByText('已处理 3 条装扮消息')).toBeTruthy()
  })
  it('does not offer the Majsoul plugin on another platform', () => {
    useConfigStore.setState({ config: { ...fixture, platform: { kind: 'Tenhou' } } })
    render(<MemoryRouter><Cosmetics /></MemoryRouter>)
    expect(screen.getByRole('switch', { name: '启用 MajsoulMax' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '保存设置' }).hasAttribute('disabled')).toBe(true)
  })
})


describe('RiichiCityUnlock cosmetics settings', () => {
  it('offers the selected platform plugin and keeps MajsoulMax settings untouched', async () => {
    const previous: AppConfig = { ...fixture, platform: { kind: 'RiichiCity' },
      proxy: { ...fixture.proxy, majsoulmax: { enabled: true, python: 'private-python', worker: 'worker', data_dir: 'private-data' } } }
    useConfigStore.setState({ config: structuredClone(previous) })
    render(<MemoryRouter><Cosmetics /></MemoryRouter>)
    expect(screen.queryByRole('switch', { name: '启用 MajsoulMax' })).toBeNull()
    fireEvent.change(screen.getByLabelText('RiichiCityUnlock 程序'), { target: { value: 'D:/tools/RiichiCityUnlock.exe' } })
    fireEvent.click(screen.getByRole('switch', { name: '启用 RiichiCityUnlock' }))
    fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('update_config', { newConfig: {
      ...previous, capture: { ...previous.capture, mode: 'mitm' },
      proxy: { ...previous.proxy, enabled: true, riichicity_unlock: {
        enabled: true, executable: 'D:/tools/RiichiCityUnlock.exe', ca_path: '', client_path: '', injector_path: '',
      } },
    } }))
  })
})


describe('ZhangxinPlus cosmetics settings', () => {
  it('shows the standalone plugin and calls its installer', async () => {
    vi.mocked(invoke).mockImplementation(async (command) => {
      if (command === 'zhangxinplus') return JSON.stringify({ status: 'installed', message: 'ZhangxinPlus 已安装 · 资源 92217' })
      if (command === 'get_game_launch_status') return { running: false, client_path: '' }
      if (command === 'get_majsoulmax_status') return { phase: 'disabled', modified: 0, snapshot: '' }
    })
    useConfigStore.setState({ config: { ...fixture, platform: { kind: 'Zhangxin' } } })
    render(<MemoryRouter><Cosmetics /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: '安装 / 更新 ZhangxinPlus' })).toBeTruthy()
    expect(screen.queryByRole('switch', { name: '启用 MajsoulMax' })).toBeNull()
    await waitFor(() => expect((screen.getByRole('button', { name: '安装 / 更新 ZhangxinPlus' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: '安装 / 更新 ZhangxinPlus' }))
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('zhangxinplus', { action: 'install' }))
  })
})


describe('AmatsukiStyle cosmetics settings', () => {
  it('can disable cosmetics without changing AI or game path', async () => {
    vi.mocked(invoke).mockReset()
    vi.mocked(invoke).mockResolvedValue(undefined)
    const previous: AppConfig = { ...fixture, platform: { kind: 'Amatsuki' },
      proxy: { ...fixture.proxy, amatsuki: { client_path: 'D:/game/mahjongP.exe', cosmetics_enabled: true } } }
    useConfigStore.setState({ config: structuredClone(previous) })
    render(<MemoryRouter><Cosmetics /></MemoryRouter>)
    fireEvent.click(screen.getByRole('switch', { name: '启用 AmatsukiStyle' }))
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('update_config', { newConfig: {
      ...previous, proxy: { ...previous.proxy, amatsuki: { ...previous.proxy.amatsuki, cosmetics_enabled: false } },
    } }))
    expect(useConfigStore.getState().config?.proxy.amatsuki?.cosmetics_enabled).toBe(false)
  })
})
