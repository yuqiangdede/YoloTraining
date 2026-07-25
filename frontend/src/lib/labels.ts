import type { AnnotationStatus, TaskType } from './api'

export const taskLabels: Record<TaskType, string> = {
  detect: '目标检测',
  segment: '实例分割',
  semantic: '语义分割',
  pose: '姿态估计',
  obb: '旋转框检测',
}

export const annotationStatusLabels: Record<AnnotationStatus, string> = {
  UNLABELED: '未标注',
  DRAFT: '预标注草稿',
  COMPLETED: '待审核',
  REVIEWED: '已审核',
}

export const jobStatusLabels: Record<string, string> = {
  QUEUED: '排队中',
  RUNNING: '训练中',
  PAUSING: '暂停中',
  PAUSED: '已暂停',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}
