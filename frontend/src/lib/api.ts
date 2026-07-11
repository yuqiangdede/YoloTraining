export type TaskType = 'detect' | 'segment' | 'semantic' | 'pose' | 'obb'

export interface Asset {
  id: string
  filename: string
  storagePath: string
  width: number
  height: number
  sizeBytes: number
  tags: string[]
  createdAt: string
}

export interface DatasetVersion {
  id: string
  name: string
  task: TaskType
  assetCount: number
  contentHash: string
  createdAt: string
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
  createdAt: string
}

export class ApiError extends Error {
  constructor(message: string, public code = 'REQUEST_FAILED') { super(message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  const body = await response.json()
  if (!response.ok) {
    const error = body.error ?? body.detail ?? {}
    throw new ApiError(error.message ?? '请求失败', error.code)
  }
  return body as T
}

export const api = {
  health: () => request<{ status: string; projectRoot: string }>('/health'),
  assets: () => request<{ data: Asset[] }>('/assets?page=1&pageSize=100'),
  uploadAssets: (files: FileList) => {
    const form = new FormData()
    Array.from(files).forEach((file) => form.append('files', file))
    return request<{ data: Asset[]; duplicates: string[] }>('/assets', { method: 'POST', body: form })
  },
  recycleAsset: (id: string) => request(`/assets/${id}`, { method: 'DELETE' }),
  getAnnotation: (id: string) => request<Record<string, unknown>>(`/assets/${id}/annotation`),
  saveAnnotation: (id: string, document: unknown) => request(`/assets/${id}/annotation`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(document),
  }),
  datasets: () => request<{ data: DatasetVersion[] }>('/datasets'),
  createDataset: (body: unknown) => request<DatasetVersion>('/datasets', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  jobs: () => request<{ data: TrainingJob[] }>('/training-jobs'),
  createJob: (body: unknown) => request<TrainingJob>('/training-jobs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  jobAction: (id: string, action: 'pause' | 'resume' | 'cancel') => request<TrainingJob>(`/training-jobs/${id}/${action}`, { method: 'POST' }),
  artifacts: (jobId: string) => request<{ data: Array<Record<string, unknown>> }>(`/training-jobs/${jobId}/artifacts`),
}
