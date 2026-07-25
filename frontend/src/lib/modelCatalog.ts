import type { TaskType } from './api'

export type ModelSize = 'n' | 's' | 'm' | 'l' | 'x'

export const MODEL_SIZES: ModelSize[] = ['n', 's', 'm', 'l', 'x']

export const modelSizeLabels: Record<ModelSize, string> = {
  n: 'Nano（n）',
  s: 'Small（s）',
  m: 'Medium（m）',
  l: 'Large（l）',
  x: 'X-Large（x）',
}

export const modelKindLabels: Record<TaskType, string> = {
  detect: '目标检测',
  segment: '实例分割',
  semantic: '语义分割',
  pose: '姿态估计',
  obb: '旋转框检测',
}

const taskSuffix: Record<TaskType, string> = {
  detect: '',
  segment: '-seg',
  semantic: '-sem',
  pose: '-pose',
  obb: '-obb',
}

export function modelPathFor(task: TaskType, size: ModelSize): string {
  return `models/pretrained/yolo26${size}${taskSuffix[task]}.pt`
}
