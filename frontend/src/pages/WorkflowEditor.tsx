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
  type ReactFlowInstance,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

/* React Flow 스타일은 index.css의 .workflow-canvas 섹션에 정의 */
import {
  Play, Save, Trash2, Plus, Loader2, ChevronRight,
  Wrench, Zap, ArrowRight, GripVertical, Settings2, Cpu, Search, X,
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
  display_name?: string
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

// ─── 그래프 엔티티 검색 필드 ─────────────────────────────────────────────────

interface GraphEntity {
  id: string
  name: string
  entity_type: string
  mentions: number
  properties?: Record<string, any>
}

function GraphSearchField({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GraphEntity[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [selectedEntity, setSelectedEntity] = useState<GraphEntity | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  const abortRef = useRef<AbortController>()
  const wrapperRef = useRef<HTMLDivElement>(null)

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as HTMLElement)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // value로부터 초기 선택 상태 복원
  useEffect(() => {
    if (value && !selectedEntity) {
      setQuery(value)
    }
  }, [value])

  function handleSearch(q: string) {
    setQuery(q)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!q.trim()) {
      setResults([])
      setOpen(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setLoading(true)
      try {
        const uid = getUserId()
        const r = await fetch(`${API}/api/v1/graph/entities?q=${encodeURIComponent(q)}&limit=8`, {
          headers: { 'X-User-Id': uid },
          signal: controller.signal,
        })
        if (!r.ok) { setResults([]); return }
        const d = await r.json()
        setResults(d.entities || [])
        setOpen(true)
      } catch {
        if (!controller.signal.aborted) setResults([])
      }
      setLoading(false)
    }, 300)
  }

  function handleSelect(entity: GraphEntity) {
    setSelectedEntity(entity)
    setQuery(entity.name)
    onChange(entity.id)
    setOpen(false)
  }

  function handleClear() {
    setSelectedEntity(null)
    setQuery('')
    onChange('')
    setOpen(false)
  }

  const TYPE_COLORS: Record<string, string> = {
    product: '#F37021', person: '#4A90D9', organization: '#34C759',
    regulation: '#AF52DE', concept: '#FF3B30', event: '#5AC8FA',
  }

  return (
    <div ref={wrapperRef} className="relative mt-0.5">
      <div className="flex items-center gap-1">
        <div className="relative flex-1">
          <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-surface-500" />
          <input
            value={query}
            onChange={e => handleSearch(e.target.value)}
            onFocus={() => results.length > 0 && setOpen(true)}
            placeholder={placeholder}
            className="input-field w-full text-2xs pl-6 pr-6"
            style={{ borderColor: selectedEntity ? 'rgba(52,199,89,0.6)' : 'rgba(74,144,217,0.5)' }}
          />
          {loading && <Loader2 size={10} className="absolute right-2 top-1/2 -translate-y-1/2 animate-spin text-surface-500" />}
          {selectedEntity && !loading && (
            <button
              onClick={handleClear}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full flex items-center justify-center text-surface-500 hover:text-status-error hover:bg-surface-200 transition-colors"
            >
              <X size={8} />
            </button>
          )}
        </div>
      </div>

      {/* 선택된 엔티티 뱃지 */}
      {selectedEntity && (
        <div
          className="flex items-center gap-1.5 mt-1 px-2 py-1 rounded text-2xs"
          style={{
            background: (TYPE_COLORS[selectedEntity.entity_type] || '#6b829e') + '14',
            border: `1px solid ${TYPE_COLORS[selectedEntity.entity_type] || '#6b829e'}33`,
          }}
        >
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: TYPE_COLORS[selectedEntity.entity_type] || '#6b829e' }} />
          <span className="font-semibold text-surface-900">{selectedEntity.name}</span>
          <span className="text-surface-600">{selectedEntity.entity_type}</span>
          <span className="text-surface-500 ml-auto">x{selectedEntity.mentions}</span>
        </div>
      )}

      {/* 검색 결과 드롭다운 */}
      {open && results.length > 0 && (
        <div
          className="absolute z-50 left-0 right-0 mt-1 rounded-md shadow-xl overflow-hidden max-h-48 overflow-y-auto"
          style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
        >
          {results.map(entity => {
            const color = TYPE_COLORS[entity.entity_type] || '#6b829e'
            return (
              <button
                key={entity.id}
                onClick={() => handleSelect(entity)}
                className="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-surface-200 transition-colors"
              >
                <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                <div className="flex-1 min-w-0">
                  <span className="text-2xs font-semibold text-surface-900 block truncate">{entity.name}</span>
                  <span className="text-2xs text-surface-600">{entity.entity_type} · 언급 {entity.mentions}회</span>
                </div>
              </button>
            )
          })}
        </div>
      )}
      {open && results.length === 0 && !loading && query.trim() && (
        <div
          className="absolute z-50 left-0 right-0 mt-1 rounded-md shadow-xl px-3 py-2"
          style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
        >
          <p className="text-2xs text-surface-600">검색 결과 없음</p>
        </div>
      )}
    </div>
  )
}

// ─── 입력 노드 ──────────────────────────────────────────────────────────────

function InputNode({ data, selected }: NodeProps) {
  const fields = (data.fields || []) as Array<{ name: string; type: string; label: string; value: string; inputType?: string }>
  const onFieldChange = data.onFieldChange as ((idx: number, value: string) => void) | undefined

  return (
    <div
      className={cn(
        'rounded-lg border shadow-lg min-w-[220px] max-w-[280px]',
        selected ? 'border-status-info ring-2 ring-status-info/30' : 'border-surface-300',
      )}
      style={{ background: 'var(--color-bg-secondary)' }}
    >
      <div className="flex items-center gap-2 px-3 py-2 rounded-t-lg" style={{ background: 'rgba(74,144,217,0.1)', borderBottom: '1px solid var(--color-border)' }}>
        <Zap size={12} className="text-status-info" />
        <span className="text-xs font-semibold text-surface-900">사용자 입력</span>
      </div>
      <div className="px-3 py-2 space-y-2">
        {fields.map((f, i) => (
          <div key={i} className="relative">
            <label className="text-2xs text-surface-600">{f.label || f.name} <span className="font-mono text-surface-500">({f.type})</span></label>
            {f.inputType === 'file' ? (
              <div className="flex gap-1 mt-0.5">
                <input
                  value={f.value}
                  onChange={e => onFieldChange?.(i, e.target.value)}
                  placeholder="/Shared/문서.md"
                  className="input-field w-full text-2xs"
                />
              </div>
            ) : f.inputType === 'graph' ? (
              <GraphSearchField
                value={f.value}
                onChange={(val) => onFieldChange?.(i, val)}
                placeholder="엔티티 검색..."
              />
            ) : (
              <input
                value={f.value}
                onChange={e => onFieldChange?.(i, e.target.value)}
                placeholder={f.label || f.name}
                className="input-field w-full text-2xs mt-0.5"
              />
            )}
            <Handle
              type="source"
              position={Position.Right}
              id={`out-${f.name}`}
              style={{ width: 8, height: 8, background: '#34C759', border: '2px solid var(--color-bg-secondary)', right: -4, top: 24 + i * 52 }}
            />
          </div>
        ))}
        {fields.length === 0 && (
          <p className="text-2xs text-surface-600 italic">스킬을 연결하면 필요한 입력이 자동 표시됩니다</p>
        )}
      </div>
    </div>
  )
}

// ─── 가드레일 노드 ───────────────────────────────────────────────────────────

function GuardrailNode({ data, selected }: NodeProps) {
  const rules = (data.rules || []) as string[]

  return (
    <div
      className={cn(
        'rounded-lg border shadow-lg min-w-[200px] max-w-[240px]',
        selected ? 'border-status-warning ring-2 ring-status-warning/30' : 'border-surface-300',
      )}
      style={{ background: 'var(--color-bg-secondary)' }}
    >
      <div className="flex items-center gap-2 px-3 py-2 rounded-t-lg" style={{ background: 'rgba(245,166,35,0.1)', borderBottom: '1px solid var(--color-border)' }}>
        <Handle type="target" position={Position.Left} style={{ width: 10, height: 10, background: '#4A90D9' }} />
        <Settings2 size={12} className="text-status-warning" />
        <span className="text-xs font-semibold text-surface-900">가드레일</span>
        <span className="text-2xs px-1 py-0.5 rounded bg-status-warning/20 text-status-warning font-semibold">필수</span>
      </div>
      <div className="px-3 py-2 space-y-0.5">
        {rules.map((r, i) => (
          <div key={i} className="flex items-center gap-1.5 text-2xs text-surface-700">
            <div className="w-1.5 h-1.5 rounded-full bg-status-warning shrink-0" />
            <span>{r}</span>
          </div>
        ))}
        <Handle type="source" position={Position.Right} style={{ width: 10, height: 10, background: '#34C759' }} />
      </div>
    </div>
  )
}

// ─── LLM 모델 노드 ──────────────────────────────────────────────────────────

function LLMNode({ data, selected }: NodeProps) {
  return (
    <div
      className={cn(
        'rounded-lg border shadow-lg min-w-[200px] max-w-[240px]',
        selected ? 'border-gold-500 ring-2 ring-gold-500/30' : 'border-surface-300',
      )}
      style={{ background: 'var(--color-bg-secondary)' }}
    >
      <div className="flex items-center gap-2 px-3 py-2 rounded-t-lg" style={{ background: 'rgba(243,112,33,0.1)', borderBottom: '1px solid var(--color-border)' }}>
        <Handle type="target" position={Position.Left} style={{ width: 10, height: 10, background: '#4A90D9' }} />
        <Cpu size={12} className="text-gold-500" />
        <span className="text-xs font-semibold text-surface-900">LLM 응답 생성</span>
      </div>
      <div className="px-3 py-2 space-y-1">
        <div className="flex items-center gap-1 text-2xs">
          <span className="text-surface-600">모드:</span>
          <span className="font-semibold text-gold-500">{(data.mode as string) || '자동'}</span>
        </div>
        <div className="flex items-center gap-1 text-2xs">
          <span className="text-surface-600">모델:</span>
          <span className="font-mono text-surface-800">{(data.model as string) || '기본 설정'}</span>
        </div>
        <p className="text-2xs text-surface-600 italic">스킬 결과를 종합하여 사용자에게 답변</p>
      </div>
    </div>
  )
}

const nodeTypes = { skill: SkillNode, input: InputNode, guardrail: GuardrailNode, llm: LLMNode }

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
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null)

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

  function addInputNode(inputType: string) {
    const id = `input-${++idCounter.current}`
    const fieldsMap: Record<string, Array<{ name: string; type: string; label: string; value: string; inputType: string }>> = {
      text: [{ name: 'text_input', type: 'string', label: '텍스트 입력', value: '', inputType: 'text' }],
      file: [{ name: 'file_path', type: 'string', label: '파일 경로', value: '', inputType: 'file' }],
      graph: [{ name: 'entity_id', type: 'string', label: '엔티티 ID', value: '', inputType: 'graph' },
              { name: 'entity_name', type: 'string', label: '엔티티명', value: '', inputType: 'graph' }],
      query: [{ name: 'query', type: 'string', label: '검색 쿼리', value: '', inputType: 'text' }],
      customer: [{ name: 'customer_id', type: 'string', label: '고객번호', value: '', inputType: 'text' },
                 { name: 'customer_name', type: 'string', label: '고객명', value: '', inputType: 'text' }],
      product: [{ name: 'product_code', type: 'string', label: '상품코드', value: '', inputType: 'text' },
                { name: 'insured_age', type: 'integer', label: '피보험자 나이', value: '', inputType: 'text' }],
      underwriting: [
        { name: 'customer_id', type: 'string', label: '고객번호', value: '', inputType: 'text' },
        { name: 'product_code', type: 'string', label: '상품코드', value: '', inputType: 'text' },
        { name: 'sum_insured', type: 'number', label: '가입금액 (원)', value: '', inputType: 'text' },
      ],
    }
    const fields = fieldsMap[inputType] || fieldsMap.text
    const labels: Record<string, string> = {
      text: '텍스트', file: '파일', graph: '그래프 엔티티',
      query: '검색 쿼리', customer: '고객 정보', product: '상품 정보',
      underwriting: '언더라이팅 심사',
    }
    const newNode: Node = {
      id,
      type: 'input',
      position: { x: 30, y: 80 + nodes.filter(n => n.type === 'input').length * 200 },
      data: {
        label: labels[inputType] || '입력',
        fields,
        onFieldChange: (idx: number, value: string) => {
          setNodes(nds => nds.map(n => {
            if (n.id !== id) return n
            const updatedFields = [...(n.data.fields as any[])]
            updatedFields[idx] = { ...updatedFields[idx], value }
            return { ...n, data: { ...n.data, fields: updatedFields } }
          }))
        },
      },
    }
    setNodes(nds => [...nds, newNode])
  }

  function addLLMNode() {
    // 가드레일이 없으면 자동 추가
    const hasGuardrail = nodes.some(n => n.type === 'guardrail')
    const newNodes: Node[] = []

    if (!hasGuardrail) {
      const gId = `guardrail-${++idCounter.current}`
      newNodes.push({
        id: gId,
        type: 'guardrail',
        position: { x: 550, y: 100 },
        data: {
          label: '가드레일',
          rules: [
            'PII 마스킹',
            '프롬프트 인젝션 방어',
            '주제 제한 검사',
            '출처 인용 필수',
            '할루시네이션 가드',
          ],
        },
        deletable: false,
      })
    }

    const llmId = `llm-${++idCounter.current}`
    newNodes.push({
      id: llmId,
      type: 'llm',
      position: { x: 830, y: 100 },
      data: {
        label: 'LLM 응답',
        mode: '자동',
        model: '기본 설정',
      },
    })

    setNodes(nds => [...nds, ...newNodes])

    // 가드레일 → LLM 자동 연결
    if (!hasGuardrail && newNodes.length === 2) {
      const [guardrailNode, llmNode] = newNodes
      setEdges(eds => addEdge({
        source: guardrailNode.id,
        target: llmNode.id,
        animated: true,
        style: { stroke: '#F5A623', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#F5A623' },
      }, eds))
    }
  }

  function addSkillNode(skill: Skill, position?: { x: number; y: number }) {
    const id = `skill-${++idCounter.current}`
    const newNode: Node = {
      id,
      type: 'skill',
      position: position ?? { x: 100 + (nodes.length % 3) * 300, y: 80 + Math.floor(nodes.length / 3) * 250 },
      data: {
        label: skill.display_name || skill.skill_name,
        description: skill.description,
        category: skill.category,
        inputs: skill.inputs || {},
        outputs: skill.outputs || {},
        skillData: skill,
      },
    }
    setNodes(nds => [...nds, newNode])
  }

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const skillName = e.dataTransfer.getData('application/malife-skill')
      if (!skillName || !reactFlowInstance) return

      const skill = skills.find(s => s.skill_name === skillName)
      if (!skill) return

      const position = reactFlowInstance.screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      })
      addSkillNode(skill, position)
    },
    [reactFlowInstance, skills],
  )

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
        {/* 입력/출력 노드 */}
        <div className="mb-3">
          <p className="text-2xs font-semibold text-surface-600 uppercase mb-1.5">입력 노드</p>
          <div className="grid grid-cols-2 gap-1">
            {[
              { type: 'text', label: '텍스트', icon: '📝' },
              { type: 'file', label: '파일', icon: '📁' },
              { type: 'graph', label: '그래프', icon: '🔗' },
              { type: 'customer', label: '고객', icon: '👤' },
              { type: 'product', label: '상품', icon: '📦' },
              { type: 'underwriting', label: '언더라이팅', icon: '🏥' },
            ].map(inp => (
              <button
                key={inp.type}
                onClick={() => addInputNode(inp.type)}
                className="flex items-center gap-1.5 p-1.5 rounded text-2xs hover:bg-surface-200 transition-colors"
                style={{ border: '1px solid var(--color-border)' }}
              >
                <span>{inp.icon}</span>
                <span className="text-surface-800">{inp.label}</span>
              </button>
            ))}
          </div>
          <button
            onClick={addLLMNode}
            className="w-full mt-1.5 flex items-center justify-center gap-1.5 p-2 rounded text-xs font-semibold text-gold-500 hover:bg-surface-200 transition-colors"
            style={{ border: '1px solid var(--color-border)' }}
          >
            <Cpu size={12} /> LLM 응답 + 가드레일
          </button>
        </div>

        <div className="flex items-center justify-between mb-2" style={{ borderTop: '1px solid var(--color-border)', paddingTop: 8 }}>
          <p className="text-xs font-semibold text-surface-800">스킬</p>
          <Wrench size={13} className="text-gold-500" />
        </div>

        {skills.map(skill => {
          const catColor = CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.custom
          return (
            <div
              key={skill.skill_name}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('application/malife-skill', skill.skill_name)
                e.dataTransfer.effectAllowed = 'move'
              }}
              onClick={() => addSkillNode(skill)}
              className="w-full text-left p-2.5 rounded-md hover:bg-surface-200 transition-colors group cursor-grab active:cursor-grabbing"
              style={{ border: '1px solid var(--color-border)' }}
            >
              <div className="flex items-center gap-2">
                <GripVertical size={12} className="text-surface-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: catColor }} />
                <span className="text-sm font-semibold text-surface-900 truncate">{skill.display_name || skill.skill_name}</span>
              </div>
              <p className="text-xs text-surface-600 line-clamp-2 mt-1 ml-9">{skill.description}</p>
            </div>
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
          <span className="text-2xs text-surface-600 whitespace-nowrap">{nodes.length}개 노드 · {edges.length}개 연결</span>
          <button onClick={clearCanvas} className="btn-secondary text-xs whitespace-nowrap flex items-center gap-1"><Trash2 size={12} /> 초기화</button>
          <button onClick={saveWorkflow} className="btn-secondary text-xs whitespace-nowrap flex items-center gap-1"><Save size={12} /> 저장</button>
          <button
            onClick={runWorkflow}
            disabled={running || nodes.length === 0}
            className="btn-primary text-xs whitespace-nowrap flex items-center gap-1"
          >
            {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            {running ? '실행 중...' : '실행'}
          </button>
        </div>

        {/* React Flow */}
        <div ref={reactFlowWrapper} className="w-full h-full pt-10 workflow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setReactFlowInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            nodeTypes={nodeTypes}
            deleteKeyCode={['Backspace', 'Delete']}
            fitView
            className="bg-surface-DEFAULT"
            defaultEdgeOptions={{
              animated: true,
              style: { stroke: '#F37021', strokeWidth: 2 },
              markerEnd: { type: MarkerType.ArrowClosed, color: '#F37021' },
            }}
          >
            <Background color="var(--color-border)" gap={20} />
            <Controls />
            <MiniMap
              nodeColor={(n) => CATEGORY_COLORS[(n.data?.category as string)] || '#6b829e'}
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
