import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('App', () => {
  it('exposes the complete local training workflow', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><App /></MemoryRouter></QueryClientProvider>)
    expect(screen.getAllByText('视觉模型训练台').length).toBeGreaterThan(0)
    expect(screen.getByText('项目')).toBeInTheDocument()
    expect(screen.getAllByText('数据集').length).toBeGreaterThan(0)
    expect(screen.getByText('训练任务')).toBeInTheDocument()
    expect(screen.getByText('模型结果')).toBeInTheDocument()
  })
})
