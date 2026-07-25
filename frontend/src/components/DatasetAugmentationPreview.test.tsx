import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DatasetAugmentationPreview } from './DatasetAugmentationPreview'

const assets = [
  { id: 'asset-1', filename: 'one.jpg', storagePath: 'uploads/assets/one.jpg', width: 100, height: 80, sizeBytes: 1, tags: [], annotationStatus: 'REVIEWED' as const, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'asset-2', filename: 'two.jpg', storagePath: 'uploads/assets/two.jpg', width: 100, height: 80, sizeBytes: 1, tags: [], annotationStatus: 'REVIEWED' as const, createdAt: '2026-01-01T00:00:00Z' },
]

describe('DatasetAugmentationPreview', () => {
  it('shows representative augmentation examples and switches source material', () => {
    render(<DatasetAugmentationPreview assets={assets} />)

    const heading = screen.getByRole('heading', { name: '素材增强预览' })
    expect(heading).toBeInTheDocument()
    expect(heading.closest('details')).not.toHaveAttribute('open')

    fireEvent.click(heading)
    expect(screen.getByText('黑白')).toBeInTheDocument()
    expect(screen.getByText('Mosaic')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('combobox', { name: '选择预览素材' }), { target: { value: 'asset-2' } })
    expect(screen.getByAltText('two.jpg 黑白预览')).toBeInTheDocument()
  })
})
