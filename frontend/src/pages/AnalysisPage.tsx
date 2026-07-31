import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, CheckCircle2, ScanSearch, Square } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { api, type AnalysisSample } from '../lib/api'
import './AnalysisPage.css'

type ErrorFilter = 'all' | 'fp' | 'fn'

export function AnalysisPage() {
  const { datasetId = '' } = useParams()
  const client = useQueryClient()
  const { notify } = useToast()
  const dataset = useQuery({ queryKey: ['dataset', datasetId], queryFn: () => api.dataset(datasetId) })
  const models = useQuery({ queryKey: ['models'], queryFn: api.models })
  const jobs = useQuery({ queryKey: ['analysis-jobs', datasetId], queryFn: () => api.analysisJobs(datasetId), refetchInterval: (query) => query.state.data?.data.some((job) => ['QUEUED', 'RUNNING'].includes(job.status)) ? 1500 : false })
  const [modelId, setModelId] = useState('')
  const [confidence, setConfidence] = useState(.25)
  const [iouThreshold, setIouThreshold] = useState(.5)
  const [filter, setFilter] = useState<ErrorFilter>('all')
  const item = dataset.data?.data
  const compatibleModels = useMemo(() => {
    if (!item || !models.data) return []
    const trained = models.data.data.filter((model) => model.task === item.task).map((model) => ({ id: model.id, name: `${model.name} · 训练 ${model.trainingJobId.slice(0, 8)}` }))
    const pretrained = models.data.pretrained.filter((model) => model.task === item.task && model.canTest).map((model) => ({ id: `pretrained:${model.id}`, name: `${model.name}（预训练）` }))
    return [...trained, ...pretrained]
  }, [item, models.data])
  useEffect(() => { if (!modelId && compatibleModels[0]) setModelId(compatibleModels[0].id) }, [compatibleModels, modelId])
  const create = useMutation({
    mutationFn: () => api.createAnalysisJob(datasetId, { modelId, confidence, iouThreshold }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ['analysis-jobs', datasetId] }); notify('错误样本分析已加入本地队列') },
  })
  const cancel = useMutation({ mutationFn: (jobId: string) => api.cancelAnalysisJob(datasetId, jobId), onSuccess: () => client.invalidateQueries({ queryKey: ['analysis-jobs', datasetId] }) })
  const latest = jobs.data?.data[0]
  const totals = latest?.result.totals
  const samples = (latest?.result.samples ?? []).filter((sample) => filter === 'all' ? sample.fp + sample.fn > 0 : sample[filter] > 0)

  return <>
    <PageHeader title="模型错误样本分析" description={item ? `${item.name} · 按 TP / FP / FN 定位难例和漏标` : '按 TP / FP / FN 定位难例和漏标'} actions={<Link className="button secondary" to={`/datasets/${datasetId}`}><ArrowLeft size={16} />返回数据集</Link>} />
    <section className="panel compact-form">
      <div className="panel-heading"><div><h2><ScanSearch size={18} />创建分析任务</h2><p>在本机 GPU 队列执行推理，按类别和 IoU 匹配人工标注，不会修改数据集。</p></div></div>
      <div className="form-row">
        <label>模型<select aria-label="分析模型" value={modelId} onChange={(event) => setModelId(event.target.value)}>{compatibleModels.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
        <label>置信度<input aria-label="分析置信度" type="number" min="0" max="1" step="0.05" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} /></label>
        <label>IoU 阈值<input aria-label="IoU 阈值" type="number" min="0.05" max="1" step="0.05" value={iouThreshold} onChange={(event) => setIouThreshold(Number(event.target.value))} /></label>
        <button className="button primary" disabled={!modelId || create.isPending || ['QUEUED', 'RUNNING'].includes(latest?.status ?? '')} onClick={() => create.mutate()}><ScanSearch size={16} />开始分析</button>
      </div>
      {create.error && <ErrorState message={create.error.message} />}
      {!compatibleModels.length && !models.isPending && <p className="helper-text blocked">当前没有与数据集任务一致且可推理的模型。</p>}
    </section>
    {jobs.isPending ? <LoadingRows /> : jobs.isError ? <ErrorState message={jobs.error.message} onRetry={() => jobs.refetch()} /> : !latest ? <EmptyState title="还没有分析结果" message="选择模型后创建第一项错误样本分析。" /> : <>
      <section className="panel analysis-status">
        <div className="panel-heading"><div><h2>最新分析</h2><p>{latest.status === 'SUCCEEDED' ? `已分析 ${latest.result.sampleCount ?? 0} 张完成标注的素材` : latest.status === 'FAILED' ? latest.errorMessage : '正在本地队列中处理'}</p></div><span className={`badge ${latest.status.toLowerCase()}`}>{latest.status}</span></div>
        <div className="progress" role="progressbar" aria-label="错误样本分析进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={latest.progress}><i style={{ width: `${latest.progress}%` }} /></div>
        {['QUEUED', 'RUNNING'].includes(latest.status) && <button className="button ghost" disabled={cancel.isPending} onClick={() => cancel.mutate(latest.id)}><Square size={15} />取消</button>}
      </section>
      {latest.status === 'SUCCEEDED' && totals && <>
        <section className="metric-grid analysis-metrics"><article className="metric"><CheckCircle2 size={20} /><span>TP 正确检出</span><strong>{totals.tp}</strong></article><article className="metric"><AlertTriangle size={20} /><span>FP 误检</span><strong>{totals.fp}</strong></article><article className="metric"><AlertTriangle size={20} /><span>FN 漏检</span><strong>{totals.fn}</strong></article></section>
        <section className="panel"><div className="panel-heading"><div><h2>错误样本</h2><p>默认按 FP + FN 从高到低排列，优先检查最有价值的样本。</p></div><div className="analysis-filters"><button className={`button ${filter === 'all' ? 'primary' : 'ghost'}`} onClick={() => setFilter('all')}>全部错误</button><button className={`button ${filter === 'fp' ? 'primary' : 'ghost'}`} onClick={() => setFilter('fp')}>仅 FP</button><button className={`button ${filter === 'fn' ? 'primary' : 'ghost'}`} onClick={() => setFilter('fn')}>仅 FN</button></div></div>{samples.length ? <div className="analysis-sample-grid">{samples.map((sample: AnalysisSample) => <article className="analysis-sample" key={sample.assetId}><img loading="lazy" src={`/media/${sample.storagePath.replace('uploads/', '')}`} alt={sample.filename} /><div><strong>{sample.filename}</strong><span>TP {sample.tp} · FP {sample.fp} · FN {sample.fn}</span></div><Link className="button secondary" to={`/datasets/${datasetId}/annotate?asset=${encodeURIComponent(sample.assetId)}`}>打开标注</Link></article>)}</div> : <EmptyState title="当前筛选下没有错误样本" message="切换筛选条件或使用不同模型重新分析。" />}</section>
      </>}
    </>}
  </>
}
