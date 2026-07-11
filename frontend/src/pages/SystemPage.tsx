import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, CheckCircle2, Cpu, Download, Folder, HardDrive } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { api } from '../lib/api'

export function SystemPage() {
  const client = useQueryClient()
  const environment = useQuery({ queryKey: ['environment'], queryFn: api.environment })
  const backups = useQuery({ queryKey: ['backups'], queryFn: api.backups })
  const createBackup = useMutation({ mutationFn: () => api.createBackup(), onSuccess: () => client.invalidateQueries({ queryKey: ['backups'] }) })
  const gpu = environment.data?.gpu
  const gpuLabel = gpu?.isAvailable ? `${gpu.name} · ${(gpu.memoryBytes! / 1024 ** 3).toFixed(0)} GB` : '未检测到 CUDA GPU'
  return <><PageHeader title="系统环境" description="运行环境、GPU 与项目内资源检查" actions={<button className="button primary" onClick={() => createBackup.mutate()} disabled={createBackup.isPending}><Archive size={16} />{createBackup.isPending ? '正在创建备份' : '创建备份'}</button>} />
    <div className="system-grid"><article className="system-card"><Cpu /><div><span>训练设备</span><strong>{gpuLabel}</strong><small>CUDA {gpu?.cuda ?? '未启用'} · 项目内 PyTorch</small></div></article><article className="system-card"><Folder /><div><span>项目根目录</span><strong>{environment.data?.projectRoot ?? '检查中…'}</strong><small>模型、虚拟环境、素材和结果均位于此目录</small></div></article><article className="system-card"><HardDrive /><div><span>可用磁盘空间</span><strong>{environment.data ? `${(environment.data.disk.freeBytes / 1024 ** 3).toFixed(1)} GB` : '检查中…'}</strong><small>数据集、权重、运行产物均使用项目所在磁盘</small></div></article><article className="system-card"><CheckCircle2 /><div><span>项目环境</span><strong>{environment.data?.venvIsLocal ? '本地 .venv 就绪' : '未检测到 .venv'}</strong><small>仅监听 127.0.0.1</small></div></article></div>
    <section className="panel"><div className="panel-heading"><div><h2>备份与恢复</h2><p>备份包含数据、素材、模型、运行结果和资源，不包含 .venv。</p></div></div>{backups.data?.data.length ? <div className="table"><div className="table-head"><span>创建时间</span><span>标签</span><span>大小</span><span>操作</span></div>{backups.data.data.map((item) => { const filename = item.path.split('/').at(-1)!; return <div className="table-row" key={item.path}><span>{new Date(item.createdAt).toLocaleString()}</span><span>{item.label}</span><span>{(item.sizeBytes / 1024 / 1024).toFixed(1)} MB</span><a className="button secondary" href={`/api/v1/backups/${filename}/download`}><Download size={16} />下载</a></div> })}</div> : <p className="quiet-state">暂无备份。恢复时请先停止服务，再执行 scripts\restore.ps1 -BackupPath &lt;archive.zip&gt; -Confirm。</p>}</section>
  </>
}
