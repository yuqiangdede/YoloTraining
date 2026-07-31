import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Save, Search, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AnnotationCanvas, type Shape } from '../components/AnnotationCanvas'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { api, type AnnotationStatus } from '../lib/api'
import { annotationStatusLabels } from '../lib/labels'

export function AnnotationPage() {
  const { datasetId = '' } = useParams()
  const client = useQueryClient()
  const navigate = useNavigate()
  const { notify } = useToast()
  const [selectedId, setSelectedId] = useState(() => new URLSearchParams(window.location.search).get('asset') ?? '')
  const [shapes, setShapes] = useState<Shape[]>([])
  const [labelId, setLabelId] = useState('')
  const [dirty, setDirty] = useState(false)
  const [page, setPage] = useState(1)
  const [rawSearch, setRawSearch] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'ALL' | AnnotationStatus>('ALL')
  const [discardOpen, setDiscardOpen] = useState(false)
  const pendingTransition = useRef<(() => void) | null>(null)
  const assets = useQuery({ queryKey: ['assets', datasetId, page, search, status], queryFn: () => api.assets(datasetId, page, search, status === 'ALL' ? [] : [status]) })
  const dataset = useQuery({ queryKey: ['dataset', datasetId], queryFn: () => api.dataset(datasetId) })
  const selected = assets.data?.data.find((asset) => asset.id === selectedId) ?? assets.data?.data[0]
  const item = dataset.data?.data

  const requestTransition = useCallback((action: () => void) => {
    if (!dirty) { action(); return }
    pendingTransition.current = action
    setDiscardOpen(true)
  }, [dirty])
  const discardAndContinue = () => {
    setDirty(false); setDiscardOpen(false)
    const action = pendingTransition.current
    pendingTransition.current = null
    action?.()
  }

  const save = useMutation({
    mutationFn: (status: 'DRAFT' | 'COMPLETED') => api.saveAnnotation(datasetId, selected!.id, { assetId: selected!.id, task: item!.task, imageWidth: selected!.width, imageHeight: selected!.height, status, shapes }),
    onSuccess: () => {
      setDirty(false)
      notify('标注已保存')
      const items = assets.data?.data ?? []
      const index = items.findIndex((asset) => asset.id === selected?.id)
      const next = [...items.slice(index + 1), ...items.slice(0, index)].find((asset) => !['COMPLETED', 'REVIEWED'].includes(asset.annotationStatus))
      if (next) setSelectedId(next.id)
      client.invalidateQueries({ queryKey: ['assets', datasetId] })
      client.invalidateQueries({ queryKey: ['dataset', datasetId] })
    },
  })
  const upload = useMutation({ mutationFn: (files: FileList) => api.uploadAssets(datasetId, files), onSuccess: ({ data }) => { setPage(1); if (!dirty && data[0]) setSelectedId(data[0].id); client.invalidateQueries({ queryKey: ['assets', datasetId] }); client.invalidateQueries({ queryKey: ['dataset', datasetId] }); notify(`已添加 ${data.length} 张素材`) } })

  useEffect(() => { if (selected && !selectedId) setSelectedId(selected.id) }, [selected, selectedId])
  useEffect(() => { if (!labelId && item?.categories[0]) setLabelId(item.categories[0].id) }, [item, labelId])
  useEffect(() => {
    if (!selected) return
    let active = true
    api.getAnnotation(datasetId, selected.id).then(({ data }) => { if (active) { setShapes((data?.shapes as Shape[]) ?? []); setDirty(false) } }).catch(() => { if (active) { setShapes([]); setDirty(false) } })
    return () => { active = false }
  }, [datasetId, selected?.id])
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (rawSearch === search) return
      requestTransition(() => { setSearch(rawSearch); setPage(1); setSelectedId('') })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [rawSearch, requestTransition, search])
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = '' } }
    const keyboard = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (dirty && selected && !save.isPending) save.mutate('DRAFT') } }
    window.addEventListener('beforeunload', beforeUnload)
    window.addEventListener('keydown', keyboard)
    return () => { window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('keydown', keyboard) }
  }, [dirty, save, selected])

  const changePage = (next: number) => requestTransition(() => { setPage(next); setSelectedId('') })
  const changeStatus = (next: 'ALL' | AnnotationStatus) => requestTransition(() => { setStatus(next); setPage(1); setSelectedId('') })
  const uploadAction = <label className="button secondary"><Upload size={16} />添加素材<input aria-label="添加素材" type="file" accept="image/*" multiple hidden onChange={(event) => event.target.files && upload.mutate(event.target.files)} /></label>
  const backAction = <button className="button secondary" onClick={() => requestTransition(() => navigate(`/datasets/${datasetId}`))}>返回数据集</button>

  if (dataset.isPending || assets.isPending) return <LoadingRows />
  if (dataset.isError) return <ErrorState message={dataset.error.message} onRetry={() => dataset.refetch()} />
  if (assets.isError) return <ErrorState message={assets.error.message} onRetry={() => assets.refetch()} />
  if (!item || !selected) return <><PageHeader title="人工标注" description="按页加载素材，适用于大型数据集" actions={<>{backAction}{uploadAction}</>} />{upload.error && <ErrorState message={upload.error.message} />}<EmptyState title="没有匹配的素材" message={search || status !== 'ALL' ? '清除搜索或状态筛选后重试。' : '请添加图片后开始标注。'} /></>
  const pagination = assets.data?.pagination

  return <>
    <PageHeader title={`${item.name} · 人工标注`} description={`共 ${pagination?.totalItems ?? 0} 张素材，支持状态筛选与 Ctrl+S 保存`} actions={<>{backAction}{uploadAction}<button className="button secondary" disabled={save.isPending || !dirty} onClick={() => save.mutate('DRAFT')}><Save size={16} />保存草稿</button><button className="button primary" disabled={save.isPending || !dirty} onClick={() => save.mutate('COMPLETED')}><Save size={16} />完成标注</button></>} />
    <div className="annotation-layout annotation-layout-dense">
      <aside className="annotation-list" aria-label="素材列表">
        <div className="annotation-list-tools"><label className="annotation-search"><Search size={14} /><input aria-label="搜索素材" value={rawSearch} onChange={(event) => setRawSearch(event.target.value)} placeholder="搜索文件名" /></label><select className="annotation-filter" aria-label="标注状态" value={status} onChange={(event) => changeStatus(event.target.value as 'ALL' | AnnotationStatus)}><option value="ALL">全部状态</option>{Object.entries(annotationStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><div><button aria-label="上一页" disabled={page <= 1} onClick={() => changePage(page - 1)}><ChevronLeft size={15} /></button><span>{page}/{pagination?.totalPages || 1}</span><button aria-label="下一页" disabled={!pagination || page >= pagination.totalPages} onClick={() => changePage(page + 1)}><ChevronRight size={15} /></button></div></div>
        {assets.data.data.map((asset) => { const assetStatus = asset.annotationStatus ?? 'UNLABELED'; return <button key={asset.id} className={asset.id === selected.id ? 'selected' : ''} onClick={() => requestTransition(() => setSelectedId(asset.id))}><img loading="lazy" src={`/media/${asset.storagePath.replace('uploads/', '')}`} alt="" /><span className="annotation-list-item-copy"><span>{asset.filename}</span><span className={`status-badge ${assetStatus.toLowerCase()}`}>{annotationStatusLabels[assetStatus]}</span></span></button> })}
      </aside>
      <section className="annotation-workspace"><div className="annotation-controls"><label>类别<select value={labelId} onChange={(event) => setLabelId(event.target.value)}>{item.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><span className={`annotation-save-state ${dirty ? 'is-dirty' : 'is-saved'}`} role="status">{dirty ? '未保存修改' : '修改已保存'} · 草稿与完成状态分离</span></div><AnnotationCanvas asset={selected} task={item.task} labelId={labelId} categories={item.categories} shapes={shapes} onChange={(next) => { setShapes(next); setDirty(true) }} />{save.error && <ErrorState message={save.error.message} />}</section>
    </div>
    <ConfirmDialog open={discardOpen} danger={false} title="放弃未保存的标注？" description="切换素材、翻页、筛选或返回会丢失当前修改。你可以先取消并使用 Ctrl+S 保存。" confirmLabel="放弃修改" onCancel={() => { setDiscardOpen(false); pendingTransition.current = null }} onConfirm={discardAndContinue} />
  </>
}
