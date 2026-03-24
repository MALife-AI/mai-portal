import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useState, useEffect, useCallback } from 'react'
import { Cpu } from 'lucide-react'
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
    const interval = setInterval(fetchStatus, 30000) // 30초마다
    return () => clearInterval(interval)
  }, [fetchStatus])

  if (servers.length === 0) return null

  const SIGNAL_COLORS: Record<string, string> = { green: '#34C759', yellow: '#F5A623', red: '#FF3B30' }

  return (
    <div className="flex items-center gap-2">
      {servers.map(srv => {
        const color = SIGNAL_COLORS[srv.signal] || SIGNAL_COLORS.red
        return (
          <div
            key={srv.id}
            className="flex items-center gap-1.5 px-2 py-1 rounded-md text-2xs font-mono"
            style={{ border: '1px solid var(--color-border)' }}
            title={`${srv.name} · ${srv.model} · ${srv.label} (${srv.load_pct}%)`}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: color, boxShadow: srv.online ? `0 0 6px ${color}66` : 'none' }}
            />
            <Cpu size={10} className="text-surface-600" />
            <span className="text-surface-800">{srv.name}</span>
            <span style={{ color, fontSize: '9px' }}>{srv.label}</span>
          </div>
        )
      })}
    </div>
  )
}

export function Layout() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] ?? '—'

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg-primary)' }}>
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Top bar */}
        <header
          className="flex items-center px-6 shrink-0"
          style={{
            height: 'var(--header-height)',
            borderBottom: '1px solid var(--color-border)',
            background: 'var(--color-bg-secondary)',
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="text-2xs font-mono text-surface-600 uppercase tracking-widest"
            >
              M:AI PORTAL
            </span>
            <span className="text-surface-600">/</span>
            <h1
              className="font-display font-semibold text-surface-900"
              style={{ fontSize: '0.9375rem' }}
            >
              {title}
            </h1>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <GpuHealthIndicator />
            <span className="text-2xs font-mono text-surface-600">
              {new Date().toLocaleDateString('ko-KR', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </span>
          </div>
        </header>

        {/* Page content with animation */}
        <main className="flex-1 overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
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
