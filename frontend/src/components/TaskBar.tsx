import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, X, CheckCircle2, XCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { getUserId } from '@/api/client'

const API_BASE = ''

interface Task {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  total: number
  message: string
  error: string
}

export function TaskBar() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [collapsed, setCollapsed] = useState(false)

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/ingest/tasks`, {
        headers: { 'X-User-Id': getUserId() },
      })
      if (res.ok) {
        const data = await res.json()
        setTasks(data.tasks ?? [])
      }
    } catch {
      // ignore
    }
  }, [])

  const hasActive = tasks.some((t) => t.status === 'running' || t.status === 'pending')

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  useEffect(() => {
    // 활성 태스크가 있을 때만 폴링
    if (!hasActive) return
    const interval = setInterval(fetchTasks, 2000)
    return () => clearInterval(interval)
  }, [fetchTasks, hasActive])

  const cancelTask = async (taskId: string) => {
    try {
      await fetch(`${API_BASE}/api/v1/ingest/tasks/${taskId}`, {
        method: 'DELETE',
        headers: { 'X-User-Id': getUserId() },
      })
      fetchTasks()
    } catch {
      // ignore
    }
  }

  // 활성 태스크만 표시 (pending, running)
  const activeTasks = tasks.filter((t) => t.status === 'pending' || t.status === 'running')
  // 최근 완료/실패 (5초 이내)
  const recentDone = tasks.filter(
    (t) => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled',
  ).slice(0, 3)

  const visibleTasks = [...activeTasks, ...recentDone]
  if (visibleTasks.length === 0) return null

  const statusIcon = (status: Task['status']) => {
    switch (status) {
      case 'running':
      case 'pending':
        return <Loader2 size={12} className="text-gold-500 animate-spin" aria-hidden="true" />
      case 'completed':
        return <CheckCircle2 size={12} className="text-status-success" aria-hidden="true" />
      case 'failed':
        return <XCircle size={12} className="text-status-error" aria-hidden="true" />
      case 'cancelled':
        return <X size={12} className="text-surface-600" aria-hidden="true" />
    }
  }

  return (
    <motion.aside
      initial={{ y: 40, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.24, ease: [0.23, 1, 0.32, 1] }}
      className="fixed bottom-4 right-4 z-50"
      style={{ width: '340px' }}
      aria-label="백그라운드 작업"
    >
      <div
        className="rounded-lg shadow-lg overflow-hidden"
        style={{
          background: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
        }}
      >
        {/* Header */}
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          className="w-full flex items-center justify-between px-3 py-2"
          style={{ borderBottom: '1px solid var(--color-border)', minHeight: '36px' }}
          aria-expanded={!collapsed}
          aria-controls="taskbar-list"
          aria-label={`백그라운드 작업 ${activeTasks.length}건 ${collapsed ? '펼치기' : '접기'}`}
        >
          <div className="flex items-center gap-2">
            {activeTasks.length > 0 && (
              <Loader2 size={12} className="text-gold-500 animate-spin" aria-hidden="true" />
            )}
            <span className="text-xs font-semibold text-surface-800">
              작업 {activeTasks.length > 0 ? `진행 중 (${activeTasks.length})` : '완료'}
            </span>
          </div>
          {collapsed
            ? <ChevronUp size={12} className="text-surface-600" aria-hidden="true" />
            : <ChevronDown size={12} className="text-surface-600" aria-hidden="true" />
          }
        </button>

        {/* Task list */}
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              id="taskbar-list"
              initial={{ height: 0 }}
              animate={{ height: 'auto' }}
              exit={{ height: 0 }}
              transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
              style={{ overflow: 'hidden' }}
            >
              <ul className="max-h-48 overflow-y-auto">
                {visibleTasks.map((task) => {
                  const percent = task.total > 0 ? Math.round((task.progress / task.total) * 100) : 0
                  const inProgress = task.status === 'running' || task.status === 'pending'
                  return (
                    <li
                      key={task.id}
                      className="flex items-center gap-2 px-3 py-2"
                      style={{ borderBottom: '1px solid var(--color-border)' }}
                    >
                      {statusIcon(task.status)}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-surface-800 truncate">{task.name}</p>
                        <p className="text-2xs text-surface-600 truncate">
                          {task.error || task.message || `${task.progress}/${task.total}`}
                        </p>
                        {inProgress && task.total > 0 && (
                          <div
                            className="mt-1 h-1 rounded-full overflow-hidden"
                            style={{ background: 'var(--color-bg-primary)' }}
                            role="progressbar"
                            aria-valuenow={percent}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label={`${task.name} 진행률 ${percent}%`}
                          >
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${percent}%`,
                                background: 'var(--color-gold)',
                                transition: 'width 280ms var(--ease-out)',
                              }}
                            />
                          </div>
                        )}
                      </div>
                      {inProgress && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            cancelTask(task.id)
                          }}
                          className="shrink-0 inline-flex items-center justify-center rounded text-surface-600 hover:text-status-error hover:bg-surface-200"
                          style={{
                            width: '24px',
                            height: '24px',
                            transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
                          }}
                          aria-label={`${task.name} 취소`}
                        >
                          <X size={11} aria-hidden="true" />
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  )
}
