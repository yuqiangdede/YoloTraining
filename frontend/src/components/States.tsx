import { AlertTriangle, Inbox } from 'lucide-react'

export function EmptyState({ title, message }: { title: string; message: string }) {
  return <div className="empty-state" role="status"><Inbox size={28} /><strong>{title}</strong><span>{message}</span></div>
}

export function ErrorState({ message }: { message: string }) {
  return <div className="error-state" role="alert"><AlertTriangle size={18} /><span>{message}</span></div>
}

export function LoadingRows() {
  return <div className="loading-rows" aria-busy="true" aria-label="加载中">{[1, 2, 3].map((i) => <span key={i} />)}</div>
}
