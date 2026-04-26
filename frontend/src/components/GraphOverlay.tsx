import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Loader2, Maximize2, Minimize2, FileText } from 'lucide-react'
import ForceGraph2D, { type NodeObject, type LinkObject } from 'react-force-graph-2d'
import { graphApi, type SourceNode } from '@/api/client'

const CITE_COLORS = [
  '#F37021', '#4A90D9', '#34C759', '#AF52DE', '#FF3B30',
  '#5AC8FA', '#FFCC00', '#FF2D55', '#64D2FF', '#30D158',
]

interface Props {
  sourceNodes: SourceNode[]
  focusIndex: number
  onClose: () => void
}

interface GNode extends NodeObject {
  id: string
  name: string
  type: string
  mentions: number
  isHighlighted?: boolean
  isReferenced?: boolean      // 답변에 참조된 노드
  highlightColor?: string
  highlightIndex?: number
}

interface GLink extends LinkObject {
  relation_type?: string
  isReferencedPath?: boolean  // 참조 경로에 포함된 엣지
}

export function GraphOverlay({ sourceNodes, focusIndex, onClose }: Props) {
  const [loading, setLoading] = useState(true)
  const [graphData, setGraphData] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState<GNode | null>(null)
  const [expanded, setExpanded] = useState(false)
  const graphRef = useRef<any>(null)

  // Esc 키로 닫기 + body scroll lock
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (selectedNode) setSelectedNode(null)
        else onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose, selectedNode])

  // Fetch subgraphs for all source nodes and merge
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      const allNodes = new Map<string, GNode>()
      const allLinks: GLink[] = []
      const highlightIds = new Set<string>()
      const referencedIds = new Set<string>(sourceNodes.map(sn => sn.id))

      // Map source node IDs to their citation index + color
      const idToIndex = new Map<string, number>()
      sourceNodes.forEach((sn, i) => {
        idToIndex.set(sn.id, i)
        highlightIds.add(sn.id)
      })

      // Fetch subgraph for the focused node
      const focusNode = sourceNodes[focusIndex]
      if (!focusNode) { setLoading(false); return }

      try {
        const data = await graphApi.getSubgraph(focusNode.id, 2)
        if (cancelled) return

        for (const n of data.nodes) {
          const isSource = idToIndex.has(n.id)
          const idx = idToIndex.get(n.id)
          allNodes.set(n.id, {
            ...n,
            isHighlighted: isSource,
            highlightColor: isSource ? CITE_COLORS[(idx ?? 0) % CITE_COLORS.length] : undefined,
            highlightIndex: isSource ? (idx ?? 0) + 1 : undefined,
          })
        }

        for (const e of data.edges) {
          const isRefPath = referencedIds.has(e.source) || referencedIds.has(e.target)
          allLinks.push({
            source: e.source,
            target: e.target,
            relation_type: e.relation_type || e.type || '',
            isReferencedPath: isRefPath,
          })
        }

        // Mark neighbor nodes of referenced nodes as "referenced"
        for (const e of data.edges) {
          if (referencedIds.has(e.source) && allNodes.has(e.target)) {
            const n = allNodes.get(e.target)!
            if (!n.isHighlighted) n.isReferenced = true
          }
          if (referencedIds.has(e.target) && allNodes.has(e.source)) {
            const n = allNodes.get(e.source)!
            if (!n.isHighlighted) n.isReferenced = true
          }
        }

        // Also fetch subgraphs for other source nodes (shallow, depth=1)
        const otherFetches = sourceNodes
          .filter((_, i) => i !== focusIndex)
          .slice(0, 3) // limit to avoid too many requests
          .map(async (sn) => {
            try {
              const d = await graphApi.getSubgraph(sn.id, 1)
              return d
            } catch { return null }
          })

        const otherResults = await Promise.all(otherFetches)
        if (cancelled) return

        for (const data of otherResults) {
          if (!data) continue
          for (const n of data.nodes) {
            if (!allNodes.has(n.id)) {
              const isSource = idToIndex.has(n.id)
              const idx = idToIndex.get(n.id)
              allNodes.set(n.id, {
                ...n,
                isHighlighted: isSource,
                highlightColor: isSource ? CITE_COLORS[(idx ?? 0) % CITE_COLORS.length] : undefined,
                highlightIndex: isSource ? (idx ?? 0) + 1 : undefined,
              })
            }
          }
          for (const e of data.edges) {
            const isRefPath = referencedIds.has(e.source) || referencedIds.has(e.target)
            allLinks.push({
              source: e.source,
              target: e.target,
              relation_type: e.relation_type || e.type || '',
              isReferencedPath: isRefPath,
            })
          }
        }

        setGraphData({
          nodes: Array.from(allNodes.values()),
          links: allLinks,
        })
      } catch (err) {
        console.error('Subgraph fetch failed:', err)
      }
      setLoading(false)
    }
    load()
    return () => { cancelled = true }
  }, [sourceNodes, focusIndex])

  // Center on focus node after graph loads
  useEffect(() => {
    if (!loading && graphRef.current && graphData.nodes.length > 0) {
      const focusNode = sourceNodes[focusIndex]
      const node = graphData.nodes.find(n => n.id === focusNode?.id)
      if (node && node.x != null && node.y != null) {
        setTimeout(() => {
          graphRef.current?.centerAt(node.x, node.y, 500)
          graphRef.current?.zoom(2, 500)
        }, 300)
      }
    }
  }, [loading, graphData, sourceNodes, focusIndex])

  const paintNode = useCallback((node: GNode, ctx: CanvasRenderingContext2D) => {
    const x = node.x ?? 0
    const y = node.y ?? 0
    const r = node.isHighlighted ? 8 : 4

    // Canvas는 CSS 변수를 직접 못 쓰므로 루트 computed style에서 읽어 테마 변경도 반영
    const rootStyle = getComputedStyle(document.documentElement)
    const goldColor = rootStyle.getPropertyValue('--color-gold').trim() || '#F37021'
    const mutedColor = rootStyle.getPropertyValue('--color-text-muted').trim() || '#8a9fb8'
    const textPrimary = rootStyle.getPropertyValue('--color-text-primary').trim() || '#e8edf4'

    if (node.isHighlighted && node.highlightColor) {
      // Glow effect
      ctx.beginPath()
      ctx.arc(x, y, r + 4, 0, 2 * Math.PI)
      ctx.fillStyle = `${node.highlightColor}33`
      ctx.fill()

      // Main circle
      ctx.beginPath()
      ctx.arc(x, y, r, 0, 2 * Math.PI)
      ctx.fillStyle = node.highlightColor
      ctx.fill()
      ctx.strokeStyle = textPrimary
      ctx.lineWidth = 1.5
      ctx.stroke()

      // Citation number
      ctx.fillStyle = textPrimary
      ctx.font = 'bold 8px monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(String(node.highlightIndex ?? ''), x, y)

      // Label
      ctx.fillStyle = node.highlightColor
      ctx.font = 'bold 10px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.name, x, y + r + 10)
    } else if (node.isReferenced) {
      // 참조된 하위 노드: 점선 테두리 + gold 강조 (테마 반응)
      ctx.beginPath()
      ctx.arc(x, y, 6, 0, 2 * Math.PI)
      ctx.fillStyle = `${goldColor}40`
      ctx.fill()
      ctx.setLineDash([2, 2])
      ctx.strokeStyle = goldColor
      ctx.lineWidth = 1.5
      ctx.stroke()
      ctx.setLineDash([])

      ctx.fillStyle = goldColor
      ctx.font = 'bold 8px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.name.slice(0, 12), x, y + 12)
    } else {
      ctx.beginPath()
      ctx.arc(x, y, r, 0, 2 * Math.PI)
      ctx.fillStyle = mutedColor
      ctx.fill()

      ctx.fillStyle = `${mutedColor}88`
      ctx.font = '7px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.name.slice(0, 8), x, y + r + 7)
    }
  }, [])

  const width = expanded ? window.innerWidth - 100 : 600
  const height = expanded ? window.innerHeight - 100 : 400

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
        className="fixed inset-0 z-50 flex items-center justify-center"
        style={{ background: 'var(--color-overlay)', backdropFilter: 'blur(4px)' }}
        onClick={onClose}
        role="presentation"
      >
        <motion.div
          initial={{ scale: 0.96, opacity: 0, y: 8 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.96, opacity: 0, y: 8 }}
          transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
          onClick={(e) => e.stopPropagation()}
          className="rounded-xl overflow-hidden"
          role="dialog"
          aria-modal="true"
          aria-labelledby="graph-overlay-title"
          style={{
            width: width + 32,
            background: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
            boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
          }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid var(--color-border)' }}
          >
            <div className="flex items-center gap-2">
              <h2 id="graph-overlay-title" className="text-sm font-semibold text-surface-900">
                참조 지식그래프
              </h2>
              <span className="text-2xs font-mono text-surface-600">
                {graphData.nodes.length} nodes / {graphData.links.length} edges
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setExpanded(v => !v)}
                className="inline-flex items-center justify-center rounded text-surface-600 hover:text-surface-900 hover:bg-surface-200"
                style={{
                  width: '32px',
                  height: '32px',
                  transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
                }}
                aria-label={expanded ? '그래프 축소' : '그래프 확대'}
              >
                {expanded
                  ? <Minimize2 size={14} aria-hidden="true" />
                  : <Maximize2 size={14} aria-hidden="true" />
                }
              </button>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex items-center justify-center rounded text-surface-600 hover:text-status-error hover:bg-surface-200"
                style={{
                  width: '32px',
                  height: '32px',
                  transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
                }}
                aria-label="그래프 닫기"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          </div>

          {/* Legend */}
          <ul
            className="flex flex-wrap gap-2 px-4 py-2"
            style={{ borderBottom: '1px solid var(--color-border)' }}
            aria-label="참조 출처 목록"
          >
            {sourceNodes.map((sn, i) => {
              const color = CITE_COLORS[i % CITE_COLORS.length]
              return (
                <li
                  key={sn.id}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono"
                  style={{
                    background: `color-mix(in srgb, ${color} 13%, transparent)`,
                    color,
                    border: `1px solid color-mix(in srgb, ${color} 27%, transparent)`,
                  }}
                >
                  <span className="font-bold">[{i + 1}]</span> {sn.name}
                </li>
              )
            })}
          </ul>

          {/* Graph */}
          <div style={{ width, height, margin: '0 auto' }}>
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 size={24} className="animate-spin text-gold-500" />
              </div>
            ) : graphData.nodes.length === 0 ? (
              <div className="flex items-center justify-center h-full text-surface-600 text-sm">
                서브그래프 데이터 없음
              </div>
            ) : (
              <ForceGraph2D
                ref={graphRef}
                graphData={graphData as any}
                width={width}
                height={height}
                nodeCanvasObject={paintNode}
                nodePointerAreaPaint={(node: GNode, color, ctx) => {
                  ctx.beginPath()
                  ctx.arc(node.x ?? 0, node.y ?? 0, 10, 0, 2 * Math.PI)
                  ctx.fillStyle = color
                  ctx.fill()
                }}
                linkColor={(link: any) => link.isReferencedPath ? 'rgba(243, 112, 33, 0.6)' : 'rgba(107, 130, 158, 0.2)'}
                linkWidth={(link: any) => link.isReferencedPath ? 1.5 : 0.5}
                linkDirectionalArrowLength={3}
                linkDirectionalArrowRelPos={1}
                linkLabel={(link: any) => link.relation_type || ''}
                onNodeClick={(node: any) => setSelectedNode(node)}
                nodeLabel={(node: any) => {
                  const sn = sourceNodes.find(s => s.id === node.id)
                  const docs = sn?.source_titles?.join(', ') || ''
                  return `${node.name} (${node.type})${docs ? `\n출처: ${docs}` : ''}`
                }}
                cooldownTicks={60}
                enableZoomInteraction={true}
                enablePanInteraction={true}
              />
            )}

            {/* 선택된 노드 상세 패널 */}
            {selectedNode && (
              <div
                className="absolute bottom-4 left-4 right-4 rounded-lg p-3"
                role="region"
                aria-label={`노드 상세: ${selectedNode.name}`}
                style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ background: selectedNode.highlightColor || (selectedNode.isReferenced ? 'var(--color-gold)' : 'var(--color-text-muted)') }}
                      aria-hidden="true"
                    />
                    <span className="text-xs font-semibold text-surface-900">{selectedNode.name}</span>
                    <span className="text-2xs font-mono text-surface-600">{selectedNode.type}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedNode(null)}
                    className="inline-flex items-center justify-center rounded text-surface-600 hover:text-surface-900"
                    style={{
                      width: '24px',
                      height: '24px',
                      transition: 'color 200ms var(--ease-out)',
                    }}
                    aria-label="노드 상세 닫기"
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                </div>
                {/* 문서명 (소스 노드인 경우) */}
                {(() => {
                  const sn = sourceNodes.find(s => s.id === selectedNode.id)
                  return sn?.source_titles && sn.source_titles.length > 0 ? (
                    <p className="flex items-center gap-1 text-2xs text-surface-600 mb-1">
                      <FileText size={10} className="shrink-0" aria-hidden="true" />
                      <span>
                        {sn.source_titles.join(', ')}
                        {sn.page_start != null && ` · p.${sn.page_start}${sn.page_end && sn.page_end !== sn.page_start ? `-${sn.page_end}` : ''}`}
                      </span>
                    </p>
                  ) : null
                })()}
                {/* 연결된 관계 표시 */}
                <div className="flex flex-wrap gap-1 mt-1">
                  {graphData.links
                    .filter((l: any) => {
                      const src = typeof l.source === 'object' ? l.source.id : l.source
                      const tgt = typeof l.target === 'object' ? l.target.id : l.target
                      return src === selectedNode.id || tgt === selectedNode.id
                    })
                    .slice(0, 8)
                    .map((l: any, i: number) => {
                      const src = typeof l.source === 'object' ? l.source : graphData.nodes.find(n => n.id === l.source)
                      const tgt = typeof l.target === 'object' ? l.target : graphData.nodes.find(n => n.id === l.target)
                      const other = (src as any)?.id === selectedNode.id ? tgt : src
                      return (
                        <span key={i} className="text-2xs px-1.5 py-0.5 rounded" style={{ background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)' }}>
                          <span className="text-gold-500">{l.relation_type || '관계'}</span>
                          <span className="text-surface-600"> → </span>
                          <span className="text-surface-800">{(other as any)?.name || '?'}</span>
                        </span>
                      )
                    })}
                </div>
              </div>
            )}
          </div>

          {/* 각주 (Footnotes) */}
          <div
            className="px-4 py-3 space-y-1.5 overflow-y-auto"
            style={{ borderTop: '1px solid var(--color-border)', maxHeight: expanded ? 200 : 140 }}
          >
            <p className="text-2xs font-semibold text-surface-600 uppercase tracking-widest mb-1">참조 출처</p>
            {sourceNodes.map((sn, idx) => {
              const color = CITE_COLORS[idx % CITE_COLORS.length]
              // 위치 정보 구성
              const location = [
                sn.section_ref || '',
                sn.page_start != null ? `p.${sn.page_start}${sn.page_end && sn.page_end !== sn.page_start ? `-${sn.page_end}` : ''}` : '',
                sn.effective_date ? `시행 ${sn.effective_date}` : '',
              ].filter(Boolean).join(' · ')

              return (
                <div key={sn.id} className="flex items-start gap-2 text-2xs">
                  <span
                    className="inline-flex items-center justify-center rounded font-bold shrink-0 mt-0.5"
                    style={{
                      fontSize: '8px',
                      width: '16px',
                      height: '16px',
                      background: `color-mix(in srgb, ${color} 20%, transparent)`,
                      color,
                    }}
                    aria-label={`출처 ${idx + 1}`}
                  >
                    {idx + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <span className="font-semibold text-surface-900">{sn.name}</span>
                    {sn.description && (
                      <span className="text-surface-600 ml-1">— {sn.description}</span>
                    )}
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                      {sn.match_reason && (
                        <span className="text-gold-500">{sn.match_reason}</span>
                      )}
                      {location && (
                        <span className="text-surface-600 font-mono">{location}</span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
