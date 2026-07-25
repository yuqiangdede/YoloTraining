import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DatasetsPage } from './DatasetsPage'

const { api } = vi.hoisted(() => ({ api: {
  datasets: vi.fn(),
  createDataset: vi.fn(),
  importVoc: vi.fn(),
} }))

vi.mock('../lib/api', () => ({ api }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><DatasetsPage /></MemoryRouter></QueryClientProvider>)
}

describe('DatasetsPage', () => {
  beforeEach(() => {
    cleanup()
    api.datasets.mockResolvedValue({ data: [] })
    api.createDataset.mockResolvedValue({ data: { id: 'dataset-1' } })
    api.importVoc.mockResolvedValue({ data: {
      dataset: { id: 'dataset-imported' },
      version: { id: 'version-1' },
      report: { importedImages: 4, split: { train: 3, val: 1 }, repairedXml: 1 },
    } })
  })

  it('adds unique category labels and removes them before creating a dataset', async () => {
    renderPage()
    fireEvent.click((await screen.findAllByRole('button', { name: '新建数据集' }))[0])

    const input = await screen.findByLabelText('类别名称')
    fireEvent.change(input, { target: { value: 'car' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByText('car')).toBeInTheDocument()

    fireEvent.change(input, { target: { value: 'CAR' } })
    fireEvent.click(screen.getByRole('button', { name: '添加类别' }))
    expect(screen.getAllByText('car')).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: '删除类别 car' }))
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'roads' } })
    fireEvent.click(screen.getByRole('button', { name: '创建数据集' }))
    expect(api.createDataset).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: 'car' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'roads' } })
    fireEvent.click(screen.getByRole('button', { name: '创建数据集' }))
    await waitFor(() => expect(api.createDataset).toHaveBeenCalledWith({ name: 'roads', task: 'detect', categories: [{ name: 'car' }] }))
  })

  it('includes keypoint count when creating a pose dataset', async () => {
    renderPage()
    fireEvent.click((await screen.findAllByRole('button', { name: '新建数据集' }))[0])
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'people' } })
    fireEvent.change(screen.getAllByLabelText('任务')[0], { target: { value: 'pose' } })
    const categoryInput = screen.getByLabelText('类别名称')
    fireEvent.change(categoryInput, { target: { value: 'person' } })
    fireEvent.keyDown(categoryInput, { key: 'Enter' })
    fireEvent.click(screen.getByRole('button', { name: '创建数据集' }))

    await waitFor(() => expect(api.createDataset).toHaveBeenCalledWith(expect.objectContaining({ task: 'pose', keypointCount: 17, categories: [{ name: 'person' }] })))
  })

  it('imports a VOC folder with editable split settings and opens the workspace', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: '导入 VOC 数据集' }))
    fireEvent.change(screen.getByLabelText('VOC 数据集目录'), { target: { value: 'H:\\BaiduNetdiskDownload\\SeaShips(7000)' } })
    fireEvent.change(screen.getByLabelText('训练集比例'), { target: { value: '0.75' } })
    fireEvent.change(screen.getByLabelText('验证集比例'), { target: { value: '0.25' } })
    fireEvent.change(screen.getByLabelText('随机种子'), { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: '开始一键导入' }))

    await waitFor(() => expect(api.importVoc).toHaveBeenCalledWith({
      sourcePath: 'H:\\BaiduNetdiskDownload\\SeaShips(7000)', name: 'SeaShips(7000)', trainRatio: 0.75, valRatio: 0.25, seed: 7,
    }))
  })
})
