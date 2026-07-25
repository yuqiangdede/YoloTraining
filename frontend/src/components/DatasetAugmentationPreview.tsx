import { useMemo, useState } from 'react'
import type { Asset } from '../lib/api'
import './DatasetAugmentationPreview.css'

type PreviewKind = 'original' | 'rotate' | 'crop' | 'flip' | 'grayscale' | 'color' | 'blur' | 'mosaic' | 'mixup' | 'copy-paste'

const examples: Array<{ kind: PreviewKind; label: string; description: string }> = [
  { kind: 'original', label: '原图', description: '基准素材' },
  { kind: 'rotate', label: '旋转', description: '随机角度旋转' },
  { kind: 'crop', label: '裁切 / 缩放', description: '模拟不同取景范围' },
  { kind: 'flip', label: '翻转', description: '水平镜像' },
  { kind: 'grayscale', label: '黑白', description: '去除颜色信息' },
  { kind: 'color', label: '色彩扰动', description: '亮度与饱和度变化' },
  { kind: 'blur', label: '噪声 / 模糊', description: '模拟低质量采集' },
  { kind: 'mosaic', label: 'Mosaic', description: '多张素材拼接' },
  { kind: 'mixup', label: 'MixUp', description: '多张素材叠加' },
  { kind: 'copy-paste', label: 'Copy-Paste', description: '实例复制粘贴示意' },
]

function imageUrl(asset: Asset) {
  return `/media/${asset.storagePath.replace('uploads/', '')}`
}

export function DatasetAugmentationPreview({ assets }: { assets: Asset[] }) {
  const [selectedId, setSelectedId] = useState(assets[0]?.id ?? '')
  const selected = assets.find((asset) => asset.id === selectedId) ?? assets[0]
  const companions = useMemo(() => assets.filter((asset) => asset.id !== selected?.id).slice(0, 3), [assets, selected?.id])

  if (!selected) return null

  return <details className="panel dataset-augmentation-preview">
    <summary className="panel-heading">
      <div><h2>素材增强预览</h2><p>从当前素材集中抽取代表性效果，帮助检查增强方向；仅用于预览，不会新增素材或修改标注。</p></div>
    </summary>
    <div className="augmentation-preview-content">
      <label className="augmentation-source">预览素材<select aria-label="选择预览素材" value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>{assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.filename}</option>)}</select></label>
      <div className="augmentation-example-grid">
        {examples.map((example) => <article className="augmentation-example" key={example.kind}>
          <div className={`augmentation-example-stage is-${example.kind}`}>
            {example.kind === 'mosaic' ? <div className="augmentation-mosaic">{[selected, ...companions].map((asset) => <img key={asset.id} src={imageUrl(asset)} alt="" />)}</div> : example.kind === 'mixup' || example.kind === 'copy-paste' ? <><img src={imageUrl(selected)} alt={`${selected.filename} ${example.label}预览`} />{companions[0] && <img className="augmentation-overlay" src={imageUrl(companions[0])} alt="" />}</> : <img src={imageUrl(selected)} alt={`${selected.filename} ${example.label}预览`} />}
          </div>
          <div className="augmentation-example-copy"><strong>{example.label}</strong><span>{example.description}</span></div>
        </article>)}
      </div>
    </div>
  </details>
}
