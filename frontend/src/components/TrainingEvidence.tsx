import type { TrainingQuality } from '../lib/api'

const PARAMETER_LABELS: Record<string, string> = {
  modelPath: '模型权重', epochs: '训练轮次', imgsz: '输入尺寸', batch: '批量大小',
  device: '设备', optimizer: '优化器', lr0: '初始学习率', patience: '早停耐心值',
  amp: 'AMP 混合精度', deterministic: '确定性训练', seed: '随机种子',
}

const STATE_LABELS: Record<TrainingQuality['state'], string> = {
  SUFFICIENT: '验证证据完整',
  INCOMPLETE: '证据不完整',
  NOT_READY: '尚无完整证据',
}

const NOTE_LABELS: Record<string, string> = {
  VALIDATION_METRICS_AVAILABLE: '训练结果包含有效验证集指标。',
  RESULTS_FILE_MISSING: '未找到 results.csv，无法确认验证集表现。',
  PRIMARY_VALIDATION_METRIC_MISSING: '未识别到主要验证指标，建议检查训练日志。',
  PRIMARY_VALIDATION_METRIC_INVALID: '主要验证指标不是有效数值，暂不能判断。',
  TRAINING_NOT_COMPLETE: '训练尚未完成，最终验证指标还不可用。',
}

export function trainingMetricLabel(key: string): string {
  if (key.includes('mAP50-95')) return 'mAP50-95（严格）'
  if (key.includes('mAP50')) return 'mAP50'
  if (key.includes('precision')) return 'Precision（精确率）'
  if (key.includes('recall')) return 'Recall（召回率）'
  if (key.includes('box_loss')) return key.startsWith('val/') ? '验证 box loss' : '训练 box loss'
  if (key.includes('cls_loss')) return key.startsWith('val/') ? '验证 cls loss' : '训练 cls loss'
  if (key.includes('dfl_loss')) return key.startsWith('val/') ? '验证 dfl loss' : '训练 dfl loss'
  return key
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(4)
}

function formatParameter(key: string, value: unknown): string {
  if (typeof value === 'boolean') return value ? '开启' : '关闭'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(5).replace(/0+$/, '').replace(/\.$/, '')
  return String(value ?? '—')
}

export function TrainingEvidence({
  params,
  quality,
  compact = false,
}: {
  params?: Record<string, unknown>
  quality?: TrainingQuality | null
  compact?: boolean
}) {
  const visibleParameters = Object.keys(PARAMETER_LABELS).filter((key) => params?.[key] !== undefined)
  const validationMetrics = Object.entries(quality?.validationMetrics ?? {})
  const lossMetrics = Object.entries(quality?.lossMetrics ?? {})
  const state = quality?.state ?? 'INCOMPLETE'
  const notes = quality?.notes ?? ['RESULTS_FILE_MISSING']

  return <section className={`training-evidence ${compact ? 'compact' : ''}`} aria-label="训练依据">
    <div className="training-evidence-heading">
      <div><h3>训练依据</h3><p>参数说明和验证集结果，用于判断训练记录是否完整。</p></div>
      <span className={`evidence-state ${state.toLowerCase()}`}>{STATE_LABELS[state]}</span>
    </div>
    {visibleParameters.length > 0 && <dl className="evidence-parameters">
      {visibleParameters.map((key) => <div key={key}><dt>{PARAMETER_LABELS[key]}</dt><dd>{formatParameter(key, params?.[key])}</dd></div>)}
    </dl>}
    {quality?.primaryMetric && <div className="evidence-primary">
      <div><span>主要验证指标</span><strong>{trainingMetricLabel(quality.primaryMetric)}</strong></div>
      <div><span>最佳值</span><strong>{formatNumber(quality.bestValue)}</strong><small>{quality.bestEpoch ? `第 ${quality.bestEpoch} 轮` : '最佳轮次未知'}</small></div>
      <div><span>最终值</span><strong>{formatNumber(quality.finalValue)}</strong></div>
    </div>}
    {validationMetrics.length > 0 && <div className="evidence-metrics">
      <div><h4>验证集指标</h4><p>mAP 越高越好；Precision 反映误检，Recall 反映漏检。</p></div>
      <dl>{validationMetrics.map(([key, value]) => <div key={key}><dt>{trainingMetricLabel(key)}</dt><dd>{formatNumber(value)}</dd></div>)}</dl>
    </div>}
    {!compact && lossMetrics.length > 0 && <div className="evidence-metrics evidence-losses">
      <div><h4>损失指标</h4><p>loss 越低通常越好，但仍需结合验证集指标判断。</p></div>
      <dl>{lossMetrics.map(([key, value]) => <div key={key}><dt>{trainingMetricLabel(key)}</dt><dd>{formatNumber(value)}</dd></div>)}</dl>
    </div>}
    <p className="evidence-note">{NOTE_LABELS[notes[0]] ?? '训练结果需要结合数据集难度和业务目标进一步验证。'}{!compact && ' 以上是客观证据，不代表模型已满足具体业务阈值。'}</p>
  </section>
}
