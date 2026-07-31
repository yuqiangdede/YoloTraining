import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Database, FolderKanban, Layers, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { api } from '../lib/api'
import { taskLabels } from '../lib/labels'
import './ProjectsPage.css'

export function ProjectsPage() {
  const client = useQueryClient()
  const { notify } = useToast()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => api.createProject({ name: name.trim(), description: description.trim() }),
    onSuccess: ({ data }) => {
      setName('')
      setDescription('')
      client.invalidateQueries({ queryKey: ['projects'] })
      notify(`项目“${data.name}”已创建`)
    },
  })

  return <>
    <PageHeader title="项目" description="用项目组织数据集、训练任务和模型结果" />
    <section className="panel compact-form">
      <div className="panel-heading"><div><h2><Plus size={18} />新建项目</h2><p>项目是完整视觉任务的顶层容器，后续数据和模型都会保留归属关系。</p></div></div>
      <form className="form-row" onSubmit={(event) => { event.preventDefault(); if (name.trim()) create.mutate() }}>
        <label>项目名称<input aria-label="项目名称" value={name} maxLength={100} onChange={(event) => setName(event.target.value)} /></label>
        <label>用途说明<input aria-label="用途说明" value={description} maxLength={1000} onChange={(event) => setDescription(event.target.value)} placeholder="例如：厂区安全帽检测" /></label>
        <button className="button primary" disabled={!name.trim() || create.isPending}><Plus size={16} />创建项目</button>
      </form>
      {create.error && <ErrorState message={create.error.message} />}
    </section>
    <section className="panel">
      <div className="panel-heading"><div><h2>项目列表</h2><p>进入项目后，从数据准备一路推进到模型验证。</p></div></div>
      {projects.isPending ? <LoadingRows /> : projects.isError ? <ErrorState message={projects.error.message} onRetry={() => projects.refetch()} /> : projects.data.data.length ? <div className="project-grid">{projects.data.data.map((project) => <Link className="project-card" to={`/projects/${project.id}`} key={project.id}>
        <div className="project-card-title"><FolderKanban size={20} /><div><h3>{project.name}</h3><p>{project.description || '尚未填写用途说明'}</p></div></div>
        <dl><div><dt>数据集</dt><dd>{project.datasetCount}</dd></div><div><dt>训练</dt><dd>{project.trainingCount}</dd></div><div><dt>模型</dt><dd>{project.modelCount}</dd></div></dl>
        <span className="project-enter">进入项目<ArrowRight size={15} /></span>
      </Link>)}</div> : <EmptyState title="还没有项目" message="创建项目后再添加数据集。" />}
    </section>
  </>
}

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => api.project(projectId), enabled: Boolean(projectId) })
  const datasets = useQuery({ queryKey: ['datasets', projectId], queryFn: () => api.datasets(projectId), enabled: Boolean(projectId) })
  const item = project.data?.data

  return <>
    <PageHeader title={item?.name ?? '项目工作台'} description={item?.description || '从数据准备推进到本地 GPU 模型'} actions={<Link className="button primary" to={`/datasets?project=${encodeURIComponent(projectId)}&create=1`}><Plus size={16} />新建数据集</Link>} />
    {project.isPending ? <LoadingRows /> : project.isError ? <ErrorState message={project.error.message} onRetry={() => project.refetch()} /> : item && <section className="metric-grid project-metrics" aria-label="项目指标">
      <article className="metric"><Database size={20} /><span>数据集</span><strong>{item.datasetCount}</strong></article>
      <article className="metric"><Sparkles size={20} /><span>训练任务</span><strong>{item.trainingCount}</strong></article>
      <article className="metric"><Layers size={20} /><span>模型结果</span><strong>{item.modelCount}</strong></article>
    </section>}
    <section className="panel">
      <div className="panel-heading"><div><h2>项目数据集</h2><p>上传、标注、冻结版本后即可进入训练。</p></div><Link className="button ghost" to={`/datasets?project=${encodeURIComponent(projectId)}`}>查看全部数据集<ArrowRight size={15} /></Link></div>
      {datasets.isPending ? <LoadingRows /> : datasets.isError ? <ErrorState message={datasets.error.message} onRetry={() => datasets.refetch()} /> : datasets.data.data.length ? <div className="table"><div className="table-head"><span>数据集</span><span>任务</span><span>素材</span><span>下一步</span></div>{datasets.data.data.map((dataset) => <div className="table-row" key={dataset.id}><strong>{dataset.name}</strong><span>{taskLabels[dataset.task]}</span><span>{dataset.assetCount}</span><Link className="button secondary" to={`/datasets/${dataset.id}`}>打开工作台</Link></div>)}</div> : <EmptyState title="项目内还没有数据集" message="新建数据集后上传图片并开始标注。" action={<Link className="button primary" to={`/datasets?project=${encodeURIComponent(projectId)}&create=1`}><Plus size={16} />新建数据集</Link>} />}
    </section>
  </>
}
