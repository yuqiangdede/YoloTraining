import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ModelTestPage } from './ModelTestPage'

const { api } = vi.hoisted(() => ({ api: {
  models: vi.fn().mockResolvedValue({ data: [{ id: 'model-1', trainingJobId: 'job-1', name: 'best.pt', task: 'detect', path: 'runs/job-1/weights/best.pt', kind: 'BEST', sha256: 'hash', metrics: {} }], pretrained: [] }),
  exports: vi.fn().mockResolvedValue({ data: [] }),
  predict: vi.fn().mockResolvedValue({ data: { model: { id: 'model-1', name: 'best.pt', format: 'pt', task: 'detect' }, image: { width: 100, height: 80, mimeType: 'image/png' }, annotatedImage: 'data:image/jpeg;base64,result', predictions: [{ label: 'cat', confidence: .91, kind: 'rectangle', points: [[.1, .2], [.5, .8]] }] } }),
  createVideoJob: vi.fn().mockResolvedValue({ id: 'video-job-1', modelId: 'model-1', modelFormat: 'pt', task: 'detect', status: 'QUEUED', progress: 0, currentFrame: 0, totalFrames: 10, fps: 25, width: 100, height: 80, params: { confidence: .25 }, createdAt: '', updatedAt: '' }),
  videoJob: vi.fn().mockResolvedValue({ id: 'video-job-1', modelId: 'model-1', modelFormat: 'pt', task: 'detect', status: 'SUCCEEDED', progress: 100, currentFrame: 10, totalFrames: 10, fps: 25, width: 100, height: 80, params: { confidence: .25 }, downloadUrl: '/api/v1/models/video-jobs/video-job-1/download', createdAt: '', updatedAt: '' }),
  cancelVideoJob: vi.fn(),
} }))

vi.mock('../lib/api', () => ({ api }))
afterEach(() => cleanup())

describe('ModelTestPage', () => {
  it('selects a trained model, previews an image and renders prediction details', async () => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:test') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><ModelTestPage /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText('best.pt · 目标检测')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('选择测试图片'), { target: { files: [new File(['image'], 'test.png', { type: 'image/png' })] } })
    fireEvent.click(screen.getByRole('button', { name: '开始测试' }))
    await waitFor(() => expect(api.predict).toHaveBeenCalledWith('model-1', expect.any(File), .25, 'pt'))
    expect(await screen.findByText('cat')).toBeInTheDocument()
    expect(screen.getByText('91.0%')).toBeInTheDocument()
  })

  it('allows an exported ONNX model to be selected for prediction', async () => {
    api.exports.mockResolvedValueOnce({ data: [{ id: 'export-1', artifactId: 'model-1', status: 'SUCCEEDED', progress: 100, outputPath: 'runs/exports/export-1/best.onnx' }] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><ModelTestPage /></MemoryRouter></QueryClientProvider>)
    const format = await screen.findByLabelText('模型格式')
    fireEvent.change(format, { target: { value: 'onnx' } })
    const input = screen.getByLabelText('选择测试图片')
    fireEvent.change(input, { target: { files: [new File(['image'], 'test.png', { type: 'image/png' })] } })
    fireEvent.click(screen.getByRole('button', { name: '开始测试' }))
    await waitFor(() => expect(api.predict).toHaveBeenCalledWith('model-1', expect.any(File), .25, 'onnx'))
  })

  it('submits a video job and renders the completed output', async () => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:video') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><ModelTestPage /></MemoryRouter></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('tab', { name: '视频推理' }))
    fireEvent.change(screen.getByLabelText('选择测试视频'), { target: { files: [new File(['video'], 'test.mp4', { type: 'video/mp4' })] } })
    fireEvent.click(screen.getByRole('button', { name: '开始视频推理' }))
    await waitFor(() => expect(api.createVideoJob).toHaveBeenCalledWith('model-1', expect.any(File), .25, 'pt'))
    expect(await screen.findByText('处理完成')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '下载叠加视频' })).toHaveAttribute('href', '/api/v1/models/video-jobs/video-job-1/download')
  })
})
