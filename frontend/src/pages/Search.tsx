import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search as SearchIcon,
  FileText,
  Tag,
  User,
  Calendar,
  ArrowRight,
  Loader2,
  X,
  SlidersHorizontal,
} from 'lucide-react'
import { searchApi, type SearchResult } from '@/api/client'
import { useStore } from '@/store/useStore'
import { useToast } from '@/store/useStore'
import { formatDate, truncate, cn } from '@/lib/utils'

// Highlight matching text safely without innerHTML
function HighlightedText({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <span>{text}</span>
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  const parts = text.split(regex)
  return (
    <span>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark
            key={i}
            className="rounded px-0.5"
            style={{ background: 'rgba(243, 112, 33, 0.25)', color: '#F37021' }}
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </span>
  )
}

function ResultCard({
  result,
  query,
  onNavigate,
}: {
  result: SearchResult
  query: string
  onNavigate: (path: string) => void
}) {
  const path = result.metadata?.path ?? ''
  const title =
    result.metadata?.title ??
    (path ? path.split('/').pop()?.replace('.md', '') : null) ??
    '제목 없음'
  const excerpt = truncate(result.document ?? '', 300)
  const tags = Array.isArray(result.metadata?.tags) ? (result.metadata.tags as string[]) : []
  const owner = result.metadata?.owner ?? ''
  const date = result.metadata?.date ?? ''
  const score = result.distance !== undefined ? (1 - result.distance).toFixed(3) : result.score?.toFixed(3)
  const workspace = result.metadata?.workspace ?? path.split('/')[0] ?? ''

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card p-5 cursor-pointer group"
      onClick={() => path && onNavigate(path)}
    >
      <div className="flex items-start justify-between gap-4 mb-2">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div
            className="w-8 h-8 rounded-md flex items-center justify-center shrink-0 mt-0.5"
            style={{ background: 'var(--color-bg-elevated)' }}
          >
            <FileText size={14} className="text-gold-500" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-surface-900 group-hover:text-gold-500 transition-colors truncate">
              {title}
            </h3>
            <p className="text-2xs font-mono text-surface-600 mt-0.5 truncate">{path}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {score && (
            <div
              className="px-2 py-0.5 rounded text-2xs font-mono"
              style={{ background: 'var(--color-bg-elevated)' }}
            >
              <span className="text-surface-600">유사도 </span>
              <span className="text-gold-500 font-bold">{score}</span>
            </div>
          )}
          {workspace && (
            <span className={cn('tag', workspace === 'Shared' ? 'tag-success' : 'tag-warning')}>
              {workspace}
            </span>
          )}
          <ArrowRight
            size={14}
            className="text-surface-600 group-hover:text-gold-500 group-hover:translate-x-1 transition-all"
          />
        </div>
      </div>

      {/* Excerpt with safe highlighting */}
      {excerpt && (
        <div
          className="mt-3 px-3 py-2.5 rounded text-xs text-surface-700 leading-relaxed"
          style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
        >
          <HighlightedText text={excerpt} query={query} />
        </div>
      )}

      {/* Meta */}
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        {owner && (
          <div className="flex items-center gap-1 text-2xs text-surface-600 font-mono">
            <User size={10} />
            {owner}
          </div>
        )}
        {date && (
          <div className="flex items-center gap-1 text-2xs text-surface-600 font-mono">
            <Calendar size={10} />
            {formatDate(date)}
          </div>
        )}
        {tags.map((tag) => (
          <div key={tag} className="flex items-center gap-0.5 text-2xs">
            <Tag size={9} className="text-gold-600" />
            <span className="tag tag-gold py-0 px-1.5">{tag}</span>
          </div>
        ))}
      </div>
    </motion.div>
  )
}

export default function Search({ hideHeader = false }: { hideHeader?: boolean } = {}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const setSelectedVaultPath = useStore((s) => s.setSelectedVaultPath)

  const initialQuery = searchParams.get('q') ?? ''
  const [query, setQuery] = useState(initialQuery)
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [resultCount, setResultCount] = useState(10)

  // Filters
  const [showFilters, setShowFilters] = useState(false)
  const [filterWorkspace, setFilterWorkspace] = useState<'all' | 'Shared' | 'Private'>('all')

  const doSearch = useCallback(
    async (q: string, n = resultCount) => {
      if (!q.trim()) {
        setResults([])
        setHasSearched(false)
        return
      }
      setIsLoading(true)
      setHasSearched(true)
      try {
        const data = await searchApi.search(q.trim(), n)
        let res = data.results ?? []

        // Client-side workspace filter
        if (filterWorkspace !== 'all') {
          res = res.filter((r) => {
            const path = r.metadata?.path ?? ''
            return path.startsWith(filterWorkspace)
          })
        }

        setResults(res)
        setSearchParams({ q: q.trim() }, { replace: true })
      } catch (err) {
        toast.error('검색 실패', String(err))
        setResults([])
      } finally {
        setIsLoading(false)
      }
    },
    [resultCount, filterWorkspace, setSearchParams, toast],
  )

  // Search on initial load if query param present
  useEffect(() => {
    if (initialQuery) {
      doSearch(initialQuery)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    doSearch(query)
  }

  function handleResultClick(path: string) {
    setSelectedVaultPath(path)
    navigate('/docs')
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      {!hideHeader && (
        <div>
          <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">시맨틱 검색</h2>
          <p className="text-sm text-surface-600">
            ChromaDB 벡터 검색 — 자연어로 질의하면 의미적으로 가장 유사한 문서를 찾습니다.
          </p>
        </div>
      )}

      {/* Search form */}
      <div className="panel p-4">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative flex items-center gap-3">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-600 pointer-events-none">
                <SearchIcon size={16} />
              </span>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="자연어로 검색하세요... 예: 보험 면책 조항 관련 규정"
                className="input-field pl-10 text-base"
                style={{ fontSize: '0.9375rem', paddingLeft: '2.5rem' }}
                autoFocus
              />
              {query && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('')
                    setResults([])
                    setHasSearched(false)
                    setSearchParams({})
                  }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-600 hover:text-surface-900"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <button type="submit" className="btn-primary px-5 py-2.5 flex items-center gap-2 whitespace-nowrap">
              {isLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <SearchIcon size={14} />
              )}
              검색
            </button>
            <button
              type="button"
              onClick={() => setShowFilters((v) => !v)}
              className={cn(
                'btn-secondary py-2.5 flex items-center gap-1.5 whitespace-nowrap',
                showFilters && 'border-gold-500/30 text-gold-500',
              )}
            >
              <SlidersHorizontal size={13} />
              필터
            </button>
          </div>

          {/* Filters */}
          <AnimatePresence>
            {showFilters && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                style={{ overflow: 'hidden' }}
              >
                <div className="pt-3 border-t border-surface-300 flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-surface-700 font-semibold whitespace-nowrap">
                      워크스페이스:
                    </label>
                    {(['all', 'Shared', 'Private'] as const).map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => setFilterWorkspace(opt)}
                        className={cn(
                          'px-2.5 py-1 rounded text-xs font-semibold transition-colors',
                          filterWorkspace === opt
                            ? 'bg-gold-500/20 text-gold-500 border border-gold-500/30'
                            : 'bg-surface-200 text-surface-700 border border-surface-300 hover:border-surface-400',
                        )}
                      >
                        {opt === 'all' ? '전체' : opt}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-surface-700 font-semibold whitespace-nowrap">
                      결과 수:
                    </label>
                    {[5, 10, 20, 50].map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setResultCount(n)}
                        className={cn(
                          'w-10 py-1 rounded text-xs font-mono transition-colors',
                          resultCount === n
                            ? 'bg-gold-500/20 text-gold-500 border border-gold-500/30'
                            : 'bg-surface-200 text-surface-700 border border-surface-300 hover:border-surface-400',
                        )}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </form>
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-28 rounded-md" />
          ))}
        </div>
      ) : hasSearched ? (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-surface-700">
              <span className="font-mono font-bold text-surface-900">{results.length}</span>개 결과
              {query && (
                <span>
                  {' '}— <span className="text-gold-500">"{query}"</span>
                </span>
              )}
            </p>
          </div>

          {results.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-16"
            >
              <SearchIcon size={36} className="text-surface-600 mx-auto mb-3" />
              <h3 className="font-display font-semibold text-surface-800 text-lg mb-2">
                검색 결과 없음
              </h3>
              <p className="text-sm text-surface-600">
                "{query}"에 대한 결과가 없습니다. 다른 검색어를 시도해보세요.
              </p>
            </motion.div>
          ) : (
            <div className="space-y-3">
              {results.map((result, i) => (
                <motion.div
                  key={result.id ?? i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <ResultCard
                    result={result}
                    query={query}
                    onNavigate={handleResultClick}
                  />
                </motion.div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16"
        >
          <SearchIcon size={48} className="text-surface-600 mx-auto mb-4 opacity-50" />
          <h3 className="font-display font-semibold text-surface-800 text-lg mb-2">
            시맨틱 검색
          </h3>
          <p className="text-sm text-surface-600 max-w-sm mx-auto mb-6">
            자연어로 질의하면 ChromaDB 벡터 유사도 기반으로 가장 관련성 높은 문서를 찾습니다.
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {[
              '보험 약관 면책 조항',
              '투자 위험 고지',
              '고객 민원 처리',
              '금융 규정 준수',
            ].map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => {
                  setQuery(suggestion)
                  doSearch(suggestion)
                }}
                className="tag tag-gold cursor-pointer hover:bg-gold-500/30 transition-colors text-sm py-1 px-3"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}
