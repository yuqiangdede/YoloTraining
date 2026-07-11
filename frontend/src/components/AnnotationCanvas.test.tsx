import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AnnotationCanvas } from './AnnotationCanvas'

const asset = {
  id: 'asset-1', filename: 'image.png', storagePath: 'uploads/assets/image.png',
  width: 100, height: 100, sizeBytes: 10, tags: [], createdAt: '2026-01-01T00:00:00Z',
}

describe('AnnotationCanvas', () => {
  it('offers a semantic brush that commits a freehand region as a polygon', () => {
    const onChange = vi.fn()
    render(<AnnotationCanvas asset={asset} task="semantic" labelId="road" shapes={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: '画笔' }))
    expect(screen.getByText('按住拖动画笔绘制区域')).toBeInTheDocument()
  })
})
