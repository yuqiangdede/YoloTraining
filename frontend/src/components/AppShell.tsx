import { Box, Database, Gauge, Image, Layers, Settings, Shapes, Sparkles } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const navigation = [
  { to: '/', label: '总览', icon: Gauge },
  { to: '/assets', label: '素材库', icon: Image },
  { to: '/annotate', label: '人工标注', icon: Shapes },
  { to: '/datasets', label: '数据集版本', icon: Database },
  { to: '/training', label: '训练任务', icon: Sparkles },
  { to: '/models', label: '模型结果', icon: Layers },
  { to: '/system', label: '系统环境', icon: Settings },
]

export function AppShell() {
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Box size={20} /></span><span>YOLO26 Studio</span></div>
      <nav aria-label="主导航">
        {navigation.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'}>
          <Icon size={18} /><span>{label}</span>
        </NavLink>)}
      </nav>
      <div className="runtime"><span className="status-dot" />RTX 3060 · 本机</div>
    </aside>
    <main className="main-content"><Outlet /></main>
  </div>
}
