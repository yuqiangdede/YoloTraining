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

export interface AnnotationCategory { id: string; name: string; color: string }

const kindByTask: Record<TaskType, Shape['kind']> = {
  detect: 'rectangle', segment: 'polygon', semantic: 'polygon', pose: 'keypoints', obb: 'obb',
}

export function AnnotationCanvas({ asset, task, labelId, categories = [], shapes, onChange, selectedShapeId, onSelectShape }: {
  asset: Asset; task: TaskType; labelId: string; categories?: AnnotationCategory[]; shapes: Shape[]; onChange: (shapes: Shape[]) => void; selectedShapeId?: string; onSelectShape?: (id: string | undefined) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [draft, setDraft] = useState<number[][]>([])
  const draftRef = useRef<number[][]>([])
  const [semanticTool, setSemanticTool] = useState<'polygon' | 'brush'>('polygon')
  const [history, setHistory] = useState<Shape[][]>([shapes])
  const [historyIndex, setHistoryIndex] = useState(0)
  const [internalSelected, setInternalSelected] = useState<string | undefined>()
  const dragRef = useRef<{ id: string; corner?: number; start: number[]; points: number[][] } | undefined>(undefined)
  const canvasWidth = asset.width > 0 && asset.height > 0 ? (asset.width / asset.height) * 100 : 100
  const activeShapeId = selectedShapeId ?? internalSelected
  const selectShape = (id: string | undefined) => { setInternalSelected(id); onSelectShape?.(id) }

  useEffect(() => { draftRef.current = []; setDraft([]); setHistory([shapes]); setHistoryIndex(0); setSemanticTool('polygon') }, [asset.id, task])

  const point = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current!.getBoundingClientRect()
    const scale = Math.min(rect.width / canvasWidth, rect.height / 100)
    const width = canvasWidth * scale
    const height = 100 * scale
    const left = rect.left + (rect.width - width) / 2
    const top = rect.top + (rect.height - height) / 2
    return [Math.max(0, Math.min(1, (event.clientX - left) / width)), Math.max(0, Math.min(1, (event.clientY - top) / height))]
  }, [canvasWidth])

  const commit = (next: Shape[]) => {
    const nextHistory = [...history.slice(0, historyIndex + 1), next]
    setHistory(nextHistory); setHistoryIndex(nextHistory.length - 1); onChange(next)
  }

  const replaceDraft = (next: number[][]) => { draftRef.current = next; setDraft(next) }

  const finishDraft = () => {
    const points = draftRef.current
    const minimum = task === 'pose' ? 1 : 3
    if (points.length < minimum) return
    const shape: Shape = {
      id: crypto.randomUUID(), labelId, kind: kindByTask[task], points,
      visibility: task === 'pose' ? points.map(() => 2) : undefined,
    }
    commit([...shapes, shape]); replaceDraft([])
  }

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    const nextPoint = point(event)
    if (task === 'detect' || task === 'obb' || (task === 'semantic' && semanticTool === 'brush')) {
      replaceDraft([nextPoint]); svgRef.current?.setPointerCapture?.(event.pointerId)
    } else replaceDraft([...draftRef.current, nextPoint])
  }

  const startRectangleEdit = (event: React.PointerEvent<SVGElement>, shape: Shape, corner?: number) => {
    event.stopPropagation(); selectShape(shape.id)
    dragRef.current = { id: shape.id, corner, start: point(event as unknown as React.PointerEvent<SVGSVGElement>), points: shape.points.map((item) => [...item]) }
    svgRef.current?.setPointerCapture?.(event.pointerId)
  }

  const editRectangle = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag) return false
    const [x, y] = point(event); const [[x1, y1], [x2, y2]] = drag.points
    let next: number[][]
    if (drag.corner === undefined) {
      const dx = x - drag.start[0]; const dy = y - drag.start[1]
      const left = Math.max(0, Math.min(1 - Math.abs(x2 - x1), Math.min(x1, x2) + dx)); const top = Math.max(0, Math.min(1 - Math.abs(y2 - y1), Math.min(y1, y2) + dy))
      next = [[left, top], [left + Math.abs(x2 - x1), top + Math.abs(y2 - y1)]]
    } else {
      const fixed = [[x2, y2], [x1, y2], [x2, y1], [x1, y1]][drag.corner]
      const min = .005; const nx = Math.max(0, Math.min(1, x)); const ny = Math.max(0, Math.min(1, y))
      next = [[Math.min(nx, fixed[0] - min), Math.min(ny, fixed[1] - min)], [Math.max(nx, fixed[0] + min), Math.max(ny, fixed[1] + min)]]
    }
    onChange(shapes.map((shape) => shape.id === drag.id ? { ...shape, points: next } : shape))
    return true
  }

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (editRectangle(event)) return
    if ((task === 'detect' || task === 'obb') && draftRef.current.length) replaceDraft([draftRef.current[0], point(event)])
    if (task === 'semantic' && semanticTool === 'brush' && draftRef.current.length) {
      const next = point(event); const previous = draftRef.current.at(-1)!
      if (Math.hypot(next[0] - previous[0], next[1] - previous[1]) > 0.004) replaceDraft([...draftRef.current, next])
    }
  }

  const onPointerUp = () => {
    if (dragRef.current) { dragRef.current = undefined; return }
    if ((task === 'detect' || task === 'obb') && draftRef.current.length === 2) {
      const shape: Shape = { id: crypto.randomUUID(), labelId, kind: kindByTask[task], points: draftRef.current, rotation: task === 'obb' ? 0 : undefined }
      commit([...shapes, shape]); replaceDraft([])
    }
    if (task === 'semantic' && semanticTool === 'brush') finishDraft()
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
      if (event.key === 'Escape') { replaceDraft([]); selectShape(undefined) }
      if ((event.key === 'Delete' || event.key === 'Backspace') && activeShapeId) {
        event.preventDefault(); commit(shapes.filter((shape) => shape.id !== activeShapeId)); selectShape(undefined)
      }
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  })

  const renderShape = (shape: Shape, index: number) => {
    const coordinates = shape.points.map(([x, y]) => `${x * canvasWidth},${y * 100}`).join(' ')
    if (shape.kind === 'rectangle' || shape.kind === 'obb') {
      const [[x1, y1], [x2, y2]] = shape.points
      const x = Math.min(x1, x2) * canvasWidth; const y = Math.min(y1, y2) * 100
      const width = Math.abs(x2 - x1) * canvasWidth; const height = Math.abs(y2 - y1) * 100
      const category = categories.find((item) => item.id === shape.labelId)
      const displayLabel = category?.name ?? '未分类'
      const selected = shape.id === activeShapeId
      return <g key={shape.id} onPointerDown={(event) => startRectangleEdit(event, shape)}>
        <rect x={x} y={y} width={width} height={height} className={`annotation-shape ${selected ? 'selected' : ''}`} stroke={category?.color} transform={shape.kind === 'obb' ? `rotate(${shape.rotation ?? 0} ${(x1+x2)*canvasWidth / 2} ${(y1+y2)*50})` : undefined} />
        <rect x={x} y={Math.max(0, y - 4)} width={Math.max(width, 12)} height="3.5" fill={category?.color ?? '#e36a22'} className="annotation-label-bg" /><text x={x + .7} y={Math.max(0, y - 1.3)} className="annotation-label">{displayLabel}</text>
        {selected && [[x, y], [x + width, y], [x, y + height], [x + width, y + height]].map(([cx, cy], handleIndex) => <circle key={handleIndex} onPointerDown={(event) => startRectangleEdit(event, shape, handleIndex)} cx={cx} cy={cy} r="1.25" className="annotation-handle" fill={category?.color ?? '#e36a22'} />)}
      </g>
    }
    if (shape.kind === 'keypoints') return <g key={shape.id}>{shape.points.map(([x, y], pointIndex) => <circle key={pointIndex} cx={x * canvasWidth} cy={y * 100} r="1.2" className="annotation-point" />)}</g>
    return <polygon key={`${shape.id}-${index}`} points={coordinates} className="annotation-shape polygon" />
  }

  return <div className="annotation-canvas-wrap">
    <div className="canvas-toolbar">
      <button className="button ghost" onClick={undo} disabled={!historyIndex}>撤销</button>
      <button className="button ghost" onClick={redo} disabled={historyIndex >= history.length - 1}>重做</button>
      {task === 'semantic' && <><button className={`button ghost ${semanticTool === 'polygon' ? 'active-tool' : ''}`} onClick={() => setSemanticTool('polygon')}>多边形</button><button className={`button ghost ${semanticTool === 'brush' ? 'active-tool' : ''}`} onClick={() => setSemanticTool('brush')}>画笔</button></>}
      {(task === 'segment' || task === 'semantic' || task === 'pose') && <button className="button secondary" onClick={finishDraft}>完成当前形状</button>}
      <span>{task === 'detect' || task === 'obb' ? '按住拖动绘制' : task === 'semantic' && semanticTool === 'brush' ? '按住拖动画笔绘制区域' : '逐点单击，Enter 完成'}</span>
    </div>
    <svg ref={svgRef} className="annotation-canvas" viewBox={`0 0 ${canvasWidth} 100`} preserveAspectRatio="xMidYMid meet" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onDoubleClick={finishDraft} aria-label="标注画布">
      <image href={`/media/${asset.storagePath.replace('uploads/', '')}`} x="0" y="0" width={canvasWidth} height="100" preserveAspectRatio="xMidYMid meet" />
      {shapes.map(renderShape)}
      {draft.length > 1 && <polyline points={draft.map(([x, y]) => `${x * canvasWidth},${y * 100}`).join(' ')} className="annotation-draft" />}
      {draft.map(([x, y], index) => <circle key={index} cx={x * canvasWidth} cy={y * 100} r=".8" className="annotation-point draft" />)}
    </svg>
  </div>
}
