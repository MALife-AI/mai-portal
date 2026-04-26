import { lazy, Suspense, useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import ForceGraph2D, { type NodeObject, type LinkObject } from 'react-force-graph-2d'

// 3D 그래프는 사용자가 명시적으로 토글을 켠 경우에만 로드 (추가 ~200KB 라이브러리)
const ForceGraph3D = lazy(() => import('react-force-graph-3d'))
import {
  Search,
  RefreshCw,
  Hammer,
  ChevronDown,
  ChevronUp,
  X,
  Network,
  FileText,
  Users,
  Layers,
  ZoomIn,
  Box,
  Square,
} from 'lucide-react'
import {
  graphApi,
  type GraphVisualizationData,
  type GraphStats,
  type GraphEntity,
  type GraphCommunity,
  type GraphRAGSearchResult,
  type BuildProgress,
} from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { cn } from '@/lib/utils'

// ─── Entity colour palette ────────────────────────────────────────────────────

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
  image: '#E91E63',
  table: '#00BCD4',
  fact: '#78909C',
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

// ─── Internal graph types ─────────────────────────────────────────────────────

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

const ENTITY_TYPES = ['all', 'product', 'coverage', 'condition', 'person', 'organization', 'regulation', 'concept', 'document', 'term', 'actuarial']

const PROP_LABELS: Record<string, string> = {
  product_code: '상품코드',
  rider_code: '보종코드',
  coverage_amount: '보장금액',
  coverage_period: '보장기간',
  payment_period: '납입기간',
  payment_frequency: '납입주기',
  waiting_period: '면책기간',
  renewal_type: '갱신유형',
  age_range: '가입연령',
  underwriting_class: '심사등급',
  premium_type: '보험료유형',
  surrender_type: '환급유형',
  surrender_ratio: '환급비율',
  base_amount: '기준가입금액',
  sub_types: '세부유형',
  parent_product: '주계약',
  claim_conditions: '지급조건',
  exclusions: '면책사항',
  duplicate_surgery_rule: '중복수술규칙',
  effective_date: '시행일',
  document_type: '문서유형',
  icd_code: '질병코드',
  severity: '중증도',
  article_number: '조항번호',
  definition: '정의',
  rate_reference: '위험률출처',
  expense_ratio: '사업비율',
  lapse_rate: '해지율',
  mandatory_riders: '의무동시가입',
  conversion_period: '전환가능기간',
  revival_period: '부활기간',
  premium_exemption: '납입면제',
  source_document: '출처문서',
  content_type: '콘텐츠유형',
  description: '설명',
}

const RAG_MODES = [
  { value: 'local', label: '로컬' },
  { value: 'global', label: '글로벌' },
  { value: 'hybrid', label: '하이브리드' },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

// ─── Sub-components ───────────────────────────────────────────────────────────

interface StatBadgeProps {
  label: string
  value: number | string
  color?: string
}

function StatBadge({ label, value, color }: StatBadgeProps) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-md px-4 py-2 min-w-[72px]"
      style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
    >
      <span
        className="text-xl font-mono font-bold leading-none"
        style={{ color: color ?? 'var(--color-text-primary)' }}
      >
        {value}
      </span>
      <span className="text-2xs text-surface-600 mt-0.5 font-mono uppercase tracking-widest">
        {label}
      </span>
    </div>
  )
}

interface TypeTagProps {
  type: string
}

function TypeTag({ type }: TypeTagProps) {
  const color = entityColor(type)
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-2xs font-mono font-semibold"
      style={{
        background: `${color}22`,
        color,
        border: `1px solid ${color}55`,
      }}
    >
      {type}
    </span>
  )
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

interface DetailPanelProps {
  entityId: string | null
  onClose: () => void
  onSubgraph: (id: string) => void
}

function DetailPanel({ entityId, onClose, onSubgraph }: DetailPanelProps) {
  const navigate = useNavigate()
  const [data, setData] = useState<{
    entity: GraphEntity
    neighbors: GraphEntity[]
    relationships: import('@/api/client').GraphRelationship[]
  } | null>(null)
  const [communities] = useState<GraphCommunity[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!entityId) {
      setData(null)
      return
    }
    setIsLoading(true)
    graphApi.getEntity(entityId)
      .then((entityData) => {
        setData(entityData)
      })
      .catch((err) => console.error('Entity fetch error:', err))
      .finally(() => setIsLoading(false))
  }, [entityId])

  if (!entityId) return null

  const entity = data?.entity
  const communityList = Array.isArray(communities) ? communities : []
  const entityCommunity = entity?.id
    ? communityList.find((c) => c.entity_ids?.includes(entity.id))
    : undefined

  return (
    <motion.div
      key="detail-panel"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.2 }}
      className="panel flex flex-col overflow-hidden"
      style={{ minHeight: 0 }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <span className="text-xs font-mono text-surface-600 uppercase tracking-widest">
          엔티티 상세
        </span>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center justify-center rounded text-surface-600 hover:text-surface-900 hover:bg-surface-200"
          style={{
            width: '28px',
            height: '28px',
            transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
          }}
          aria-label="엔티티 상세 닫기"
        >
          <X size={13} aria-hidden="true" />
        </button>
      </div>

      {isLoading ? (
        <div
          className="flex-1 p-4 space-y-2"
          role="status"
          aria-busy="true"
          aria-label="엔티티 상세 불러오는 중"
        >
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-8 rounded" aria-hidden="true" />
          ))}
        </div>
      ) : entity ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Name + type */}
          <div>
            <h3 className="text-base font-display font-semibold text-surface-900 leading-tight mb-1.5">
              {entity.name}
            </h3>
            <div className="flex items-center gap-2 flex-wrap">
              <TypeTag type={entity.entity_type} />
              <span className="font-mono text-2xs text-surface-600">
                언급 {entity.mentions}회
              </span>
            </div>
          </div>

          {/* Properties */}
          {Object.keys(entity.properties).length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                속성
              </p>
              <div className="space-y-1">
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
              <ul className="space-y-1">
                {entity.source_paths.map((path) => (
                  <li key={path}>
                    <button
                      type="button"
                      onClick={() => navigate(`/docs?path=${encodeURIComponent(path)}`)}
                      className="w-full text-left flex items-center gap-2 px-2 py-1.5 rounded text-xs text-gold-500 hover:bg-surface-200"
                      style={{
                        minHeight: '30px',
                        transition: 'background-color 200ms var(--ease-out)',
                      }}
                      aria-label={`${path} 문서 열기`}
                    >
                      <FileText size={11} className="shrink-0" aria-hidden="true" />
                      <span className="truncate font-mono">{path.split('/').pop() || path}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Related entities */}
          {(data?.neighbors ?? []).length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                연관 엔티티
              </p>
              <ul className="flex flex-wrap gap-1.5" aria-label="연관 엔티티">
                {(data?.neighbors ?? []).slice(0, 10).map((n) => {
                  const c = entityColor(n.entity_type)
                  return (
                    <li
                      key={n.id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs"
                      style={{
                        background: `color-mix(in srgb, ${c} 10%, transparent)`,
                        color: c,
                        border: `1px solid color-mix(in srgb, ${c} 25%, transparent)`,
                      }}
                    >
                      {n.name}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {/* Community */}
          {entityCommunity && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                커뮤니티
              </p>
              <div
                className="rounded-md p-3 space-y-1"
                style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
              >
                <div className="flex items-center gap-2">
                  <Users size={12} className="text-gold-500 shrink-0" />
                  <span className="text-xs font-semibold text-surface-900">
                    {entityCommunity.name}
                  </span>
                  <span className="ml-auto font-mono text-2xs text-surface-600">
                    Lv.{entityCommunity.level}
                  </span>
                </div>
                {entityCommunity.summary && (
                  <p className="text-xs text-surface-700 leading-relaxed mt-1.5">
                    {entityCommunity.summary}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Subgraph button */}
          <button
            type="button"
            onClick={() => onSubgraph(entity.id)}
            className="btn-secondary w-full flex items-center justify-center gap-2 mt-2"
            aria-label={`${entity.name} 서브그래프 보기`}
          >
            <ZoomIn size={13} aria-hidden="true" />
            서브그래프 보기
          </button>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-4" role="status">
          <p className="text-sm text-surface-600">엔티티를 불러올 수 없습니다.</p>
        </div>
      )}
    </motion.div>
  )
}

// ─── GraphRAG Bottom Panel ────────────────────────────────────────────────────

interface RagPanelProps {
  onSendToAgent: (context: string) => void
}

function RagPanel({ onSendToAgent }: RagPanelProps) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [isSearching, setIsSearching] = useState(false)
  const [result, setResult] = useState<GraphRAGSearchResult | null>(null)
  const toast = useToast()

  async function handleSearch() {
    if (!query.trim()) return
    setIsSearching(true)
    try {
      const data = await graphApi.graphRAGSearch({ query: query.trim(), mode, n_results: 10 })
      setResult(data)
    } catch (err) {
      toast.error('GraphRAG 검색 실패', String(err))
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Search row */}
      <form
        className="flex items-center gap-2"
        role="search"
        onSubmit={(e) => { e.preventDefault(); void handleSearch() }}
      >
        <label htmlFor="rag-query" className="sr-only">GraphRAG 쿼리</label>
        <input
          id="rag-query"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="GraphRAG 쿼리 입력..."
          className="input-field flex-1"
          autoComplete="off"
        />
        <label htmlFor="rag-mode" className="sr-only">검색 모드</label>
        <select
          id="rag-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="input-field w-32"
          aria-label="검색 모드"
        >
          {RAG_MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={isSearching || !query.trim()}
          className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
          aria-busy={isSearching}
        >
          {isSearching ? (
            <RefreshCw size={13} className="animate-spin" aria-hidden="true" />
          ) : (
            <Search size={13} aria-hidden="true" />
          )}
          검색
        </button>
      </form>

      {result && (
        <div className="space-y-3">
          {/* Graph context */}
          <div>
            <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
              그래프 컨텍스트
            </p>
            <div
              className="rounded-md p-3 text-xs text-surface-800 leading-relaxed max-h-32 overflow-y-auto"
              style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
            >
              {result.graph_context || '—'}
            </div>
          </div>

          {/* Matched entities */}
          {result.matched_entities.length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                매칭 엔티티
              </p>
              <div className="flex flex-wrap gap-1.5">
                {result.matched_entities.map((e) => (
                  <TypeTag key={e.id} type={e.entity_type} />
                ))}
                {result.matched_entities.map((e) => (
                  <span key={`${e.id}-name`} className="text-xs text-surface-800 self-center">
                    {e.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Related entities */}
          {result.related_entities.length > 0 && (
            <div>
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                연관 엔티티
              </p>
              <ul className="flex flex-wrap gap-1.5" aria-label="연관 엔티티">
                {result.related_entities.slice(0, 12).map((e) => {
                  const c = entityColor(e.entity_type)
                  return (
                    <li
                      key={e.id}
                      className="px-2 py-0.5 rounded text-xs"
                      style={{
                        background: `color-mix(in srgb, ${c} 10%, transparent)`,
                        color: c,
                        border: `1px solid color-mix(in srgb, ${c} 25%, transparent)`,
                      }}
                    >
                      {e.name}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {/* Send to agent */}
          <button
            type="button"
            onClick={() => onSendToAgent(result.combined_context)}
            className="btn-secondary flex items-center gap-2"
            aria-label="검색 결과를 에이전트 컨텍스트로 전달"
          >
            <Network size={13} aria-hidden="true" />
            에이전트에 전달
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function KnowledgeGraph() {
  const navigate = useNavigate()
  const toast = useToast()
  const { userId } = useStore()
  const isAdmin = userId.startsWith('admin')

  const graphRef = useRef<HTMLDivElement>(null)

  // Data state
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [graphData, setGraphData] = useState<GraphVisualizationData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isBuilding, setIsBuilding] = useState(false)
  const [buildProgress, setBuildProgress] = useState<BuildProgress | null>(null)

  // Search / filter state
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [highlightId, setHighlightId] = useState<string | null>(null)

  // Selection state
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  // Tooltip state
  const [tooltip, setTooltip] = useState<{ x: number; y: number; name: string; type: string } | null>(null)

  // Bottom panel collapse state
  const [ragOpen, setRagOpen] = useState(false)

  // Subgraph mode: null = full graph, string = entity id
  const [subgraphEntityId, setSubgraphEntityId] = useState<string | null>(null)
  const [is3D, setIs3D] = useState(false)
  const [colorBy, setColorBy] = useState<'type' | 'community'>('type')
  const [subgraphData, setSubgraphData] = useState<GraphVisualizationData | null>(null)

  // ── Fetch ──────────────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setIsLoading(true)
    try {
      const [statsData, vizData] = await Promise.all([
        graphApi.getStats(),
        graphApi.getVisualization(),
      ])
      setStats(statsData)
      setGraphData(vizData)
    } catch (err) {
      toast.error('그래프 데이터 로드 실패', String(err))
    } finally {
      setIsLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

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

  // ── Build graph ────────────────────────────────────────────────────────────

  async function handleBuildGraph() {
    setIsBuilding(true)
    setBuildProgress(null)
    try {
      await graphApi.buildGraph()
      // 비동기 빌드 — 2초마다 진행 상황 폴링
      const poll = setInterval(async () => {
        try {
          const r = await fetch('/api/v1/graph/build/progress', { headers: { 'X-User-Id': userId } })
          const p = await r.json()
          setBuildProgress(p)
          if (p.status === 'completed') {
            clearInterval(poll)
            setIsBuilding(false)
            setBuildProgress(null)
            toast.success(
              '그래프 빌드 완료',
              `엔티티 ${p.entities ?? 0}개, 관계 ${p.relationships ?? 0}개`,
            )
            await fetchData()
          } else if (p.status === 'error' || p.status === 'idle') {
            clearInterval(poll)
            setIsBuilding(false)
            setBuildProgress(null)
            if (p.status === 'error') toast.error('그래프 빌드 실패', p.current_file || '알 수 없는 오류')
          }
        } catch { /* ignore */ }
      }, 2000)
    } catch (err) {
      toast.error('그래프 빌드 실패', String(err))
      setIsBuilding(false)
    }
  }

  // ── Entity search ──────────────────────────────────────────────────────────

  async function handleEntitySearch() {
    const q = searchQuery.trim()
    if (!q) {
      setHighlightId(null)
      return
    }
    try {
      const results = await graphApi.searchEntities(
        q,
        typeFilter !== 'all' ? typeFilter : undefined,
        1,
      )
      const hit = results[0]
      if (hit) {
        setHighlightId(hit.id)
        setSelectedNodeId(hit.id)
        toast.info('엔티티 발견', hit.name)
      } else {
        setHighlightId(null)
        toast.warning('검색 결과 없음', `"${q}"에 해당하는 엔티티가 없습니다.`)
      }
    } catch (err) {
      toast.error('엔티티 검색 실패', String(err))
    }
  }

  // ── Active graph data (full or subgraph) ───────────────────────────────────

  const activeVizData: GraphVisualizationData | null =
    subgraphEntityId && subgraphData ? subgraphData : graphData

  // ── Derived force-graph data ───────────────────────────────────────────────

  // 커뮤니티 → 노드 매핑
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
      .map((e) => ({
        source: e.source,
        target: e.target,
        type: e.type,
        weight: e.weight,
      }))

    return { nodes, links }
  }, [activeVizData, typeFilter, highlightId, nodeCommunityMap])

  // ── Canvas node painter ────────────────────────────────────────────────────

  const paintNode = useCallback(
    (node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as GraphNode
      const size = nodeSize(n.mentions ?? 1)
      const color = colorBy === 'community'
        ? communityColor(n.community)
        : entityColor(n.type ?? '')
      const isSelected = n.id === selectedNodeId
      const isHighlighted = n.highlighted

      ctx.beginPath()
      ctx.arc(n.x ?? 0, n.y ?? 0, size, 0, 2 * Math.PI)

      if (isHighlighted) {
        // Pulsing ring for search highlight
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

      // Label at zoom >= 2
      if (globalScale >= 2) {
        const label = n.name ?? n.id
        ctx.font = `${Math.max(10, size * 0.9) / globalScale}px JetBrains Mono, monospace`
        ctx.fillStyle = 'rgba(232,237,244,0.95)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(label, n.x ?? 0, (n.y ?? 0) + size + 2 / globalScale)
      }
    },
    [selectedNodeId, colorBy],
  )

  // ── Link canvas painter ────────────────────────────────────────────────────

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

  // ── Send GraphRAG context to agent ─────────────────────────────────────────

  function handleSendToAgent(context: string) {
    // Store to localStorage so AgentConsole can pick it up
    try {
      localStorage.setItem('malife_pending_agent_query', context)
    } catch {
      // ignore
    }
    toast.success('에이전트에 전달됨', '에이전트 콘솔로 이동합니다.')
    navigate('/agent')
  }

  // ── Tooltip handler ────────────────────────────────────────────────────────

  function handleNodeHover(node: NodeObject | null) {
    if (!node) {
      setTooltip(null)
      return
    }
    const n = node as GraphNode
    setTooltip({ x: n.x ?? 0, y: n.y ?? 0, name: n.name ?? n.id, type: n.type ?? '' })
  }

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--color-bg-primary)' }}>
      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-4 py-3 shrink-0 flex-wrap"
        style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
      >
        {/* Search */}
        <form
          role="search"
          onSubmit={(e) => { e.preventDefault(); void handleEntitySearch() }}
          className="flex items-center gap-2 flex-1 min-w-0 max-w-md"
        >
          <label htmlFor="entity-search" className="sr-only">엔티티 검색</label>
          <div className="relative flex-1">
            <Search
              size={13}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-600 pointer-events-none"
              aria-hidden="true"
            />
            <input
              id="entity-search"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="엔티티 검색..."
              className="input-field pl-8 w-full"
              autoComplete="off"
            />
          </div>
          <button
            type="submit"
            className="btn-secondary flex items-center gap-1.5 whitespace-nowrap"
          >
            <Search size={12} aria-hidden="true" />
            검색
          </button>
        </form>

        {/* Type filter */}
        <label htmlFor="type-filter" className="sr-only">타입 필터</label>
        <select
          id="type-filter"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="input-field w-36"
          aria-label="엔티티 타입 필터"
        >
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === 'all' ? '전체 타입' : t}
            </option>
          ))}
        </select>

        {/* Subgraph mode indicator */}
        {subgraphEntityId && (
          <div className="flex items-center gap-2" role="status">
            <span className="text-xs font-mono text-gold-500">서브그래프 모드</span>
            <button
              type="button"
              onClick={() => {
                setSubgraphEntityId(null)
                setSelectedNodeId(null)
              }}
              className="btn-secondary flex items-center gap-1 text-xs"
              aria-label="서브그래프 종료 및 전체 보기"
            >
              <X size={11} aria-hidden="true" />
              전체 보기
            </button>
          </div>
        )}

        {/* 클러스터 기준 */}
        <label htmlFor="color-by" className="sr-only">색상 기준</label>
        <select
          id="color-by"
          value={colorBy}
          onChange={(e) => setColorBy(e.target.value as 'type' | 'community')}
          className="input-field text-xs py-1.5 px-2"
          style={{ width: 'auto', minWidth: 0 }}
          aria-label="노드 색상 기준"
        >
          <option value="type">엔티티 타입별</option>
          <option value="community">커뮤니티별</option>
        </select>

        {/* 2D/3D 토글 */}
        <button
          type="button"
          onClick={() => setIs3D((v) => !v)}
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-mono',
            is3D
              ? 'bg-gold-500/15 text-gold-500 border border-gold-500/30'
              : 'btn-secondary',
          )}
          style={{
            minHeight: '30px',
            transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
          }}
          aria-pressed={is3D}
          aria-label={is3D ? '2D로 전환' : '3D로 전환'}
        >
          {is3D
            ? <Box size={13} aria-hidden="true" />
            : <Square size={13} aria-hidden="true" />
          }
          {is3D ? '3D' : '2D'}
        </button>

        <div className="flex-1" />

        {/* Stats */}
        {stats && (
          <div className="flex items-center gap-2" role="status" aria-label="그래프 통계">
            <StatBadge label="노드" value={stats.node_count} color="var(--color-gold)" />
            <StatBadge label="엣지" value={stats.edge_count} color="var(--color-blue)" />
            <StatBadge label="커뮤니티" value={stats.communities} color="var(--color-success)" />
          </div>
        )}

        {/* Build button (admin only) */}
        {isAdmin && (
          <button
            type="button"
            onClick={() => void handleBuildGraph()}
            disabled={isBuilding}
            className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
            aria-busy={isBuilding}
          >
            {isBuilding ? (
              <RefreshCw size={13} className="animate-spin" aria-hidden="true" />
            ) : (
              <Hammer size={13} aria-hidden="true" />
            )}
            그래프 빌드
          </button>
        )}

        <button
          type="button"
          onClick={() => void fetchData()}
          disabled={isLoading}
          className="btn-secondary flex items-center gap-1.5"
          aria-label="그래프 데이터 새로고침"
        >
          <RefreshCw
            size={13}
            className={cn(isLoading && 'animate-spin')}
            aria-hidden="true"
          />
        </button>
      </div>

      {/* Build progress bar */}
      <AnimatePresence initial={false}>
        {isBuilding && buildProgress && buildProgress.status === 'running' && (() => {
          const isRetry = Boolean(buildProgress.retry_round)
          const total = isRetry ? (buildProgress.retry_total ?? 0) : buildProgress.total_files
          const done = isRetry ? (buildProgress.retry_done ?? 0) : buildProgress.processed
          const percent = total > 0 ? Math.round((done / total) * 100) : 0
          return (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
              className="mx-4 mb-2 p-3 rounded-md text-xs"
              style={{ background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)' }}
              role="status"
              aria-live="polite"
            >
              {isRetry ? (
                <>
                  <div className="flex items-center justify-between mb-1.5 text-surface-700">
                    <span>재시도 {buildProgress.retry_round}차: {done} / {total} 파일</span>
                    <span className="font-mono">{percent}%</span>
                  </div>
                  <div
                    className="h-1.5 rounded-full overflow-hidden"
                    style={{ background: 'var(--color-border)' }}
                    role="progressbar"
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`그래프 재시도 ${percent}%`}
                  >
                    <motion.div
                      className="h-full rounded-full bg-gold-500"
                      initial={{ width: 0 }}
                      animate={{ width: `${percent}%` }}
                      transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
                    />
                  </div>
                  <div className="flex items-center justify-between mt-1.5 text-2xs text-surface-600">
                    <span>성공 {(buildProgress.retry_done ?? 0) - (buildProgress.retry_failed ?? 0)}개 · 실패 {buildProgress.retry_failed ?? 0}개 · 엔티티 {buildProgress.entities}개</span>
                    <span className="font-mono truncate ml-2 max-w-[200px]">{buildProgress.current_file}</span>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-1.5 text-surface-700">
                    <span>{done} / {total} 파일 처리 중{done > 0 && buildProgress.entities > done * 10 ? ' (이어서 빌드)' : ''}</span>
                    <span className="font-mono">{percent}%</span>
                  </div>
                  <div
                    className="h-1.5 rounded-full overflow-hidden"
                    style={{ background: 'var(--color-border)' }}
                    role="progressbar"
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`그래프 빌드 ${percent}%`}
                  >
                    <motion.div
                      className="h-full rounded-full bg-gold-500"
                      initial={{ width: 0 }}
                      animate={{ width: `${percent}%` }}
                      transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
                    />
                  </div>
                  <div className="flex items-center justify-between mt-1.5 text-2xs text-surface-600">
                    <span>엔티티 {buildProgress.entities}개 · 관계 {buildProgress.relationships}개</span>
                    <span className="font-mono truncate ml-2 max-w-[200px]">{buildProgress.current_file}</span>
                  </div>
                </>
              )}
            </motion.div>
          )
        })()}
      </AnimatePresence>

      {/* ── Main split area ──────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: graph canvas */}
        <div
          ref={graphRef}
          className="relative overflow-hidden"
          style={{ flex: selectedNodeId ? '0 0 70%' : '1 1 100%', transition: 'flex 0.2s' }}
        >
          {isLoading ? (
            <div
              className="flex flex-col items-center justify-center h-full gap-4"
              role="status"
              aria-live="polite"
            >
              <RefreshCw size={28} className="text-gold-500 animate-spin" aria-hidden="true" />
              <p className="text-sm text-surface-600">그래프 데이터 로드 중...</p>
            </div>
          ) : forceData.nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <Network size={48} className="text-surface-600" aria-hidden="true" />
              <p className="text-sm text-surface-700">그래프 데이터가 없습니다.</p>
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => void handleBuildGraph()}
                  disabled={isBuilding}
                  className="btn-primary flex items-center gap-2"
                  aria-busy={isBuilding}
                >
                  <Hammer size={14} aria-hidden="true" />
                  그래프 빌드 시작
                </button>
              )}
            </div>
          ) : (
            <GraphCanvas
              data={forceData}
              paintNode={paintNode}
              paintLink={paintLink}
              onNodeClick={(node) => setSelectedNodeId((node as GraphNode).id)}
              onNodeHover={handleNodeHover}
              is3D={is3D}
              colorBy={colorBy}
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

          {/* Legend overlay */}
          <div
            className="absolute top-3 left-3 rounded-md p-3 space-y-1.5"
            style={{
              background: 'rgba(20,30,51,0.85)',
              border: '1px solid var(--color-border)',
              backdropFilter: 'blur(4px)',
            }}
          >
            <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
              타입 범례
            </p>
            {Object.entries(ENTITY_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: color }}
                />
                <span className="text-2xs font-mono text-surface-700">{type}</span>
              </div>
            ))}
          </div>

          {/* Node count overlay */}
          <div
            className="absolute bottom-3 right-3 text-2xs font-mono text-surface-600"
          >
            {forceData.nodes.length} nodes · {forceData.links.length} edges
          </div>
        </div>

        {/* Right: detail panel */}
        <AnimatePresence>
          {selectedNodeId && (
            <div
              className="shrink-0 overflow-hidden flex"
              style={{
                width: '30%',
                borderLeft: '1px solid var(--color-border)',
                minHeight: 0,
              }}
            >
              <DetailPanel
                entityId={selectedNodeId}
                onClose={() => setSelectedNodeId(null)}
                onSubgraph={(id) => {
                  setSubgraphEntityId(id)
                  setSelectedNodeId(null)
                }}
              />
            </div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Bottom collapsible RAG panel ─────────────────────────────────────── */}
      <div
        className="shrink-0"
        style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
      >
        {/* Collapse toggle */}
        <button
          onClick={() => setRagOpen((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-100 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Layers size={13} className="text-gold-500" />
            <span className="text-xs font-semibold text-surface-800">GraphRAG 검색</span>
          </div>
          {ragOpen ? (
            <ChevronDown size={13} className="text-surface-600" />
          ) : (
            <ChevronUp size={13} className="text-surface-600" />
          )}
        </button>

        <AnimatePresence>
          {ragOpen && (
            <motion.div
              key="rag-panel"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 pt-1">
                <RagPanel onSendToAgent={handleSendToAgent} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// ─── GraphCanvas wrapper (2D/3D 전환 지원) ──────────────────────────────────

interface GraphCanvasProps {
  data: InternalGraphData
  paintNode: (node: NodeObject, ctx: CanvasRenderingContext2D, scale: number) => void
  paintLink: (link: LinkObject, ctx: CanvasRenderingContext2D) => void
  onNodeClick: (node: NodeObject) => void
  onNodeHover: (node: NodeObject | null) => void
  is3D?: boolean
  colorBy?: 'type' | 'community'
}

function GraphCanvas({ data, paintNode, paintLink, onNodeClick, onNodeHover, is3D = false, colorBy = 'type' }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        })
      }
    })
    obs.observe(el)
    setDimensions({ width: el.clientWidth, height: el.clientHeight })
    return () => obs.disconnect()
  }, [])

  if (is3D) {
    return (
      <div ref={containerRef} className="w-full h-full">
        <Suspense
          fallback={
            <div
              className="flex items-center justify-center h-full"
              role="status"
              aria-live="polite"
            >
              <RefreshCw size={24} className="animate-spin text-gold-500" aria-hidden="true" />
              <span className="ml-2 text-sm text-surface-600">3D 엔진 로드 중...</span>
            </div>
          }
        >
          <ForceGraph3D
            graphData={data}
            width={dimensions.width}
            height={dimensions.height}
            onNodeClick={onNodeClick}
            onNodeHover={onNodeHover}
            nodeLabel={(node) => (node as GraphNode).name ?? ''}
            nodeColor={(node) => {
              const n = node as GraphNode
              return colorBy === 'community'
                ? communityColor(n.community)
                : entityColor(n.type ?? '')
            }}
            nodeVal={(node) => nodeSize((node as GraphNode).mentions ?? 1)}
            nodeOpacity={0.9}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkColor={(link) => edgeColor((link as GraphLink).type ?? '')}
            linkWidth={(link) => Math.max(0.5, ((link as GraphLink).weight ?? 1) * 0.8)}
            linkOpacity={0.6}
            backgroundColor="#0d1117"
            cooldownTicks={120}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
          />
        </Suspense>
      </div>
    )
  }

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
