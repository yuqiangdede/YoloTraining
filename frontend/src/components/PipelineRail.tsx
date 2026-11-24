import { useLocation } from 'react-router-dom'

const stages = ['项目', '数据集', '标注', '训练', '模型', '验证'] as const

function stageIndex(pathname: string): number {
  if (pathname === '/' || pathname === '/system') return -1
  if (pathname.startsWith('/projects')) return 0
  if (/^\/datasets\/[^/]+\/(annotate|analysis)/.test(pathname)) return 2
  if (pathname.startsWith('/datasets')) return 1
  if (pathname.startsWith('/training')) return 3
  if (pathname.startsWith('/models/test')) return 5
  if (pathname.startsWith('/models')) return 4
  return -1
}

export function PipelineRail() {
  const { pathname } = useLocation()
  const current = stageIndex(pathname)
  if (current < 0) return null
  return <nav className="pipeline-rail" aria-label="训练流水线">
    <ol>{stages.map((label, index) => {
      const state = index < current ? 'done' : index === current ? 'current' : 'next'
      return <li className={state} key={label}>
        <span className="pipeline-node" aria-hidden="true">{index < current ? '✓' : index + 1}</span>
        <span className="pipeline-label">{label}</span>
      </li>
    })}</ol>
  </nav>
}
