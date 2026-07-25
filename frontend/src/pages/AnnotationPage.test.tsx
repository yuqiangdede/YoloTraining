import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AnnotationPage } from './AnnotationPage'

const { api, state } = vi.hoisted(() => {
  const existingAsset = { id: 'asset-old', filename: 'old.png', storagePath: 'uploads/assets/old.png', width: 64, height: 48, sizeBytes: 1, tags: [], createdAt: '2026-01-01T00:00:00Z' }
  const addedAsset = { ...existingAsset, id: 'asset-new', filename: 'new.png' }
  const state = { assets: [existingAsset], existingAsset, addedAsset }
  const api = {
  assets: vi.fn(() => Promise.resolve({ data: state.assets })),
  dataset: vi.fn(() => Promise.resolve({ data: { id: 'dataset-1', name: 'Roads', task: 'detect', categories: [{ id: 'car', name: 'car', color: '#000' }] } })),
  uploadAssets: vi.fn(() => { state.assets = [state.addedAsset, ...state.assets]; return Promise.resolve({ data: [state.addedAsset], duplicates: [] as string[] }) }),
  getAnnotation: vi.fn(() => Promise.resolve({ data: null })),
  saveAnnotation: vi.fn(),
  models: vi.fn(() => Promise.resolve({ data: [], pretrained: [] })),
  createPrelabel: vi.fn(),
  }
  return { api, state }
})

vi.mock('../lib/api', () => ({ api }))
vi.mock('../components/AnnotationCanvas', () => ({ AnnotationCanvas: () => <div>标注画布</div> }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/datasets/dataset-1/annotate']}><Routes><Route path="/datasets/:datasetId/annotate" element={<AnnotationPage />} /></Routes></MemoryRouter></QueryClientProvider>)
}

describe('AnnotationPage', () => {
  beforeEach(() => {
    cleanup()
    state.assets = [state.existingAsset]
    api.assets.mockClear(); api.dataset.mockClear(); api.uploadAssets.mockClear(); api.getAnnotation.mockClear()
  })

  it('uploads a material into the current dataset and selects the first uploaded asset', async () => {
    renderPage()
    await screen.findByText('old.png')
    const upload = screen.getByLabelText('添加素材')
    fireEvent.change(upload, { target: { files: [new File(['image'], 'new.png', { type: 'image/png' })] } })

    await waitFor(() => expect(api.uploadAssets).toHaveBeenCalledWith('dataset-1', expect.anything()))
    await screen.findByText('new.png')
    await waitFor(() => expect(document.querySelector('.annotation-list .selected')?.textContent).toContain('new.png'))
  })

  it('keeps the current material selected when upload returns only duplicates', async () => {
    api.uploadAssets.mockImplementationOnce(() => Promise.resolve({ data: [], duplicates: ['new.png'] }))
    renderPage()
    await screen.findByText('old.png')
    fireEvent.change(screen.getByLabelText('添加素材'), { target: { files: [new File(['image'], 'new.png', { type: 'image/png' })] } })

    await waitFor(() => expect(api.uploadAssets).toHaveBeenCalled())
    expect(document.querySelector('.annotation-list .selected')?.textContent).toContain('old.png')
  })

  it('keeps the current material selected when upload fails', async () => {
    api.uploadAssets.mockImplementationOnce(() => Promise.reject(new Error('upload failed')))
    renderPage()
    await screen.findByText('old.png')
    fireEvent.change(screen.getByLabelText('添加素材'), { target: { files: [new File(['image'], 'new.png', { type: 'image/png' })] } })

    await waitFor(() => expect(api.uploadAssets).toHaveBeenCalled())
    expect(document.querySelector('.annotation-list .selected')?.textContent).toContain('old.png')
  })
})
