import { useQuery } from '@tanstack/react-query'
import { Activity, Database, Image, Layers } from 'lucide-react'
import { api } from '../lib/api'
import { PageHeader } from '../components/PageHeader'

export function DashboardPage() {
  const assets = useQuery({ queryKey: ['assets'], queryFn: api.assets })
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs, refetchInterval: 3000 })
  const running = jobs.data?.data.filter((job) => ['RUNNING', 'QUEUED', 'PAUSING'].includes(job.status)) ?? []
  const cards = [
    { label: '素材总数', value: assets.data?.data.length ?? 0, icon: Image },
    { label: '数据集版本', value: datasets.data?.data.length ?? 0, icon: Database },
    { label: '训练中', value: running.length, icon: Activity },
    { label: '已完成模型', value: jobs.data?.data.filter((job) => job.status === 'SUCCEEDED').length ?? 0, icon: Layers },
  ]
  return <><PageHeader title="训练总览" description="从素材到模型的本地训练流水线" />
    <section className="metric-grid">{cards.map(({ label, value, icon: Icon }) => <article className="metric" key={label}><Icon size={20} /><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="panel"><div className="panel-heading"><div><h2>当前任务</h2><p>GPU 训练队列与最新进度</p></div></div>
      {running.length ? running.map((job) => <div className="job-row" key={job.id}><div><strong>{job.name}</strong><span>{job.task} · Epoch {job.currentEpoch}</span></div><div className="progress"><i style={{ width: `${job.progress}%` }} /></div><span className={`badge ${job.status.toLowerCase()}`}>{job.status}</span></div>) : <div className="quiet-state">当前没有运行中的任务</div>}
    </section></>
}
