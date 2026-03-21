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
} from 'lucide-react'
import { agentApi, type ExecutionStep, type StreamCallbacks } from '@/api/client'
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
      case 'success': return <CheckCircle2 size={12} className="text-status-success" />
      case 'error': return <XCircle size={12} className="text-status-error" />
      case 'running': return <Loader2 size={12} className="text-gold-500 animate-spin" />
      default: return <Clock size={12} className="text-surface-600" />
    }
  }

  return (
    <div className="space-y-2">
      {/* Reasoning */}
      {reasoning && (
        <div className="panel">
          <button
            className="w-full flex items-center justify-between px-3 py-2.5"
            onClick={() => setShowReasoning((v) => !v)}
          >
            <div className="flex items-center gap-2">
              <Brain size={13} className="text-gold-500" />
              <span className="text-xs font-semibold text-surface-800">추론 과정</span>
            </div>
            {showReasoning ? (
              <ChevronDown size={12} className="text-surface-600" />
            ) : (
              <ChevronRight size={12} className="text-surface-600" />
            )}
          </button>
          <AnimatePresence>
            {showReasoning && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
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

        return (
          <div key={i} className="panel">
            <button
              className="w-full flex items-center gap-2 px-3 py-2.5"
              onClick={() => toggleStep(i)}
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
                <ChevronDown size={11} className="text-surface-600 shrink-0" />
              ) : (
                <ChevronRight size={11} className="text-surface-600 shrink-0" />
              )}
            </button>

            <AnimatePresence>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
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
                      <div className="rounded p-2" style={{ background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.2)' }}>
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

function MessageBubble({ message }: { message: AgentMessage }) {
  const isUser = message.role === 'user'
  const [showLog, setShowLog] = useState(false)
  const [graphOverlay, setGraphOverlay] = useState<{ focusIndex: number } | null>(null)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('flex gap-3', isUser && 'flex-row-reverse')}
    >
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center mt-0.5"
        style={{
          background: isUser
            ? 'rgba(74, 158, 255, 0.2)'
            : 'rgba(243, 112, 33, 0.2)',
          border: isUser
            ? '1px solid rgba(74, 158, 255, 0.3)'
            : '1px solid rgba(243, 112, 33, 0.3)',
        }}
      >
        {isUser ? (
          <User size={13} className="text-slate-data" />
        ) : (
          <Bot size={13} className="text-gold-500" />
        )}
      </div>

      {/* Content */}
      <div className={cn('max-w-[75%] space-y-2', isUser && 'items-end flex flex-col')}>
        <div className={cn(isUser ? 'bubble-user' : 'bubble-agent', 'px-4 py-3')}>
          {isUser ? (
            <p className="text-sm text-surface-900 leading-relaxed">{message.content}</p>
          ) : (
            <div className="text-sm">
              <MarkdownViewer content={message.content} />
            </div>
          )}
        </div>

        <div className={cn('flex items-center gap-2', isUser && 'flex-row-reverse')}>
          <span className="text-2xs text-surface-600 font-mono">
            {formatRelativeTime(message.timestamp)}
          </span>

          {!isUser && message.source_nodes && message.source_nodes.length > 0 && (
            <button
              onClick={() => setGraphOverlay({ focusIndex: 0 })}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono font-semibold hover:opacity-80 transition-opacity cursor-pointer"
              style={{
                background: 'rgba(139, 92, 246, 0.12)',
                color: 'rgb(139, 92, 246)',
                border: '1px solid rgba(139, 92, 246, 0.25)',
              }}
              title="클릭하여 참조 그래프 보기"
            >
              <Brain size={9} />
              GraphRAG
            </button>
          )}
          {!isUser && (!message.source_nodes || message.source_nodes.length === 0) && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono font-semibold"
              style={{
                background: 'rgba(139, 92, 246, 0.12)',
                color: 'rgb(139, 92, 246)',
                border: '1px solid rgba(139, 92, 246, 0.25)',
              }}
            >
              <Brain size={9} />
              GraphRAG
            </span>
          )}

          {!isUser && message.execution_log && message.execution_log.length > 0 && (
            <button
              onClick={() => setShowLog((v) => !v)}
              className="flex items-center gap-1 text-2xs text-surface-600 hover:text-gold-500 transition-colors font-mono"
            >
              <Terminal size={10} />
              {showLog ? '로그 숨기기' : `실행 로그 (${message.execution_log.length})`}
            </button>
          )}
        </div>

        {/* 출처: 번호 매긴 엔티티 + 소스 문서 */}
        {!isUser && message.source_nodes && message.source_nodes.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {message.source_nodes.map((node, idx) => {
              const colors = ['#F37021','#4A90D9','#34C759','#AF52DE','#FF3B30','#5AC8FA','#FFCC00','#FF2D55','#64D2FF','#30D158']
              const color = colors[idx % colors.length]
              return (
                <button
                  key={node.id}
                  onClick={() => setGraphOverlay({ focusIndex: idx })}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded text-2xs font-mono leading-tight hover:opacity-80 transition-opacity cursor-pointer"
                  style={{
                    background: `${color}14`,
                    color: color,
                    border: `1px solid ${color}33`,
                  }}
                  title={node.description || node.name}
                >
                  <span
                    className="inline-flex items-center justify-center rounded font-bold"
                    style={{ fontSize: '8px', width: '14px', height: '14px', background: `${color}33` }}
                  >
                    {idx + 1}
                  </span>
                  <span className="font-semibold">{node.name}</span>
                  {node.source_titles.length > 0 && (
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '9px' }}>
                      | {node.source_titles[0]}{node.source_titles.length > 1 ? ` 외 ${node.source_titles.length - 1}건` : ''}
                      {node.page_start != null && (
                        <> p.{node.page_start}{node.page_end != null && node.page_end !== node.page_start ? `-${node.page_end}` : ''}</>
                      )}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {/* Inline execution log */}
        {!isUser && showLog && message.execution_log && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
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
    </motion.div>
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
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={cn(
        'group flex items-center gap-2 px-3 py-2.5 rounded-md cursor-pointer transition-colors',
        isActive
          ? 'bg-surface-200 border border-surface-300'
          : 'hover:bg-surface-100',
      )}
      onClick={onSelect}
    >
      <MessageSquare
        size={13}
        className={cn('shrink-0', isActive ? 'text-gold-500' : 'text-surface-600')}
      />
      <div className="flex-1 min-w-0">
        <p className={cn('text-xs font-semibold truncate', isActive ? 'text-gold-500' : 'text-surface-800')}>
          {thread.title}
        </p>
        <p className="text-2xs text-surface-600 font-mono mt-0.5">
          {thread.messages.length}개 메시지 · {formatRelativeTime(thread.updatedAt)}
        </p>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
        className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center rounded text-surface-600 hover:text-status-error hover:bg-surface-300 transition-all shrink-0"
      >
        <Trash2 size={11} />
      </button>
    </motion.div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface ServerInfo { id: string; name: string; model: string; url: string; description: string; online: boolean; signal: string; label: string; load_pct: number }

const SIGNAL_COLORS: Record<string, string> = { green: '#34C759', yellow: '#F5A623', red: '#FF3B30' }

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
  const [showExecSidebar, setShowExecSidebar] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 추론 서버 상태 + 모델 선택
  const [servers, setServers] = useState<ServerInfo[]>([])
  const [selectedServer, setSelectedServer] = useState<string>('local')
  const [loadingStatus, setLoadingStatus] = useState(false)
  // Derived: avoid servers.find() on every render/send
  const selectedServerInfo = servers.find(s => s.id === selectedServer)

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
  })

  const handleNewThread = useCallback(() => {
    createThread()
    setQuery('')
    inputRef.current?.focus()
  }, [createThread])

  async function handleSend() {
    const trimmedQuery = query.trim()
    if (!trimmedQuery || isRunning) return

    let threadId = activeThreadId
    if (!threadId) {
      threadId = createThread()
    }

    const userMsg: AgentMessage = {
      id: generateId(),
      role: 'user',
      content: trimmedQuery,
      timestamp: new Date().toISOString(),
    }
    addMessageToThread(threadId, userMsg)
    setQuery('')
    setIsRunning(true)

    // 빈 에이전트 메시지를 먼저 추가 (스트리밍으로 채워감)
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

    const tid = threadId // capture for callbacks
    await agentApi.stream(
      { query: trimmedQuery, thread_id: threadId, server_url: selectedServerInfo?.url },
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
          const content = streamContentRef.current
          updateMessageInThread(tid, agentMsgId, (msg) => ({
            ...msg,
            content,
          }))
        },
        onDone: () => {
          setIsRunning(false)
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
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Thread list */}
      <div
        className="flex flex-col shrink-0"
        style={{
          width: '220px',
          borderRight: '1px solid var(--color-border)',
          background: 'var(--color-bg-secondary)',
        }}
      >
        <div
          className="flex items-center justify-between px-3 py-2.5"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <span className="text-2xs font-mono text-surface-600 uppercase tracking-widest">
            대화 목록
          </span>
          <button
            onClick={handleNewThread}
            className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-gold-500 hover:bg-surface-200 transition-colors"
            title="새 대화"
          >
            <Plus size={13} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {threads.length === 0 ? (
            <div className="px-2 py-6 text-center">
              <Bot size={20} className="text-surface-600 mx-auto mb-2" />
              <p className="text-xs text-surface-600">대화 없음</p>
              <button
                onClick={handleNewThread}
                className="mt-2 text-xs text-gold-500 hover:text-gold-400 transition-colors"
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
                onSelect={() => setActiveThread(thread.id)}
                onDelete={() => deleteThread(thread.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Chat header */}
        <div
          className="flex items-center justify-between px-5 py-2.5 shrink-0"
          style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
        >
          <div className="flex items-center gap-2">
            <Bot size={15} className="text-gold-500" />
            <span className="text-sm font-semibold text-surface-900">
              {activeThread?.title ?? '미래에셋 에이전트'}
            </span>
            {isRunning && (
              <span className="flex items-center gap-1 text-xs text-gold-500">
                <Loader2 size={11} className="animate-spin" />
                응답 생성 중...
              </span>
            )}
          </div>
          <button
            onClick={() => setShowExecSidebar((v) => !v)}
            className="btn-secondary flex items-center gap-1.5 text-xs py-1"
          >
            <Terminal size={12} />
            {showExecSidebar ? '로그 숨기기' : '실행 로그'}
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Messages */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
              {!activeThread || activeThread.messages.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-col items-center justify-center h-full text-center"
                >
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
                    style={{ background: 'rgba(243, 112, 33, 0.1)', border: '1px solid rgba(243, 112, 33, 0.2)' }}
                  >
                    <Bot size={28} className="text-gold-500" />
                  </div>
                  <h3 className="font-display font-semibold text-surface-800 text-xl mb-2">
                    미래에셋 에이전트
                  </h3>
                  <p className="text-sm text-surface-600 max-w-sm mb-6">
                    금융 문서 분석, RAG 검색, 스킬 실행까지. 무엇이든 물어보세요.
                  </p>
                  <div className="grid grid-cols-2 gap-2 max-w-sm">
                    {[
                      '보험 약관에서 면책 조항 추출해줘',
                      '최근 투자 보고서 요약해줘',
                      '고객 민원 데이터 분석해줘',
                      '스킬 목록 보여줘',
                    ].map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setQuery(suggestion)}
                        className="text-left p-3 rounded-md text-xs text-surface-700 hover:text-surface-900 transition-colors"
                        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </motion.div>
              ) : (
                <>
                  <AnimatePresence>
                    {activeThread.messages.map((msg) => (
                      <MessageBubble key={msg.id} message={msg} />
                    ))}
                  </AnimatePresence>
                  {isRunning && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex items-center gap-3"
                    >
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center"
                        style={{ background: 'rgba(243, 112, 33, 0.2)', border: '1px solid rgba(243, 112, 33, 0.3)' }}
                      >
                        <Bot size={13} className="text-gold-500" />
                      </div>
                      <div className="bubble-agent px-4 py-3">
                        <div className="flex gap-1">
                          {[0, 1, 2].map((i) => (
                            <span
                              key={i}
                              className="w-1.5 h-1.5 rounded-full bg-gold-500 animate-bounce"
                              style={{ animationDelay: `${i * 150}ms` }}
                            />
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  )}
                  <div ref={messagesEndRef} />
                </>
              )}
            </div>

            {/* Input area */}
            <div
              className="px-5 py-3 shrink-0 space-y-2"
              style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
            >
              {/* Model selector + traffic lights */}
              {servers.length > 0 && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={fetchServerStatus}
                    disabled={loadingStatus}
                    className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-gold-500 hover:bg-surface-200 transition-colors shrink-0"
                    title="서버 상태 새로고침"
                  >
                    {loadingStatus ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                  </button>
                  {servers.map((srv) => {
                    const signalColor = SIGNAL_COLORS[srv.signal] ?? SIGNAL_COLORS.red
                    const isSelected = selectedServer === srv.id
                    return (
                      <button
                        key={srv.id}
                        onClick={() => setSelectedServer(srv.id)}
                        className={cn(
                          'flex items-center gap-2 px-3 py-1.5 rounded-md text-2xs font-mono transition-all',
                          isSelected
                            ? 'ring-1 ring-gold-500/50'
                            : 'opacity-60 hover:opacity-100',
                        )}
                        style={{
                          background: isSelected ? 'var(--color-bg-elevated)' : 'transparent',
                          border: `1px solid ${isSelected ? 'var(--color-gold)' : 'var(--color-border)'}`,
                        }}
                        title={`${srv.description} — ${srv.label} (${srv.load_pct}%)`}
                      >
                        {/* Traffic light */}
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{
                            background: signalColor,
                            boxShadow: srv.online ? `0 0 6px ${signalColor}66` : 'none',
                          }}
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

              <div
                className="flex items-end gap-3 rounded-lg p-3"
                style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
              >
                <textarea
                  ref={inputRef}
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
                />
                <button
                  onClick={handleSend}
                  disabled={!query.trim() || isRunning}
                  className={cn(
                    'w-8 h-8 rounded-md flex items-center justify-center shrink-0 transition-colors',
                    query.trim() && !isRunning
                      ? 'bg-gold-500 text-surface-DEFAULT hover:bg-gold-400'
                      : 'bg-surface-300 text-surface-600 cursor-not-allowed',
                  )}
                >
                  {isRunning ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Send size={14} />
                  )}
                </button>
              </div>
              <p className="text-2xs text-surface-600 text-center font-mono">
                Enter 전송 · Shift+Enter 줄바꿈 · 대화 ID: {activeThreadId?.slice(-8) ?? '—'}
              </p>
            </div>
          </div>

          {/* Execution Log Sidebar */}
          <AnimatePresence>
            {showExecSidebar && (
              <motion.div
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 280, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="flex flex-col overflow-hidden shrink-0"
                style={{ borderLeft: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
              >
                <div
                  className="px-3 py-2.5"
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                >
                  <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest">
                    실행 로그
                  </p>
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {lastAgentMessage?.execution_log && lastAgentMessage.execution_log.length > 0 ? (
                    <ExecutionLog
                      steps={lastAgentMessage.execution_log}
                      reasoning={lastAgentMessage.reasoning}
                    />
                  ) : (
                    <div className="text-center py-8">
                      <Terminal size={20} className="text-surface-600 mx-auto mb-2" />
                      <p className="text-xs text-surface-600">실행 로그 없음</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
