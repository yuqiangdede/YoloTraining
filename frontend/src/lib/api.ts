export type TaskType = 'detect' | 'segment' | 'semantic' | 'pose' | 'obb'
export type PrelabelMode = 'yolo' | 'yolo_sam' | 'sam'
export type AnnotationStatus = 'UNLABELED' | 'DRAFT' | 'COMPLETED' | 'REVIEWED'

export interface CreatePrelabelInput {
  modelPath: string
  task: TaskType
  assetIds: string[]
  confidence: number
  mode: PrelabelMode
}

export interface PrelabelJob {
  id: string
  datasetId: string | null
  modelPath: string
  task: TaskType
  status: string
  params: Record<string, unknown>
  result: { applied?: number; skipped?: number; unmatchedCategories?: Record<string, number> }
  errorMessage?: string | null
  createdAt: string
}

export interface Asset {
  id: string
  filename: string
  storagePath: string
  width: number
  height: number
  sizeBytes: number
  tags: string[]
  annotationStatus: AnnotationStatus
  isDeleted?: boolean
  createdAt: string
}

export interface Pagination { page: number; pageSize: number; totalItems: number; totalPages: number }

export interface Dataset {
  id: string
  projectId: string
  name: string
  task: TaskType
  assetCount: number
  annotationCounts: { unlabeled: number; draft: number; completed: number; reviewed: number }
  categories: Category[]
  keypointCount: number | null
  flipIdx: number[] | null
  createdAt: string
  updatedAt: string
  prelabelModelPath: string | null
  prelabelMode: PrelabelMode
  prelabelConfidence: number
}

export interface Project {
  id: string
  name: string
  description: string
  datasetCount: number
  trainingCount: number
  modelCount: number
  createdAt: string
  updatedAt: string
}

export interface Category {
  id: string
  name: string
  color: string
  createdAt: string
}

export interface DatasetVersion {
  id: string
  datasetId: string
  name: string
  task: TaskType
  assetCount: number
  contentHash: string
  createdAt: string
  parentVersionId?: string | null
  quality?: QualityReport
  source?: Record<string, unknown>
}

export interface QualityIssue { code: string; severity: 'BLOCKING' | 'WARNING' | 'INFO'; message: string; assetIds?: string[]; details?: Record<string, unknown> }
export interface QualityReport { status: 'PASS' | 'WARNING' | 'BLOCKED'; generatedAt: string; assetCount: number; annotatedCount: number; completedCount: number; annotationCount: number; classCounts: Record<string, number>; issues: QualityIssue[] }
export interface DatasetExport { id: string; datasetId: string; versionId: string; format: string; status: string; outputPath?: string | null; errorMessage?: string | null; createdAt: string }

export interface VocImportRequest {
  sourcePath: string
  name?: string
  trainRatio?: number
  valRatio?: number
  seed?: number
}

export interface VocImportReport {
  sourceFormat: 'VOC'
  totalImages: number
  importedImages: number
  annotationCount: number
  categories: string[]
  repairedXml: number
  repairedFiles: string[]
  split: { train: number; val: number; test: number }
  seed: number
}

export interface TrainingJob {
  id: string
  name: string
  task: TaskType
  modelPath: string
  status: string
  progress: number
  currentEpoch: number
  params: Record<string, unknown>
  errorMessage?: string | null
  queuePosition?: number
  queueSize?: number
  waitSeconds?: number
  createdAt: string
}

export type TrainingQualityState = 'SUFFICIENT' | 'INCOMPLETE' | 'NOT_READY'

export interface TrainingQuality {
  state: TrainingQualityState
  primaryMetric: string | null
  bestEpoch: number | null
  bestValue: number | null
  finalValue: number | null
  validationMetrics: Record<string, number>
  lossMetrics: Record<string, number>
  notes: string[]
}

export interface WorkerHealth {
  alive: boolean
  currentJobId: string | null
  currentKind: string | null
  currentStartedAt: string | null
  lastActivityAt: string | null
  lastError: string | null
}

export interface ModelArtifact {
  id: string
  trainingJobId: string
  name: string
  task: TaskType
  path: string
  kind: string
  sha256: string
  metrics: Record<string, string | number>
  trainingQuality?: TrainingQuality
}

export interface TrainingArtifact extends ModelArtifact {
  createdAt?: string
}

export interface PretrainedModel {
  id: string
  name: string
  path: string
  kind: 'PRETRAINED'
  task: TaskType
  canTest: boolean
  sizeBytes: number
}

export interface PredictionRow {
  label: string
  confidence: number
  kind: 'rectangle' | 'polygon' | 'keypoints'
  points: number[][]
}

export interface PredictionResult {
  model: { id: string; name: string; format: 'pt' | 'onnx'; task: TaskType }
  image: { width: number; height: number; mimeType: string }
  annotatedImage: string
  predictions: PredictionRow[]
}

export interface VideoInferenceJob {
  id: string
  modelId: string
  modelFormat: 'pt' | 'onnx'
  task: TaskType
  status: string
  progress: number
  currentFrame: number
  totalFrames: number
  fps: number | null
  width: number | null
  height: number | null
  params: { confidence: number; sourceName?: string }
  errorMessage?: string | null
  outputPath?: string | null
  downloadUrl?: string | null
  createdAt: string
  updatedAt: string
}

export interface BackupRecord {
  label: string
  path: string
  createdAt: string
  sizeBytes: number
}

export class ApiError extends Error {
  constructor(message: string, public code = 'REQUEST_FAILED', public details?: unknown) { super(message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  const body = await response.json()
  if (!response.ok) {
    const error = body.error ?? body.detail ?? {}
    throw new ApiError(error.message ?? '请求失败', error.code, error.details)
  }
  return body as T
}

export const api = {
  health: () => request<{ status: string; projectRoot: string }>('/health'),
  environment: () => request<{ python: string; gpu: { isAvailable: boolean; name: string | null; cuda: string | null; memoryBytes: number | null }; disk: { totalBytes: number; freeBytes: number }; projectRoot: string; venvIsLocal: boolean }>('/system/environment'),
  projects: () => request<{ data: Project[] }>('/projects'),
  project: (id: string) => request<{ data: Project }>(`/projects/${id}`),
  createProject: (body: { name: string; description?: string }) => request<{ data: Project }>('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  datasets: (projectId?: string) => request<{ data: Dataset[] }>(`/datasets${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  dataset: (id: string) => request<{ data: Dataset }>(`/datasets/${id}`),
  datasetSummary: (id: string) => request<{ data: { dataset: Dataset; quality: QualityReport; versions: number } }>(`/datasets/${id}/summary`),
  datasetQuality: (id: string) => request<{ data: QualityReport }>(`/datasets/${id}/quality`),
  checkDatasetQuality: (id: string) => request<{ data: QualityReport }>(`/datasets/${id}/quality/check`, { method: 'POST' }),
  createDataset: (body: unknown) => request<{ data: Dataset }>('/datasets', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  importVoc: (body: VocImportRequest) => request<{ data: { dataset: Dataset; version: DatasetVersion; report: VocImportReport } }>('/datasets/imports/voc', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  updateDataset: (id: string, body: { name: string; prelabelModelPath?: string | null; prelabelMode?: PrelabelMode; prelabelConfidence?: number }) => request<{ data: Dataset }>(`/datasets/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  deleteDataset: (id: string) => request(`/datasets/${id}`, { method: 'DELETE' }),
  assets: (datasetId: string, page = 1, search = '', annotationStatuses: AnnotationStatus[] = []) => {
    const params = new URLSearchParams({ page: String(page), pageSize: '100' })
    if (search) params.set('search', search)
    annotationStatuses.forEach((value) => params.append('annotationStatus', value))
    return request<{ data: Asset[]; pagination: Pagination }>(`/datasets/${datasetId}/assets?${params}`)
  },
  categories: (datasetId: string) => request<{ data: Category[] }>(`/datasets/${datasetId}/categories`),
  createCategory: (datasetId: string, name: string) => request<{ data: Category }>(`/datasets/${datasetId}/categories`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  updateCategory: (datasetId: string, categoryId: string, name: string) => request<{ data: Category }>(`/datasets/${datasetId}/categories/${categoryId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  deleteCategory: (datasetId: string, categoryId: string) => request(`/datasets/${datasetId}/categories/${categoryId}`, { method: 'DELETE' }),
  uploadAssets: (datasetId: string, files: FileList) => {
    const form = new FormData()
    Array.from(files).forEach((file) => form.append('files', file))
    return request<{ data: Asset[]; duplicates: string[] }>(`/datasets/${datasetId}/assets`, { method: 'POST', body: form })
  },
  recycleAsset: (datasetId: string, id: string) => request(`/datasets/${datasetId}/assets/${id}`, { method: 'DELETE' }),
  restoreAsset: (datasetId: string, id: string) => request<Asset>(`/datasets/${datasetId}/assets/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ isDeleted: false }) }),
  getAnnotation: (datasetId: string, id: string) => request<{ data: Record<string, unknown> | null }>(`/datasets/${datasetId}/assets/${id}/annotation`),
  saveAnnotation: (datasetId: string, id: string, document: unknown) => request(`/datasets/${datasetId}/assets/${id}/annotation`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(document),
  }),
  datasetVersions: (datasetId: string) => request<{ data: DatasetVersion[] }>(`/datasets/${datasetId}/versions`),
  deleteDatasetVersion: (datasetId: string, versionId: string) => request(`/datasets/${datasetId}/versions/${versionId}`, { method: 'DELETE' }),
  allDatasetVersions: () => request<{ data: DatasetVersion[] }>('/datasets/versions/all'),
  createDatasetVersion: (datasetId: string, body: unknown) => request<DatasetVersion>(`/datasets/${datasetId}/versions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  datasetVersion: (datasetId: string, versionId: string) => request<{ data: DatasetVersion }>(`/datasets/${datasetId}/versions/${versionId}`),
  copyDatasetVersion: (datasetId: string, versionId: string, body: unknown) => request<{ data: DatasetVersion }>(`/datasets/${datasetId}/versions/${versionId}/copy`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  datasetExports: (datasetId: string) => request<{ data: DatasetExport[] }>(`/datasets/${datasetId}/exports`),
  createDatasetExport: (datasetId: string, versionId: string, format: 'yolo' | 'coco' | 'voc' | 'platform_json') => request<DatasetExport>(`/datasets/${datasetId}/versions/${versionId}/exports`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ format }) }),
  jobs: () => request<{ data: TrainingJob[]; worker: WorkerHealth }>('/training-jobs'),
  createJob: (body: unknown) => request<TrainingJob>('/training-jobs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  jobAction: (id: string, action: 'pause' | 'resume' | 'cancel') => request<TrainingJob>(`/training-jobs/${id}/${action}`, { method: 'POST' }),
  deleteJob: (id: string) => request(`/training-jobs/${id}`, { method: 'DELETE' }),
  jobLog: (id: string) => request<{ content: string; sizeBytes: number }>(`/training-jobs/${id}/log`),
  artifacts: (jobId: string) => request<{ data: TrainingArtifact[] }>(`/training-jobs/${jobId}/artifacts`),
  models: () => request<{ data: ModelArtifact[]; pretrained: PretrainedModel[] }>('/models'),
  deleteModel: (id: string) => request(`/models/${id}`, { method: 'DELETE' }),
  predict: (artifactId: string, image: File, confidence = 0.25, format: 'pt' | 'onnx' = 'pt') => {
    const form = new FormData()
    form.append('image', image)
    form.append('confidence', String(confidence))
    form.append('format', format)
    return request<{ data: PredictionResult }>(`/models/${artifactId}/predict`, { method: 'POST', body: form })
  },
  predictPretrained: (modelId: string, image: File, confidence = 0.25) => {
    const form = new FormData()
    form.append('image', image)
    form.append('confidence', String(confidence))
    return request<{ data: PredictionResult }>(`/models/pretrained/${encodeURIComponent(modelId)}/predict`, { method: 'POST', body: form })
  },
  createVideoJob: (modelId: string, video: File, confidence = 0.25, format: 'pt' | 'onnx' = 'pt') => {
    const form = new FormData()
    form.append('modelId', modelId)
    form.append('video', video)
    form.append('confidence', String(confidence))
    form.append('format', format)
    return request<VideoInferenceJob>('/models/video-jobs', { method: 'POST', body: form })
  },
  videoJob: (jobId: string) => request<VideoInferenceJob>(`/models/video-jobs/${jobId}`),
  cancelVideoJob: (jobId: string) => request<VideoInferenceJob>(`/models/video-jobs/${jobId}/cancel`, { method: 'POST' }),
  exports: () => request<{ data: Array<{ id: string; artifactId: string; status: string; progress: number; outputPath?: string | null; errorMessage?: string | null }> }>('/models/exports'),
  createPrelabel: (body: CreatePrelabelInput) => request<{ id: string; status: string }>('/prelabel-jobs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  datasetPrelabel: (datasetId: string, body: { modelPath?: string; mode?: PrelabelMode; confidence?: number } = {}) => request<PrelabelJob>(`/prelabel-jobs/datasets/${datasetId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  prelabelJobs: (datasetId: string) => request<{ data: PrelabelJob[] }>(`/prelabel-jobs?dataset_id=${encodeURIComponent(datasetId)}`),
  backups: () => request<{ data: BackupRecord[] }>('/backups'),
  createBackup: (label = 'manual') => request<BackupRecord>('/backups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label }) }),
}
