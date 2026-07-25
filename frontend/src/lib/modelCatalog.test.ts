import { describe, expect, it } from 'vitest'
import { modelPathFor } from './modelCatalog'

describe('model catalog', () => {
  it('builds task-specific paths for the selected training size', () => {
    expect(modelPathFor('detect', 'm')).toBe('models/pretrained/yolo26m.pt')
    expect(modelPathFor('segment', 'm')).toBe('models/pretrained/yolo26m-seg.pt')
  })
})
