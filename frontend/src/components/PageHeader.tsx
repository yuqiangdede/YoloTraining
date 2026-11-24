import type { ReactNode } from 'react'

export function PageHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return <header className="page-header">
    <div className="page-header-content"><span className="page-kicker">视觉模型训练台 / WORKSPACE</span><h1>{title}</h1><p>{description}</p></div>
    {actions && <div className="page-actions">{actions}</div>}
  </header>
}
