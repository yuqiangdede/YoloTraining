import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, GitCompare, Layers, ScanSearch, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { TrainingEvidence, trainingMetricLabel } from '../components/TrainingEvidence'
import { useToast } from '../components/Toast'
import { api, type ModelArtifact } from '../lib/api'
import { formatBytes, taskLabels } from '../lib/labels'
import { compareMetrics } from '../lib/modelComparison'
import './ModelsPage.css'

const exportStatusLabels: Record<string, string> = {
  QUEUED: '排队中',
  RUNNING: '导出中',
  SUCCEEDED: '已完成',
  FAILED: '失败',
}

export function ModelsPage() {
  const client = useQueryClient()
  const { notify } = useToast()
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs })
  const models = useQuery({ queryKey: ['models'], queryFn: api.models })
  const exports = useQuery({ queryKey: ['exports'], queryFn: api.exports, refetchInterval: 2000 })
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [deleting, setDeleting] = useState<ModelArtifact | null>(null)
  const removeModel = useMutation({
    mutationFn: api.deleteModel,
    onSuccess: (_data, id) => {
      setSelectedIds((current) => current.filter((item) => item !== id))
      setDeleting(null)
      client.invalidateQueries({ queryKey: ['models'] })
      client.invalidateQueries({ queryKey: ['exports'] })
      notify('模型产物及关联导出已删除')
    },
  })
  const selectedModels = models.data?.data.filter((model) => selectedIds.includes(model.id)) ?? []
  const comparison = selectedModels.length === 2 ? compareMetrics(selectedModels[0].metrics, selectedModels[1].metrics) : []
  const toggleSelected = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 2 ? [...current, id] : current)
  const completed = jobs.data?.data.filter((job) => job.status === 'SUCCEEDED') ?? []
  const hasTestable = Boolean(models.data?.data.length || models.data?.pretrained.some((model) => model.canTest))

  return <>
    <PageHeader title="模型结果" description="区分训练产物、官方预训练模型与 ONNX 导出状态" actions={hasTestable ? <Link className="button primary" to="/models/test"><ScanSearch size={16} />单图测试</Link> : undefined} />
    <section className="panel">
      <div className="panel-heading"><div><h2>训练产物</h2><p>每张卡片提供模型测试、训练依据、来源追溯、下载和删除操作。</p></div><span className="badge">已选 {selectedIds.length}/2</span></div>
      {removeModel.error && <ErrorState message={removeModel.error.message} />}
      {models.isPending || exports.isPending ? <LoadingRows /> : models.isError ? <ErrorState message={models.error.message} onRetry={() => models.refetch()} /> : exports.isError ? <ErrorState message={exports.error.message} onRetry={() => exports.refetch()} /> : models.data.data.length ? <div className="model-grid">{models.data.data.map((model) => {
        const exportJob = exports.data.data.find((item) => item.artifactId === model.id)
        const trainingJob = jobs.data?.data.find((job) => job.id === model.trainingJobId)
        const checked = selectedIds.includes(model.id)
        const compareDisabled = !checked && selectedIds.length >= 2
        return <article className={`model-card ${checked ? 'selected-model' : ''}`} key={model.id}>
          <label className="model-select"><input type="checkbox" checked={checked} disabled={compareDisabled} onChange={() => toggleSelected(model.id)} />{compareDisabled ? '对比已选满' : '用于对比'}</label>
          <div className="model-icon"><Layers size={22} /></div>
          <div><span className="status-badge succeeded">训练产物 · {taskLabels[model.task]}</span><h2>{model.name}</h2><p>{model.path}</p></div>
          <dl>{Object.entries(model.metrics).slice(0, 3).map(([key, value]) => <div key={key}><dt>{trainingMetricLabel(key)}</dt><dd>{String(value)}</dd></div>)}</dl>
          <TrainingEvidence params={trainingJob?.params} quality={model.trainingQuality} compact />
          <div className="row-actions">
            <Link className="button primary" to={`/models/test?model=${model.id}`}><ScanSearch size={16} />测试</Link>
            <a className="button secondary" href={`/api/v1/models/${model.id}/download`}><Download size={16} />PT</a>
            <Link className="button secondary" to={`/training?job=${model.trainingJobId}`}>训练来源</Link>
            {exportJob?.status === 'SUCCEEDED' && <a className="button secondary" href={`/api/v1/models/${model.id}/onnx/download`}><Download size={16} />ONNX</a>}
            <button className="button danger" disabled={removeModel.isPending} onClick={() => setDeleting(model)}><Trash2 size={16} />删除</button>
          </div>
          {exportJob ? <div className="export-status" role="status"><span>ONNX：{exportStatusLabels[exportJob.status] ?? exportJob.status}</span>{['RUNNING', 'QUEUED'].includes(exportJob.status) && <progress max="100" value={exportJob.progress} aria-label={`${model.name} ONNX 导出进度`} />}{exportJob.errorMessage && <span>{exportJob.errorMessage}</span>}</div> : <p className="quiet-state">ONNX：等待自动创建导出任务</p>}
        </article>
      })}</div> : <EmptyState title="还没有训练产物" message="成功完成训练后，权重和指标会出现在这里。" action={<Link className="button secondary" to="/training">创建训练任务</Link>} />}
    </section>

    {comparison.length > 0 && <section className="panel"><div className="panel-heading"><div><h2><GitCompare size={18} />实验对比</h2><p>{selectedModels[0].name} 与 {selectedModels[1].name}</p></div></div><div className="table"><div className="table-head"><span>指标</span><span>模型 A</span><span>模型 B</span><span>差值（B - A）</span></div>{comparison.map((metric) => <div className="table-row" key={metric.key}><code>{trainingMetricLabel(metric.key)}</code><span>{metric.first ?? '—'}</span><span>{metric.second ?? '—'}</span><strong className={metric.delta !== null && metric.delta >= 0 ? 'metric-up' : 'metric-down'}>{metric.delta === null ? '—' : `${metric.delta >= 0 ? '+' : ''}${metric.delta}`}</strong></div>)}</div></section>}

    <section className="panel"><div className="panel-heading"><div><h2>官方预训练模型</h2><p>只有标准 YOLO 模型支持无提示词单图测试；SAM3 仅用于带流程提示的预标注。</p></div></div>{models.isPending ? <LoadingRows /> : models.data?.pretrained.length ? <div className="table"><div className="table-head"><span>文件</span><span>任务</span><span>大小</span><span>操作</span></div>{models.data.pretrained.map((model) => <div className="table-row" key={model.id}><strong><Layers size={16} />{model.name}</strong><span>{taskLabels[model.task]}</span><span>{formatBytes(model.sizeBytes)}</span>{model.canTest ? <Link className="button secondary" to={`/models/test?model=${encodeURIComponent(`pretrained:${model.id}`)}`}><ScanSearch size={15} />测试</Link> : <span className="status-badge">仅用于预标注</span>}</div>)}</div> : <EmptyState title="未发现预训练模型" message="请将官方权重放入 models/pretrained 目录。" />}</section>
    {completed.length > 0 && <p className="quiet-state">已保留 {completed.length} 次成功训练记录，可从模型卡片追溯训练来源。</p>}
    <ConfirmDialog open={Boolean(deleting)} title="删除模型产物" description={`“${deleting?.name}”及其 ONNX 导出会被永久删除，训练历史仍保留。`} confirmLabel="确认删除" pending={removeModel.isPending} onCancel={() => setDeleting(null)} onConfirm={() => deleting && removeModel.mutate(deleting.id)} />
  </>
}
