import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Network, Combine } from 'lucide-react'
import { cn } from '@/lib/utils'

// 기존 페이지를 그대로 재사용
import SearchPage from './Search'
import KnowledgeGraphPage from './KnowledgeGraph'

type Mode = 'integrated' | 'document' | 'graph'

export default function KnowledgeSearch() {
  const [mode, setMode] = useState<Mode>('graph')

  const tabs: { id: Mode; label: string; icon: typeof Search }[] = [
    { id: 'integrated', label: '통합', icon: Combine },
    { id: 'document', label: '문서', icon: Search },
    { id: 'graph', label: '그래프', icon: Network },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 모드 탭 */}
      <div
        className="flex items-center gap-4 px-6 py-3 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
      >
        <div className="flex items-center gap-2">
          <Search size={18} className="text-gold-500" />
          <h2 className="font-display font-semibold text-surface-900 text-lg">지식 검색</h2>
        </div>
        <div className="flex gap-1 ml-4">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setMode(id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all',
                mode === id
                  ? 'bg-gold-500 text-surface-DEFAULT'
                  : 'text-surface-600 hover:text-surface-800 hover:bg-surface-200',
              )}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 콘텐츠 */}
      <div className="flex-1 overflow-hidden">
        <motion.div
          key={mode}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="h-full"
        >
          {mode === 'graph' && <KnowledgeGraphPage />}
          {mode === 'document' && <SearchPage />}
          {mode === 'integrated' && (
            <div className="flex h-full">
              {/* 좌측: 문서 검색 */}
              <div className="flex-1 overflow-y-auto" style={{ borderRight: '1px solid var(--color-border)' }}>
                <SearchPage hideHeader />
              </div>
              {/* 우측: 그래프 */}
              <div className="flex-1 overflow-hidden">
                <KnowledgeGraphPage />
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
