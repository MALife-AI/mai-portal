// ─── KnowledgeSearch.tsx ──────────────────────────────────────────────────────
// Unified 지식 검색 page: merges semantic document search + graph entity search
// in a single split-panel interface with three search modes.

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ForceGraph2D, { type NodeObject, type LinkObject } from 'react-force-graph-2d'
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
  Network,
  Layers,
  ZoomIn,
  RefreshCw,
  ChevronRight,
  BookOpen,
  GitBranch,
  Combine,
} from 'lucide-react'
import {
  searchApi,
  graphApi,
  type SearchResult,
  type GraphEntity,
  type GraphVisualizationData,
  type GraphStats,
  type GraphRelationship,
} from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { formatDate, truncate, cn } from '@/lib/utils'

// ─── Entity colour palette (from KnowledgeGraph.tsx) ─────────────────────────

const ENTITY_COLORS: Record<string, string> = {
  product: '#F37021',
  coverage: '#FF6B6B',
  condition: '#E74C3C',
  person: '#4A90D9',
  organization: '#34C759',
  org: '#34C759',
  regulation: '#F5A623',
  concept: '#8da0b8',
  document: '#6BAAE8',
  term: '#9B59B6',
  actuarial: '#1ABC9C',
}

function entityColor(type: string | undefined): string {
  if (!type) return '#8da0b8'
  return ENTITY_COLORS[type.toLowerCase()] ?? '#8da0b8'
}

const COMMUNITY_PALETTE = [
  '#F37021', '#4A90D9', '#34C759', '#F5A623', '#9B59B6',
  '#E74C3C', '#1ABC9C', '#FF6B6B', '#3498DB', '#2ECC71',
  '#E67E22', '#8E44AD', '#16A085', '#D35400', '#2980B9',
  '#27AE60', '#C0392B', '#7F8C8D', '#F39C12', '#1F77B4',
]

function communityColor(communityId: string | undefined): string {
  if (!communityId) return '#8da0b8'
  const idx = parseInt(communityId.replace('community_', ''), 10)
  return COMMUNITY_PALETTE[idx % COMMUNITY_PALETTE.length] ?? '#8da0b8'
}

function nodeSize(mentions: number): number {
  return Math.max(4, Math.min(20, 4 + Math.sqrt(mentions) * 2))
}

function edgeColor(type: string | undefined): string {
  if (!type) return 'rgba(141,160,184,0.35)'
  const palette: Record<string, string> = {
    mentions: 'rgba(243,112,33,0.5)',
    related_to: 'rgba(74,144,217,0.45)',
    part_of: 'rgba(52,199,89,0.45)',
    governs: 'rgba(245,166,35,0.5)',
    issued_by: 'rgba(141,160,184,0.45)',
  }
  return palette[type.toLowerCase()] ?? 'rgba(141,160,184,0.35)'
}

const ENTITY_TYPES = [
  'all', 'product', 'coverage', 'condition', 'person',
  'organization', 'regulation', 'concept', 'document', 'term', 'actuarial',
]

const PROP_LABELS: Record<string, string> = {
  product_code: '상품코드',
  rider_code: '보종코드',
  coverage_amount: '보장금액',
  coverage_period: '보장기간',
  payment_period: '납입기간',
  effective_date: '시행일',
  document_type: '문서유형',
  description: '설명',
  definition: '정의',
  article_number: '조항번호',
  exclusions: '면책사항',
  claim_conditions: '지급조건',
}

// ─── Search mode ──────────────────────────────────────────────────────────────

type SearchMode = '통합' | '문서' | '그래프'

const SEARCH_MODES: { id: SearchMode; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: '통합', label: '통합', icon: <Combine size={13} />, desc: '문서 + 그래프 동시 검색' },
  { id: '문서', label: '문서', icon: <BookOpen size={13} />, desc: '시맨틱 벡터 검색' },
  { id: '그래프', label: '그래프', icon: <GitBranch size={13} />, desc: '지식 그래프 탐색' },
]

// ─── Internal force-graph types ───────────────────────────────────────────────

interface GraphNode extends NodeObject {
  id: string
  name: string
  type: string
  mentions: number
  community?: string
  highlighted?: boolean
  [key: string]: unknown
}

interface GraphLink extends LinkObject {
  source: string | GraphNode
  target: string | GraphNode
  type: string
  weight: number
}

interface InternalGraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

// ─── Shared sub-components ────────────────────────────────────────────────────

// Copied from Search.tsx — highlight matching text safely without innerHTML
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

function TypeTag({ type }: { type: string }) {
  const color = entityColor(type)
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-2xs font-mono font-semibold"
      style={{ background: `${color}22`, color, border: `1px solid ${color}55` }}
    >
      {type}
    </span>
  )
}

// ─── Document result card ─────────────────────────────────────────────────────

function DocResultCard({
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
  const excerpt = truncate(result.document ?? '', 280)
  const tags = Array.isArray(result.metadata?.tags) ? (result.metadata.tags as string[]) : []
  const owner = result.metadata?.owner ?? ''
  const date = result.metadata?.date ?? ''
  const score =
    result.distance !== undefined
      ? (1 - result.distance).toFixed(3)
      : result.score?.toFixed(3)
  const workspace = result.metadata?.workspace ?? path.split('/')[0] ?? ''

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="card p-4 cursor-pointer group"
      onClick={() => path && onNavigate(path)}
    >
      <div className="flex items-start justify-between gap-3 mb-1.5">
        <div className="flex items-start gap-2.5 flex-1 min-w-0">
          <div
            className="w-7 h-7 rounded flex items-center justify-center shrink-0 mt-0.5"
            style={{ background: 'var(--color-bg-elevated)' }}
          >
            <FileText size={12} className="text-gold-500" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-surface-900 group-hover:text-gold-500 transition-colors truncate text-sm">
              {title}
            </h3>
            <p className="text-2xs font-mono text-surface-600 mt-0.5 truncate">{path}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {score && (
            <div
              className="px-1.5 py-0.5 rounded text-2xs font-mono"
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
            size={12}
            className="text-surface-600 group-hover:text-gold-500 group-hover:translate-x-1 transition-all"
          />
        </div>
      </div>

      {excerpt && (
        <div
          className="mt-2 px-2.5 py-2 rounded text-xs text-surface-700 leading-relaxed"
          style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
        >
          <HighlightedText text={excerpt} query={query} />
        </div>
      )}

      <div className="flex items-center gap-2.5 mt-2 flex-wrap">
        {owner && (
          <div className="flex items-center gap-1 text-2xs text-surface-600 font-mono">
            <User size={9} />
            {owner}
          </div>
        )}
        {date && (
          <div className="flex items-center gap-1 text-2xs text-surface-600 font-mono">
            <Calendar size={9} />
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

// ─── Entity row (compact, clickable) ─────────────────────────────────────────

function EntityRow({
  entity,
  isSelected,
  onClick,
}: {
  entity: GraphEntity
  isSelected: boolean
  onClick: () => void
}) {
  const color = entityColor(entity.entity_type)
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-2.5 px-3 py-2 rounded text-left transition-colors',
        isSelected
          ? 'bg-gold-500/15 border border-gold-500/30'
          : 'hover:bg-surface-200 border border-transparent',
      )}
    >
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ background: color }}
      />
      <span className="text-xs font-medium text-surface-900 flex-1 truncate">
        {entity.name}
      </span>
      <TypeTag type={entity.entity_type} />
      <span className="text-2xs font-mono text-surface-600 shrink-0">{entity.mentions}회</span>
      <ChevronRight size={11} className="text-surface-500 shrink-0" />
    </button>
  )
}

// ─── Entity detail panel (right panel content) ───────────────────────────────

interface EntityDetailProps {
  entityId: string
  onClose: () => void
  onSubgraph: (id: string) => void
}

function EntityDetail({ entityId, onClose, onSubgraph }: EntityDetailProps) {
  const navigate = useNavigate()
  const [data, setData] = useState<{
    entity: GraphEntity
    neighbors: GraphEntity[]
    relationships: GraphRelationship[]
  } | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    setIsLoading(true)
    graphApi
      .getEntity(entityId)
      .then((d) => setData(d))
      .catch((err) => console.error('Entity fetch error:', err))
      .finally(() => setIsLoading(false))
  }, [entityId])

  const entity = data?.entity

  return (
    <motion.div
      key="entity-detail"
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.18 }}
      className="flex flex-col h-full"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <span className="text-xs font-mono text-surface-600 uppercase tracking-widest">
          엔티티 상세
        </span>
        <button
          onClick={onClose}
          className="w-6 h-6 flex items-center justify-center rounded text-surface-600 hover:text-surface-900 hover:bg-surface-200 transition-colors"
        >
          <X size={13} />
        </button>
      </div>

      {isLoading ? (
        <div className="flex-1 p-4 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-8 rounded" />
          ))}
        </div>
      ) : entity ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Name + type */}
          <div>
            <div
              className="w-10 h-10 rounded-md flex items-center justify-center mb-3"
              style={{ background: `${entityColor(entity.entity_type)}18` }}
            >
              <Network size={16} style={{ color: entityColor(entity.entity_type) }} />
            </div>
            <h3 className="text-sm font-display font-semibold text-surface-900 leading-tight mb-1.5">
              {entity.name}
            </h3>
            <div className="flex items-center gap-2 flex-wrap">
              <TypeTag type={entity.entity_type} />
              <span className="font-mono text-2xs text-surface-600">언급 {entity.mentions}회</span>
            </div>
          </div>

          {/* Properties */}
          {Object.keys(entity.properties).length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                속성
              </p>
              <div
                className="rounded-md p-3 space-y-1.5"
                style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
              >
                {Object.entries(entity.properties).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-xs">
                    <span className="font-mono text-surface-600 shrink-0">{PROP_LABELS[k] ?? k}:</span>
                    <span className="text-surface-800 break-all">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Source documents */}
          {entity.source_paths.length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                소스 문서
              </p>
              <div className="space-y-1">
                {entity.source_paths.map((path) => (
                  <button
                    key={path}
                    onClick={() => navigate(`/vault?path=${encodeURIComponent(path)}`)}
                    className="w-full text-left flex items-center gap-2 px-2 py-1.5 rounded text-xs text-gold-500 hover:bg-surface-200 transition-colors"
                  >
                    <FileText size={11} className="shrink-0" />
                    <span className="truncate font-mono">{path}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Neighbors */}
          {(data?.neighbors ?? []).length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                연관 엔티티
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(data?.neighbors ?? []).slice(0, 12).map((n) => (
                  <span
                    key={n.id}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs cursor-default"
                    style={{
                      background: `${entityColor(n.entity_type)}18`,
                      color: entityColor(n.entity_type),
                      border: `1px solid ${entityColor(n.entity_type)}40`,
                    }}
                  >
                    {n.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Relationships */}
          {(data?.relationships ?? []).length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                관계 ({data!.relationships.length})
              </p>
              <div className="space-y-1">
                {data!.relationships.slice(0, 8).map((rel, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 text-2xs font-mono text-surface-700 px-2 py-1 rounded"
                    style={{ background: 'var(--color-bg-elevated)' }}
                  >
                    <span className="text-surface-500 truncate">{rel.source_id}</span>
                    <span
                      className="shrink-0 px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(243,112,33,0.12)', color: '#F37021' }}
                    >
                      {rel.relation_type}
                    </span>
                    <span className="text-surface-500 truncate">{rel.target_id}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Subgraph button */}
          <button
            onClick={() => onSubgraph(entity.id)}
            className="btn-secondary w-full flex items-center justify-center gap-2"
          >
            <ZoomIn size={13} />
            서브그래프 보기
          </button>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-sm text-surface-600">엔티티를 불러올 수 없습니다.</p>
        </div>
      )}
    </motion.div>
  )
}

// ─── Graph canvas (2D only, adapted for embedded right-panel use) ─────────────

interface GraphCanvasProps {
  data: InternalGraphData
  paintNode: (node: NodeObject, ctx: CanvasRenderingContext2D, scale: number) => void
  paintLink: (link: LinkObject, ctx: CanvasRenderingContext2D) => void
  onNodeClick: (node: NodeObject) => void
  onNodeHover: (node: NodeObject | null) => void
}

function GraphCanvas({ data, paintNode, paintLink, onNodeClick, onNodeHover }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height })
      }
    })
    obs.observe(el)
    setDimensions({ width: el.clientWidth, height: el.clientHeight })
    return () => obs.disconnect()
  }, [])

  return (
    <div ref={containerRef} className="w-full h-full">
      <ForceGraph2D
        graphData={data}
        width={dimensions.width}
        height={dimensions.height}
        nodeCanvasObject={paintNode}
        linkCanvasObject={paintLink}
        onNodeClick={onNodeClick}
        onNodeHover={onNodeHover}
        nodeLabel={(node) => (node as GraphNode).name ?? ''}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        backgroundColor="transparent"
        nodeRelSize={1}
        cooldownTicks={120}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
      />
    </div>
  )
}

// ─── Stats bar ────────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: GraphStats }) {
  return (
    <div
      className="flex items-center gap-4 px-4 py-2 shrink-0 flex-wrap"
      style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
    >
      <Layers size={12} className="text-gold-500 shrink-0" />
      <div className="flex items-center gap-1 text-2xs font-mono text-surface-600">
        <span className="text-surface-900 font-bold">{stats.node_count}</span>
        <span>노드</span>
      </div>
      <div className="h-3 w-px bg-surface-300" />
      <div className="flex items-center gap-1 text-2xs font-mono text-surface-600">
        <span className="text-surface-900 font-bold">{stats.edge_count}</span>
        <span>엣지</span>
      </div>
      <div className="h-3 w-px bg-surface-300" />
      <div className="flex items-center gap-1 text-2xs font-mono text-surface-600">
        <span className="text-surface-900 font-bold">{stats.communities}</span>
        <span>커뮤니티</span>
      </div>
      <div className="h-3 w-px bg-surface-300" />
      {Object.entries(stats.entity_types)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
        .map(([type, count]) => (
          <div key={type} className="flex items-center gap-1 text-2xs font-mono">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: entityColor(type) }}
            />
            <span className="text-surface-600">{type}</span>
            <span className="text-surface-900 font-bold">{count}</span>
          </div>
        ))}
    </div>
  )
}

// ─── Helper: entity selection check ──────────────────────────────────────────
// Defined as a module-level function so TypeScript does not narrow its
// rightPanel parameter inside a JSX branch that has already narrowed it.

type RightPanelView =
  | { type: 'entity-detail'; entityId: string }
  | { type: 'graph-viz' }
  | null

function isEntitySelected(panel: RightPanelView, entityId: string): boolean {
  return panel?.type === 'entity-detail' && panel.entityId === entityId
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function KnowledgeSearch() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const setSelectedVaultPath = useStore((s) => s.setSelectedVaultPath)

  const initialQuery = searchParams.get('q') ?? ''
  const [query, setQuery] = useState(initialQuery)
  const [mode, setMode] = useState<SearchMode>('통합')

  // ── Document search state ──────────────────────────────────────────────────

  const [docResults, setDocResults] = useState<SearchResult[]>([])
  const [docLoading, setDocLoading] = useState(false)
  const [docSearched, setDocSearched] = useState(false)
  const [resultCount, setResultCount] = useState(10)
  const [showFilters, setShowFilters] = useState(false)
  const [filterWorkspace, setFilterWorkspace] = useState<'all' | 'Shared' | 'Private'>('all')

  // ── Graph state ────────────────────────────────────────────────────────────

  const [graphData, setGraphData] = useState<GraphVisualizationData | null>(null)
  const [graphStats, setGraphStats] = useState<GraphStats | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [entityResults, setEntityResults] = useState<GraphEntity[]>([])
  const [entityLoading, setEntityLoading] = useState(false)

  // ── Right panel state ──────────────────────────────────────────────────────
  // Tracks what is shown in the right panel. Can be entity detail or graph viz.

  const [rightPanel, setRightPanel] = useState<RightPanelView>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [subgraphEntityId, setSubgraphEntityId] = useState<string | null>(null)
  const [subgraphData, setSubgraphData] = useState<GraphVisualizationData | null>(null)
  const [typeFilter, setTypeFilter] = useState('all')
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<{ name: string; type: string } | null>(null)

  // ── Load graph on mount (for graph + 통합 modes) ───────────────────────────

  const fetchGraph = useCallback(async () => {
    if (graphData) return  // already loaded
    setGraphLoading(true)
    try {
      const [statsData, vizData] = await Promise.all([
        graphApi.getStats(),
        graphApi.getVisualization(),
      ])
      setGraphStats(statsData)
      setGraphData(vizData)
    } catch (err) {
      toast.error('그래프 데이터 로드 실패', String(err))
    } finally {
      setGraphLoading(false)
    }
  }, [graphData, toast])

  useEffect(() => {
    if (mode === '그래프' || mode === '통합') {
      void fetchGraph()
    }
  }, [mode, fetchGraph])

  // ── Subgraph fetch ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!subgraphEntityId) {
      setSubgraphData(null)
      return
    }
    graphApi.getSubgraph(subgraphEntityId, 2)
      .then((data) => setSubgraphData(data))
      .catch((err) => {
        toast.error('서브그래프 로드 실패', String(err))
        setSubgraphEntityId(null)
      })
  }, [subgraphEntityId, toast])

  // ── Document search ────────────────────────────────────────────────────────

  const doDocSearch = useCallback(
    async (q: string, n = resultCount) => {
      if (!q.trim()) {
        setDocResults([])
        setDocSearched(false)
        return
      }
      setDocLoading(true)
      setDocSearched(true)
      try {
        const data = await searchApi.search(q.trim(), n)
        let res = data.results ?? []
        if (filterWorkspace !== 'all') {
          res = res.filter((r) => {
            const path = r.metadata?.path ?? ''
            return path.startsWith(filterWorkspace)
          })
        }
        setDocResults(res)
      } catch (err) {
        toast.error('문서 검색 실패', String(err))
        setDocResults([])
      } finally {
        setDocLoading(false)
      }
    },
    [resultCount, filterWorkspace, toast],
  )

  // ── Graph entity search ────────────────────────────────────────────────────

  const doEntitySearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setEntityResults([])
        setHighlightId(null)
        return
      }
      setEntityLoading(true)
      try {
        const results = await graphApi.searchEntities(
          q.trim(),
          typeFilter !== 'all' ? typeFilter : undefined,
          20,
        )
        setEntityResults(results)
        if (results[0]) {
          setHighlightId(results[0].id)
        }
      } catch (err) {
        toast.error('엔티티 검색 실패', String(err))
        setEntityResults([])
      } finally {
        setEntityLoading(false)
      }
    },
    [typeFilter, toast],
  )

  // ── Unified search ─────────────────────────────────────────────────────────

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) return
      setSearchParams({ q: q.trim() }, { replace: true })

      if (mode === '통합') {
        await Promise.all([doDocSearch(q), doEntitySearch(q)])
      } else if (mode === '문서') {
        await doDocSearch(q)
      } else {
        await doEntitySearch(q)
      }
    },
    [mode, doDocSearch, doEntitySearch, setSearchParams],
  )

  // ── Initial search from URL ────────────────────────────────────────────────

  useEffect(() => {
    if (initialQuery) {
      void doSearch(initialQuery)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── When mode switches, show appropriate right panel ──────────────────────

  useEffect(() => {
    if (mode === '그래프') {
      setRightPanel({ type: 'graph-viz' })
    } else {
      // In 통합 / 문서 mode keep entity detail if one was selected, otherwise null
      setRightPanel((prev) => (prev?.type === 'entity-detail' ? prev : null))
    }
  }, [mode])

  // ── Form submit ────────────────────────────────────────────────────────────

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    void doSearch(query)
  }

  function handleClear() {
    setQuery('')
    setDocResults([])
    setEntityResults([])
    setDocSearched(false)
    setSearchParams({})
    setHighlightId(null)
    setRightPanel(mode === '그래프' ? { type: 'graph-viz' } : null)
  }

  function handleDocClick(path: string) {
    setSelectedVaultPath(path)
    navigate('/vault')
  }

  function handleEntityClick(entity: GraphEntity) {
    setRightPanel({ type: 'entity-detail', entityId: entity.id })
    setSelectedNodeId(entity.id)
    setHighlightId(entity.id)
  }

  function handleSubgraph(id: string) {
    setSubgraphEntityId(id)
    setRightPanel({ type: 'graph-viz' })
    setSelectedNodeId(null)
  }

  // ── Force-graph derived data ───────────────────────────────────────────────

  const activeVizData: GraphVisualizationData | null =
    subgraphEntityId && subgraphData ? subgraphData : graphData

  const nodeCommunityMap = useMemo(() => {
    const map = new Map<string, string>()
    if (!activeVizData?.communities) return map
    for (const c of activeVizData.communities) {
      for (const eid of c.entity_ids ?? []) {
        map.set(eid, c.id)
      }
    }
    return map
  }, [activeVizData])

  const forceData = useMemo((): InternalGraphData => {
    if (!activeVizData) return { nodes: [], links: [] }
    const filteredNodes = activeVizData.nodes.filter((n) =>
      typeFilter === 'all' ? true : (n.type ?? '').toLowerCase() === typeFilter,
    )
    const nodeIdSet = new Set(filteredNodes.map((n) => n.id))
    const nodes: GraphNode[] = filteredNodes.map((n) => ({
      ...n,
      community: nodeCommunityMap.get(n.id),
      highlighted: n.id === highlightId,
    }))
    const links: GraphLink[] = activeVizData.edges
      .filter((e) => {
        const src = typeof e.source === 'string' ? e.source : (e.source as GraphNode).id
        const tgt = typeof e.target === 'string' ? e.target : (e.target as GraphNode).id
        return nodeIdSet.has(src) && nodeIdSet.has(tgt)
      })
      .map((e) => ({ source: e.source, target: e.target, type: e.type, weight: e.weight }))
    return { nodes, links }
  }, [activeVizData, typeFilter, highlightId, nodeCommunityMap])

  // ── Canvas painters ────────────────────────────────────────────────────────

  const paintNode = useCallback(
    (node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as GraphNode
      const size = nodeSize(n.mentions ?? 1)
      const color = entityColor(n.type ?? '')
      const isSelected = n.id === selectedNodeId
      const isHighlighted = n.highlighted

      ctx.beginPath()
      ctx.arc(n.x ?? 0, n.y ?? 0, size, 0, 2 * Math.PI)
      if (isHighlighted) {
        ctx.shadowColor = color
        ctx.shadowBlur = 12
      }
      ctx.fillStyle = isSelected ? '#ffffff' : color
      ctx.fill()
      ctx.shadowBlur = 0
      if (isSelected || isHighlighted) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2 / globalScale
        ctx.stroke()
      }
      if (globalScale >= 2) {
        const label = n.name ?? n.id
        ctx.font = `${Math.max(10, size * 0.9) / globalScale}px JetBrains Mono, monospace`
        ctx.fillStyle = 'rgba(232,237,244,0.95)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(label, n.x ?? 0, (n.y ?? 0) + size + 2 / globalScale)
      }
    },
    [selectedNodeId],
  )

  const paintLink = useCallback((link: LinkObject, ctx: CanvasRenderingContext2D) => {
    const l = link as GraphLink
    const src = l.source as GraphNode
    const tgt = l.target as GraphNode
    if (!src?.x || !tgt?.x) return
    ctx.beginPath()
    ctx.moveTo(src.x, src.y ?? 0)
    ctx.lineTo(tgt.x, tgt.y ?? 0)
    ctx.strokeStyle = edgeColor(l.type ?? '')
    ctx.lineWidth = Math.max(0.5, (l.weight ?? 1) * 0.8)
    ctx.stroke()
  }, [])

  // ─────────────────────────────────────────────────────────────────────────────

  const isAnyLoading = docLoading || entityLoading

  // Determine if we should show the right panel at all
  const showRightPanel =
    rightPanel !== null && (mode !== '문서' || rightPanel.type === 'entity-detail')

  // Entity list to show in compact right panel (통합 mode) or left (그래프 mode)
  const showEntityList = (mode === '통합' && entityResults.length > 0) || mode === '그래프'

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--color-bg-primary)' }}
    >
      {/* ── Search bar + mode toggle ──────────────────────────────────────────── */}
      <div
        className="shrink-0 px-4 pt-4 pb-0"
        style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
      >
        {/* Page title */}
        <div className="flex items-center gap-3 mb-3">
          <div
            className="w-8 h-8 rounded-md flex items-center justify-center"
            style={{ background: 'rgba(243,112,33,0.12)' }}
          >
            <SearchIcon size={15} className="text-gold-500" />
          </div>
          <div>
            <h2 className="font-display font-semibold text-surface-900 text-base leading-tight">
              지식 검색
            </h2>
            <p className="text-2xs text-surface-600 font-mono">
              문서 벡터 검색 + 지식 그래프 통합 탐색
            </p>
          </div>
        </div>

        {/* Mode tabs */}
        <div className="flex items-center gap-1 mb-3">
          {SEARCH_MODES.map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-t text-xs font-semibold transition-colors border-b-2',
                mode === m.id
                  ? 'text-gold-500 border-gold-500 bg-gold-500/8'
                  : 'text-surface-600 border-transparent hover:text-surface-800 hover:bg-surface-200',
              )}
              title={m.desc}
            >
              {m.icon}
              {m.label}
            </button>
          ))}
        </div>

        {/* Search form */}
        <form onSubmit={handleSubmit} className="pb-3 space-y-2">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-600 pointer-events-none">
                <SearchIcon size={15} />
              </span>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={
                  mode === '문서'
                    ? '자연어로 검색하세요... 예: 보험 면책 조항 관련 규정'
                    : mode === '그래프'
                    ? '엔티티 검색... 예: 암보험, 삼성생명, 보장기간'
                    : '통합 검색... 예: 면책 조항 관련 엔티티와 문서'
                }
                className="input-field pl-10"
                autoFocus
              />
              {query && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-600 hover:text-surface-900 transition-colors"
                >
                  <X size={13} />
                </button>
              )}
            </div>
            <button
              type="submit"
              disabled={isAnyLoading || !query.trim()}
              className="btn-primary px-4 py-2.5 flex items-center gap-1.5 whitespace-nowrap"
            >
              {isAnyLoading ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <SearchIcon size={13} />
              )}
              검색
            </button>
            {mode !== '그래프' && (
              <button
                type="button"
                onClick={() => setShowFilters((v) => !v)}
                className={cn(
                  'btn-secondary py-2.5 flex items-center gap-1.5 whitespace-nowrap',
                  showFilters && 'border-gold-500/30 text-gold-500',
                )}
              >
                <SlidersHorizontal size={12} />
                필터
              </button>
            )}
            {mode === '그래프' && (
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="input-field w-36"
              >
                {ENTITY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t === 'all' ? '전체 타입' : t}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Filters (문서 / 통합 mode) */}
          <AnimatePresence>
            {showFilters && mode !== '그래프' && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                style={{ overflow: 'hidden' }}
              >
                <div className="pt-2 flex flex-wrap items-center gap-4">
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

      {/* ── Main content area ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left panel ────────────────────────────────────────────────────── */}
        <div
          className="flex flex-col overflow-hidden"
          style={{
            flex: showRightPanel ? '0 0 50%' : '1 1 100%',
            transition: 'flex 0.2s ease',
            borderRight: showRightPanel ? '1px solid var(--color-border)' : 'none',
          }}
        >
          {/* ── 그래프 mode: show full graph visualization on left ── */}
          {mode === '그래프' ? (
            <div className="flex flex-1 overflow-hidden">
              {/* Graph canvas */}
              <div className="relative flex-1 overflow-hidden">
                {graphLoading ? (
                  <div className="flex flex-col items-center justify-center h-full gap-4">
                    <RefreshCw size={24} className="text-gold-500 animate-spin" />
                    <p className="text-sm text-surface-600">그래프 데이터 로드 중...</p>
                  </div>
                ) : forceData.nodes.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full gap-3">
                    <Network size={40} className="text-surface-600 opacity-40" />
                    <p className="text-sm text-surface-600">그래프 데이터가 없습니다.</p>
                    <p className="text-xs text-surface-500">먼저 그래프를 빌드해주세요.</p>
                  </div>
                ) : (
                  <GraphCanvas
                    data={forceData}
                    paintNode={paintNode}
                    paintLink={paintLink}
                    onNodeClick={(node) => {
                      const n = node as GraphNode
                      setSelectedNodeId(n.id)
                      setRightPanel({ type: 'entity-detail', entityId: n.id })
                    }}
                    onNodeHover={(node) => {
                      if (!node) {
                        setTooltip(null)
                        return
                      }
                      const n = node as GraphNode
                      setTooltip({ name: n.name ?? n.id, type: n.type ?? '' })
                    }}
                  />
                )}

                {/* Floating tooltip */}
                {tooltip && (
                  <div
                    className="absolute pointer-events-none z-10 px-2.5 py-1.5 rounded text-xs"
                    style={{
                      left: '50%',
                      bottom: 12,
                      transform: 'translateX(-50%)',
                      background: 'var(--color-bg-elevated)',
                      border: '1px solid var(--color-border)',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
                    }}
                  >
                    <span className="font-semibold text-surface-900">{tooltip.name}</span>
                    <span className="mx-1.5 text-surface-600">·</span>
                    <TypeTag type={tooltip.type} />
                  </div>
                )}

                {/* Legend */}
                <div
                  className="absolute top-3 left-3 rounded-md p-2.5 space-y-1"
                  style={{
                    background: 'rgba(20,30,51,0.85)',
                    border: '1px solid var(--color-border)',
                    backdropFilter: 'blur(4px)',
                  }}
                >
                  <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1.5">
                    타입
                  </p>
                  {Object.entries(ENTITY_COLORS).map(([type, color]) => (
                    <div key={type} className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                      <span className="text-2xs font-mono text-surface-700">{type}</span>
                    </div>
                  ))}
                </div>

                {/* Subgraph indicator */}
                {subgraphEntityId && (
                  <div className="absolute top-3 right-3 flex items-center gap-2">
                    <span className="text-xs font-mono text-gold-500">서브그래프 모드</span>
                    <button
                      onClick={() => {
                        setSubgraphEntityId(null)
                        setSelectedNodeId(null)
                      }}
                      className="btn-secondary flex items-center gap-1 text-xs py-1"
                    >
                      <X size={11} />
                      전체 보기
                    </button>
                  </div>
                )}

                {/* Node/edge count */}
                <div className="absolute bottom-3 right-3 text-2xs font-mono text-surface-600">
                  {forceData.nodes.length} nodes · {forceData.links.length} edges
                </div>
              </div>
            </div>

          ) : (
            /* ── 문서 / 통합 mode: document results on left ── */
            <div className="flex flex-col flex-1 overflow-hidden">
              {/* Entity compact list in 통합 mode */}
              <AnimatePresence>
                {mode === '통합' && showEntityList && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="shrink-0 overflow-hidden"
                    style={{ borderBottom: '1px solid var(--color-border)' }}
                  >
                    <div className="px-4 py-2.5">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <Network size={12} className="text-gold-500" />
                          <span className="text-xs font-semibold text-surface-800">
                            관련 엔티티
                          </span>
                          <span className="font-mono text-2xs text-surface-600">
                            ({entityResults.length})
                          </span>
                        </div>
                        {entityLoading && (
                          <Loader2 size={12} className="animate-spin text-surface-600" />
                        )}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {entityResults.slice(0, 8).map((entity) => (
                          <button
                            key={entity.id}
                            onClick={() => handleEntityClick(entity)}
                            className={cn(
                              'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors',
                              rightPanel?.type === 'entity-detail' && rightPanel.entityId === entity.id
                                ? 'bg-gold-500/15 border border-gold-500/30'
                                : 'border border-surface-300 hover:border-surface-400 bg-surface-100 hover:bg-surface-200',
                            )}
                          >
                            <span
                              className="w-1.5 h-1.5 rounded-full shrink-0"
                              style={{ background: entityColor(entity.entity_type) }}
                            />
                            <span className="text-surface-800 font-medium truncate max-w-[120px]">
                              {entity.name}
                            </span>
                            <TypeTag type={entity.entity_type} />
                          </button>
                        ))}
                        {entityResults.length > 8 && (
                          <span className="flex items-center text-2xs text-surface-500 font-mono px-1">
                            +{entityResults.length - 8}개
                          </span>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Document results list */}
              <div className="flex-1 overflow-y-auto p-4">
                {docLoading ? (
                  <div className="space-y-3">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="skeleton h-24 rounded-md" />
                    ))}
                  </div>
                ) : docSearched ? (
                  <>
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-xs text-surface-700">
                        <span className="font-mono font-bold text-surface-900">
                          {docResults.length}
                        </span>
                        개 문서 결과
                        {query && (
                          <span>
                            {' '}— <span className="text-gold-500">"{query}"</span>
                          </span>
                        )}
                      </p>
                    </div>
                    {docResults.length === 0 ? (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-center py-12"
                      >
                        <FileText size={32} className="text-surface-600 mx-auto mb-3 opacity-40" />
                        <p className="text-sm text-surface-600">
                          "{query}"에 해당하는 문서가 없습니다.
                        </p>
                      </motion.div>
                    ) : (
                      <div className="space-y-2.5">
                        {docResults.map((result, i) => (
                          <motion.div
                            key={result.id ?? i}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.04 }}
                          >
                            <DocResultCard
                              result={result}
                              query={query}
                              onNavigate={handleDocClick}
                            />
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  /* Empty state */
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-center py-14"
                  >
                    <div className="flex items-center justify-center gap-3 mb-4">
                      {mode === '통합' ? (
                        <Combine size={40} className="text-surface-600 opacity-40" />
                      ) : (
                        <BookOpen size={40} className="text-surface-600 opacity-40" />
                      )}
                    </div>
                    <h3 className="font-display font-semibold text-surface-800 text-base mb-2">
                      {mode === '통합' ? '통합 검색' : '문서 검색'}
                    </h3>
                    <p className="text-sm text-surface-600 max-w-sm mx-auto mb-5">
                      {mode === '통합'
                        ? '문서와 지식 그래프를 동시에 검색합니다. 관련 엔티티와 문서 청크를 함께 확인하세요.'
                        : '자연어로 질의하면 ChromaDB 벡터 유사도 기반으로 관련 문서를 찾습니다.'}
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
                            void doSearch(suggestion)
                          }}
                          className="tag tag-gold cursor-pointer hover:bg-gold-500/30 transition-colors text-xs py-1 px-3"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Right panel ───────────────────────────────────────────────────── */}
        <AnimatePresence>
          {showRightPanel && (
            <motion.div
              key="right-panel"
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: '50%' }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.2 }}
              className="flex flex-col overflow-hidden shrink-0"
              style={{ background: 'var(--color-bg-secondary)' }}
            >
              {rightPanel?.type === 'entity-detail' ? (
                <EntityDetail
                  entityId={rightPanel.entityId}
                  onClose={() => {
                    setRightPanel(mode === '그래프' ? { type: 'graph-viz' } : null)
                    setSelectedNodeId(null)
                  }}
                  onSubgraph={handleSubgraph}
                />
              ) : rightPanel?.type === 'graph-viz' && mode !== '그래프' ? (
                /* Compact graph preview in 통합 mode when no entity is selected */
                <div className="flex flex-col h-full">
                  <div
                    className="flex items-center justify-between px-4 py-3 shrink-0"
                    style={{ borderBottom: '1px solid var(--color-border)' }}
                  >
                    <div className="flex items-center gap-2">
                      <Network size={13} className="text-gold-500" />
                      <span className="text-xs font-semibold text-surface-800">지식 그래프</span>
                      {graphStats && (
                        <span className="font-mono text-2xs text-surface-600">
                          {graphStats.node_count}N · {graphStats.edge_count}E
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => setRightPanel(null)}
                      className="w-6 h-6 flex items-center justify-center rounded text-surface-600 hover:text-surface-900 hover:bg-surface-200 transition-colors"
                    >
                      <X size={13} />
                    </button>
                  </div>
                  <div className="flex-1 relative overflow-hidden">
                    {graphLoading ? (
                      <div className="flex flex-col items-center justify-center h-full gap-3">
                        <RefreshCw size={20} className="text-gold-500 animate-spin" />
                        <p className="text-xs text-surface-600">로드 중...</p>
                      </div>
                    ) : forceData.nodes.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full gap-3">
                        <Network size={32} className="text-surface-600 opacity-40" />
                        <p className="text-xs text-surface-600">그래프 데이터 없음</p>
                      </div>
                    ) : (
                      <GraphCanvas
                        data={forceData}
                        paintNode={paintNode}
                        paintLink={paintLink}
                        onNodeClick={(node) => {
                          const n = node as GraphNode
                          setSelectedNodeId(n.id)
                          setRightPanel({ type: 'entity-detail', entityId: n.id })
                        }}
                        onNodeHover={(node) => {
                          if (!node) {
                            setTooltip(null)
                            return
                          }
                          const n = node as GraphNode
                          setTooltip({ name: n.name ?? n.id, type: n.type ?? '' })
                        }}
                      />
                    )}
                    {tooltip && (
                      <div
                        className="absolute pointer-events-none z-10 px-2 py-1 rounded text-xs"
                        style={{
                          left: '50%',
                          bottom: 10,
                          transform: 'translateX(-50%)',
                          background: 'var(--color-bg-elevated)',
                          border: '1px solid var(--color-border)',
                        }}
                      >
                        <span className="font-semibold text-surface-900">{tooltip.name}</span>
                        <span className="mx-1 text-surface-600">·</span>
                        <TypeTag type={tooltip.type} />
                      </div>
                    )}
                    <div className="absolute bottom-2 right-2 text-2xs font-mono text-surface-600">
                      {forceData.nodes.length}N · {forceData.links.length}E
                    </div>
                  </div>
                </div>

              ) : rightPanel?.type === 'graph-viz' && mode === '그래프' ? (
                /* In 그래프 mode, entity list in right panel */
                <div className="flex flex-col h-full">
                  <div
                    className="flex items-center justify-between px-4 py-3 shrink-0"
                    style={{ borderBottom: '1px solid var(--color-border)' }}
                  >
                    <div className="flex items-center gap-2">
                      <SearchIcon size={12} className="text-gold-500" />
                      <span className="text-xs font-semibold text-surface-800">엔티티 검색 결과</span>
                      {entityLoading && <Loader2 size={11} className="animate-spin text-surface-600" />}
                    </div>
                    {entityResults.length > 0 && (
                      <span className="font-mono text-2xs text-surface-600">
                        {entityResults.length}개
                      </span>
                    )}
                  </div>
                  <div className="flex-1 overflow-y-auto p-3">
                    {entityResults.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
                        <Network size={28} className="text-surface-600 opacity-40" />
                        <p className="text-xs text-surface-600">
                          검색어를 입력하면 관련 엔티티를 표시합니다.
                        </p>
                        <p className="text-2xs text-surface-500">그래프 노드를 클릭해도 상세 정보를 볼 수 있습니다.</p>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        {entityResults.map((entity) => (
                          <EntityRow
                            key={entity.id}
                            entity={entity}
                            isSelected={isEntitySelected(rightPanel, entity.id)}
                            onClick={() => handleEntityClick(entity)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Stats bar at bottom ───────────────────────────────────────────────── */}
      <AnimatePresence>
        {graphStats && (mode === '그래프' || mode === '통합') && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.15 }}
            className="shrink-0"
          >
            <StatsBar stats={graphStats} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
