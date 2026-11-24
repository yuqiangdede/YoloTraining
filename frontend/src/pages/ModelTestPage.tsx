import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, Film, ImagePlus, ScanSearch, Upload, XCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { api, type PredictionResult } from '../lib/api'
import { taskLabels } from '../lib/labels'
import { rfDetrLabel } from '../lib/modelCatalog'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const MAX_VIDEO_BYTES = 500 * 1024 * 1024
type TestMode = 'image' | 'video'

export function ModelTestPage() {
  const models = useQuery({ queryKey: ['models'], queryFn: api.models })
  const exports = useQuery({ queryKey: ['exports'], queryFn: api.exports, refetchInterval: 2000 })
  const [mode, setMode] = useState<TestMode>('image')
  const [selectedId, setSelectedId] = useState(() => new URLSearchParams(window.location.search).get('model') ?? '')
  const [modelFormat, setModelFormat] = useState<'pt' | 'onnx'>(() => new URLSearchParams(window.location.search).get('format') === 'onnx' ? 'onnx' : 'pt')
  const [confidence, setConfidence] = useState(0.25)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [videoPreview, setVideoPreview] = useState('')
  const [localError, setLocalError] = useState('')
  const [result, setResult] = useState<PredictionResult | null>(null)
  const [videoJobId, setVideoJobId] = useState('')
  const selectedArtifact = models.data?.data.find((model) => model.id === selectedId)
  const isRfDetr = selectedArtifact?.engine === 'rfdetr'
  const pretrainedId = selectedId.startsWith('pretrained:') ? selectedId.slice('pretrained:'.length) : ''
  const selectedPretrained = models.data?.pretrained.find((model) => model.id === pretrainedId && model.canTest)
  const selectedExport = exports.data?.data.find((item) => item.artifactId === selectedId && item.status === 'SUCCEEDED' && item.outputPath)
  const canUseOnnx = Boolean(selectedArtifact && selectedExport && !isRfDetr)
  const testablePretrained = useMemo(() => models.data?.pretrained.filter((model) => model.canTest) ?? [], [models.data?.pretrained])
  const predict = useMutation({
    mutationFn: () => selectedPretrained ? api.predictPretrained(selectedPretrained.id, imageFile!, confidence) : api.predict(selectedId, imageFile!, confidence, modelFormat),
    onSuccess: ({ data }) => setResult(data),
  })
  const createVideo = useMutation({
    mutationFn: () => api.createVideoJob(selectedId, videoFile!, confidence, modelFormat),
    onSuccess: (job) => setVideoJobId(job.id),
  })
  const cancelVideo = useMutation({ mutationFn: () => api.cancelVideoJob(videoJobId) })
  const videoJobQuery = useQuery({
    queryKey: ['video-job', videoJobId],
    queryFn: () => api.videoJob(videoJobId),
    enabled: mode === 'video' && Boolean(videoJobId),
    refetchInterval: (videoJobQuery) => ['QUEUED', 'RUNNING'].includes(videoJobQuery.state.data?.status ?? '') ? 2000 : false,
  })
  const videoJob = videoJobQuery.data

  useEffect(() => {
    if (selectedId || !models.data) return
    if (models.data.data[0]) setSelectedId(models.data.data[0].id)
    else if (testablePretrained[0]) setSelectedId(`pretrained:${testablePretrained[0].id}`)
  }, [models.data, selectedId, testablePretrained])
  useEffect(() => {
    if (!imageFile) { setPreview(''); return }
    const url = URL.createObjectURL(imageFile); setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [imageFile])
  useEffect(() => {
    if (!videoFile) { setVideoPreview(''); return }
    const url = URL.createObjectURL(videoFile); setVideoPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [videoFile])
  useEffect(() => { if ((modelFormat === 'onnx' && !canUseOnnx) || selectedPretrained) setModelFormat('pt') }, [canUseOnnx, modelFormat, selectedPretrained])
  useEffect(() => { if (isRfDetr) setMode('image') }, [isRfDetr])

  const clearResult = () => {
    setResult(null); setVideoJobId(''); predict.reset(); createVideo.reset(); cancelVideo.reset()
  }
  const selectFile = (candidate: File | undefined) => {
    setLocalError(''); clearResult()
    if (!candidate) return
    const suffix = candidate.name.slice(candidate.name.lastIndexOf('.')).toLowerCase()
    if (mode === 'image') {
      if (!candidate.type.startsWith('image/')) { setImageFile(null); setLocalError('请上传 JPG、PNG、WebP 等图片文件。'); return }
      if (candidate.size > MAX_IMAGE_BYTES) { setImageFile(null); setLocalError('图片大小不能超过 10 MB。'); return }
      setImageFile(candidate)
    } else {
      if (!candidate.type.startsWith('video/') && !['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'].includes(suffix)) { setVideoFile(null); setLocalError('请上传 MP4、MOV、AVI、MKV 或 WebM 视频。'); return }
      if (candidate.size > MAX_VIDEO_BYTES) { setVideoFile(null); setLocalError('视频大小不能超过 500 MB。'); return }
      setVideoFile(candidate)
    }
  }
  const switchMode = (nextMode: TestMode) => { setMode(nextMode); setLocalError(''); clearResult() }
  const selectedName = selectedArtifact?.name ?? selectedPretrained?.name
  const selectedTask = selectedArtifact?.task ?? selectedPretrained?.task
  const hasTestable = Boolean(models.data?.data.length || testablePretrained.length)
  const activeFile = mode === 'image' ? imageFile : videoFile
  const videoBusy = createVideo.isPending || ['QUEUED', 'RUNNING'].includes(videoJob?.status ?? '')

  return <>
    <PageHeader title="模型测试" description="使用训练产物或官方 YOLO 模型进行图片测试和视频逐帧推理" actions={<Link className="button secondary" to="/models"><ArrowLeft size={16} />返回模型结果</Link>} />
    {(models.isPending || exports.isPending) && <LoadingRows />}
    {models.isError && <ErrorState message={models.error.message} onRetry={() => models.refetch()} />}
    {exports.isError && <ErrorState message={exports.error.message} onRetry={() => exports.refetch()} />}
    {!models.isPending && !models.isError && !hasTestable && <EmptyState title="暂无可测试模型" message="可以先完成一次训练，或将官方 YOLO 权重放入 models/pretrained。SAM3 不支持无提示词推理。" action={<Link className="button secondary" to="/training">前往训练任务</Link>} />}
    {hasTestable && <>
      <section className="panel compact-form model-test-controls">
        <div className="panel-heading"><div><h2><ScanSearch size={18} />选择模型与输入</h2><p>图片和视频只用于本次推理，不会加入数据集；视频任务会在后台逐帧处理。</p></div></div>
        <div className="test-mode-tabs" role="tablist" aria-label="推理模式">
          <button className={mode === 'image' ? 'button primary' : 'button secondary'} role="tab" aria-selected={mode === 'image'} onClick={() => switchMode('image')}><ImagePlus size={16} />图片测试</button>
          {!isRfDetr && <button className={mode === 'video' ? 'button primary' : 'button secondary'} role="tab" aria-selected={mode === 'video'} onClick={() => switchMode('video')}><Film size={16} />视频推理</button>}
        </div>
        <div className="form-grid">
          <label>测试模型<select value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setModelFormat('pt'); clearResult() }}><option value="">请选择模型</option>{models.data?.data.length ? <optgroup label="训练产物">{models.data.data.map((model) => <option key={model.id} value={model.id}>{model.engine === 'rfdetr' && `${rfDetrLabel(model.modelVariant)} · `}{model.name} · {taskLabels[model.task]}</option>)}</optgroup> : null}{testablePretrained.length ? <optgroup label="官方预训练模型">{testablePretrained.map((model) => <option key={model.id} value={`pretrained:${model.id}`}>{model.name} · {taskLabels[model.task]}</option>)}</optgroup> : null}</select></label>
          <label>模型格式<select value={modelFormat} disabled={Boolean(selectedPretrained) || isRfDetr} onChange={(event) => { setModelFormat(event.target.value as 'pt' | 'onnx'); clearResult() }}><option value="pt">{isRfDetr ? 'PTH 权重' : 'PT 权重'}</option>{!isRfDetr && <option value="onnx" disabled={!canUseOnnx}>ONNX 导出{canUseOnnx ? '' : '（未完成）'}</option>}</select></label>
          <label>置信度<input type="number" min="0" max="1" step="0.05" value={confidence} aria-invalid={confidence < 0 || confidence > 1} onChange={(event) => { setConfidence(Number(event.target.value)); clearResult() }} />{(confidence < 0 || confidence > 1) && <small className="field-error">请输入 0–1 之间的数值。</small>}</label>
          <div className="model-test-upload"><span>{mode === 'image' ? '测试图片' : '输入视频'}</span><label className="button secondary" htmlFor="test-media"><Upload size={16} />{activeFile ? '重新选择文件' : '选择文件'}</label><input id="test-media" aria-label={mode === 'image' ? '选择测试图片' : '选择测试视频'} className="sr-only" type="file" accept={mode === 'image' ? 'image/*' : 'video/*,.mkv'} onChange={(event) => selectFile(event.target.files?.[0])} /></div>
          <button className="button primary model-test-submit" disabled={!selectedId || !activeFile || confidence < 0 || confidence > 1 || (mode === 'image' ? predict.isPending : videoBusy)} onClick={() => mode === 'image' ? predict.mutate() : createVideo.mutate()}>{mode === 'image' ? <><ScanSearch size={16} />{predict.isPending ? '正在推理…' : result ? '重新测试' : '开始测试'}</> : <><Film size={16} />{createVideo.isPending ? '正在上传…' : videoBusy ? '视频处理中…' : '开始视频推理'}</>}</button>
        </div>
        {selectedName && <p className="quiet-state model-test-model">当前模型：{selectedName} · {selectedTask ? taskLabels[selectedTask] : ''} · {isRfDetr ? 'PTH' : modelFormat.toUpperCase()}{selectedPretrained ? ' · 官方预训练模型' : ' · 训练产物'}</p>}
        {activeFile && <p role="status" className="helper-text">已选择 {activeFile.name}，大小 {(activeFile.size / 1024 / 1024).toFixed(2)} MB。</p>}
        {localError && <ErrorState message={localError} />}
        {predict.error && mode === 'image' && <ErrorState message={predict.error.message} />}
        {createVideo.error && <ErrorState message={createVideo.error.message} />}
        {videoJobQuery.error && <ErrorState message={videoJobQuery.error.message} />}
      </section>
      {mode === 'image' && (preview || result) && <section className="model-test-result" aria-live="polite"><div className="panel model-test-image-panel"><div className="panel-heading"><div><h2>原图</h2><p>{imageFile?.name}</p></div></div>{preview && <img className="model-test-image" src={preview} alt="待测试图片" />}</div><div className="panel model-test-image-panel"><div className="panel-heading"><div><h2>推理结果</h2><p>{result ? `${result.predictions.length} 个结果 · ${result.image.width} × ${result.image.height}` : predict.isPending ? '正在生成结果' : '点击开始测试查看结果'}</p></div></div>{result ? <img className="model-test-image" src={result.annotatedImage} alt="模型推理叠加结果" /> : <div className="model-test-placeholder"><ImagePlus size={28} /><span>结果将在这里显示</span></div>}</div></section>}
      {mode === 'image' && result && <section className="panel"><div className="panel-heading"><div><h2>预测明细</h2><p>{result.predictions.length ? '按模型返回顺序展示预测。' : '没有达到当前置信度的预测结果。'}</p></div><span className="badge succeeded">{result.predictions.length} 个结果</span></div>{result.predictions.length > 0 && <div className="table model-test-predictions"><div className="table-head"><span>类别</span><span>置信度</span><span>类型</span><span>位置点</span></div>{result.predictions.map((prediction, index) => <div className="table-row" key={`${prediction.label}-${index}`}><strong>{prediction.label}</strong><span>{(prediction.confidence * 100).toFixed(1)}%</span><span>{prediction.kind}</span><code>{prediction.points.length} 个点</code></div>)}</div>}</section>}
      {mode === 'video' && videoFile && <section className="model-test-result video-test-result" aria-live="polite"><div className="panel model-test-image-panel"><div className="panel-heading"><div><h2>原视频</h2><p>{videoFile.name}</p></div></div>{videoPreview ? <video className="model-test-video" controls muted src={videoPreview} /> : <div className="model-test-placeholder"><Film size={28} /><span>正在加载视频预览</span></div>}</div><div className="panel model-test-image-panel"><div className="panel-heading"><div><h2>叠加结果</h2><p>{videoJob ? videoJob.status === 'SUCCEEDED' ? '处理完成' : videoJob.status === 'FAILED' ? '处理失败' : `正在处理 ${videoJob.progress}% · ${videoJob.currentFrame}/${videoJob.totalFrames || '未知'} 帧` : '提交任务后显示结果'}</p></div></div>{videoJob?.status === 'SUCCEEDED' && videoJob.downloadUrl ? <><video className="model-test-video" controls src={videoJob.downloadUrl} /><a className="button secondary video-download" href={videoJob.downloadUrl} download><Download size={16} />下载叠加视频</a></> : <div className="model-test-placeholder"><Film size={28} /><span>{videoJob?.status === 'FAILED' ? videoJob.errorMessage : videoBusy ? `视频处理中 ${videoJob?.progress ?? 0}%` : '结果将在这里显示'}</span></div>}{videoJob?.status === 'FAILED' && <p className="field-error">请检查视频编码、模型文件和 FFmpeg 配置后重试。</p>}{videoJob && ['QUEUED', 'RUNNING'].includes(videoJob.status) && <button className="button secondary" onClick={() => cancelVideo.mutate()} disabled={cancelVideo.isPending}><XCircle size={16} />取消任务</button>}</div></section>}
    </>}
  </>
}
