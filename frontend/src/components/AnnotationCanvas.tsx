import { useCallback, useEffect, useRef, useState } from 'react'
import type { Asset, TaskType } from '../lib/api'

export interface Shape {
  id: string
  labelId: string
  kind: 'rectangle' | 'polygon' | 'mask' | 'keypoints' | 'obb'
  points: number[][]
  rotation?: number
  visibility?: number[]
  maskPath?: string
}

const kindByTask: Record<TaskType, Shape['kind']> = {
  detect: 'rectangle', segment: 'polygon', semantic: 'polygon', pose: 'keypoints', obb: 'obb',
}

export function AnnotationCanvas({ asset, task, labelId, shapes, onChange }: {
  asset: Asset; task: TaskType; labelId: string; shapes: Shape[]; onChange: (shapes: Shape[]) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [draft, setDraft] = useState<number[][]>([])
  const [history, setHistory] = useState<Shape[][]>([shapes])
  const [historyIndex, setHistoryIndex] = useState(0)

  useEffect(() => { setDraft([]); setHistory([shapes]); setHistoryIndex(0) }, [asset.id, task])

  const point = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current!.getBoundingClientRect()
    return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))]
  }, [])

  const commit = (next: Shape[]) => {
    const nextHistory = [...history.slice(0, historyIndex + 1), next]
    setHistory(nextHistory); setHistoryIndex(nextHistory.length - 1); onChange(next)
  }

  const finishDraft = () => {
    const minimum = task === 'pose' ? 1 : 3
    if (draft.length < minimum) return
    const shape: Shape = {
      id: crypto.randomUUID(), labelId, kind: kindByTask[task], points: draft,
      visibility: task === 'pose' ? draft.map(() => 2) : undefined,
    }
    commit([...shapes, shape]); setDraft([])
  }

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    const nextPoint = point(event)
    if (task === 'detect' || task === 'obb') {
      setDraft([nextPoint]); svgRef.current?.setPointerCapture(event.pointerId)
    } else setDraft((current) => [...current, nextPoint])
  }

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if ((task === 'detect' || task === 'obb') && draft.length) setDraft([draft[0], point(event)])
  }

  const onPointerUp = () => {
    if ((task === 'detect' || task === 'obb') && draft.length === 2) {
      const shape: Shape = { id: crypto.randomUUID(), labelId, kind: kindByTask[task], points: draft, rotation: task === 'obb' ? 0 : undefined }
      commit([...shapes, shape]); setDraft([])
    }
  }

  const undo = () => {
    if (historyIndex === 0) return
    const index = historyIndex - 1; setHistoryIndex(index); onChange(history[index])
  }
  const redo = () => {
    if (historyIndex >= history.length - 1) return
    const index = historyIndex + 1; setHistoryIndex(index); onChange(history[index])
  }

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key.toLowerCase() === 'z') { event.preventDefault(); undo() }
      if (event.ctrlKey && event.key.toLowerCase() === 'y') { event.preventDefault(); redo() }
      if (event.key === 'Enter') finishDraft()
      if (event.key === 'Escape') setDraft([])
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  })

  const renderShape = (shape: Shape, index: number) => {
    const coordinates = shape.points.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')
    if (shape.kind === 'rectangle' || shape.kind === 'obb') {
      const [[x1, y1], [x2, y2]] = shape.points
      return <rect key={shape.id} x={Math.min(x1, x2) * 100} y={Math.min(y1, y2) * 100} width={Math.abs(x2 - x1) * 100} height={Math.abs(y2 - y1) * 100} className="annotation-shape" transform={shape.kind === 'obb' ? `rotate(${shape.rotation ?? 0} ${(x1+x2)*50} ${(y1+y2)*50})` : undefined} />
    }
    if (shape.kind === 'keypoints') return <g key={shape.id}>{shape.points.map(([x, y], pointIndex) => <circle key={pointIndex} cx={x * 100} cy={y * 100} r="1.2" className="annotation-point" />)}</g>
    return <polygon key={`${shape.id}-${index}`} points={coordinates} className="annotation-shape polygon" />
  }

  return <div className="annotation-canvas-wrap">
    <div className="canvas-toolbar">
      <button className="button ghost" onClick={undo} disabled={!historyIndex}>撤销</button>
      <button className="button ghost" onClick={redo} disabled={historyIndex >= history.length - 1}>重做</button>
      {(task === 'segment' || task === 'semantic' || task === 'pose') && <button className="button secondary" onClick={finishDraft}>完成当前形状</button>}
      <span>{task === 'detect' || task === 'obb' ? '按住拖动绘制' : '逐点单击，Enter 完成'}</span>
    </div>
    <svg ref={svgRef} className="annotation-canvas" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onDoubleClick={finishDraft} aria-label="标注画布">
      <image href={`/media/${asset.storagePath.replace('uploads/', '')}`} x="0" y="0" width="100" height="100" preserveAspectRatio="xMidYMid meet" />
      {shapes.map(renderShape)}
      {draft.length > 1 && <polyline points={draft.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')} className="annotation-draft" />}
      {draft.map(([x, y], index) => <circle key={index} cx={x * 100} cy={y * 100} r=".8" className="annotation-point draft" />)}
    </svg>
  </div>
}
