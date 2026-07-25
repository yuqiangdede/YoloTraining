import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AnnotationCanvas } from './AnnotationCanvas'

const asset = {
  id: 'asset-1', filename: 'image.png', storagePath: 'uploads/assets/image.png',
  width: 100, height: 100, sizeBytes: 10, tags: [], annotationStatus: 'UNLABELED' as const, createdAt: '2026-01-01T00:00:00Z',
}

describe('AnnotationCanvas', () => {
  it('shows the category name instead of a long internal label ID', () => {
    const onChange = vi.fn()
    const internalLabelId = 'b81e2b6c-4f83-46d4-a0cb-5fbc1d7c91c3'
    render(<AnnotationCanvas asset={asset} task="detect" labelId={internalLabelId} categories={[{ id: internalLabelId, name: 'car', color: '#e36a22' }]} shapes={[{ id: 'box-1', labelId: internalLabelId, kind: 'rectangle', points: [[0.1, 0.1], [0.6, 0.6]] }]} onChange={onChange} />)

    fireEvent.pointerDown(document.querySelector('.annotation-shape')!, { clientX: 20, clientY: 20 })

    expect(screen.getByText('car')).toBeInTheDocument()
    expect(screen.queryByText(internalLabelId)).not.toBeInTheDocument()
    expect(document.querySelectorAll('.annotation-handle')).toHaveLength(4)
  })

  it('shows 未分类 instead of an unmatched internal label ID', () => {
    const onChange = vi.fn()
    const internalLabelId = '9ee5c09a-51b0-44e7-9fb8-673604bdb570'
    render(<AnnotationCanvas asset={asset} task="obb" labelId={internalLabelId} categories={[]} shapes={[{ id: 'obb-1', labelId: internalLabelId, kind: 'obb', points: [[0.1, 0.1], [0.6, 0.6]], rotation: 0 }]} onChange={onChange} />)

    expect(screen.getByText('未分类')).toBeInTheDocument()
    expect(screen.queryByText(internalLabelId)).not.toBeInTheDocument()
  })

  it('maps pointer coordinates to the displayed image rather than SVG letterboxing', () => {
    const onChange = vi.fn()
    render(<AnnotationCanvas asset={asset} task="pose" labelId="point" shapes={[]} onChange={onChange} />)
    const canvas = document.querySelector<SVGSVGElement>('.annotation-canvas')!
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 500, width: 1000, height: 500,
      toJSON: () => ({}),
    })

    const pointerDown = new Event('pointerdown', { bubbles: true })
    Object.defineProperties(pointerDown, { clientX: { value: 300 }, clientY: { value: 250 } })
    fireEvent(canvas, pointerDown)

    expect(canvas.querySelector('.annotation-point')).toHaveAttribute('cx', '10')
    expect(canvas.querySelector('.annotation-point')).toHaveAttribute('cy', '50')
  })

  it('offers a semantic brush that commits a freehand region as a polygon', () => {
    const onChange = vi.fn()
    render(<AnnotationCanvas asset={asset} task="semantic" labelId="road" shapes={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: '画笔' }))
    expect(screen.getByText('按住拖动画笔绘制区域')).toBeInTheDocument()
  })
})
