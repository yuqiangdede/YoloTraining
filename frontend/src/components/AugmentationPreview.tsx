import './AugmentationPreview.css'

export function AugmentationPreview({ imageUrl, degrees, scale, fliplr, flipud }: {
  imageUrl: string
  degrees: number
  scale: number
  fliplr: number
  flipud: number
}) {
  const mirrorX = fliplr >= 0.5 ? -1 : 1
  const mirrorY = flipud >= 0.5 ? -1 : 1
  const magnitude = 1 + Math.min(Math.max(scale, 0), 1) * 0.2
  const labels = [`旋转 ${degrees}°`, `缩放 ${scale.toFixed(2)}`]
  if (mirrorX < 0) labels.push('水平翻转')
  if (mirrorY < 0) labels.push('垂直翻转')
  return <section className="panel augmentation-preview">
    <div className="panel-heading"><div><h2>增强预览</h2><p>训练时随机应用；此处展示当前几何参数的代表性效果。</p></div></div>
    <div className="augmentation-stage"><img src={imageUrl} alt="增强后的素材预览" style={{ transform: `rotate(${degrees}deg) scale(${magnitude}) scaleX(${mirrorX}) scaleY(${mirrorY})` }} /></div>
    <p className="augmentation-caption">{labels.join(' · ')}</p>
  </section>
}
