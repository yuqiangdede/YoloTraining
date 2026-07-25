import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'
import { AppShell } from './AppShell'
import { ToastProvider, useToast } from './Toast'

const { api } = vi.hoisted(() => ({ api: {
  health: vi.fn(), environment: vi.fn(), jobs: vi.fn(),
} }))
vi.mock('../lib/api', () => ({ api }))

describe('interaction foundation', () => {
  beforeEach(() => {
    api.health.mockResolvedValue({ status: 'ok', projectRoot: 'E:/project' })
    api.environment.mockResolvedValue({ python: 'python', gpu: { isAvailable: true, name: 'RTX TEST', cuda: '12.6', memoryBytes: 8 }, disk: { totalBytes: 100, freeBytes: 50 }, projectRoot: 'E:/project', venvIsLocal: true })
    api.jobs.mockResolvedValue({ data: [], worker: { alive: true, currentJobId: null, currentKind: null, currentStartedAt: null, lastActivityAt: null, lastError: null } })
  })
  afterEach(() => { cleanup(); vi.useRealTimers() })

  it('focuses the safe action and closes on Escape', async () => {
    const onCancel = vi.fn()
    render(<ConfirmDialog open title="删除数据？" description="无法恢复" onCancel={onCancel} onConfirm={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('button', { name: '取消' })).toHaveFocus())
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('announces a toast and removes it after its lifecycle', () => {
    vi.useFakeTimers()
    function Trigger() { const { notify } = useToast(); return <button onClick={() => notify('操作成功')}>触发</button> }
    render(<ToastProvider><Trigger /></ToastProvider>)
    fireEvent.click(screen.getByRole('button', { name: '触发' }))
    expect(screen.getByText('操作成功')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(4100))
    expect(screen.queryByText('操作成功')).not.toBeInTheDocument()
  })

  it('uses live health data and lets keyboard users close mobile navigation', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<h1>内容</h1>} /></Route></Routes></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText('RTX TEST')).toBeInTheDocument()
    expect(screen.getByText('系统正常')).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: '打开导航菜单' })
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('does not report a healthy system when worker status cannot be loaded', async () => {
    api.jobs.mockRejectedValueOnce(new Error('worker unavailable'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<h1>内容</h1>} /></Route></Routes></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText('工作线程状态不可用')).toBeInTheDocument()
    expect(screen.queryByText('系统正常')).not.toBeInTheDocument()
  })
})
