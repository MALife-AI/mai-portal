import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Loader2, Maximize2, Minimize2 } from 'lucide-react'
import ForceGraph2D, { type NodeObject, type LinkObject } from 'react-force-graph-2d'
import { graphApi, type GraphVisualizationData } from '@/api/client'

const CITE_COLORS = [
  '#F37021', '#4A90D9', '#34C759', '#AF52DE', '#FF3B30',
  '#5AC8FA', '#FFCC00', '#FF2D55', '#64D2FF', '#30D158',
]

interface SourceNode {
  id: string
  name: string
  type: string
  description?: string
  source_titles: string[]
  page_start?: number | null
  page_end?: number | null
}

interface Props {
  sourceNodes: SourceNode[]
  focusIndex: number // 0-based, which source was clicked
  onClose: () => void
}

interface GNode extends NodeObject {
  id: string
  name: string
  type: string
  mentions: number
  isHighlighted?: boolean
  highlightColor?: string
  highlightIndex?: number
}

export function GraphOverlay({ sourceNodes, focusIndex, onClose }: Props) {
  const [loading, setLoading] = useState(true)
  const [graphData, setGraphData] = useState<{ nodes: GNode[]; links: LinkObject[] }>({ nodes: [], links: [] })
  const [expanded, setExpanded] = useState(false)
  const graphRef = useRef<any>(null)

  // Fetch subgraphs for all source nodes and merge
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      const allNodes = new Map<string, GNode>()
      const allLinks: LinkObject[] = []
      const highlightIds = new Set<string>()

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
          allLinks.push({ source: e.source, target: e.target })
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
            allLinks.push({ source: e.source, target: e.target })
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
  }, [loading, graphData])

  const paintNode = useCallback((node: GNode, ctx: CanvasRenderingContext2D) => {
    const x = node.x ?? 0
    const y = node.y ?? 0
    const r = node.isHighlighted ? 8 : 4

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
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.5
      ctx.stroke()

      // Citation number
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 8px monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(String(node.highlightIndex ?? ''), x, y)

      // Label
      ctx.fillStyle = node.highlightColor
      ctx.font = 'bold 10px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.name, x, y + r + 10)
    } else {
      ctx.beginPath()
      ctx.arc(x, y, r, 0, 2 * Math.PI)
      ctx.fillStyle = '#6b829e'
      ctx.fill()

      // Label (smaller)
      ctx.fillStyle = '#6b829e88'
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
        className="fixed inset-0 z-50 flex items-center justify-center"
        style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
          className="rounded-xl overflow-hidden"
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
              <span className="text-sm font-semibold text-surface-900">참조 지식그래프</span>
              <span className="text-2xs font-mono text-surface-600">
                {graphData.nodes.length} nodes / {graphData.links.length} edges
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setExpanded(v => !v)}
                className="w-7 h-7 rounded flex items-center justify-center text-surface-600 hover:text-surface-900 hover:bg-surface-200 transition-colors"
              >
                {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>
              <button
                onClick={onClose}
                className="w-7 h-7 rounded flex items-center justify-center text-surface-600 hover:text-status-error hover:bg-surface-200 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-2 px-4 py-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
            {sourceNodes.map((sn, i) => {
              const color = CITE_COLORS[i % CITE_COLORS.length]
              return (
                <span
                  key={sn.id}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono"
                  style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}
                >
                  <span className="font-bold">[{i + 1}]</span> {sn.name}
                </span>
              )
            })}
          </div>

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
                graphData={graphData}
                width={width}
                height={height}
                nodeCanvasObject={paintNode}
                nodePointerAreaPaint={(node: GNode, color, ctx) => {
                  ctx.beginPath()
                  ctx.arc(node.x ?? 0, node.y ?? 0, 10, 0, 2 * Math.PI)
                  ctx.fillStyle = color
                  ctx.fill()
                }}
                linkColor={() => 'rgba(107, 130, 158, 0.3)'}
                linkWidth={0.5}
                cooldownTicks={60}
                enableZoomInteraction={true}
                enablePanInteraction={true}
              />
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
