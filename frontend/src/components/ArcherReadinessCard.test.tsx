import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ArcherReadinessCard } from './ArcherReadinessCard'

describe('Archer readiness card', () => {
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
