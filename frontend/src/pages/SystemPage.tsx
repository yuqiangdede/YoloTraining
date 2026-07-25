import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, CheckCircle2, Cpu, Download, Folder, HardDrive } from 'lucide-react'
import { useState } from 'react'
import { ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { api } from '../lib/api'
import { formatBytes, formatDate } from '../lib/labels'

export function SystemPage() {
  const client = useQueryClient()
  const { notify } = useToast()
  const [newBackupPath, setNewBackupPath] = useState('')
  const environment = useQuery({ queryKey: ['environment'], queryFn: api.environment })
  const backups = useQuery({ queryKey: ['backups'], queryFn: api.backups })
  const createBackup = useMutation({ mutationFn: () => api.createBackup(), onSuccess: (backup) => { setNewBackupPath(backup.path); client.invalidateQueries({ queryKey: ['backups'] }); notify(`备份“${backup.label}”已创建`) } })
  const gpu = environment.data?.gpu
  const gpuLabel = gpu?.isAvailable ? `${gpu.name ?? 'CUDA GPU'}${gpu.memoryBytes ? ` · ${formatBytes(gpu.memoryBytes)}` : ''}` : '未检测到 CUDA GPU'

  return <>
    <PageHeader title="系统环境" description="运行环境、GPU 与项目内资源检查" actions={<button className="button primary" onClick={() => createBackup.mutate()} disabled={createBackup.isPending}><Archive size={16} />{createBackup.isPending ? '正在创建备份…' : '创建备份'}</button>} />
    {environment.isPending ? <LoadingRows count={4} /> : environment.isError ? <ErrorState message={environment.error.message} onRetry={() => environment.refetch()} /> : <div className="system-grid system-health-grid"><article className="system-card"><Cpu /><div><span>训练设备</span><strong>{gpuLabel}</strong><small>CUDA {gpu?.cuda ?? '未启用'} · 项目内 PyTorch</small></div></article><article className="system-card"><Folder /><div><span>项目根目录</span><strong>{environment.data.projectRoot}</strong><small>模型、虚拟环境、素材和结果均位于此目录</small></div></article><article className="system-card"><HardDrive /><div><span>可用磁盘空间</span><strong>{formatBytes(environment.data.disk.freeBytes)}</strong><small>共 {formatBytes(environment.data.disk.totalBytes)}</small></div></article><article className="system-card"><CheckCircle2 /><div><span>项目环境</span><strong>{environment.data.venvIsLocal ? '本地 .venv 就绪' : '未检测到项目内 .venv'}</strong><small>服务仅监听本机地址</small></div></article></div>}
    {createBackup.error && <ErrorState message={createBackup.error.message} onRetry={() => createBackup.mutate()} />}
    <section className="panel"><div className="panel-heading"><div><h2>备份与恢复</h2><p>备份包含数据、素材、模型、运行结果和资源，不包含 .venv。</p></div></div>{backups.isPending ? <LoadingRows /> : backups.isError ? <ErrorState message={backups.error.message} onRetry={() => backups.refetch()} /> : backups.data.data.length ? <div className="table"><div className="table-head"><span>创建时间</span><span>标签</span><span>大小</span><span>操作</span></div>{backups.data.data.map((item) => { const filename = item.path.split('/').at(-1)!; return <div className={`table-row ${item.path === newBackupPath ? 'is-new' : ''}`} key={item.path}><span>{formatDate(item.createdAt)}</span><span>{item.label}</span><span>{formatBytes(item.sizeBytes)}</span><a className="button secondary" href={`/api/v1/backups/${filename}/download`}><Download size={16} />下载</a></div> })}</div> : <p className="quiet-state">暂无备份。</p>}<p className="helper-text">恢复仍使用现有 CLI：停止服务后执行 <code>scripts\restore.ps1 -BackupPath &lt;archive.zip&gt; -Confirm</code>。</p></section>
  </>
}
