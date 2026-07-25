import { CheckCircle2, Info, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

type ToastKind = 'success' | 'info'
interface ToastInput { message: string; kind?: ToastKind; actionLabel?: string; onAction?: () => void; duration?: number }
interface ToastItem extends ToastInput { id: number; kind: ToastKind }
const ToastContext = createContext<{ notify: (input: ToastInput | string) => number; dismiss: (id: number) => void }>({ notify: () => 0, dismiss: () => undefined })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const dismiss = useCallback((id: number) => setItems((current) => current.filter((item) => item.id !== id)), [])
  const notify = useCallback((input: ToastInput | string) => {
    const item = typeof input === 'string' ? { message: input } : input
    const id = Date.now() + Math.random()
    setItems((current) => [...current, { ...item, id, kind: item.kind ?? 'success' }])
    return id
  }, [])
  const value = useMemo(() => ({ notify, dismiss }), [dismiss, notify])
  return <ToastContext.Provider value={value}>{children}<div className="toast-region" aria-live="polite" aria-atomic="false">{items.map((item) => <ToastEntry key={item.id} item={item} dismiss={dismiss} />)}</div></ToastContext.Provider>
}

function ToastEntry({ item, dismiss }: { item: ToastItem; dismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => dismiss(item.id), item.duration ?? (item.actionLabel ? 6500 : 4000))
    return () => window.clearTimeout(timer)
  }, [dismiss, item.actionLabel, item.duration, item.id])
  const Icon = item.kind === 'success' ? CheckCircle2 : Info
  return <div className={`toast ${item.kind}`} role="status"><Icon size={19} /><span>{item.message}</span>{item.actionLabel && <button onClick={() => { item.onAction?.(); dismiss(item.id) }}>{item.actionLabel}</button>}<button className="toast-close" aria-label="关闭提示" onClick={() => dismiss(item.id)}><X size={16} /></button></div>
}

export function useToast() {
  return useContext(ToastContext)
}
