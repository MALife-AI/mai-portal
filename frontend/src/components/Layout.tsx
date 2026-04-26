import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useState, useEffect, useCallback } from 'react'
import { Cpu, Menu, X } from 'lucide-react'
import { getUserId } from '@/api/client'
import { Sidebar } from './Sidebar'
import { ToastContainer } from './Toast'
import { TaskBar } from './TaskBar'

const PAGE_TITLES: Record<string, string> = {
  '/': '대시보드',
  '/docs': '문서 관리',
  '/agent': '에이전트 콘솔',
  '/knowledge': '지식 검색',
  '/workflow': '워크플로우',
  '/skills': '스킬',
  '/settings': '계정 설정',
  '/admin': '관리 패널',
}

interface GpuServer {
  id: string
  name: string
  model: string
  online: boolean
  signal: string
  label: string
  load_pct: number
}

function GpuHealthIndicator() {
  const [servers, setServers] = useState<GpuServer[]>([])

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/admin/inference-status', { headers: { 'X-User-Id': getUserId() } })
      if (r.ok) {
        const d = await r.json()
        setServers(d.servers || [])
      }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  if (servers.length === 0) return null

  const SIGNAL_VAR: Record<string, string> = {
    green: 'var(--color-success)',
    yellow: 'var(--color-warning)',
    red: 'var(--color-error)',
  }

  return (
    <ul className="flex items-center gap-2" aria-label="GPU 추론 서버 상태">
      {servers.map(srv => {
        const color = SIGNAL_VAR[srv.signal] ?? SIGNAL_VAR.red
        const statusText = srv.online ? '정상' : '오프라인'
        return (
          <li
            key={srv.id}
            className="flex items-center gap-1.5 px-2 py-1 rounded-md text-2xs font-mono"
            style={{ border: '1px solid var(--color-border)' }}
            title={`${srv.name} · ${srv.model} · ${srv.label} (${srv.load_pct}%)`}
            aria-label={`${srv.name} ${statusText} · ${srv.label} · 부하 ${srv.load_pct}%`}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{
                background: color,
                boxShadow: srv.online ? `0 0 6px color-mix(in srgb, ${color} 40%, transparent)` : 'none',
              }}
              aria-hidden="true"
            />
            <Cpu size={10} className="text-surface-600" aria-hidden="true" />
            <span className="text-surface-800 hidden sm:inline">{srv.name}</span>
            <span style={{ color, fontSize: '9px' }}>{srv.label}</span>
          </li>
        )
      })}
    </ul>
  )
}

export function Layout() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] ?? '—'
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // 페이지 이동 시 모바일 사이드바 닫기
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  // Esc 키로 모바일 드로어 닫기
  useEffect(() => {
    if (!sidebarOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSidebarOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [sidebarOpen])

  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg-primary)' }}>
      {/* Skip link (a11y) */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[100] focus:px-3 focus:py-1.5 focus:rounded focus:bg-surface-900 focus:text-white focus:text-sm"
      >
        본문으로 건너뛰기
      </a>

      {/* Mobile sidebar overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
            className="fixed inset-0 z-40 md:hidden"
            style={{ background: 'var(--color-overlay)' }}
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* Sidebar — 데스크탑: 항상 표시, 모바일: 슬라이드 오버레이 */}
      <div
        className="fixed inset-y-0 left-0 z-50 md:relative md:translate-x-0 md:z-auto"
        style={{
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 280ms cubic-bezier(0.32, 0.72, 0, 1)',
        }}
      >
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Top bar */}
        <header
          className="flex items-center px-3 sm:px-6 shrink-0"
          style={{
            height: 'var(--header-height)',
            borderBottom: '1px solid var(--color-border)',
            background: 'var(--color-bg-secondary)',
          }}
        >
          {/* Hamburger (mobile only) */}
          <button
            type="button"
            className="mr-2 inline-flex items-center justify-center rounded-md hover:bg-surface-100 md:hidden"
            style={{ width: '40px', height: '40px' }}
            onClick={() => setSidebarOpen(true)}
            aria-label="메뉴 열기"
            aria-expanded={sidebarOpen}
            aria-controls="primary-sidebar"
          >
            <Menu size={18} className="text-surface-600" aria-hidden="true" />
          </button>

          <div className="flex items-center gap-2 min-w-0">
            <span className="text-2xs font-mono text-surface-600 uppercase tracking-widest hidden sm:inline">
              M:AI PORTAL
            </span>
            <span className="text-surface-600 hidden sm:inline" aria-hidden="true">/</span>
            <h1
              className="font-display font-semibold text-surface-900 truncate"
              style={{ fontSize: '0.9375rem' }}
            >
              {title}
            </h1>
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <GpuHealthIndicator />
            <time
              className="text-2xs font-mono text-surface-600 hidden sm:inline"
              dateTime={new Date().toISOString().slice(0, 10)}
            >
              {new Date().toLocaleDateString('ko-KR', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </time>
          </div>
        </header>

        {/* Page content with animation */}
        <main id="main-content" className="flex-1 overflow-hidden" tabIndex={-1}>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={reducedMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -4 }}
              transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
              className="h-full overflow-auto"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Toast notifications */}
      <ToastContainer />

      {/* 백그라운드 태스크 진행바 (모든 페이지에서 표시) */}
      <TaskBar />
    </div>
  )
}
