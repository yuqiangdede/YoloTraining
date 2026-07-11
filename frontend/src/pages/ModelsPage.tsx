import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileOutput, GitCompare, Layers } from 'lucide-react'
import { useState } from 'react'
import { EmptyState } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { api } from '../lib/api'
import { compareMetrics } from '../lib/modelComparison'
import './ModelsPage.css'

export function ModelsPage() {
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs })
  const completed = jobs.data?.data.filter((job) => job.status === 'SUCCEEDED') ?? []
  const models = useQuery({ queryKey: ['models'], queryFn: api.models })
  const client = useQueryClient()
  const exportModel = useMutation({ mutationFn: api.createExport, onSuccess: () => client.invalidateQueries({ queryKey: ['models'] }) })
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const selectedModels = models.data?.data.filter((model) => selectedIds.includes(model.id)) ?? []
  const comparison = selectedModels.length === 2 ? compareMetrics(selectedModels[0].metrics, selectedModels[1].metrics) : []
  const toggleSelected = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 2 ? [...current, id] : [current[1], id])
  return <><PageHeader title="模型结果" description="管理训练权重、指标和 ONNX 导出" />
    <section className="panel"><div className="panel-heading"><div><h2>训练产物</h2><p>勾选两个模型即可比较最终指标。</p></div><span className="badge">已选 {selectedIds.length}/2</span></div>{models.data?.data.length ? <div className="model-grid">{models.data.data.map((model) => <article className={`model-card ${selectedIds.includes(model.id) ? 'selected-model' : ''}`} key={model.id}><label className="model-select"><input type="checkbox" checked={selectedIds.includes(model.id)} onChange={() => toggleSelected(model.id)} />用于对比</label><div className="model-icon"><Layers size={22} /></div><div><span className="badge succeeded">{model.task}</span><h2>{model.name}</h2><p>{model.path}</p></div><dl>{Object.entries(model.metrics).slice(0, 3).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl><div className="row-actions"><a className="button secondary" href={`/api/v1/models/${model.id}/download`}><Download size={16} />下载 PT</a><button className="button secondary" disabled={exportModel.isPending} onClick={() => exportModel.mutate(model.id)}><FileOutput size={16} />{exportModel.isSuccess ? '导出已排队' : '导出 ONNX'}</button></div></article>)}</div> : <EmptyState title="还没有训练产物" message="成功完成训练后，权重和指标会出现在这里" />}</section>
    {comparison.length > 0 && <section className="panel"><div className="panel-heading"><div><h2><GitCompare size={18} />实验对比</h2><p>{selectedModels[0].name} 与 {selectedModels[1].name}</p></div></div><div className="table"><div className="table-head"><span>指标</span><span>模型 A</span><span>模型 B</span><span>差值 (B - A)</span></div>{comparison.map((metric) => <div className="table-row" key={metric.key}><code>{metric.key}</code><span>{metric.first ?? '—'}</span><span>{metric.second ?? '—'}</span><strong className={metric.delta !== null && metric.delta >= 0 ? 'metric-up' : 'metric-down'}>{metric.delta === null ? '—' : `${metric.delta >= 0 ? '+' : ''}${metric.delta}`}</strong></div>)}</div></section>}
    <section className="panel"><div className="panel-heading"><div><h2>官方预训练模型</h2><p>项目内可直接用于微调的 YOLO26 权重</p></div></div><div className="table"><div className="table-head"><span>文件</span><span>大小</span><span>路径</span><span>状态</span></div>{models.data?.pretrained.map((model) => <div className="table-row" key={model.path}><strong><Layers size={16} />{model.name}</strong><span>{(model.sizeBytes / 1024 / 1024).toFixed(1)} MB</span><code>{model.path}</code><span className="badge succeeded">就绪</span></div>)}</div></section>
    {completed.length > 0 && <section className="panel"><div className="panel-heading"><div><h2>实验记录</h2><p>{completed.length} 次成功训练，可按数据集和参数追溯</p></div></div></section>}
  </>
}
