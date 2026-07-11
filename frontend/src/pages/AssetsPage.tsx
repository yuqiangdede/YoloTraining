import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { EmptyState, ErrorState, LoadingRows } from '../components/States'
import { PageHeader } from '../components/PageHeader'

export function AssetsPage() {
  const client = useQueryClient(); const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['assets'], queryFn: api.assets })
  const upload = useMutation({ mutationFn: api.uploadAssets, onSuccess: () => client.invalidateQueries({ queryKey: ['assets'] }) })
  const recycle = useMutation({ mutationFn: api.recycleAsset, onSuccess: () => client.invalidateQueries({ queryKey: ['assets'] }) })
  const assets = query.data?.data.filter((asset) => asset.filename.toLowerCase().includes(search.toLowerCase())) ?? []
  return <><PageHeader title="素材库" description="原始图片只读保存，重复内容自动识别" actions={<label className="button primary"><Upload size={16} />导入图片<input type="file" accept="image/*" multiple hidden onChange={(event) => event.target.files && upload.mutate(event.target.files)} /></label>} />
    <div className="filterbar"><label className="search"><Search size={16} /><input aria-label="搜索素材" placeholder="搜索文件名" value={search} onChange={(event) => setSearch(event.target.value)} /></label><span>{assets.length} 个素材</span></div>
    {upload.error && <ErrorState message={upload.error.message} />}{query.isLoading ? <LoadingRows /> : assets.length === 0 ? <EmptyState title="还没有素材" message="导入 JPG、PNG、WEBP 等图片开始标注" /> : <div className="asset-grid">{assets.map((asset) => <article className="asset-card" key={asset.id}><img src={`/media/${asset.storagePath.replace('uploads/', '')}`} alt={asset.filename} loading="lazy" /><div><strong title={asset.filename}>{asset.filename}</strong><span>{asset.width} × {asset.height} · {(asset.sizeBytes / 1024).toFixed(0)} KB</span></div><button aria-label={`删除 ${asset.filename}`} className="icon-button" onClick={() => recycle.mutate(asset.id)}><Trash2 size={16} /></button></article>)}</div>}
  </>
}
