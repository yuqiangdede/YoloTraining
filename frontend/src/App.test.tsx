import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('App', () => {
  it('exposes the complete local training workflow', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><App /></MemoryRouter></QueryClientProvider>)
    expect(screen.getByText('YOLO26 Studio')).toBeInTheDocument()
    expect(screen.getByText('素材库')).toBeInTheDocument()
    expect(screen.getByText('人工标注')).toBeInTheDocument()
    expect(screen.getByText('训练任务')).toBeInTheDocument()
    expect(screen.getByText('模型结果')).toBeInTheDocument()
  })
})
