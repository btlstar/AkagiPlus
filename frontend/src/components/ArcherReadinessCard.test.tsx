import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/i18n'
import { ArcherReadinessCard } from './ArcherReadinessCard'

describe('Archer readiness card', () => {
  beforeEach(async () => { await i18n.changeLanguage('zh-CN') })

  it('updates an open card from the main window language setting', async () => {
    render(<ArcherReadinessCard status={{ state: 'error', code: 'invalid_key',
      message: 'API 密钥无效', elapsed_ms: 0, models: [] }} recheck={vi.fn()} />)
    window.dispatchEvent(new StorageEvent('storage', { key: 'akagi.lang', newValue: 'ja' }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('API キーが無効です'))
    expect(screen.getByRole('button', { name: '再確認' })).toBeTruthy()
  })
  it('shows model names and a working retry without in-game accounting', () => {
    const recheck = vi.fn()
    render(<ArcherReadinessCard status={{
      state: 'ready', message: '连接正常', elapsed_ms: 12,
      models: [{ players: 4, name: 'R260706', available: true }, { players: 3, name: 'NH260304', available: true }],
    }} recheck={recheck} />)
    expect(screen.getByRole('status').textContent).toContain('等待对局开始')
    expect(screen.getByText('NH260304')).toBeTruthy()
    expect(screen.getByRole('status').textContent).not.toContain('Token')
    fireEvent.click(screen.getByRole('button'))
    expect(recheck).toHaveBeenCalledTimes(1)
  })
  it('disables retry while a check is in progress', () => {
    const recheck = vi.fn()
    render(<ArcherReadinessCard status={{
      state: 'checking', message: '正在检查 Archer 连接…', elapsed_ms: 0, models: [],
    }} recheck={recheck} />)
    fireEvent.click(screen.getByRole('button'))
    expect(recheck).not.toHaveBeenCalled()
  })
})
