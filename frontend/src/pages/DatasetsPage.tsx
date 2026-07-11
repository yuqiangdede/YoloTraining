import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, Plus } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { api, type TaskType } from '../lib/api'

export function DatasetsPage() {
  const client = useQueryClient(); const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets }); const assets = useQuery({ queryKey: ['assets'], queryFn: api.assets })
  const [name, setName] = useState('dataset-v1'); const [task, setTask] = useState<TaskType>('detect'); const [classes, setClasses] = useState('object:目标'); const [keypointCount, setKeypointCount] = useState(17)
  const create = useMutation({ mutationFn: () => api.createDataset({ name, task, assetIds: assets.data?.data.map((asset) => asset.id) ?? [], classes: classes.split(',').map((item) => { const [id, label] = item.trim().split(':'); return { id, name: label || id } }), trainRatio: 0.8, valRatio: 0.2, testRatio: 0, seed: 0, keypointCount: task === 'pose' ? keypointCount : undefined }), onSuccess: () => client.invalidateQueries({ queryKey: ['datasets'] }) })
  return <><PageHeader title="数据集版本" description="每个快照不可变，可复现训练输入" />
    <section className="panel compact-form"><div className="panel-heading"><div><h2>创建训练快照</h2><p>使用当前素材库中已审核且任务一致的标注</p></div></div><div className="form-row"><label>版本名称<input value={name} onChange={(e) => setName(e.target.value)} /></label><label>任务<select value={task} onChange={(e) => setTask(e.target.value as TaskType)}><option value="detect">检测</option><option value="segment">实例分割</option><option value="semantic">语义分割</option><option value="pose">姿态</option><option value="obb">OBB</option></select></label><label className="wide">类别（ID:名称，逗号分隔）<input value={classes} onChange={(e) => setClasses(e.target.value)} /></label>{task === 'pose' && <label>关键点数量<input type="number" min="1" value={keypointCount} onChange={(e) => setKeypointCount(Number(e.target.value))} /></label>}<button className="button primary" disabled={!assets.data?.data.length || create.isPending} onClick={() => create.mutate()}><Plus size={16} />创建版本</button></div>{create.error && <ErrorState message={create.error.message} />}</section>
    <section className="panel"><div className="panel-heading"><div><h2>历史版本</h2><p>{datasets.data?.data.length ?? 0} 个不可变快照</p></div></div>{datasets.data?.data.length ? <div className="table"><div className="table-head"><span>名称</span><span>任务</span><span>素材数</span><span>内容哈希</span></div>{datasets.data.data.map((item) => <div className="table-row" key={item.id}><strong><Database size={16} />{item.name}</strong><span>{item.task}</span><span>{item.assetCount}</span><code>{item.contentHash.slice(0, 12)}</code></div>)}</div> : <EmptyState title="暂无数据集版本" message="审核标注后创建第一个训练快照" />}</section>
  </>
}
