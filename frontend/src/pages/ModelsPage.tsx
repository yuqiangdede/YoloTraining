import { useQuery } from '@tanstack/react-query'
import { Download, GitCompare, Layers } from 'lucide-react'
import { EmptyState } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { api } from '../lib/api'

export function ModelsPage() {
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs })
  const completed = jobs.data?.data.filter((job) => job.status === 'SUCCEEDED') ?? []
  return <><PageHeader title="模型结果" description="比较训练记录，下载 PT 或创建 ONNX 导出" actions={<button className="button secondary" disabled={completed.length < 2}><GitCompare size={16} />对比所选</button>} />
    <section className="panel">{completed.length ? <div className="model-grid">{completed.map((job) => <article className="model-card" key={job.id}><div className="model-icon"><Layers size={22} /></div><div><span className="badge succeeded">{job.task}</span><h2>{job.name}</h2><p>{job.modelPath}</p></div><dl><div><dt>Epoch</dt><dd>{job.currentEpoch}</dd></div><div><dt>进度</dt><dd>{job.progress}%</dd></div><div><dt>创建时间</dt><dd>{new Date(job.createdAt).toLocaleDateString()}</dd></div></dl><button className="button secondary"><Download size={16} />查看产物</button></article>)}</div> : <EmptyState title="还没有训练结果" message="成功完成训练后，best.pt、last.pt 和指标会出现在这里" />}</section>
  </>
}
