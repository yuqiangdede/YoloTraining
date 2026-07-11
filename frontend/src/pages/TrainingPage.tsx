import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, Plus, Square } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { AugmentationPreview } from '../components/AugmentationPreview'
import { api } from '../lib/api'

const numericFields = [
  ['epochs', '训练轮次', 100], ['imgsz', '图像尺寸', 640], ['batch', '批量', 8], ['workers', '加载线程', 4],
  ['patience', '早停耐心', 100], ['lr0', '初始学习率', 0.01], ['lrf', '最终学习率比例', 0.01], ['momentum', '动量', 0.937],
  ['weightDecay', '权重衰减', 0.0005], ['warmupEpochs', '预热轮次', 3], ['degrees', '旋转角度', 0], ['translate', '平移', 0.1],
  ['scale', '缩放', 0.5], ['shear', '剪切', 0], ['flipud', '上下翻转', 0], ['fliplr', '左右翻转', 0.5],
  ['hsvH', '色相', 0.015], ['hsvS', '饱和度', 0.7], ['hsvV', '亮度', 0.4], ['mosaic', 'Mosaic', 1],
]

export function TrainingPage() {
  const client = useQueryClient(); const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets }); const assets = useQuery({ queryKey: ['assets'], queryFn: api.assets }); const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs, refetchInterval: 2000 })
  const [form, setForm] = useState<Record<string, string | number | boolean>>({ name: 'train-yolo26n', datasetVersionId: '', modelPath: 'models/pretrained/yolo26n.pt', device: '0', optimizer: 'auto', amp: true, deterministic: true, ...Object.fromEntries(numericFields.map(([key, , value]) => [key, value])) })
  const selectedDataset = datasets.data?.data.find((item) => item.id === form.datasetVersionId) ?? datasets.data?.data[0]
  const create = useMutation({ mutationFn: () => api.createJob({ ...form, datasetVersionId: selectedDataset?.id, task: selectedDataset?.task }), onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }) })
  const action = useMutation({ mutationFn: ({ id, action }: { id: string; action: 'pause' | 'resume' | 'cancel' }) => api.jobAction(id, action), onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }) })
  const update = (key: string, value: string | number | boolean) => setForm((current) => ({ ...current, [key]: value }))
  return <><PageHeader title="训练任务" description="全部参数显式可见，单 GPU 任务串行排队" actions={<button className="button primary" disabled={!selectedDataset || create.isPending} onClick={() => create.mutate()}><Plus size={16} />加入训练队列</button>} />
    <section className="panel training-form"><div className="panel-heading"><div><h2>新建训练</h2><p>参数在创建时随数据集快照一同固化</p></div></div><div className="form-grid"><label>任务名称<input value={form.name as string} onChange={(e) => update('name', e.target.value)} /></label><label>数据集版本<select value={selectedDataset?.id ?? ''} onChange={(e) => update('datasetVersionId', e.target.value)}>{datasets.data?.data.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.task}</option>)}</select></label><label>项目内模型路径<input value={form.modelPath as string} onChange={(e) => update('modelPath', e.target.value)} /></label><label>设备<input value={form.device as string} onChange={(e) => update('device', e.target.value)} /></label>{numericFields.map(([key, label]) => <label key={key as string}>{label}<input type="number" step="any" value={form[key as string] as number} onChange={(e) => update(key as string, Number(e.target.value))} /></label>)}<label>优化器<select value={form.optimizer as string} onChange={(e) => update('optimizer', e.target.value)}><option>auto</option><option>MuSGD</option><option>SGD</option><option>AdamW</option></select></label><label className="check"><input type="checkbox" checked={form.amp as boolean} onChange={(e) => update('amp', e.target.checked)} />AMP 混合精度</label><label className="check"><input type="checkbox" checked={form.deterministic as boolean} onChange={(e) => update('deterministic', e.target.checked)} />确定性训练</label></div>{create.error && <ErrorState message={create.error.message} />}</section>
    {assets.data?.data[0] && <AugmentationPreview imageUrl={`/media/${assets.data.data[0].storagePath.replace('uploads/', '')}`} degrees={Number(form.degrees)} scale={Number(form.scale)} fliplr={Number(form.fliplr)} flipud={Number(form.flipud)} />}
    <section className="panel"><div className="panel-heading"><div><h2>任务队列</h2><p>安全暂停会等待当前 epoch 保存 checkpoint</p></div></div>{jobs.data?.data.length ? jobs.data.data.map((job) => <div className="job-row" key={job.id}><div><strong>{job.name}</strong><span>{job.task} · Epoch {job.currentEpoch}</span></div><div className="progress"><i style={{ width: `${job.progress}%` }} /></div><span className={`badge ${job.status.toLowerCase()}`}>{job.status}</span><div className="row-actions">{job.status === 'RUNNING' && <button aria-label="暂停" onClick={() => action.mutate({ id: job.id, action: 'pause' })}><Pause size={15} /></button>}{job.status === 'PAUSED' && <button aria-label="恢复" onClick={() => action.mutate({ id: job.id, action: 'resume' })}><Play size={15} /></button>}{!['SUCCEEDED', 'CANCELLED'].includes(job.status) && <button aria-label="取消" onClick={() => action.mutate({ id: job.id, action: 'cancel' })}><Square size={15} /></button>}</div></div>) : <EmptyState title="训练队列为空" message="选择数据集和项目内预训练模型后创建任务" />}</section>
  </>
}
