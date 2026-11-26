import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import i18n from '@/i18n'
import { invoke } from '@/lib/tauri'
import { useBotStore } from '@/stores/botStore'
import { useConfigStore } from '@/stores/configStore'
import type { AppConfig, BotInfo } from '@/types'
import { Bots } from './Bots'

vi.mock('@/lib/tauri', () => ({ invoke: vi.fn() }))
vi.mock('@/components/NativeApiFields', () => ({ NativeApiFields: () => null }))

const archer = 'archer-api'
const plugin = {
  name: archer, dir: archer, env_ready: true, has_pyproject: true,
  manifest: { bot: { name: archer, version: '0.4.5', supported_modes: ['4p', '3p'] } },
} as BotInfo

function mount(initiallyConfigured: boolean) {
  let configured = initiallyConfigured
  let config = {
    bot: {
      active_4p: '', active_3p: '',
      api: {
        enabled: false, base_url: '', key: '', model_4p: '', model_3p: '',
        proxy_enabled: false, proxy: '', react_timeout_ms: 3000,
      },
    },
  } as AppConfig
  useConfigStore.setState({ config })
  useBotStore.setState({ list: [plugin] })
  const settings = {
    manifest: { settings: {
      api_key: { label: 'API key', type: 'string', default: '', secret: true },
      model: { label: '4P', type: 'string', default: '' },
      model_3p: { label: '3P', type: 'string', default: '' },
    } },
    values: { api_key: 'fixture-key', model: '4p-model', model_3p: '3p-model' },
  }
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command === 'get_bot_settings') return settings
    if (command === 'diagnose_archer') return { ok: true, action: { type: 'dahai' } }
    if (command === 'update_bot_settings') {
      configured = true
      return
    }
    if (command === 'set_archer_active') {
      if (args?.enabled && !configured) throw 'setup_required'
      const name = args?.enabled ? archer : ''
      config = { ...config, bot: {
        ...config.bot,
        active_4p: args?.mode === '3p' ? config.bot.active_4p : name,
        active_3p: args?.mode === '4p' ? config.bot.active_3p : name,
      } }
      return config
    }
  })
  render(<RouterProvider router={createMemoryRouter([{ path: '/', element: <Bots /> }])} />)
  return {
    master: screen.getByRole('switch', { name: 'Enable Archer API' }),
    modes: within(screen.getByRole('row', { name: /Archer API/ })).getAllByRole('switch'),
  }
}

beforeEach(async () => {
  await i18n.changeLanguage('en')
  vi.mocked(invoke).mockReset()
})
afterEach(cleanup)

it('enables both modes and collapses after the last mode is turned off', async () => {
  const { master, modes } = mount(true)
  expect(screen.queryByRole('button', { name: 'Fetch models' })).toBeNull()
  fireEvent.click(master)
  await waitFor(() => expect(modes.map(mode => mode.getAttribute('aria-checked'))).toEqual(['true', 'true']))
  fireEvent.click(modes[0])
  await screen.findByText('Three players only')
  expect(master.getAttribute('aria-checked')).toBe('true')
  await waitFor(() => expect((modes[1] as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(modes[1])
  await waitFor(() => expect(master.getAttribute('aria-checked')).toBe('false'))
  expect(screen.queryByRole('button', { name: 'Fetch models' })).toBeNull()
})

it('opens first-time setup with both modes off until settings are saved', async () => {
  const { master, modes } = mount(false)
  fireEvent.click(master)
  await screen.findByText('Setup pending')
  expect(master.getAttribute('aria-checked')).toBe('false')
  expect(modes.map(mode => mode.getAttribute('aria-checked'))).toEqual(['false', 'false'])
  const save = await screen.findByRole('button', { name: 'Save and enable' })
  await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(save)
  await waitFor(() => expect(modes.map(mode => mode.getAttribute('aria-checked'))).toEqual(['true', 'true']))
})

it('shows diagnostics with the model actions and requires confirmation before a paid test', async () => {
  const { master } = mount(true)
  fireEvent.click(master)
  const fetchModels = await screen.findByRole('button', { name: 'Fetch models' })
  const actions = within(fetchModels.parentElement!)
  expect(actions.getByRole('button', { name: 'Health check' })).toBeTruthy()
  expect(actions.getByRole('button', { name: 'Test three-player' })).toBeTruthy()
  fireEvent.click(actions.getByRole('button', { name: 'Test four-player' }))
  expect(vi.mocked(invoke).mock.calls.some(([command]) => command === 'diagnose_archer')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Run paid test' }))
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('diagnose_archer', expect.objectContaining({ action: 'test4' })))
  await screen.findByText('Inference test passed · dahai')
})
