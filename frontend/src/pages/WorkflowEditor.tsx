import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Play, Save, Trash2, Plus, Loader2, ChevronRight,
  Wrench, Zap, ArrowRight, GripVertical, Settings2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/store/useStore'
import { getUserId } from '@/api/client'

const API = ''
async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'X-User-Id': getUserId(), 'Content-Type': 'application/json', ...opts.headers },
  })
  return r.json()
}

// ─── Skill 타입 ─────────────────────────────────────────────────────────────

interface SkillIO {
  type: string
  description: string
  label?: string
}

interface Skill {
  skill_name: string
  description: string
  endpoint: string
  method: string
  category: string
  params: Record<string, any>
  inputs?: Record<string, SkillIO>
  outputs?: Record<string, SkillIO>
  depends_on?: string[]
}

interface Workflow {
  id: string
  name: string
  nodes: Node[]
  edges: Edge[]
  created_at: string
}

// ─── 색상 ────────────────────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  search: '#4A90D9',
  analysis: '#F37021',
  report: '#34C759',
  custom: '#6b829e',
}

// ─── 커스텀 노드 ─────────────────────────────────────────────────────────────

function SkillNode({ data, selected }: NodeProps) {
  const catColor = CATEGORY_COLORS[data.category as string] || CATEGORY_COLORS.custom
  const inputs = data.inputs as Record<string, SkillIO> | undefined
  const outputs = data.outputs as Record<string, SkillIO> | undefined

  return (
    <div
      className={cn(
        'rounded-lg border shadow-lg min-w-[200px] max-w-[260px]',
        selected ? 'border-gold-500 ring-2 ring-gold-500/30' : 'border-surface-300',
      )}
      style={{ background: 'var(--color-bg-secondary)' }}
    >
      {/* 헤더 */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-t-lg" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <GripVertical size={12} className="text-surface-600 cursor-grab" />
        <div className="w-2 h-2 rounded-full" style={{ background: catColor }} />
        <span className="text-xs font-semibold text-surface-900 truncate flex-1">{data.label as string}</span>
        <span className="text-2xs font-mono px-1 py-0.5 rounded" style={{ background: catColor + '20', color: catColor }}>
          {data.category as string}
        </span>
      </div>

      {/* 설명 */}
      <div className="px-3 py-1.5">
        <p className="text-2xs text-surface-600 line-clamp-2">{data.description as string}</p>
      </div>

      {/* 입력 핸들 */}
      {inputs && Object.keys(inputs).length > 0 && (
        <div className="px-3 pb-1">
          <p className="text-2xs font-semibold text-surface-600 mb-0.5">입력</p>
          {Object.entries(inputs).map(([key, io]) => (
            <div key={key} className="flex items-center gap-1 text-2xs text-surface-700 py-0.5 relative">
              <Handle
                type="target"
                position={Position.Left}
                id={`in-${key}`}
                style={{ width: 8, height: 8, background: '#4A90D9', border: '2px solid var(--color-bg-secondary)', left: -4 }}
              />
              <span className="font-mono text-gold-500">{key}</span>
              <span className="text-surface-600">: {io.type}</span>
            </div>
          ))}
        </div>
      )}

      {/* 출력 핸들 */}
      {outputs && Object.keys(outputs).length > 0 && (
        <div className="px-3 pb-2">
          <p className="text-2xs font-semibold text-surface-600 mb-0.5">출력</p>
          {Object.entries(outputs).map(([key, io]) => (
            <div key={key} className="flex items-center justify-end gap-1 text-2xs text-surface-700 py-0.5 relative">
              <span className="font-mono text-status-success">{key}</span>
              <span className="text-surface-600">: {io.type}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={`out-${key}`}
                style={{ width: 8, height: 8, background: '#34C759', border: '2px solid var(--color-bg-secondary)', right: -4 }}
              />
            </div>
          ))}
        </div>
      )}

      {/* 입출력 없으면 기본 핸들 */}
      {(!inputs || Object.keys(inputs).length === 0) && (
        <Handle type="target" position={Position.Left} style={{ width: 10, height: 10, background: '#4A90D9' }} />
      )}
      {(!outputs || Object.keys(outputs).length === 0) && (
        <Handle type="source" position={Position.Right} style={{ width: 10, height: 10, background: '#34C759' }} />
      )}
    </div>
  )
}

const nodeTypes = { skill: SkillNode }

// ─── 워크플로우 저장/로드 ────────────────────────────────────────────────────

const WORKFLOWS_KEY = 'mai_workflows'

function loadWorkflows(): Workflow[] {
  try {
    return JSON.parse(localStorage.getItem(WORKFLOWS_KEY) || '[]')
  } catch { return [] }
}

function saveWorkflows(workflows: Workflow[]) {
  localStorage.setItem(WORKFLOWS_KEY, JSON.stringify(workflows))
}

// ─── 메인 컴포넌트 ──────────────────────────────────────────────────────────

export default function WorkflowEditor() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [workflows, setWorkflowsList] = useState<Workflow[]>([])
  const [currentName, setCurrentName] = useState('새 워크플로우')
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [runLog, setRunLog] = useState<Array<{ skill: string; status: string; result?: string }>>([])
  const toast = useToast()
  const idCounter = useRef(0)

  useEffect(() => {
    api('/api/v1/skills/list').then(d => setSkills(d.skills || []))
    setWorkflowsList(loadWorkflows())
  }, [])

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges(eds => addEdge({
        ...connection,
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#F37021' },
        style: { stroke: '#F37021', strokeWidth: 2 },
      }, eds))
    },
    [setEdges],
  )

  function addSkillNode(skill: Skill) {
    const id = `skill-${++idCounter.current}`
    const newNode: Node = {
      id,
      type: 'skill',
      position: { x: 100 + (nodes.length % 3) * 300, y: 80 + Math.floor(nodes.length / 3) * 250 },
      data: {
        label: skill.skill_name,
        description: skill.description,
        category: skill.category,
        inputs: skill.inputs || {},
        outputs: skill.outputs || {},
        skillData: skill,
      },
    }
    setNodes(nds => [...nds, newNode])
  }

  function clearCanvas() {
    setNodes([])
    setEdges([])
    setCurrentId(null)
    setCurrentName('새 워크플로우')
    setRunLog([])
  }

  function saveWorkflow() {
    const id = currentId || `wf-${Date.now()}`
    const wf: Workflow = {
      id,
      name: currentName,
      nodes: nodes.map(n => ({ ...n, data: { ...n.data } })),
      edges: [...edges],
      created_at: new Date().toISOString(),
    }
    const existing = loadWorkflows()
    const idx = existing.findIndex(w => w.id === id)
    if (idx >= 0) existing[idx] = wf; else existing.push(wf)
    saveWorkflows(existing)
    setWorkflowsList(existing)
    setCurrentId(id)
    toast.success('워크플로우 저장', currentName)
  }

  function loadWorkflow(wf: Workflow) {
    setNodes(wf.nodes)
    setEdges(wf.edges)
    setCurrentId(wf.id)
    setCurrentName(wf.name)
    setRunLog([])
  }

  function deleteWorkflow(id: string) {
    const existing = loadWorkflows().filter(w => w.id !== id)
    saveWorkflows(existing)
    setWorkflowsList(existing)
    if (currentId === id) clearCanvas()
    toast.success('워크플로우 삭제', '')
  }

  // 위상 정렬로 실행 순서 결정
  function getExecutionOrder(): string[] {
    const inDegree: Record<string, number> = {}
    const adj: Record<string, string[]> = {}
    for (const node of nodes) {
      inDegree[node.id] = 0
      adj[node.id] = []
    }
    for (const edge of edges) {
      adj[edge.source].push(edge.target)
      inDegree[edge.target] = (inDegree[edge.target] || 0) + 1
    }
    const queue = Object.keys(inDegree).filter(k => inDegree[k] === 0)
    const order: string[] = []
    while (queue.length > 0) {
      const node = queue.shift()!
      order.push(node)
      for (const next of adj[node] || []) {
        inDegree[next]--
        if (inDegree[next] === 0) queue.push(next)
      }
    }
    return order
  }

  async function runWorkflow() {
    setRunning(true)
    setRunLog([])
    const order = getExecutionOrder()

    for (const nodeId of order) {
      const node = nodes.find(n => n.id === nodeId)
      if (!node) continue
      const skillName = node.data.label as string
      setRunLog(prev => [...prev, { skill: skillName, status: 'running' }])

      // 시뮬레이션 (실제로는 스킬 엔드포인트 호출)
      await new Promise(r => setTimeout(r, 1000 + Math.random() * 1500))

      setRunLog(prev =>
        prev.map(l => l.skill === skillName ? { ...l, status: 'done', result: '성공' } : l)
      )
    }

    setRunning(false)
    toast.success('워크플로우 실행 완료', `${order.length}개 스킬 실행`)
  }

  return (
    <div className="h-[calc(100vh-var(--header-height))] flex">
      {/* 좌측: 스킬 팔레트 */}
      <div
        className="w-64 shrink-0 overflow-y-auto p-3 space-y-2"
        style={{ background: 'var(--color-bg-secondary)', borderRight: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-surface-800">스킬 팔레트</p>
          <Wrench size={13} className="text-gold-500" />
        </div>

        {skills.map(skill => {
          const catColor = CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.custom
          return (
            <button
              key={skill.skill_name}
              onClick={() => addSkillNode(skill)}
              className="w-full text-left p-2 rounded-md hover:bg-surface-200 transition-colors group"
              style={{ border: '1px solid var(--color-border)' }}
            >
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full shrink-0" style={{ background: catColor }} />
                <span className="text-xs font-semibold text-surface-900 truncate">{skill.skill_name}</span>
              </div>
              <p className="text-2xs text-surface-600 line-clamp-1 mt-0.5 ml-4">{skill.description}</p>
              {skill.inputs && (
                <div className="flex gap-1 mt-1 ml-4">
                  {Object.keys(skill.inputs).map(k => (
                    <span key={k} className="text-2xs font-mono px-1 rounded bg-surface-200 text-surface-700">{k}</span>
                  ))}
                </div>
              )}
            </button>
          )
        })}

        {/* 워크플로우 목록 */}
        <div className="pt-3 mt-3" style={{ borderTop: '1px solid var(--color-border)' }}>
          <p className="text-xs font-semibold text-surface-800 mb-2">저장된 워크플로우</p>
          {workflows.length === 0 ? (
            <p className="text-2xs text-surface-600">저장된 워크플로우가 없습니다</p>
          ) : (
            workflows.map(wf => (
              <div key={wf.id} className="flex items-center justify-between py-1.5 group">
                <button onClick={() => loadWorkflow(wf)} className="text-xs text-surface-700 hover:text-gold-500 truncate flex-1 text-left">
                  {wf.name}
                </button>
                <button onClick={() => deleteWorkflow(wf.id)} className="opacity-0 group-hover:opacity-100 text-surface-600 hover:text-status-error">
                  <Trash2 size={11} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 중앙: 캔버스 */}
      <div className="flex-1 relative">
        {/* 상단 툴바 */}
        <div
          className="absolute top-0 left-0 right-0 z-10 flex items-center gap-2 px-4 py-2"
          style={{ background: 'var(--color-bg-secondary)', borderBottom: '1px solid var(--color-border)' }}
        >
          <Zap size={14} className="text-gold-500" />
          <input
            value={currentName}
            onChange={e => setCurrentName(e.target.value)}
            className="input-field text-xs font-semibold w-48"
            placeholder="워크플로우 이름"
          />
          <div className="flex-1" />
          <span className="text-2xs text-surface-600">{nodes.length}개 노드 · {edges.length}개 연결</span>
          <button onClick={clearCanvas} className="btn-secondary text-2xs flex items-center gap-1"><Trash2 size={10} /> 초기화</button>
          <button onClick={saveWorkflow} className="btn-secondary text-2xs flex items-center gap-1"><Save size={10} /> 저장</button>
          <button
            onClick={runWorkflow}
            disabled={running || nodes.length === 0}
            className="btn-primary text-2xs flex items-center gap-1"
          >
            {running ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
            {running ? '실행 중...' : '실행'}
          </button>
        </div>

        {/* React Flow */}
        <div className="w-full h-full pt-10">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            className="bg-surface-DEFAULT"
            defaultEdgeOptions={{
              animated: true,
              style: { stroke: '#F37021', strokeWidth: 2 },
              markerEnd: { type: MarkerType.ArrowClosed, color: '#F37021' },
            }}
          >
            <Background color="var(--color-border)" gap={20} />
            <Controls
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 6 }}
            />
            <MiniMap
              nodeColor={(n) => CATEGORY_COLORS[(n.data?.category as string)] || '#6b829e'}
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 6 }}
            />
          </ReactFlow>
        </div>
      </div>

      {/* 우측: 실행 로그 */}
      {runLog.length > 0 && (
        <div
          className="w-56 shrink-0 overflow-y-auto p-3"
          style={{ background: 'var(--color-bg-secondary)', borderLeft: '1px solid var(--color-border)' }}
        >
          <p className="text-xs font-semibold text-surface-800 mb-3">실행 로그</p>
          <div className="space-y-2">
            {runLog.map((log, i) => (
              <div key={i} className="flex items-center gap-2">
                {log.status === 'running' ? (
                  <Loader2 size={12} className="animate-spin text-gold-500" />
                ) : (
                  <div className="w-3 h-3 rounded-full bg-status-success" />
                )}
                <div>
                  <p className="text-xs font-mono text-surface-900">{log.skill}</p>
                  <p className="text-2xs text-surface-600">{log.status === 'running' ? '실행 중...' : log.result}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
