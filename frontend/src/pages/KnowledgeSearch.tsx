import { lazy, Suspense, useId, useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Network, Combine, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

// 각 탭은 lazy-load — react-force-graph(135KB)·recharts 같은 무거운 의존성이
// 실제로 탭이 열릴 때까지 번들에서 분리되도록 함
const SearchPage = lazy(() => import('./Search'))
const KnowledgeGraphPage = lazy(() => import('./KnowledgeGraph'))

function TabFallback() {
  return (
    <div
      className="flex items-center justify-center h-full"
      role="status"
      aria-live="polite"
      aria-label="탭 불러오는 중"
    >
      <Loader2 size={20} className="animate-spin text-gold-500" aria-hidden="true" />
    </div>
  )
}

type Mode = 'integrated' | 'document' | 'graph'

export default function KnowledgeSearch() {
  const [mode, setMode] = useState<Mode>('graph')
  const tablistId = useId()

  const tabs: { id: Mode; label: string; icon: typeof Search }[] = [
    { id: 'integrated', label: '통합', icon: Combine },
    { id: 'document', label: '문서', icon: Search },
    { id: 'graph', label: '그래프', icon: Network },
  ]

  function handleTabKey(e: React.KeyboardEvent, currentIdx: number) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const delta = e.key === 'ArrowRight' ? 1 : -1
    const next = (currentIdx + delta + tabs.length) % tabs.length
    setMode(tabs[next]!.id)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 모드 탭 */}
      <div
        className="flex items-center gap-4 px-6 py-3 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
      >
        <div className="flex items-center gap-2">
          <Search size={18} className="text-gold-500" aria-hidden="true" />
          <h2 className="font-display font-semibold text-surface-900 text-lg">지식 검색</h2>
        </div>
        <div
          role="tablist"
          aria-label="검색 모드"
          id={tablistId}
          className="flex gap-1 ml-4"
        >
          {tabs.map(({ id, label, icon: Icon }, idx) => {
            const selected = mode === id
            return (
              <button
                key={id}
                type="button"
                role="tab"
                id={`${tablistId}-tab-${id}`}
                aria-selected={selected}
                aria-controls={`${tablistId}-panel-${id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setMode(id)}
                onKeyDown={(e) => handleTabKey(e, idx)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold active:scale-[0.97]',
                  selected
                    ? 'bg-gold-500 text-surface-DEFAULT'
                    : 'text-surface-600 hover:text-surface-800 hover:bg-surface-200',
                )}
                style={{
                  minHeight: '30px',
                  transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out), transform 120ms var(--ease-out)',
                }}
              >
                <Icon size={13} aria-hidden="true" />
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* 콘텐츠 */}
      <div
        className="flex-1 overflow-hidden"
        role="tabpanel"
        id={`${tablistId}-panel-${mode}`}
        aria-labelledby={`${tablistId}-tab-${mode}`}
      >
        <motion.div
          key={mode}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
          className="h-full"
        >
          <Suspense fallback={<TabFallback />}>
            {mode === 'graph' && <KnowledgeGraphPage />}
            {mode === 'document' && <SearchPage />}
            {mode === 'integrated' && (
              <div className="flex h-full">
                {/* 좌측: 문서 검색 */}
                <section
                  className="flex-1 overflow-y-auto"
                  style={{ borderRight: '1px solid var(--color-border)' }}
                  aria-label="문서 검색"
                >
                  <SearchPage hideHeader />
                </section>
                {/* 우측: 그래프 */}
                <section className="flex-1 overflow-hidden" aria-label="지식 그래프">
                  <KnowledgeGraphPage />
                </section>
              </div>
            )}
          </Suspense>
        </motion.div>
      </div>
    </div>
  )
}
