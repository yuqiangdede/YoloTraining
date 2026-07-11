import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AugmentationPreview } from './AugmentationPreview'

describe('AugmentationPreview', () => {
  it('renders the selected geometric augmentation values', () => {
    render(<AugmentationPreview imageUrl="/media/assets/example.png" degrees={15} scale={0.5} fliplr={1} flipud={0} />)
    expect(screen.getByRole('heading', { name: '增强预览' })).toBeInTheDocument()
    expect(screen.getByText('旋转 15° · 缩放 0.50 · 水平翻转')).toBeInTheDocument()
  })
})
