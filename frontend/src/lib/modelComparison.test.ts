import { describe, expect, it } from 'vitest'

import { compareMetrics } from './modelComparison'

describe('compareMetrics', () => {
  it('aligns numeric metrics and calculates the second model delta', () => {
    expect(compareMetrics({ map50: '0.41', loss: '1.2' }, { map50: '0.56', loss: '0.9' })).toEqual([
      { key: 'loss', first: 1.2, second: 0.9, delta: -0.3 },
      { key: 'map50', first: 0.41, second: 0.56, delta: 0.15 },
    ])
  })
})
