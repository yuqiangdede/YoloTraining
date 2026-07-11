export interface MetricDelta {
  key: string
  first: number | null
  second: number | null
  delta: number | null
}

export function compareMetrics(first: Record<string, string | number>, second: Record<string, string | number>): MetricDelta[] {
  const keys = [...new Set([...Object.keys(first), ...Object.keys(second)])].sort()
  return keys.map((key) => {
    const left = Number(first[key]); const right = Number(second[key])
    const validLeft = Number.isFinite(left); const validRight = Number.isFinite(right)
    return {
      key,
      first: validLeft ? left : null,
      second: validRight ? right : null,
      delta: validLeft && validRight ? Number((right - left).toFixed(6)) : null,
    }
  })
}
