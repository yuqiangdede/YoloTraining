import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ClipboardList, Database, Film, Pencil, PenLine, Plus, Save, Sparkles, Trash2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { WorkflowSteps } from '../components/WorkflowSteps'
import { DatasetAugmentationPreview } from '../components/DatasetAugmentationPreview'
import { api, type Category, type PrelabelMode } from '../lib/api'
import { annotationStatusLabels, jobStatusLabels, taskLabels } from '../lib/labels'
import { modelKindLabels } from '../lib/modelCatalog'
import './DatasetWorkspacePage.css'

const modeLabels: Record<PrelabelMode, string> = { yolo: 'YOLO 预标注', yolo_sam: 'YOLO + SAM3 精细分割', sam: 'SAM3 按类别自动分割' }
type Confirmation = { kind: 'category' | 'version' | 'dataset'; id?: string; name: string }

export function DatasetWorkspacePage() {
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const { notify } = useToast()
  const [versionName, setVersionName] = useState(() => new Date().toISOString().slice(0, 16).replace('T', ' '))
  const [prelabelMode, setPrelabelMode] = useState<PrelabelMode>('yolo')
  const [confidence, setConfidence] = useState(.25)
  const [newCategory, setNewCategory] = useState('')
  const [taskName, setTaskName] = useState('')
  const [assignee, setAssignee] = useState('')
  const [frameStep, setFrameStep] = useState(30)
  const [editingCategory, setEditingCategory] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const dataset = useQuery({ queryKey: ['dataset', datasetId], queryFn: () => api.dataset(datasetId) })
  const assets = useQuery({ queryKey: ['assets', datasetId], queryFn: () => api.assets(datasetId) })
  const versions = useQuery({ queryKey: ['versions', datasetId], queryFn: () => api.datasetVersions(datasetId) })
  const quality = useQuery({ queryKey: ['quality', datasetId], queryFn: () => api.datasetQuality(datasetId), refetchInterval: 10000 })
  const exports = useQuery({ queryKey: ['dataset-exports', datasetId], queryFn: () => api.datasetExports(datasetId) })
  const jobs = useQuery({ queryKey: ['prelabel-jobs', datasetId], queryFn: () => api.prelabelJobs(datasetId), refetchInterval: (query) => ['QUEUED', 'RUNNING'].includes(query.state.data?.data[0]?.status ?? '') ? 2000 : false })
  const annotationTasks = useQuery({ queryKey: ['annotation-tasks', datasetId], queryFn: () => api.annotationTasks(datasetId), refetchInterval: 5000 })
  const item = dataset.data?.data
  const qualityCheck = useMutation({ mutationFn: () => api.checkDatasetQuality(datasetId), onSuccess: () => { client.invalidateQueries({ queryKey: ['quality', datasetId] }); notify('质量检查已完成') } })
  useEffect(() => { if (item) { setPrelabelMode(item.prelabelMode ?? 'yolo'); setConfidence(item.prelabelConfidence ?? .25) } }, [item?.id, item?.prelabelMode, item?.prelabelConfidence])

  const refresh = () => {
    client.invalidateQueries({ queryKey: ['dataset', datasetId] })
    client.invalidateQueries({ queryKey: ['datasets'] })
    client.invalidateQueries({ queryKey: ['assets', datasetId] })
    client.invalidateQueries({ queryKey: ['versions', datasetId] })
    client.invalidateQueries({ queryKey: ['prelabel-jobs', datasetId] })
    client.invalidateQueries({ queryKey: ['annotation-tasks', datasetId] })
  }
  const upload = useMutation({ mutationFn: (files: FileList) => api.uploadAssets(datasetId, files), onSuccess: ({ data }) => { refresh(); notify(`已导入 ${data.length} 张素材`) } })
  const uploadVideo = useMutation({ mutationFn: (file: File) => api.uploadVideoFrames(datasetId, file, frameStep), onSuccess: ({ data, totalFrames }) => { refresh(); notify(`已从 ${totalFrames} 帧视频中导入 ${data.length} 张图片`) } })
  const createTask = useMutation({ mutationFn: () => api.createAnnotationTask(datasetId, { name: taskName.trim(), assignee: assignee.trim() }), onSuccess: () => { setTaskName(''); refresh(); notify('标注任务已分发') } })
  const remove = useMutation({ mutationFn: (id: string) => api.recycleAsset(datasetId, id), onSuccess: (_data, id) => { const name = assets.data?.data.find((asset) => asset.id === id)?.filename ?? '素材'; refresh(); notify({ message: `“${name}”已移入回收站`, kind: 'info', actionLabel: '撤销', onAction: () => { void api.restoreAsset(datasetId, id).then(() => { refresh(); notify('素材已恢复') }) } }) } })
  const freeze = useMutation({ mutationFn: () => api.createDatasetVersion(datasetId, { name: versionName.trim(), trainRatio: .8, valRatio: .2, testRatio: 0, seed: 0 }), onSuccess: () => { refresh(); notify('训练版本已冻结') } })
  const removeVersion = useMutation({ mutationFn: (id: string) => api.deleteDatasetVersion(datasetId, id), onSuccess: () => { refresh(); setConfirmation(null); notify('训练版本已删除') } })
  const removeDataset = useMutation({ mutationFn: () => api.deleteDataset(datasetId), onSuccess: () => { setConfirmation(null); notify('数据集已删除'); navigate('/datasets') } })
  const saveSettings = useMutation({ mutationFn: () => api.updateDataset(datasetId, { name: item!.name, prelabelMode, prelabelConfidence: confidence }), onSuccess: () => { refresh(); notify('默认预标注配置已保存') } })
  const prelabel = useMutation({ mutationFn: () => api.datasetPrelabel(datasetId, { mode: prelabelMode, confidence }), onSuccess: () => { refresh(); notify('预标注任务已创建，当前配置已同时保存') } })
  const createCategory = useMutation({ mutationFn: () => api.createCategory(datasetId, newCategory.trim()), onSuccess: () => { setNewCategory(''); refresh(); notify('标签已添加') } })
  const updateCategory = useMutation({ mutationFn: ({ id, name }: { id: string; name: string }) => api.updateCategory(datasetId, id, name), onSuccess: () => { setEditingCategory(null); refresh(); notify('标签已重命名') } })
  const deleteCategory = useMutation({ mutationFn: (id: string) => api.deleteCategory(datasetId, id), onSuccess: () => { refresh(); setConfirmation(null); notify('标签及其关联标注已清理') } })

  if (dataset.isPending) return <LoadingRows />
  if (dataset.isError) return <ErrorState message={dataset.error.message} onRetry={() => dataset.refetch()} />
  if (!item) return <ErrorState message="数据集不存在" />
  const counts = item.annotationCounts ?? { unlabeled: item.assetCount, draft: 0, completed: 0, reviewed: 0 }
  const latestJob = jobs.data?.data[0]
  const canUseSam = item.task === 'segment' || item.task === 'detect'
  const canPrelabel = item.categories.length > 0 && item.assetCount > 0
  const settingsDirty = prelabelMode !== item.prelabelMode || Math.abs(confidence - item.prelabelConfidence) > .0001
  const canFreeze = item.assetCount >= 2 && (counts.completed + counts.reviewed) >= item.assetCount && quality.data?.data.status !== 'BLOCKED'
  const completedCount = counts.completed + counts.reviewed
  const freezeReason = item.assetCount < 2 ? '至少需要 2 张素材，才能保留训练集和验证集。' : completedCount !== item.assetCount ? `还有 ${item.assetCount - completedCount} 张素材未完成标注。` : '全部素材均已完成，可以冻结训练版本。'
  const categoryActionError = createCategory.error ?? updateCategory.error ?? deleteCategory.error
  const confirmPending = removeVersion.isPending || removeDataset.isPending || deleteCategory.isPending
  const confirmDescription = confirmation?.kind === 'category' ? `删除标签“${confirmation.name}”后，所有素材中引用该标签的标注都会被清理。` : confirmation?.kind === 'version' ? `删除训练版本“${confirmation.name}”时，会一并删除它的训练历史和模型产物，且无法恢复。` : `永久删除数据集“${confirmation?.name}”、素材、标注和未关联训练版本，且无法恢复。`
  const confirmAction = () => { if (!confirmation) return; if (confirmation.kind === 'category' && confirmation.id) deleteCategory.mutate(confirmation.id); else if (confirmation.kind === 'version' && confirmation.id) removeVersion.mutate(confirmation.id); else removeDataset.mutate() }

  return <>
    <nav className="workspace-tabs" aria-label="数据集工作区">
      <Link className="workspace-tab active" to={`/datasets/${datasetId}`}>概览</Link>
      <Link className="workspace-tab" to={`/datasets/${datasetId}/annotate`}>标注</Link>
      <Link className="workspace-tab" to={`/datasets/${datasetId}/analysis`}>错误分析</Link>
      <a className="workspace-tab" href="#workspace-assets">素材</a>
      <a className="workspace-tab" href="#quality-report">质量</a>
      <a className="workspace-tab" href="#dataset-versions">版本</a>
    </nav>
    <section id="quality-report" className="panel quality-panel"><div className="panel-heading"><div><h2>数据质量</h2><p>版本冻结前自动检查结构、标注完整性、类别和重复素材。</p></div><button className="button secondary" disabled={qualityCheck.isPending} onClick={() => qualityCheck.mutate()}>重新检查</button></div>{quality.isPending ? <LoadingRows /> : quality.isError ? <ErrorState message={quality.error.message} onRetry={() => quality.refetch()} /> : quality.data?.data && <><div className="quality-summary"><strong className={`quality-state ${quality.data.data.status.toLowerCase()}`}>{quality.data.data.status}</strong><span>{quality.data.data.completedCount}/{quality.data.data.assetCount} 个素材已完成</span><span>{quality.data.data.annotationCount} 个标注</span></div>{quality.data.data.issues.length ? <div className="quality-issues">{quality.data.data.issues.slice(0, 8).map((issue) => <div className={`quality-issue ${issue.severity.toLowerCase()}`} key={`${issue.code}-${issue.message}`}><strong>{issue.severity}</strong><span>{issue.message}</span><small>{issue.assetIds?.length ? `${issue.assetIds.length} 个素材` : ''}</small></div>)}</div> : <p className="quiet-state">未发现质量问题。</p>}</>}</section>
    <PageHeader title={item.name} description={`${taskLabels[item.task]} · ${item.categories.map((category) => category.name).join('、')}`} actions={<><Link className="button secondary" to="/datasets"><ArrowLeft size={16} />返回列表</Link><Link className="button secondary" to={`/datasets/${datasetId}/annotate`}><PenLine size={16} />标注素材</Link><label className="button secondary"><Film size={16} />视频抽帧<input aria-label="导入视频抽帧" type="file" accept="video/*" hidden onChange={(event) => event.target.files?.[0] && uploadVideo.mutate(event.target.files[0])} /></label><label className="button primary"><Upload size={16} />导入图片<input aria-label="导入素材" type="file" accept="image/*" multiple hidden onChange={(event) => event.target.files && upload.mutate(event.target.files)} /></label></>} />
    <WorkflowSteps steps={[
      { label: '导入素材', detail: `${item.assetCount} 个素材`, state: item.assetCount ? 'complete' : 'current' },
      { label: '配置与预标注', detail: `${counts.draft} 个草稿`, state: counts.draft || counts.completed || counts.reviewed ? 'complete' : item.assetCount ? 'current' : 'next' },
      { label: '人工标注', detail: `${completedCount}/${item.assetCount} 已完成`, state: completedCount === item.assetCount && item.assetCount ? 'complete' : item.assetCount ? 'current' : 'next', action: <Link to={`/datasets/${datasetId}/annotate`}>打开</Link> },
      { label: '冻结版本', detail: `${versions.data?.data.length ?? 0} 个版本`, state: versions.data?.data.length ? 'complete' : canFreeze ? 'current' : 'next' },
    ]} />
    {(upload.error || uploadVideo.error) && <ErrorState message={(upload.error ?? uploadVideo.error)?.message ?? '素材导入失败'} />}

    <section className="panel compact-form"><div className="panel-heading"><div><h2><Film size={18} />视频抽帧设置</h2><p>上传视频时每隔指定帧数提取一张图片，原视频与抽帧结果均保存在项目目录。</p></div></div><div className="form-row"><label>抽帧间隔<input aria-label="抽帧间隔" type="number" min="1" max="10000" value={frameStep} onChange={(event) => setFrameStep(Math.max(1, Number(event.target.value) || 1))} /></label><span className="helper-text">当前设置：每 {frameStep} 帧提取 1 张</span></div></section>

    <section className="panel compact-form"><div className="panel-heading"><div><h2><ClipboardList size={18} />标注任务分发</h2><p>任务直接进入标注流程，不设置审核步骤；进度按已完成素材自动计算。</p></div></div><div className="form-row"><label>任务名称<input aria-label="标注任务名称" value={taskName} onChange={(event) => setTaskName(event.target.value)} /></label><label>负责人<input aria-label="标注负责人" value={assignee} onChange={(event) => setAssignee(event.target.value)} placeholder="可留空" /></label><button className="button primary" disabled={!taskName.trim() || !item.assetCount || createTask.isPending} onClick={() => createTask.mutate()}><Plus size={16} />分发全部素材</button></div>{createTask.error && <ErrorState message={createTask.error.message} />}{annotationTasks.isPending ? <LoadingRows /> : annotationTasks.isError ? <ErrorState message={annotationTasks.error.message} onRetry={() => annotationTasks.refetch()} /> : annotationTasks.data.data.length ? <div className="annotation-task-list">{annotationTasks.data.data.map((task) => <div className="annotation-task-row" key={task.id}><div><strong>{task.name}</strong><span>{task.assignee || '未指定负责人'} · {task.completedCount}/{task.assetCount} 已完成</span></div><div className="progress" role="progressbar" aria-label={`${task.name} 标注进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={task.progress}><i style={{ width: `${task.progress}%` }} /></div><span className={`badge ${task.status.toLowerCase()}`}>{task.status === 'NEW' ? '待处理' : task.status === 'IN_PROGRESS' ? '进行中' : '已完成'}</span></div>)}</div> : <p className="quiet-state">尚未分发标注任务。</p>}</section>

    <section className="panel compact-form"><div className="panel-heading"><div><h2>预标注设置</h2><p>开始预标注会同时保存当前配置，并处理全部未删除素材；预标注模型固定使用 n 档。</p></div></div><div className="form-row"><label>模型分类<output className="model-setting-value">{modelKindLabels[item.task]}</output></label><label>预标注方式<select value={prelabelMode} onChange={(event) => setPrelabelMode(event.target.value as PrelabelMode)}><option value="yolo">{modeLabels.yolo}</option><option value="yolo_sam" disabled={!canUseSam}>{modeLabels.yolo_sam}</option><option value="sam" disabled={!canUseSam}>{modeLabels.sam}</option></select></label><label>置信度<input type="number" min="0" max="1" step="0.05" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} /></label><button className="button secondary" disabled={!settingsDirty || saveSettings.isPending} onClick={() => saveSettings.mutate()}><Save size={16} />保存为默认配置</button><button className="button primary" disabled={!canPrelabel || prelabel.isPending || ['QUEUED', 'RUNNING'].includes(latestJob?.status ?? '')} onClick={() => prelabel.mutate()}><Sparkles size={16} />开始预标注并保存配置</button></div>{latestJob && <p role="status" className="quiet-state">最近任务：{jobStatusLabels[latestJob.status] ?? latestJob.status} · 已应用 {latestJob.result.applied ?? 0} · 已跳过 {latestJob.result.skipped ?? 0}{latestJob.errorMessage ? ` · ${latestJob.errorMessage}` : ''}</p>}{saveSettings.error && <ErrorState message={saveSettings.error.message} />}{prelabel.error && <ErrorState message={prelabel.error.message} />}</section>

    <section className="panel compact-form"><div className="panel-heading"><div><h2>标签管理</h2><p>重命名不会改变已有标注 ID；删除标签会清理关联标注。</p></div></div><div className="form-row"><label>新标签名称<input value={newCategory} onChange={(event) => setNewCategory(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); if (newCategory.trim()) createCategory.mutate() } }} /></label><button className="button secondary" disabled={!newCategory.trim() || createCategory.isPending} onClick={() => createCategory.mutate()}><Plus size={16} />新增标签</button></div><div className="category-tags">{item.categories.map((category: Category) => <span className="category-tag" key={category.id}>{editingCategory === category.id ? <span className="category-edit"><input aria-label={`编辑标签 ${category.name}`} value={editingName} onChange={(event) => setEditingName(event.target.value)} /><button className="category-action category-action-save" disabled={!editingName.trim()} onClick={() => updateCategory.mutate({ id: category.id, name: editingName.trim() })}>保存</button></span> : <><span className="category-name">{category.name}</span><span className="category-actions"><button className="category-action" aria-label={`重命名标签 ${category.name}`} onClick={() => { setEditingCategory(category.id); setEditingName(category.name) }}><Pencil size={13} />重命名</button><button className="category-action category-action-danger" aria-label={`删除标签 ${category.name}`} onClick={() => setConfirmation({ kind: 'category', id: category.id, name: category.name })}><Trash2 size={13} />删除</button></span></>}</span>)}</div>{categoryActionError && <ErrorState message={categoryActionError.message} />}</section>

    <details className="panel workspace-assets"><summary className="panel-heading"><div><h2>工作区素材</h2><p>显示最近 100 个素材；大数据集请进入标注工作台筛选管理。</p></div></summary><div className="workspace-assets-content"><div className="workspace-assets-actions"><Link className="button secondary" to={`/datasets/${datasetId}/annotate`}>打开标注工作台</Link></div>{assets.isPending ? <LoadingRows /> : assets.isError ? <ErrorState message={assets.error.message} onRetry={() => assets.refetch()} /> : assets.data?.data.length ? <div className="asset-grid">{assets.data.data.map((asset) => { const assetStatus = asset.annotationStatus ?? 'UNLABELED'; return <article className="asset-card" key={asset.id}><img loading="lazy" src={`/media/${asset.storagePath.replace('uploads/', '')}`} alt={asset.filename} /><span className={`status-badge ${assetStatus.toLowerCase()}`}>{annotationStatusLabels[assetStatus]}</span><div><strong>{asset.filename}</strong><span>{asset.width} × {asset.height}</span></div><button aria-label={`移入回收站 ${asset.filename}`} className="icon-button" onClick={() => remove.mutate(asset.id)}><Trash2 size={16} /></button></article> })}</div> : <EmptyState title="还没有素材" message="导入图片后在此数据集中完成标注" />}</div></details>

    {assets.data?.data.length ? <DatasetAugmentationPreview assets={assets.data.data} /> : null}

    <section className="panel compact-form"><div className="panel-heading"><div><h2>创建训练版本</h2><p>至少 2 张素材且全部标注完成后即可冻结，无需审核步骤。</p></div></div><div className="form-row"><label>版本名称<input value={versionName} onChange={(event) => setVersionName(event.target.value)} /></label><button className="button primary" disabled={!canFreeze || !versionName.trim() || freeze.isPending} onClick={() => freeze.mutate()}><Plus size={16} />冻结版本</button></div><p className={`helper-text ${canFreeze ? '' : 'blocked'}`}>{freezeReason}</p>{freeze.error && <ErrorState message={freeze.error.message} />}{versions.isPending ? <LoadingRows /> : versions.isError ? <ErrorState message={versions.error.message} onRetry={() => versions.refetch()} /> : versions.data?.data.map((version) => <div className="table-row" key={version.id}><strong><Database size={16} />{version.name}</strong><span>{version.assetCount} 个素材</span><code>{version.contentHash.slice(0, 12)}</code><button className="button ghost" onClick={() => setConfirmation({ kind: 'version', id: version.id, name: version.name })}><Trash2 size={15} />删除</button></div>)}</section>
    <section className="panel"><button className="button danger" onClick={() => setConfirmation({ kind: 'dataset', name: item.name })}><Trash2 size={16} />删除数据集</button>{removeDataset.error && <ErrorState message={removeDataset.error.message} />}</section>
    <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.kind === 'dataset' ? '永久删除数据集？' : confirmation?.kind === 'version' ? '删除训练版本？' : '删除标签？'} description={confirmDescription} confirmLabel="确认删除" pending={confirmPending} onCancel={() => setConfirmation(null)} onConfirm={confirmAction} />
  </>
}
