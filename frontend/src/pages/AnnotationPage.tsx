import { useMutation, useQuery } from '@tanstack/react-query'
import { Save, WandSparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { AnnotationCanvas, type Shape } from '../components/AnnotationCanvas'
import { EmptyState, ErrorState } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { api, type TaskType } from '../lib/api'

const tasks: Array<{ value: TaskType; label: string }> = [
  { value: 'detect', label: '目标检测' }, { value: 'segment', label: '实例分割' },
  { value: 'semantic', label: '语义分割' }, { value: 'pose', label: '姿态估计' }, { value: 'obb', label: 'OBB' },
]
const pretrained: Record<TaskType, string> = { detect: 'yolo26n.pt', segment: 'yolo26n-seg.pt', semantic: 'yolo26n-sem.pt', pose: 'yolo26n-pose.pt', obb: 'yolo26n-obb.pt' }

export function AnnotationPage() {
  const assets = useQuery({ queryKey: ['assets'], queryFn: api.assets })
  const [selectedId, setSelectedId] = useState(''); const [task, setTask] = useState<TaskType>('detect')
  const [shapes, setShapes] = useState<Shape[]>([]); const [labelId, setLabelId] = useState('object'); const [status, setStatus] = useState('DRAFT')
  const selected = assets.data?.data.find((asset) => asset.id === selectedId) ?? assets.data?.data[0]
  useEffect(() => { if (selected && !selectedId) setSelectedId(selected.id) }, [selected, selectedId])
  useEffect(() => {
    if (!selected) return
    api.getAnnotation(selected.id).then((document) => {
      if (document.task === task) { setShapes(document.shapes as Shape[] ?? []); setStatus(document.status as string ?? 'DRAFT') }
      else setShapes([])
    }).catch(() => setShapes([]))
  }, [selected?.id, task])
  const save = useMutation({ mutationFn: () => api.saveAnnotation(selected!.id, {
    assetId: selected!.id, task, imageWidth: selected!.width, imageHeight: selected!.height, status, shapes,
  }) })
  const prelabel = useMutation({ mutationFn: () => api.createPrelabel({ modelPath: `models/pretrained/${pretrained[task]}`, task, assetIds: [selected!.id], confidence: 0.25 }) })
  return <><PageHeader title="人工标注" description="五类任务使用同一套版本化标注工作流" actions={<><button className="button secondary" disabled={!selected || prelabel.isPending} onClick={() => prelabel.mutate()}><WandSparkles size={16} />{prelabel.isSuccess ? '预标任务已排队' : '模型预标'}</button><button className="button primary" disabled={!selected || save.isPending} onClick={() => save.mutate()}><Save size={16} />{save.isPending ? '保存中' : '保存标注'}</button></>} />
    {!selected ? <EmptyState title="没有可标注图片" message="请先到素材库导入图片" /> : <div className="annotation-layout">
      <aside className="annotation-list"><h2>素材</h2>{assets.data?.data.map((asset) => <button key={asset.id} className={asset.id === selected.id ? 'selected' : ''} onClick={() => setSelectedId(asset.id)}><img src={`/media/${asset.storagePath.replace('uploads/', '')}`} alt="" /><span>{asset.filename}</span></button>)}</aside>
      <section className="annotation-workspace"><div className="annotation-controls"><label>任务<select value={task} onChange={(event) => setTask(event.target.value as TaskType)}>{tasks.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>类别 ID<input value={labelId} onChange={(event) => setLabelId(event.target.value)} /></label><label>状态<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="DRAFT">草稿</option><option value="COMPLETED">已完成</option><option value="REVIEWED">已审核</option></select></label><span>{shapes.length} 个标注</span></div><AnnotationCanvas asset={selected} task={task} labelId={labelId} shapes={shapes} onChange={setShapes} />{save.error && <ErrorState message={save.error.message} />}</section>
      <aside className="shape-list"><h2>标注对象</h2>{shapes.map((shape, index) => <div key={shape.id}><span>{index + 1}. {shape.labelId}</span><button onClick={() => setShapes(shapes.filter((item) => item.id !== shape.id))}>删除</button></div>)}</aside>
    </div>}
  </>
}
