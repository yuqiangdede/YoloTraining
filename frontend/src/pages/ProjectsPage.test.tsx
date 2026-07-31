import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { ProjectsPage } from './ProjectsPage'

const { api } = vi.hoisted(() => ({ api: {
  projects: vi.fn().mockResolvedValue({ data: [{ id: 'default', name: '默认项目', description: '', datasetCount: 2, trainingCount: 1, modelCount: 1 }] }),
  createProject: vi.fn().mockResolvedValue({ data: { id: 'project-1', name: '厂区安全' } }),
} }))

vi.mock('../lib/api', () => ({ api }))

describe('ProjectsPage', () => {
  it('shows hierarchy counts and creates a project', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><ProjectsPage /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText('默认项目')).toBeInTheDocument()
    expect(screen.getByText('进入项目')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('项目名称'), { target: { value: '厂区安全' } })
    fireEvent.change(screen.getByLabelText('用途说明'), { target: { value: '安全帽检测' } })
    fireEvent.click(screen.getByRole('button', { name: '创建项目' }))
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ name: '厂区安全', description: '安全帽检测' }))
  })
})
