import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TrainingPage } from './TrainingPage'

const { api } = vi.hoisted(() => ({ api: {
  allDatasetVersions: vi.fn().mockResolvedValue({ data: [] }),
  jobs: vi.fn().mockResolvedValue({ data: [{ id: 'failed-job', name: 'failed run', task: 'detect', modelPath: 'models/pretrained/yolo26n.pt', status: 'FAILED', progress: 0, currentEpoch: 0, params: {}, errorMessage: '\u9a8c\u8bc1\u96c6\u6ca1\u6709\u56fe\u7247' }] }),
  jobLog: vi.fn().mockResolvedValue({ content: 'validation images missing', sizeBytes: 26 }),
  artifacts: vi.fn().mockResolvedValue({ data: [{ trainingQuality: { state: 'SUFFICIENT', primaryMetric: 'metrics/mAP50-95(B)', bestEpoch: 2, bestValue: .7, finalValue: .68, validationMetrics: { 'metrics/mAP50-95(B)': .68, 'metrics/precision(B)': .8 }, lossMetrics: {}, notes: ['VALIDATION_METRICS_AVAILABLE'] } }] }),
  createJob: vi.fn(),
  jobAction: vi.fn(),
} }))

vi.mock('../lib/api', () => ({ api }))

afterEach(() => cleanup())

describe('TrainingPage', () => {
  it('shows failed job details and its log on demand', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><TrainingPage /></QueryClientProvider>)
    expect(await screen.findByText('\u9a8c\u8bc1\u96c6\u6ca1\u6709\u56fe\u7247')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '\u67e5\u770b\u65e5\u5fd7' }))
    await waitFor(() => expect(api.jobLog).toHaveBeenCalledWith('failed-job'))
    expect(await screen.findByText('validation images missing')).toBeInTheDocument()
  })

  it('shows a log loading error without hiding the failed job', async () => {
    api.jobLog.mockRejectedValueOnce(new Error('log unavailable'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><TrainingPage /></QueryClientProvider>)
    await screen.findByText('\u9a8c\u8bc1\u96c6\u6ca1\u6709\u56fe\u7247')
    fireEvent.click(screen.getByRole('button', { name: '\u67e5\u770b\u65e5\u5fd7' }))
    expect(await screen.findByText('log unavailable')).toBeInTheDocument()
    expect(screen.getByText('failed run')).toBeInTheDocument()
  })

  it('loads training evidence on demand without hiding the job row', async () => {
    api.jobs.mockResolvedValueOnce({ data: [{ id: 'completed-job', name: 'completed run', task: 'detect', modelPath: 'models/pretrained/yolo26n.pt', status: 'SUCCEEDED', progress: 100, currentEpoch: 3, params: { epochs: 3, imgsz: 640, batch: 4, optimizer: 'AdamW' } }] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><TrainingPage /></QueryClientProvider>)
    await screen.findByText('completed run')
    fireEvent.click(screen.getByRole('button', { name: '查看训练依据' }))
    expect(await screen.findByText('验证证据完整')).toBeInTheDocument()
    expect(screen.getAllByText('mAP50-95（严格）').length).toBeGreaterThan(0)
    expect(api.artifacts).toHaveBeenCalledWith('completed-job')
  })

})
