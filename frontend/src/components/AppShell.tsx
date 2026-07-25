import { useQuery } from '@tanstack/react-query'
import { Box, Database, Gauge, Layers, Menu, ScanSearch, Settings, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../lib/api'

const navigation = [
  { to: '/', label: '总览', icon: Gauge },
  { to: '/datasets', label: '数据集', icon: Database },
  { to: '/training', label: '训练任务', icon: Sparkles },
  { to: '/models', label: '模型结果', icon: Layers },
  { to: '/models/test', label: '模型测试', icon: ScanSearch },
  { to: '/system', label: '系统环境', icon: Settings },
]

export function AppShell() {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && Boolean(window.matchMedia?.('(max-width: 720px)').matches))
  const toggleRef = useRef<HTMLButtonElement>(null)
  const firstLinkRef = useRef<HTMLAnchorElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000, retry: 1 })
  const environment = useQuery({ queryKey: ['environment'], queryFn: api.environment, staleTime: 60_000 })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: api.jobs, refetchInterval: 3000 })
  const annotationMode = location.pathname.endsWith('/annotate')

  useEffect(() => {
    setMenuOpen(false)
    requestAnimationFrame(() => mainRef.current?.focus({ preventScroll: true }))
  }, [location.pathname])
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 720px)')
    if (!media) return
    const updateViewport = () => setIsMobile(media.matches)
    updateViewport()
    media.addEventListener('change', updateViewport)
    return () => media.removeEventListener('change', updateViewport)
  }, [])
  useEffect(() => {
    if (!menuOpen) return
    firstLinkRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        toggleRef.current?.focus()
        return
      }
      if (event.key === 'Tab') {
        const focusable = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? [])
        const first = focusable[0]
        const last = focusable.at(-1)
        if (!first || !last) return
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])

  const apiReady = health.data?.status === 'ok'
  const workerReady = jobs.data?.worker.alive === true
  const overallReady = apiReady && workerReady
  const statusText = health.isPending || jobs.isPending ? '正在检查系统' : health.isError ? 'API 不可用' : jobs.isError ? '工作线程状态不可用' : !workerReady ? '工作线程异常' : '系统正常'
  const gpuName = environment.isPending ? '正在读取 GPU' : environment.isError ? 'GPU 状态不可用' : environment.data?.gpu.isAvailable ? environment.data.gpu.name ?? '可用 GPU' : '未检测到 GPU'

  return <div className={`app-shell ${menuOpen ? 'menu-open' : ''} ${annotationMode ? 'annotation-mode' : ''}`}>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="mobile-header">
      <div className="mobile-brand"><span className="brand-mark"><Box size={18} /></span><strong>YOLO26</strong></div>
      <button ref={toggleRef} className="menu-toggle" aria-expanded={menuOpen} aria-controls="primary-sidebar" aria-label={menuOpen ? '关闭导航菜单' : '打开导航菜单'} onClick={() => setMenuOpen((value) => !value)}>{menuOpen ? <X size={22} /> : <Menu size={22} />}</button>
    </header>
    {menuOpen && <button className="nav-scrim" aria-label="关闭导航菜单" onClick={() => setMenuOpen(false)} />}
    <aside ref={sidebarRef} id="primary-sidebar" className="sidebar" aria-hidden={isMobile && !menuOpen} inert={isMobile && !menuOpen}>
      <div className="brand"><span className="brand-mark"><Box size={20} /></span><span className="brand-copy"><strong>YOLO26 Studio</strong><small>LOCAL TRAINING CONSOLE</small></span></div>
      <div className="workspace-label">工作空间</div>
      <nav aria-label="主导航">
        {navigation.map(({ to, label, icon: Icon }, index) => <NavLink ref={index === 0 ? firstLinkRef : undefined} key={to} to={to} end={to === '/'} onClick={() => setMenuOpen(false)}><Icon size={18} /><span>{label}</span></NavLink>)}
      </nav>
      <div className="sidebar-footer">
        <div className="runtime"><span className={`status-dot ${overallReady ? '' : 'is-error'}`} /><span><strong>{gpuName}</strong><small>{workerReady ? 'LOCAL WORKER READY' : 'WORKER OFFLINE'}</small></span></div>
        <small className="sidebar-hint">数据、模型与运行产物均保存在项目目录</small>
      </div>
    </aside>
    <main ref={mainRef} id="main-content" tabIndex={-1} className="main-content">
      <div className="topbar"><span className="topbar-path">YOLO26 / LOCAL WORKSPACE</span><span className={`topbar-status ${overallReady ? '' : 'is-error'}`} title={jobs.data?.worker.lastError ?? undefined}><span className={`status-dot ${overallReady ? '' : 'is-error'}`} />{statusText}</span></div>
      <Outlet />
    </main>
  </div>
}
