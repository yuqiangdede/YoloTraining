import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, RotateCcw } from 'lucide-react'

export function EmptyState({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return <div className="empty-state" role="status"><Inbox size={28} /><strong>{title}</strong><span>{message}</span>{action && <div className="empty-state-action">{action}</div>}</div>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="error-state" role="alert"><AlertTriangle size={18} /><span>{message}</span>{onRetry && <button className="button ghost" onClick={onRetry}><RotateCcw size={15} />重试</button>}</div>
}

export function LoadingRows({ count = 3 }: { count?: number }) {
  return <div className="loading-rows" role="status" aria-busy="true" aria-label="正在加载">{Array.from({ length: count }, (_, i) => <span key={i} />)}<span className="sr-only">正在加载</span></div>
}
