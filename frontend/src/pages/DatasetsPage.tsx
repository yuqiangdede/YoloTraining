import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, FolderOpen, Plus, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './DatasetsPage.css'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { api, type TaskType } from '../lib/api'
import { taskLabels } from '../lib/labels'

function folderName(path: string) {
  return path.replace(/[\\/]+$/, '').split(/[\\/]/).at(-1) ?? ''
}

export function DatasetsPage() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const { notify } = useToast()
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets })

  const [dialogOpen, setDialogOpen] = useState(() => new URLSearchParams(window.location.search).get('create') === '1')
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [name, setName] = useState('')
  const [task, setTask] = useState<TaskType>('detect')
  const [keypointCount, setKeypointCount] = useState(17)
  const [categoryName, setCategoryName] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [categoryError, setCategoryError] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [search, setSearch] = useState('')
  const [taskFilter, setTaskFilter] = useState<'all' | TaskType>('all')
  const [importSourcePath, setImportSourcePath] = useState('')
  const [importName, setImportName] = useState('')
  const [importNameTouched, setImportNameTouched] = useState(false)
  const [importTrainRatio, setImportTrainRatio] = useState('0.8')
  const [importValRatio, setImportValRatio] = useState('0.2')
  const [importSeed, setImportSeed] = useState('0')
  const [importSubmitted, setImportSubmitted] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const importDialogRef = useRef<HTMLDialogElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const importPathRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (dialogOpen && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '')
      requestAnimationFrame(() => nameRef.current?.focus())
    }
    if (!dialogOpen && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open')
    }
  }, [dialogOpen])

  useEffect(() => {
    const dialog = importDialogRef.current
    if (!dialog) return
    if (importDialogOpen && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '')
      requestAnimationFrame(() => importPathRef.current?.focus())
    }
    if (!importDialogOpen && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open')
    }
  }, [importDialogOpen])

  const resetForm = () => {
    setName('')
    setTask('detect')
    setKeypointCount(17)
    setCategoryName('')
    setCategories([])
    setCategoryError('')
    setSubmitted(false)
  }
  const closeDialog = () => { setDialogOpen(false); resetForm() }
  const closeImportDialog = () => {
    setImportDialogOpen(false)
    setImportSourcePath('')
    setImportName('')
    setImportNameTouched(false)
    setImportTrainRatio('0.8')
    setImportValRatio('0.2')
    setImportSeed('0')
    setImportSubmitted(false)
  }

  const addCategory = () => {
    const next = categoryName.trim()
    if (!next) { setCategoryError('请输入类别名称。'); return }
    if (categories.some((item) => item.localeCompare(next, undefined, { sensitivity: 'accent' }) === 0)) {
      setCategoryError(`类别“${next}”已经存在。`)
      return
    }
    setCategories((items) => [...items, next])
    setCategoryName('')
    setCategoryError('')
  }

  const nameError = submitted && !name.trim() ? '请输入数据集名称。' : ''
  const categoriesError = submitted && categories.length === 0 ? '至少添加一个类别。' : ''
  const keypointError = submitted && task === 'pose' && (!Number.isInteger(keypointCount) || keypointCount < 1 || keypointCount > 1000)
    ? '关键点数量必须是 1–1000 的整数。' : ''
  const create = useMutation({
    mutationFn: () => api.createDataset({ name: name.trim(), task, categories: categories.map((category) => ({ name: category })), ...(task === 'pose' ? { keypointCount } : {}) }),
    onSuccess: ({ data }) => {
      client.invalidateQueries({ queryKey: ['datasets'] })
      notify(`数据集“${data.name ?? name}”已创建`)
      closeDialog()
      navigate(`/datasets/${data.id}`)
    },
  })

  const submit = () => {
    setSubmitted(true)
    if (!name.trim() || !categories.length || (task === 'pose' && (!Number.isInteger(keypointCount) || keypointCount < 1 || keypointCount > 1000))) return
    create.mutate()
  }

  const importTrain = Number(importTrainRatio)
  const importVal = Number(importValRatio)
  const importSeedValue = Number(importSeed)
  const importRatiosValid = Number.isFinite(importTrain) && Number.isFinite(importVal) && importTrain > 0 && importVal > 0 && Math.abs(importTrain + importVal - 1) < 1e-6
  const importFormError = importSubmitted
    ? (!importSourcePath.trim() ? '请输入 VOC 数据集目录路径。' : !importRatiosValid ? '训练集和验证集比例必须大于 0，且总和为 1。' : !Number.isInteger(importSeedValue) ? '随机种子必须是整数。' : '')
    : ''
  const importVoc = useMutation({
    mutationFn: () => api.importVoc({
      sourcePath: importSourcePath.trim(), name: importName.trim() || folderName(importSourcePath),
      trainRatio: importTrain, valRatio: importVal, seed: importSeedValue,
    }),
    onSuccess: ({ data }) => {
      client.invalidateQueries({ queryKey: ['datasets'] })
      closeImportDialog()
      notify(`已导入 ${data.report.importedImages} 张图片，训练 ${data.report.split.train} / 验证 ${data.report.split.val}，修复 ${data.report.repairedXml} 个 XML`)
      navigate(`/datasets/${data.dataset.id}`)
    },
  })
  const submitImport = () => {
    setImportSubmitted(true)
    if (importFormError) return
    importVoc.mutate()
  }

  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return (datasets.data?.data ?? []).filter((item) =>
      (taskFilter === 'all' || item.task === taskFilter) &&
      (!query || item.name.toLocaleLowerCase().includes(query) || item.categories.some((category) => category.name.toLocaleLowerCase().includes(query))),
    )
  }, [datasets.data?.data, search, taskFilter])

  return <>
    <PageHeader title="数据集" description="创建工作区，导入素材并推进到可训练版本" actions={<><button className="button secondary" onClick={() => setImportDialogOpen(true)}><FolderOpen size={16} />导入 VOC 数据集</button><button className="button primary" onClick={() => setDialogOpen(true)}><Plus size={16} />新建数据集</button></>} />

    <dialog ref={dialogRef} className="confirm-dialog create-dataset-dialog" aria-labelledby="create-dataset-title" onCancel={(event) => { event.preventDefault(); closeDialog() }} onClick={(event) => { if (event.target === event.currentTarget) closeDialog() }}>
      <form className="dialog-card" onSubmit={(event) => { event.preventDefault(); submit() }}>
        <button type="button" className="icon-button dialog-close" aria-label="关闭新建数据集" onClick={closeDialog}><X size={18} /></button>
        <h2 id="create-dataset-title">新建数据集</h2><p>任务类型创建后不可修改；类别仅属于当前数据集。</p>
        <div className="dialog-form">
          <label>名称<input ref={nameRef} value={name} maxLength={100} aria-invalid={Boolean(nameError)} onChange={(event) => setName(event.target.value)} />{nameError && <small className="field-error" role="alert">{nameError}</small>}</label>
          <label>任务<select value={task} onChange={(event) => setTask(event.target.value as TaskType)}><option value="detect">目标检测</option><option value="segment">实例分割</option><option value="semantic">语义分割</option><option value="pose">姿态估计</option><option value="obb">旋转框检测</option></select></label>
          {task === 'pose' && <label>关键点数量<input type="number" min="1" max="1000" value={keypointCount} aria-invalid={Boolean(keypointError)} onChange={(event) => setKeypointCount(Number(event.target.value))} />{keypointError && <small className="field-error" role="alert">{keypointError}</small>}</label>}
          <div className="category-editor"><label>类别名称<input value={categoryName} onChange={(event) => { setCategoryName(event.target.value); setCategoryError('') }} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addCategory() } }} /></label><button type="button" className="button secondary" onClick={addCategory}>添加类别</button>{(categoryError || categoriesError) && <small className="field-error" role="alert">{categoryError || categoriesError}</small>}<div className="category-tags" aria-label="已添加类别">{categories.map((category) => <span className="category-tag" key={category}><span className="category-name">{category}</span><button className="category-action category-action-danger" type="button" aria-label={`删除类别 ${category}`} onClick={() => setCategories((items) => items.filter((item) => item !== category))}><X size={13} />删除</button></span>)}</div></div>
        </div>
        {create.error && <ErrorState message={create.error.message} />}
        <div className="dialog-actions"><button type="button" className="button secondary" onClick={closeDialog}>取消</button><button className="button primary" disabled={create.isPending}>{create.isPending ? '正在创建…' : '创建数据集'}</button></div>
      </form>
    </dialog>

    <dialog ref={importDialogRef} className="confirm-dialog create-dataset-dialog" aria-labelledby="import-voc-title" onCancel={(event) => { event.preventDefault(); closeImportDialog() }} onClick={(event) => { if (event.target === event.currentTarget) closeImportDialog() }}>
      <form className="dialog-card" onSubmit={(event) => { event.preventDefault(); submitImport() }}>
        <button type="button" className="icon-button dialog-close" aria-label="关闭 VOC 导入" onClick={closeImportDialog}><X size={18} /></button>
        <h2 id="import-voc-title">导入 Pascal VOC 数据集</h2>
        <p>直接读取本机目录中的 JPEGImages 和 Annotations，忽略原有 ImageSets 划分并重新随机分配。</p>
        <div className="dialog-form">
          <label>VOC 数据集目录<input ref={importPathRef} value={importSourcePath} aria-invalid={Boolean(importSubmitted && !importSourcePath.trim())} placeholder={'H:\\BaiduNetdiskDownload\\SeaShips(7000)'} onChange={(event) => { const value = event.target.value; setImportSourcePath(value); if (!importNameTouched) setImportName(folderName(value)) }} />{importSubmitted && !importSourcePath.trim() && <small className="field-error" role="alert">请输入源数据目录。</small>}</label>
          <label>数据集名称<input value={importName} maxLength={100} onChange={(event) => { setImportNameTouched(true); setImportName(event.target.value) }} placeholder="默认使用目录名称" /></label>
          <div className="form-row"><label>训练集比例<input type="number" min="0.01" max="0.99" step="0.01" value={importTrainRatio} aria-invalid={Boolean(importSubmitted && !importRatiosValid)} onChange={(event) => setImportTrainRatio(event.target.value)} /></label><label>验证集比例<input type="number" min="0.01" max="0.99" step="0.01" value={importValRatio} aria-invalid={Boolean(importSubmitted && !importRatiosValid)} onChange={(event) => setImportValRatio(event.target.value)} /></label><label>随机种子<input type="number" step="1" value={importSeed} aria-invalid={Boolean(importSubmitted && !Number.isInteger(importSeedValue))} onChange={(event) => setImportSeed(event.target.value)} /></label></div>
          {importSubmitted && importFormError && <small className="field-error" role="alert">{importFormError}</small>}
        </div>
        {importVoc.error && <ErrorState message={importVoc.error.message} />}
        <div className="dialog-actions"><button type="button" className="button secondary" disabled={importVoc.isPending} onClick={closeImportDialog}>取消</button><button className="button primary" disabled={importVoc.isPending}>{importVoc.isPending ? '正在导入，请稍候…' : '开始一键导入'}</button></div>
      </form>
    </dialog>

    <section className="panel"><div className="panel-heading"><div><h2>数据集工作区</h2><p>{datasets.data ? `${datasets.data.data.length} 个数据集` : '加载工作区'}</p></div></div>
      <div className="filterbar"><label><span>搜索名称或类别</span><span className="search"><Search size={16} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></span></label><label>任务<select value={taskFilter} onChange={(event) => setTaskFilter(event.target.value as 'all' | TaskType)}><option value="all">全部任务</option>{Object.entries(taskLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
      {datasets.isPending ? <LoadingRows /> : datasets.isError ? <ErrorState message={datasets.error.message} onRetry={() => datasets.refetch()} /> : filtered.length ? <div className="dataset-card-grid">{filtered.map((item) => <Link className="dataset-card" key={item.id} to={`/datasets/${item.id}`}><div><Database size={19} /><h3>{item.name}</h3></div><div className="dataset-card-meta"><span>{taskLabels[item.task]}</span><span>{item.assetCount} 个素材</span><span>{item.annotationCounts.reviewed} 个已审核</span></div><div className="dataset-card-categories">{item.categories.map((category) => category.name).join('、')}</div></Link>)}</div> : <EmptyState title={datasets.data.data.length ? '没有匹配的数据集' : '还没有数据集'} message={datasets.data.data.length ? '尝试清除搜索或切换任务类型。' : '新建数据集后即可导入素材。'} action={!datasets.data.data.length ? <button className="button primary" onClick={() => setDialogOpen(true)}><Plus size={16} />新建数据集</button> : undefined} />}
    </section>
  </>
}
