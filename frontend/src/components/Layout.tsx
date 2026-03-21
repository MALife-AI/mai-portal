import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { ToastContainer } from './Toast'
import { TaskBar } from './TaskBar'

const PAGE_TITLES: Record<string, string> = {
  '/': '대시보드',
  '/vault': '볼트 탐색기',
  '/agent': '에이전트 콘솔',
  '/ingest': '문서 업로드',
  '/search': '시맨틱 검색',
  '/skills': '스킬',
  '/admin': '관리 패널',
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
              미래에셋 Lake
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
