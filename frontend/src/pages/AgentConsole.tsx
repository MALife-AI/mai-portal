import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  Bot,
  User,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Brain,
  Terminal,
  MessageSquare,
  RefreshCw,
  Workflow,
  Settings2,
  Menu,
  X,
} from 'lucide-react'
import { agentApi, type ExecutionStep, type ClarificationData } from '@/api/client'
import { useStore, useToast, type AgentMessage, type AgentThread } from '@/store/useStore'
import { formatRelativeTime, generateId, cn } from '@/lib/utils'
import { MarkdownViewer } from '@/components/MarkdownViewer'
import { GraphOverlay } from '@/components/GraphOverlay'

// ─── Execution Log Sidebar ────────────────────────────────────────────────────

interface ExecutionLogProps {
  steps: ExecutionStep[]
  reasoning?: string
}

function ExecutionLog({ steps, reasoning }: ExecutionLogProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]))
  const [showReasoning, setShowReasoning] = useState(false)

  function toggleStep(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  const statusIcon = (status: ExecutionStep['status']) => {
    switch (status) {
      case 'success': return <CheckCircle2 size={12} className="text-status-success" aria-hidden="true" />
      case 'error': return <XCircle size={12} className="text-status-error" aria-hidden="true" />
      case 'running': return <Loader2 size={12} className="text-gold-500 animate-spin" aria-hidden="true" />
      default: return <Clock size={12} className="text-surface-600" aria-hidden="true" />
    }
  }

  return (
    <div className="space-y-2">
      {/* Reasoning */}
      {reasoning && (
        <div className="panel">
          <button
            type="button"
            className="w-full flex items-center justify-between px-3 py-2.5"
            onClick={() => setShowReasoning((v) => !v)}
            aria-expanded={showReasoning}
            aria-controls="exec-reasoning"
          >
            <div className="flex items-center gap-2">
              <Brain size={13} className="text-gold-500" aria-hidden="true" />
              <span className="text-xs font-semibold text-surface-800">추론 과정</span>
            </div>
            {showReasoning ? (
              <ChevronDown size={12} className="text-surface-600" aria-hidden="true" />
            ) : (
              <ChevronRight size={12} className="text-surface-600" aria-hidden="true" />
            )}
          </button>
          <AnimatePresence initial={false}>
            {showReasoning && (
              <motion.div
                id="exec-reasoning"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                style={{ overflow: 'hidden' }}
              >
                <div
                  className="px-3 pb-3 text-xs font-mono text-surface-700 leading-relaxed"
                  style={{ borderTop: '1px solid var(--color-border)' }}
                >
                  <div className="pt-2 whitespace-pre-wrap">{reasoning}</div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Steps */}
      {steps.map((step, i) => {
        const isOpen = expanded.has(i)
        const stepName = step.skill ?? step.name ?? `스텝 ${i + 1}`
        const stepId = `exec-step-${i}`

        return (
          <div key={i} className="panel">
            <button
              type="button"
              className="w-full flex items-center gap-2 px-3 py-2.5"
              onClick={() => toggleStep(i)}
              aria-expanded={isOpen}
              aria-controls={stepId}
            >
              {statusIcon(step.status)}
              <span className="flex-1 text-left text-xs font-mono text-surface-800 truncate">
                {stepName}
              </span>
              {step.duration_ms !== undefined && (
                <span className="text-2xs font-mono text-surface-600 shrink-0">
                  {step.duration_ms}ms
                </span>
              )}
              {isOpen ? (
                <ChevronDown size={11} className="text-surface-600 shrink-0" aria-hidden="true" />
              ) : (
                <ChevronRight size={11} className="text-surface-600 shrink-0" aria-hidden="true" />
              )}
            </button>

            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  id={stepId}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                  style={{ overflow: 'hidden' }}
                >
                  <div
                    className="px-3 pb-3 space-y-2"
                    style={{ borderTop: '1px solid var(--color-border)' }}
                  >
                    {step.input !== undefined && (
                      <div className="pt-2">
                        <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">
                          입력
                        </p>
                        <pre
                          className="text-2xs font-mono text-surface-800 overflow-x-auto rounded p-2"
                          style={{ background: 'var(--color-bg-primary)' }}
                        >
                          {typeof step.input === 'string'
                            ? step.input
                            : JSON.stringify(step.input, null, 2)}
                        </pre>
                      </div>
                    )}
                    {step.output !== undefined && (
                      <div>
                        <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">
                          출력
                        </p>
                        <pre
                          className="text-2xs font-mono text-surface-800 overflow-x-auto rounded p-2"
                          style={{ background: 'var(--color-bg-primary)' }}
                        >
                          {typeof step.output === 'string'
                            ? step.output
                            : JSON.stringify(step.output, null, 2)}
                        </pre>
                      </div>
                    )}
                    {step.error && (
                      <div
                        className="rounded p-2"
                        role="alert"
                        style={{
                          background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
                          border: '1px solid color-mix(in srgb, var(--color-error) 20%, transparent)',
                        }}
                      >
                        <p className="text-2xs font-mono text-status-error">{step.error}</p>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )
      })}
    </div>
  )
}

// ─── Message Bubble ───────────────────────────────────────────────────────────

function ClarificationButtons({
  data,
  onSelect,
}: {
  data: ClarificationData
  onSelect: (value: string, displayLabel: string) => void
}) {
  const [customInput, setCustomInput] = useState('')
  // options가 비어있으면 바로 입력 필드 표시
  const [showCustom, setShowCustom] = useState(data.options.length === 0)

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
      className="mt-3 space-y-2"
      role="group"
      aria-label={data.message}
    >
      <p className="text-xs font-semibold text-surface-800 mb-2">{data.message}</p>
      <div className="flex flex-wrap gap-2">
        {data.options.map((opt, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(opt.value, opt.label)}
            className="group flex flex-col items-start px-3.5 py-2.5 rounded-lg text-left active:scale-[0.98]"
            style={{
              minHeight: '44px',
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
              transition: 'border-color 200ms var(--ease-out), color 200ms var(--ease-out), transform 120ms var(--ease-out)',
            }}
          >
            <span className="text-xs font-semibold text-surface-900 group-hover:text-gold-500">
              {opt.label}
            </span>
            {opt.description && (
              <span className="text-2xs text-surface-600 mt-0.5 leading-snug">
                {opt.description}
              </span>
            )}
          </button>
        ))}
      </div>
      {data.allow_custom_input !== false && (
        <>
          {!showCustom ? (
            <button
              type="button"
              onClick={() => setShowCustom(true)}
              className="group flex flex-col items-start px-3.5 py-2.5 rounded-lg text-left active:scale-[0.98]"
              style={{
                minHeight: '44px',
                background: 'var(--color-bg-elevated)',
                border: '1px dashed var(--color-border)',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                transition: 'border-color 200ms var(--ease-out), color 200ms var(--ease-out), transform 120ms var(--ease-out)',
              }}
            >
              <span className="text-xs font-semibold text-surface-600 group-hover:text-gold-500">
                직접 입력
              </span>
            </button>
          ) : (
            <div
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg"
              style={{
                background: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
              }}
            >
              <label htmlFor="clarification-custom" className="sr-only">직접 입력</label>
              <input
                id="clarification-custom"
                type="text"
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && customInput.trim()) {
                    onSelect(customInput.trim(), customInput.trim())
                  }
                }}
                placeholder="직접 입력하세요..."
                autoComplete="off"
                className="flex-1 bg-transparent text-xs text-surface-900 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => customInput.trim() && onSelect(customInput.trim(), customInput.trim())}
                disabled={!customInput.trim()}
                className="px-2.5 py-1 rounded-md text-xs font-semibold bg-gold-500 text-surface-DEFAULT hover:bg-gold-hover disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                style={{ minHeight: '28px', transition: 'background-color 200ms var(--ease-out)' }}
                aria-label="전송"
              >
                전송
              </button>
            </div>
          )}
        </>
      )}
    </motion.div>
  )
}

const CITE_COLORS = [
  'var(--color-gold)',
  'var(--color-blue)',
  'var(--color-success)',
  '#AF52DE',
  'var(--color-error)',
  '#5AC8FA',
  'var(--color-warning)',
  '#FF2D55',
  '#64D2FF',
  '#30D158',
] as const

function MessageBubble({ message, onSelectOption }: { message: AgentMessage; onSelectOption?: (value: string, displayLabel: string) => void }) {
  const isUser = message.role === 'user'
  const [showLog, setShowLog] = useState(false)
  const [graphOverlay, setGraphOverlay] = useState<{ focusIndex: number } | null>(null)

  // 에이전트 메시지: content 없고 clarification도 없으면 렌더링 안 함
  if (!isUser && !message.content?.trim() && !message.clarification) return null

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
      className={cn('flex gap-3', isUser && 'flex-row-reverse')}
      aria-label={isUser ? '사용자 메시지' : '에이전트 응답'}
    >
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center mt-0.5"
        style={{
          background: isUser
            ? 'color-mix(in srgb, var(--color-blue) 20%, transparent)'
            : 'color-mix(in srgb, var(--color-gold) 20%, transparent)',
          border: isUser
            ? '1px solid color-mix(in srgb, var(--color-blue) 30%, transparent)'
            : '1px solid color-mix(in srgb, var(--color-gold) 30%, transparent)',
        }}
        aria-hidden="true"
      >
        {isUser ? (
          <User size={13} className="text-slate-data" />
        ) : (
          <Bot size={13} className="text-gold-500" />
        )}
      </div>

      {/* Content */}
      <div className={cn('max-w-[75%] space-y-2', isUser && 'items-end flex flex-col')}>
        {/* 에이전트: content가 비어있으면 버블 숨김 */}
        {(isUser || message.content?.trim()) && (
          <div className={cn(isUser ? 'bubble-user' : 'bubble-agent', 'px-4 py-3')}>
            {isUser ? (
              <p className="text-sm text-surface-900 leading-relaxed">{message.content}</p>
            ) : (
              <div className="text-sm">
                <MarkdownViewer content={message.content} />
              </div>
            )}
          </div>
        )}

        <div className={cn('flex items-center gap-2 flex-wrap', isUser && 'flex-row-reverse')}>
          <time
            className="text-2xs text-surface-600 font-mono"
            dateTime={message.timestamp}
          >
            {formatRelativeTime(message.timestamp)}
          </time>

          {!isUser && message.source_nodes && message.source_nodes.length > 0 && (
            <button
              type="button"
              onClick={() => setGraphOverlay({ focusIndex: 0 })}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono font-semibold"
              style={{
                minHeight: '20px',
                background: 'color-mix(in srgb, #8B5CF6 12%, transparent)',
                color: '#8B5CF6',
                border: '1px solid color-mix(in srgb, #8B5CF6 25%, transparent)',
                transition: 'opacity 200ms var(--ease-out)',
              }}
              aria-label={`참조 지식그래프 보기 (${message.source_nodes.length}개 출처)`}
            >
              <Brain size={9} aria-hidden="true" />
              GraphRAG
            </button>
          )}
          {!isUser && (!message.source_nodes || message.source_nodes.length === 0) && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono font-semibold"
              style={{
                background: 'color-mix(in srgb, #8B5CF6 12%, transparent)',
                color: '#8B5CF6',
                border: '1px solid color-mix(in srgb, #8B5CF6 25%, transparent)',
              }}
              aria-label="GraphRAG 처리됨 — 출처 없음"
            >
              <Brain size={9} aria-hidden="true" />
              GraphRAG
            </span>
          )}

          {!isUser && message.execution_log && message.execution_log.length > 0 && (
            <button
              type="button"
              onClick={() => setShowLog((v) => !v)}
              className="flex items-center gap-1 text-2xs text-surface-600 hover:text-gold-500 font-mono"
              style={{ transition: 'color 200ms var(--ease-out)' }}
              aria-expanded={showLog}
            >
              <Terminal size={10} aria-hidden="true" />
              {showLog ? '로그 숨기기' : `실행 로그 (${message.execution_log.length})`}
            </button>
          )}
        </div>

        {/* 출처: 번호 매긴 엔티티 + 소스 문서 + 참조 이유 */}
        {!isUser && message.source_nodes && message.source_nodes.length > 0 && (
          <ul className="flex flex-wrap gap-1.5 mt-1" aria-label="참조 출처">
            {message.source_nodes.map((node, idx) => {
              const color = CITE_COLORS[idx % CITE_COLORS.length]

              return (
                <li key={node.id}>
                <button
                  type="button"
                  onClick={() => setGraphOverlay({ focusIndex: idx })}
                  className="group relative inline-flex items-center gap-1 px-2 py-1 rounded text-2xs font-mono leading-tight"
                  style={{
                    minHeight: '22px',
                    background: `color-mix(in srgb, ${color} 8%, transparent)`,
                    color,
                    border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
                    transition: 'opacity 200ms var(--ease-out)',
                  }}
                  aria-label={`출처 ${idx + 1}: ${node.name}${node.match_reason ? ' — ' + node.match_reason : ''}`}
                >
                  {/* 커스텀 호버 툴팁 */}
                  <div
                    className="absolute bottom-full left-0 mb-1.5 hidden group-hover:block z-50 w-64 pointer-events-none"
                  >
                    <div
                      className="rounded-lg p-2.5 text-left"
                      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}
                    >
                      {node.match_reason && (
                        <p className="text-2xs font-semibold text-gold-500 mb-1">{node.match_reason}</p>
                      )}
                      {node.description && (
                        <p className="text-2xs text-surface-800 mb-1">{node.description}</p>
                      )}
                      {node.source_titles && node.source_titles.length > 0 && (
                        <p className="text-2xs text-surface-600">
                          출처: {node.source_titles.join(', ')}
                        </p>
                      )}
                      {node.section_ref && (
                        <p className="text-2xs text-surface-600">
                          위치: {node.section_ref}
                        </p>
                      )}
                      {node.page_start != null && (
                        <p className="text-2xs text-surface-600">
                          페이지: {node.page_start}{node.page_end && node.page_end !== node.page_start ? `-${node.page_end}` : ''}
                        </p>
                      )}
                      {node.effective_date && (
                        <p className="text-2xs text-surface-600">시행일: {node.effective_date}</p>
                      )}
                    </div>
                  </div>

                  <span
                    className="inline-flex items-center justify-center rounded font-bold"
                    style={{
                      fontSize: '8px',
                      width: '14px',
                      height: '14px',
                      background: `color-mix(in srgb, ${color} 20%, transparent)`,
                    }}
                    aria-hidden="true"
                  >
                    {idx + 1}
                  </span>
                  <span className="font-semibold">{node.name}</span>
                  {(node.security_grade ?? 0) >= 2 && (
                    <span
                      className="px-1 py-0 rounded font-bold"
                      style={{
                        fontSize: '8px',
                        background: (node.security_grade ?? 0) >= 3
                          ? 'color-mix(in srgb, var(--color-error) 12%, transparent)'
                          : 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
                        color: (node.security_grade ?? 0) >= 3 ? 'var(--color-error)' : 'var(--color-warning)',
                      }}
                      aria-label={`보안 등급 G${(node.security_grade ?? 0)}`}
                    >
                      G{(node.security_grade ?? 0)}
                    </span>
                  )}
                  {node.source_titles && node.source_titles.length > 0 && (
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '9px' }}>
                      | {node.source_titles[0]}{node.source_titles.length > 1 ? ` 외 ${node.source_titles.length - 1}건` : ''}
                      {node.page_start != null && (
                        <> p.{node.page_start}{node.page_end != null && node.page_end !== node.page_start ? `-${node.page_end}` : ''}</>
                      )}
                    </span>
                  )}
                </button>
                </li>
              )
            })}
          </ul>
        )}

        {/* Clarification buttons */}
        {!isUser && message.clarification && onSelectOption && (
          <ClarificationButtons
            data={message.clarification}
            onSelect={onSelectOption}
          />
        )}

        {/* Inline execution log */}
        {!isUser && showLog && message.execution_log && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
            className="w-full max-w-lg"
          >
            <ExecutionLog steps={message.execution_log} reasoning={message.reasoning} />
          </motion.div>
        )}

        {/* Graph overlay */}
        {graphOverlay && message.source_nodes && message.source_nodes.length > 0 && (
          <GraphOverlay
            sourceNodes={message.source_nodes}
            focusIndex={graphOverlay.focusIndex}
            onClose={() => setGraphOverlay(null)}
          />
        )}
      </div>
    </motion.article>
  )
}

// ─── Thread List Item ─────────────────────────────────────────────────────────

function ThreadItem({
  thread,
  isActive,
  onSelect,
  onDelete,
}: {
  thread: AgentThread
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
      className={cn(
        'group relative flex items-center gap-2 rounded-md',
        isActive
          ? 'bg-surface-200 border border-surface-300'
          : 'hover:bg-surface-100',
      )}
      style={{ transition: 'background-color 200ms var(--ease-out)' }}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex-1 flex items-center gap-2 px-3 py-2.5 text-left min-w-0"
        aria-current={isActive ? 'page' : undefined}
      >
        <MessageSquare
          size={13}
          className={cn('shrink-0', isActive ? 'text-gold-500' : 'text-surface-600')}
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <p className={cn('text-xs font-semibold truncate', isActive ? 'text-gold-500' : 'text-surface-800')}>
            {thread.title}
          </p>
          <p className="text-2xs text-surface-600 font-mono mt-0.5">
            {thread.messages.length}개 메시지 · {formatRelativeTime(thread.updatedAt)}
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
        className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 absolute right-2 inline-flex items-center justify-center rounded text-surface-600 hover:text-status-error hover:bg-surface-300 shrink-0"
        style={{
          width: '24px',
          height: '24px',
          transition: 'opacity 200ms var(--ease-out), background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
        }}
        aria-label={`${thread.title} 대화 삭제`}
      >
        <Trash2 size={11} aria-hidden="true" />
      </button>
    </motion.div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface ServerInfo { id: string; name: string; model: string; url: string; description: string; online: boolean; signal: string; label: string; load_pct: number }

const SIGNAL_COLORS: Record<string, string> = {
  green: 'var(--color-success)',
  yellow: 'var(--color-warning)',
  red: 'var(--color-error)',
}

export default function AgentConsole() {
  const toast = useToast()
  const {
    threads,
    activeThreadId,
    createThread,
    setActiveThread,
    addMessageToThread,
    updateMessageInThread,
    deleteThread,
    getActiveThread,
  } = useStore()

  const [query, setQuery] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [hasStreamContent, setHasStreamContent] = useState(false)

  // 커스텀 프롬프트
  const [globalPrompt, setGlobalPrompt] = useState(() => localStorage.getItem('mai_global_prompt') || '')
  const [sessionPrompt, setSessionPrompt] = useState('')
  const [showPromptSettings, setShowPromptSettings] = useState(false)
  const PROMPT_MAX_LENGTH = 200
  const [runningSkills, setRunningSkills] = useState<string[]>([])  // 실행 중인 스킬명
  const [showExecSidebar, setShowExecSidebar] = useState(true)
  const [showMobileThreads, setShowMobileThreads] = useState(false)
  interface AgentUiConfig {
    welcome_title?: string
    welcome_subtitle?: string
    suggestions?: string[]
  }
  const [agentUi, setAgentUi] = useState<AgentUiConfig | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 에이전트 UI 설정 로드
  useEffect(() => {
    const uid = localStorage.getItem('malife_user_id') || 'admin01'
    fetch('/api/v1/admin/agent-ui', { headers: { 'X-User-Id': uid } })
      .then(r => r.json()).then(setAgentUi).catch(() => {})
  }, [])

  // 추론 서버 상태 + 모델 선택
  const [servers, setServers] = useState<ServerInfo[]>([])
  const [selectedServer, setSelectedServer] = useState<string>('local')
  const [loadingStatus, setLoadingStatus] = useState(false)
  // Derived: avoid servers.find() on every render/send
  const selectedServerInfo = servers.find(s => s.id === selectedServer)

  // 워크플로우 목록
  interface WorkflowNode {
    id: string
    type?: string
    data?: { label?: string; skillData?: { skill_name?: string } }
  }
  interface WorkflowEdge { source: string; target: string }
  interface SavedWorkflow { id: string; name: string; nodes: WorkflowNode[]; edges: WorkflowEdge[] }
  const [workflows, setWorkflows] = useState<SavedWorkflow[]>([])
  const [showWorkflows, setShowWorkflows] = useState(false)

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('mai_workflows') || '[]')
      setWorkflows(saved)
    } catch { /* ignore */ }
  }, [])

  const fetchServerStatus = useCallback(async () => {
    setLoadingStatus(true)
    try {
      const uid = localStorage.getItem('malife_user_id') || 'admin01'
      const r = await fetch('/api/v1/admin/inference-status', { headers: { 'X-User-Id': uid } })
      if (r.ok) {
        const d = await r.json()
        setServers(d.servers || [])
      }
    } catch { /* ignore */ }
    setLoadingStatus(false)
  }, [])

  // 최초 1회만 조회
  useEffect(() => { fetchServerStatus() }, [fetchServerStatus])

  const activeThread = getActiveThread()
  const lastAgentMessage = activeThread?.messages.slice().reverse().find((m: AgentMessage) => m.role === 'agent')

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [activeThread?.messages.length])

  // 스트리밍 중 스크롤 유지
  const streamContentRef = useRef('')
  useEffect(() => {
    if (isRunning) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [isRunning, hasStreamContent])

  const handleNewThread = useCallback(() => {
    createThread()
    setQuery('')
    inputRef.current?.focus()
  }, [createThread])

  async function handleSend() {
    sendMessage(query)
  }

  const sendMessage = useCallback(async (text: string, displayText?: string) => {
    const trimmed = text.trim()
    if (!trimmed || isRunning) return

    let threadId = activeThreadId
    if (!threadId) {
      threadId = createThread()
    }

    const userMsg: AgentMessage = {
      id: generateId(),
      role: 'user',
      content: displayText || trimmed,
      timestamp: new Date().toISOString(),
    }
    addMessageToThread(threadId, userMsg)
    setQuery('')
    setIsRunning(true)

    const agentMsgId = generateId()
    const placeholderMsg: AgentMessage = {
      id: agentMsgId,
      role: 'agent',
      content: '',
      timestamp: new Date().toISOString(),
      execution_log: [],
    }
    addMessageToThread(threadId, placeholderMsg)
    streamContentRef.current = ''
    setHasStreamContent(false)
    setRunningSkills([])

    // 이전 대화 히스토리 수집 (최근 6턴 = user+agent 3쌍)
    const thread = getActiveThread()
    const prevMessages = (thread?.messages || [])
      .filter(m => m.id !== placeholderMsg.id && m.content?.trim())
      .slice(-6)
      .map(m => ({ role: m.role === 'agent' ? 'assistant' as const : 'user' as const, content: m.content }))

    const tid = threadId
    await agentApi.stream(
      {
        query: trimmed,
        thread_id: threadId,
        server_url: selectedServerInfo?.url,
        custom_prompt: [globalPrompt, sessionPrompt].filter(Boolean).join('\n') || undefined,
        history: prevMessages.length > 0 ? prevMessages : undefined,
      },
      {
        onMetadata: (meta) => {
          updateMessageInThread(tid, agentMsgId, (msg) => ({
            ...msg,
            execution_log: meta.execution_log,
            reasoning: meta.reasoning,
            thread_id: meta.thread_id,
            source_nodes: meta.source_nodes,
          }))
        },
        onToken: (token) => {
          streamContentRef.current += token
          setHasStreamContent(true)
          const content = streamContentRef.current
          updateMessageInThread(tid, agentMsgId, (msg) => ({
            ...msg,
            content,
          }))
        },
        onClarification: (data) => {
          // clarification 도착 시 앞서 출력된 reasoning 텍스트 제거
          streamContentRef.current = ''
          setHasStreamContent(false)
          updateMessageInThread(tid, agentMsgId, (msg) => ({
            ...msg,
            clarification: data,
            content: '',
          }))
        },
        onSkillStatus: (data) => {
          if (data.status === 'running') {
            setRunningSkills(data.skills)
          } else {
            setRunningSkills([])
          }
        },
        onDone: () => {
          setIsRunning(false)
          setRunningSkills([])
        },
        onError: (err) => {
          updateMessageInThread(tid, agentMsgId, (msg) => ({
            ...msg,
            content: `오류가 발생했습니다: ${err}`,
          }))
          toast.error('에이전트 실행 실패', err)
          setIsRunning(false)
        },
      },
    )
  }, [
    isRunning, activeThreadId, createThread,
    addMessageToThread, updateMessageInThread, getActiveThread,
    selectedServerInfo, globalPrompt, sessionPrompt, toast,
  ])

  const handleSelectOption = useCallback((value: string, displayLabel: string) => {
    sendMessage(value, displayLabel)
  }, [sendMessage])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Esc 키로 모바일 스레드 드로어 닫기
  useEffect(() => {
    if (!showMobileThreads) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowMobileThreads(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [showMobileThreads])

  return (
    <div className="flex h-full overflow-hidden">
      {/* Mobile thread list overlay backdrop */}
      {showMobileThreads && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: 'var(--color-overlay)' }}
          onClick={() => setShowMobileThreads(false)}
          aria-hidden="true"
        />
      )}

      {/* Thread list */}
      <aside
        id="agent-thread-list"
        className="flex flex-col shrink-0 fixed inset-y-0 left-0 z-50 md:static md:z-auto md:translate-x-0"
        style={{
          width: '220px',
          borderRight: '1px solid var(--color-border)',
          background: 'var(--color-bg-secondary)',
          transform: showMobileThreads ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 280ms cubic-bezier(0.32, 0.72, 0, 1)',
        }}
        aria-label="대화 목록"
      >
        <div
          className="flex items-center justify-between px-3 py-2.5"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <span className="text-2xs font-mono text-surface-600 uppercase tracking-widest">
            대화 목록
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handleNewThread}
              className="inline-flex items-center justify-center rounded text-surface-600 hover:text-gold-500 hover:bg-surface-200"
              style={{
                width: '28px',
                height: '28px',
                transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
              }}
              aria-label="새 대화 시작"
            >
              <Plus size={13} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setShowMobileThreads(false)}
              className="inline-flex items-center justify-center rounded text-surface-600 hover:text-gold-500 hover:bg-surface-200 md:hidden"
              style={{
                width: '28px',
                height: '28px',
                transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
              }}
              aria-label="대화 목록 닫기"
            >
              <X size={13} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {threads.length === 0 ? (
            <div className="px-2 py-6 text-center">
              <Bot size={20} className="text-surface-600 mx-auto mb-2" aria-hidden="true" />
              <p className="text-xs text-surface-600">대화 없음</p>
              <button
                type="button"
                onClick={handleNewThread}
                className="mt-2 text-xs text-gold-500 hover:text-gold-hover"
                style={{ transition: 'color 200ms var(--ease-out)' }}
              >
                새 대화 시작
              </button>
            </div>
          ) : (
            threads.map((thread) => (
              <ThreadItem
                key={thread.id}
                thread={thread}
                isActive={thread.id === activeThreadId}
                onSelect={() => { setActiveThread(thread.id); setShowMobileThreads(false) }}
                onDelete={() => deleteThread(thread.id)}
              />
            ))
          )}
        </div>
      </aside>

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Chat header */}
        <div
          className="flex items-center justify-between px-3 sm:px-5 py-2.5 shrink-0"
          style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              onClick={() => setShowMobileThreads(true)}
              className="inline-flex items-center justify-center rounded text-surface-600 hover:text-gold-500 hover:bg-surface-200 md:hidden"
              style={{
                width: '36px',
                height: '36px',
                transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
              }}
              aria-label="대화 목록 열기"
              aria-expanded={showMobileThreads}
              aria-controls="agent-thread-list"
            >
              <Menu size={15} aria-hidden="true" />
            </button>
            <Bot size={15} className="text-gold-500 shrink-0" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-surface-900 truncate">
              {activeThread?.title ?? 'M:AI 에이전트'}
            </h2>
            {isRunning && (
              <span
                className="flex items-center gap-1 text-xs text-gold-500 shrink-0"
                role="status"
                aria-live="polite"
              >
                <Loader2 size={11} className="animate-spin" aria-hidden="true" />
                응답 생성 중...
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setShowPromptSettings((v) => !v)}
              className={cn('btn-secondary flex items-center gap-1.5 text-xs py-1', showPromptSettings && 'ring-1 ring-gold-500/50')}
              aria-expanded={showPromptSettings}
              aria-controls="prompt-settings-panel"
            >
              <Settings2 size={12} aria-hidden="true" />
              <span className="hidden sm:inline">프롬프트</span>
            </button>
            <button
              type="button"
              onClick={() => setShowExecSidebar((v) => !v)}
              className="btn-secondary flex items-center gap-1.5 text-xs py-1 hidden sm:flex"
              aria-expanded={showExecSidebar}
            >
              <Terminal size={12} aria-hidden="true" />
              {showExecSidebar ? '로그 숨기기' : '실행 로그'}
            </button>
          </div>
        </div>

        {/* 프롬프트 설정 패널 */}
        <AnimatePresence initial={false}>
          {showPromptSettings && (
            <motion.div
              id="prompt-settings-panel"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
              style={{ overflow: 'hidden', borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
            >
              <div className="px-3 sm:px-5 py-3 space-y-3">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label
                      htmlFor="prompt-global"
                      className="text-2xs font-semibold text-surface-600 uppercase tracking-widest"
                    >
                      글로벌 프롬프트
                    </label>
                    <span className="text-2xs text-surface-500 font-mono" aria-live="polite">
                      {globalPrompt.length}/{PROMPT_MAX_LENGTH}
                    </span>
                  </div>
                  <textarea
                    id="prompt-global"
                    value={globalPrompt}
                    onChange={(e) => {
                      const v = e.target.value.slice(0, PROMPT_MAX_LENGTH)
                      setGlobalPrompt(v)
                      localStorage.setItem('mai_global_prompt', v)
                    }}
                    placeholder="모든 대화에 적용되는 지시사항 (예: 항상 표 형식으로 답변해줘)"
                    rows={2}
                    className="w-full bg-transparent text-xs text-surface-900 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-gold-500/50 resize-none"
                    style={{ border: '1px solid var(--color-border)' }}
                    maxLength={PROMPT_MAX_LENGTH}
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label
                      htmlFor="prompt-session"
                      className="text-2xs font-semibold text-surface-600 uppercase tracking-widest"
                    >
                      이 대화 프롬프트
                    </label>
                    <span className="text-2xs text-surface-500 font-mono" aria-live="polite">
                      {sessionPrompt.length}/{PROMPT_MAX_LENGTH}
                    </span>
                  </div>
                  <textarea
                    id="prompt-session"
                    value={sessionPrompt}
                    onChange={(e) => setSessionPrompt(e.target.value.slice(0, PROMPT_MAX_LENGTH))}
                    placeholder="이 대화에만 적용 (예: 40세 남성 기준으로 안내해줘)"
                    rows={2}
                    className="w-full bg-transparent text-xs text-surface-900 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-gold-500/50 resize-none"
                    style={{ border: '1px solid var(--color-border)' }}
                    maxLength={PROMPT_MAX_LENGTH}
                  />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex flex-1 overflow-hidden">
          {/* Messages */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div
              className="flex-1 overflow-y-auto px-3 sm:px-6 py-4 space-y-5"
              role="log"
              aria-live="polite"
              aria-label="에이전트 대화"
            >
              {!activeThread || activeThread.messages.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                  className="flex flex-col items-center justify-center h-full text-center"
                >
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
                    style={{
                      background: 'color-mix(in srgb, var(--color-gold) 10%, transparent)',
                      border: '1px solid color-mix(in srgb, var(--color-gold) 20%, transparent)',
                    }}
                    aria-hidden="true"
                  >
                    <Bot size={28} className="text-gold-500" />
                  </div>
                  <h2 className="font-display font-semibold text-surface-800 text-xl mb-2">
                    {agentUi?.welcome_title || 'M:AI 에이전트'}
                  </h2>
                  <p className="text-sm text-surface-600 max-w-sm mb-6">
                    {agentUi?.welcome_subtitle || '금융 문서 분석, RAG 검색, 스킬 실행까지. 무엇이든 물어보세요.'}
                  </p>
                  <ul
                    className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-sm"
                    aria-label="추천 질문"
                  >
                    {(agentUi?.suggestions || [
                      '보험 약관에서 면책 조항 추출해줘',
                      '최근 투자 보고서 요약해줘',
                      '고객 민원 데이터 분석해줘',
                      '스킬 목록 보여줘',
                    ]).map((suggestion: string) => (
                      <li key={suggestion}>
                        <button
                          type="button"
                          onClick={() => setQuery(suggestion)}
                          className="w-full text-left p-3 rounded-md text-xs text-surface-700 hover:text-surface-900"
                          style={{
                            minHeight: '44px',
                            background: 'var(--color-bg-secondary)',
                            border: '1px solid var(--color-border)',
                            transition: 'color 200ms var(--ease-out), border-color 200ms var(--ease-out)',
                          }}
                        >
                          {suggestion}
                        </button>
                      </li>
                    ))}
                  </ul>
                </motion.div>
              ) : (
                <>
                  <AnimatePresence initial={false}>
                    {activeThread.messages.map((msg) => (
                      <MessageBubble key={msg.id} message={msg} onSelectOption={handleSelectOption} />
                    ))}
                  </AnimatePresence>
                  {isRunning && !hasStreamContent && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                      className="flex items-center gap-3"
                      role="status"
                      aria-live="polite"
                    >
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center"
                        style={{
                          background: 'color-mix(in srgb, var(--color-gold) 20%, transparent)',
                          border: '1px solid color-mix(in srgb, var(--color-gold) 30%, transparent)',
                        }}
                        aria-hidden="true"
                      >
                        <Bot size={13} className="text-gold-500" />
                      </div>
                      <div className="bubble-agent px-4 py-3">
                        {runningSkills.length > 0 ? (
                          <div className="flex items-center gap-2">
                            <Loader2 size={13} className="animate-spin text-gold-500 shrink-0" aria-hidden="true" />
                            <span className="text-xs text-surface-800">
                              <span className="font-semibold text-gold-500">{runningSkills.join(', ')}</span>
                              {' '}실행 중...
                            </span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="sr-only">답변을 준비하고 있습니다</span>
                            <div className="flex gap-1" aria-hidden="true">
                              {[0, 1, 2].map((i) => (
                                <span
                                  key={i}
                                  className="w-1.5 h-1.5 rounded-full bg-gold-500 animate-bounce"
                                  style={{ animationDelay: `${i * 150}ms` }}
                                />
                              ))}
                            </div>
                            <span className="text-2xs text-surface-600">답변 준비 중</span>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                  <div ref={messagesEndRef} aria-hidden="true" />
                </>
              )}
            </div>

            {/* Input area */}
            <div
              className="px-3 sm:px-5 py-3 shrink-0 space-y-2"
              style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
            >
              {/* Model selector + traffic lights */}
              {servers.length > 0 && (
                <div
                  className="flex items-center gap-2 overflow-x-auto"
                  role="radiogroup"
                  aria-label="추론 서버 선택"
                >
                  <button
                    type="button"
                    onClick={fetchServerStatus}
                    disabled={loadingStatus}
                    className="inline-flex items-center justify-center rounded text-surface-600 hover:text-gold-500 hover:bg-surface-200 shrink-0"
                    style={{
                      width: '28px',
                      height: '28px',
                      transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
                    }}
                    aria-label="서버 상태 새로고침"
                  >
                    {loadingStatus
                      ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                      : <RefreshCw size={12} aria-hidden="true" />
                    }
                  </button>
                  {servers.map((srv) => {
                    const signalColor = SIGNAL_COLORS[srv.signal] ?? SIGNAL_COLORS.red
                    const isSelected = selectedServer === srv.id
                    return (
                      <button
                        key={srv.id}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        onClick={() => setSelectedServer(srv.id)}
                        className={cn(
                          'flex items-center gap-2 px-3 py-1.5 rounded-md text-2xs font-mono',
                          isSelected
                            ? 'ring-1 ring-gold-500/50'
                            : 'opacity-60 hover:opacity-100',
                        )}
                        style={{
                          minHeight: '30px',
                          background: isSelected ? 'var(--color-bg-elevated)' : 'transparent',
                          border: `1px solid ${isSelected ? 'var(--color-gold)' : 'var(--color-border)'}`,
                          transition: 'opacity 200ms var(--ease-out), background-color 200ms var(--ease-out), border-color 200ms var(--ease-out)',
                        }}
                        aria-label={`${srv.name} ${srv.description ?? ''} — ${srv.label} ${srv.load_pct}% ${srv.online ? '정상' : '오프라인'}`}
                      >
                        {/* Traffic light */}
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{
                            background: signalColor,
                            boxShadow: srv.online
                              ? `0 0 6px color-mix(in srgb, ${signalColor} 40%, transparent)`
                              : 'none',
                          }}
                          aria-hidden="true"
                        />
                        <span className={cn('font-semibold', isSelected ? 'text-surface-900' : 'text-surface-600')}>
                          {srv.name}
                        </span>
                        <span style={{ color: signalColor, fontSize: '9px' }}>
                          {srv.label}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Workflow selector */}
              {workflows.length > 0 && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowWorkflows(v => !v)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-2xs font-mono text-surface-600 hover:text-gold-500"
                    style={{
                      minHeight: '30px',
                      border: '1px solid var(--color-border)',
                      transition: 'color 200ms var(--ease-out), border-color 200ms var(--ease-out)',
                    }}
                    aria-expanded={showWorkflows}
                    aria-haspopup="menu"
                  >
                    <Workflow size={12} aria-hidden="true" />
                    워크플로우
                    <ChevronDown
                      size={10}
                      className={cn(showWorkflows && 'rotate-180')}
                      style={{ transition: 'transform 200ms var(--ease-out)' }}
                      aria-hidden="true"
                    />
                  </button>
                  <AnimatePresence>
                    {showWorkflows && (
                      <motion.div
                        initial={{ opacity: 0, y: 4, scale: 0.97 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 4, scale: 0.97 }}
                        transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                        className="absolute bottom-full mb-1 left-0 z-20 rounded-lg shadow-xl overflow-hidden min-w-[220px]"
                        style={{
                          background: 'var(--color-bg-elevated)',
                          border: '1px solid var(--color-border)',
                          transformOrigin: 'bottom left',
                        }}
                        role="menu"
                      >
                        <div className="px-3 py-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
                          <p className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">저장된 워크플로우</p>
                        </div>
                        {workflows.map(wf => (
                          <button
                            key={wf.id}
                            type="button"
                            role="menuitem"
                            onClick={() => {
                              const skillNodes = wf.nodes.filter((n) => n.type === 'skill')
                              const skillNames = skillNodes.map((n) => n.data?.label || n.data?.skillData?.skill_name).join(', ')
                              sendMessage(`[워크플로우: ${wf.name}] 다음 스킬을 순서대로 실행해줘: ${skillNames}`)
                              setShowWorkflows(false)
                            }}
                            className="w-full text-left px-3 py-2.5 hover:bg-surface-200"
                            style={{ transition: 'background-color 200ms var(--ease-out)' }}
                          >
                            <p className="text-xs font-semibold text-surface-900">{wf.name}</p>
                            <p className="text-2xs text-surface-600 mt-0.5">
                              {wf.nodes.filter((n) => n.type === 'skill').length}개 스킬 · {wf.edges.length}개 연결
                            </p>
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              <form
                onSubmit={(e) => { e.preventDefault(); handleSend() }}
                className="flex items-end gap-3 rounded-lg p-3"
                style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
                aria-label="에이전트 질문 입력"
              >
                <label htmlFor="agent-input" className="sr-only">에이전트에게 질문</label>
                <textarea
                  ref={inputRef}
                  id="agent-input"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="에이전트에게 질문하세요... (Shift+Enter로 줄바꿈)"
                  rows={1}
                  className="flex-1 bg-transparent text-surface-900 text-sm resize-none focus:outline-none leading-relaxed"
                  style={{ maxHeight: '120px', minHeight: '24px' }}
                  onInput={(e) => {
                    const el = e.currentTarget
                    el.style.height = 'auto'
                    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
                  }}
                  disabled={isRunning}
                  aria-describedby="agent-input-hint"
                />
                <button
                  type="submit"
                  disabled={!query.trim() || isRunning}
                  className={cn(
                    'w-9 h-9 rounded-md flex items-center justify-center shrink-0 active:scale-[0.97]',
                    query.trim() && !isRunning
                      ? 'bg-gold-500 text-surface-DEFAULT hover:bg-gold-hover'
                      : 'bg-surface-300 text-surface-600 cursor-not-allowed',
                  )}
                  style={{
                    transition: 'background-color 200ms var(--ease-out), transform 120ms var(--ease-out)',
                  }}
                  aria-label={isRunning ? '전송 중' : '메시지 전송'}
                  aria-busy={isRunning}
                >
                  {isRunning ? (
                    <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                  ) : (
                    <Send size={14} aria-hidden="true" />
                  )}
                </button>
              </form>
              <p
                id="agent-input-hint"
                className="text-2xs text-surface-600 text-center font-mono"
              >
                Enter 전송 · Shift+Enter 줄바꿈 · 대화 ID: {activeThreadId?.slice(-8) ?? '—'}
              </p>
            </div>
          </div>

          {/* Execution Log Sidebar */}
          <AnimatePresence initial={false}>
            {showExecSidebar && (
              <motion.aside
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 280, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
                className="flex flex-col overflow-hidden shrink-0"
                style={{ borderLeft: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
                aria-label="실행 로그"
              >
                <div
                  className="px-3 py-2.5"
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                >
                  <h2 className="text-2xs font-mono text-surface-600 uppercase tracking-widest">
                    실행 로그
                  </h2>
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {lastAgentMessage?.execution_log && lastAgentMessage.execution_log.length > 0 ? (
                    <ExecutionLog
                      steps={lastAgentMessage.execution_log}
                      reasoning={lastAgentMessage.reasoning}
                    />
                  ) : (
                    <div className="text-center py-8">
                      <Terminal size={20} className="text-surface-600 mx-auto mb-2" aria-hidden="true" />
                      <p className="text-xs text-surface-600">실행 로그 없음</p>
                    </div>
                  )}
                </div>
              </motion.aside>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
