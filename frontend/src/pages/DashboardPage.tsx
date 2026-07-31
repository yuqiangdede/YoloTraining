import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Database, Image, Layers, Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { api } from '../lib/api'
import { jobStatusLabels, taskLabels } from '../lib/labels'

export function DashboardPage() {
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api.datasets() })
  const versions = useQuery({ queryKey: ['datasetVersions'], queryFn: api.allDatasetVersions })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs, refetchInterval: 3000 })
  const models = useQuery({ queryKey: ['models'], queryFn: api.models })
  const running = jobs.data?.data.filter((job) => ['RUNNING', 'QUEUED', 'PAUSING'].includes(job.status)) ?? []
  const worker = jobs.data?.worker
  const isLoading = datasets.isPending || versions.isPending || jobs.isPending || models.isPending
  const failed = [datasets, versions, jobs, models].find((query) => query.isError)
  const retry = () => { datasets.refetch(); versions.refetch(); jobs.refetch(); models.refetch() }

  const datasetList = datasets.data?.data ?? []
  const versionList = versions.data?.data ?? []
  const trainedModels = models.data?.data ?? []
  const activeJob = running[0]
  const nextAction = datasetList.length === 0
    ? { label: '新建第一个数据集', to: '/datasets?create=1', icon: Database }
    : versionList.length === 0
      ? { label: '完成标注并冻结版本', to: `/datasets/${datasetList[0].id}`, icon: Database }
      : activeJob
        ? { label: '查看正在进行的训练', to: `/training?job=${activeJob.id}`, icon: Activity }
        : trainedModels.length === 0
          ? { label: '创建训练任务', to: '/training', icon: Play }
          : { label: '测试最新模型', to: `/models/test?model=${trainedModels[0].id}`, icon: Layers }
  const NextIcon = nextAction.icon
  const cards = [
    { label: '素材总数', value: datasetList.reduce((total, item) => total + item.assetCount, 0), icon: Image, to: '/datasets' },
    { label: '数据集', value: datasetList.length, icon: Database, to: '/datasets' },
    { label: '训练中', value: running.length, icon: Activity, to: '/training' },
    { label: '可用模型', value: trainedModels.length, icon: Layers, to: '/models' },
  ]

  return <>
    <PageHeader title="训练总览" description="从素材到模型的本地训练流水线" actions={<Link className="button primary" to={nextAction.to}><NextIcon size={16} />{nextAction.label}<ArrowRight size={16} /></Link>} />
    {isLoading ? <LoadingRows count={4} /> : failed ? <ErrorState message={failed.error.message} onRetry={retry} /> : <>
      <section className="metric-grid" aria-label="当前工作区指标">{cards.map(({ label, value, icon: Icon, to }) => <Link className="metric-link" to={to} key={label}><article className="metric"><Icon size={20} /><span>{label}</span><strong>{value}</strong></article></Link>)}</section>
      <section className="panel dashboard-jobs">
        <div className="panel-heading"><div><h2>当前任务</h2><p>GPU 训练队列与最新进度</p></div><Link className="button ghost" to="/training">打开任务队列<ArrowRight size={15} /></Link></div>
        {worker && !worker.alive && <div className="worker-warning" role="alert">工作线程不可用，排队任务不会自动开始。{worker.lastError ? ` 最近错误：${worker.lastError}` : ''}</div>}
        {running.length ? running.map((job) => <div className="job-row" key={job.id}><div><strong>{job.name}</strong><span>{taskLabels[job.task]} · {job.status === 'QUEUED' ? `前方 ${Math.max(0, (job.queuePosition ?? 1) - 1)} 个任务` : `Epoch ${job.currentEpoch}`}</span></div><div className="progress" role="progressbar" aria-label={`${job.name} 训练进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}><i style={{ width: `${job.progress}%` }} /></div><span className={`badge ${job.status.toLowerCase()}`}>{jobStatusLabels[job.status] ?? job.status}</span></div>) : <EmptyState title="当前没有运行中的任务" message={versionList.length ? '已有冻结版本，可以创建新的训练任务。' : '先完成标注并冻结一个可训练版本。'} action={<Link className="button secondary" to={versionList.length ? '/training' : datasetList[0] ? `/datasets/${datasetList[0].id}` : '/datasets?create=1'}><Play size={16} />{versionList.length ? '新建训练' : '继续准备数据'}</Link>} />}
      </section>
    </>}
  </>
}
