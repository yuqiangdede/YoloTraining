import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ModelsPage } from './ModelsPage'

const { api } = vi.hoisted(() => {
  const artifacts = ['alpha', 'beta', 'gamma'].map((name, index) => ({
    id: `model-${index + 1}`,
    trainingJobId: `job-${index + 1}`,
    name: `${name}.pt`,
    task: 'detect',
    path: `runs/${name}/best.pt`,
    kind: 'BEST',
    sha256: name,
    metrics: { map50: .8 + index / 100 },
    trainingQuality: { state: 'SUFFICIENT', primaryMetric: 'metrics/mAP50-95(B)', bestEpoch: 2, bestValue: .9, finalValue: .88, validationMetrics: { 'metrics/mAP50-95(B)': .88 }, lossMetrics: {}, notes: ['VALIDATION_METRICS_AVAILABLE'] },
  }))
  return { api: {
  jobs: vi.fn().mockResolvedValue({ data: [{ id: 'job-1', name: 'alpha run', task: 'detect', modelPath: 'models/pretrained/yolo26n.pt', status: 'SUCCEEDED', progress: 100, currentEpoch: 2, params: { epochs: 2, imgsz: 640, batch: 4 } }], worker: { alive: true } }),
  models: vi.fn().mockResolvedValue({
    data: artifacts,
    pretrained: [
      { id: 'yolo26n.pt', name: 'yolo26n.pt', path: 'models/pretrained/yolo26n.pt', kind: 'PRETRAINED', task: 'detect', canTest: true, sizeBytes: 1024 },
      { id: 'sam3.pt', name: 'sam3.pt', path: 'models/pretrained/sam3.pt', kind: 'PRETRAINED', task: 'segment', canTest: false, sizeBytes: 2048 },
    ],
  }),
  exports: vi.fn().mockResolvedValue({ data: [] }),
  deleteModel: vi.fn(),
  } }
})

vi.mock('../lib/api', () => ({ api }))
afterEach(() => cleanup())

describe('ModelsPage', () => {
  it('caps comparison at two models and preserves explicit pretrained testability', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><ModelsPage /></MemoryRouter></QueryClientProvider>)

    const checkboxes = await screen.findAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    await waitFor(() => expect(checkboxes[2]).toBeDisabled())
    expect(screen.getByText('对比已选满')).toBeInTheDocument()
    const pretrainedTest = screen.getAllByRole('link', { name: '测试' }).find((link) => link.getAttribute('href')?.includes('pretrained'))
    expect(pretrainedTest).toHaveAttribute('href', '/models/test?model=pretrained%3Ayolo26n.pt')
    expect(screen.getByText('仅用于预标注')).toBeInTheDocument()
    expect(screen.getAllByText('验证证据完整').length).toBeGreaterThan(0)
    expect(screen.getAllByText('mAP50-95（严格）').length).toBeGreaterThan(0)
  })
})
