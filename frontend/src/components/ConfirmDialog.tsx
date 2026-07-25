import { AlertTriangle, X } from 'lucide-react'
import { useEffect, useRef } from 'react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  pending?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, description, confirmLabel = '确认', cancelLabel = '取消', danger = true, pending = false, onConfirm, onCancel }: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open) {
      previousFocus.current = document.activeElement as HTMLElement
      if (!dialog.open) {
        if (typeof dialog.showModal === 'function') dialog.showModal()
        else dialog.setAttribute('open', '')
      }
      requestAnimationFrame(() => cancelRef.current?.focus())
    } else if (dialog.open) {
      if (typeof dialog.close === 'function') dialog.close()
      else dialog.removeAttribute('open')
      previousFocus.current?.focus()
    }
  }, [open])

  return <dialog ref={dialogRef} className="confirm-dialog" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-description" onCancel={(event) => { event.preventDefault(); if (!pending) onCancel() }} onClick={(event) => { if (event.target === event.currentTarget && !pending) onCancel() }}>
    <div className="dialog-card">
      <button className="icon-button dialog-close" aria-label="关闭确认框" disabled={pending} onClick={onCancel}><X size={18} /></button>
      <span className={`dialog-icon ${danger ? 'danger' : ''}`}><AlertTriangle size={22} /></span>
      <h2 id="confirm-dialog-title">{title}</h2>
      <p id="confirm-dialog-description">{description}</p>
      <div className="dialog-actions"><button ref={cancelRef} className="button secondary" disabled={pending} onClick={onCancel}>{cancelLabel}</button><button className={`button ${danger ? 'danger' : 'primary'}`} disabled={pending} onClick={onConfirm}>{pending ? '处理中…' : confirmLabel}</button></div>
    </div>
  </dialog>
}
