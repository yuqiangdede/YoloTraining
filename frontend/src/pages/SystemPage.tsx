import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Cpu, Folder, HardDrive } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { api } from '../lib/api'

export function SystemPage() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  return <><PageHeader title="系统环境" description="运行环境、GPU 与项目内资源检查" />
    <div className="system-grid"><article className="system-card"><Cpu /><div><span>训练设备</span><strong>NVIDIA RTX 3060 · 12 GB</strong><small>CUDA 运行状态由诊断脚本实时验证</small></div></article><article className="system-card"><Folder /><div><span>项目根目录</span><strong>{health.data?.projectRoot ?? '检查中…'}</strong><small>模型、虚拟环境、素材和结果均位于此目录</small></div></article><article className="system-card"><HardDrive /><div><span>数据存储</span><strong>SQLite + 本地文件</strong><small>数据库仅保存相对路径和元数据</small></div></article><article className="system-card"><CheckCircle2 /><div><span>API 状态</span><strong>{health.data?.status === 'ok' ? '正常' : '连接中'}</strong><small>仅监听 127.0.0.1</small></div></article></div>
  </>
}
