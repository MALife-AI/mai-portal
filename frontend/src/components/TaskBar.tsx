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

  useEffect(() => {
    fetchTasks()
    // 활성 태스크가 있을 때만 폴링, 없으면 멈춤
    const hasActive = tasks.some((t) => t.status === 'running' || t.status === 'pending')
    if (!hasActive) return
    const interval = setInterval(fetchTasks, 2000)
    return () => clearInterval(interval)
  }, [fetchTasks, tasks.length])

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
        return <Loader2 size={12} className="text-gold-500 animate-spin" />
      case 'completed':
        return <CheckCircle2 size={12} className="text-status-success" />
      case 'failed':
        return <XCircle size={12} className="text-status-error" />
      case 'cancelled':
        return <X size={12} className="text-surface-600" />
    }
  }

  return (
    <motion.div
      initial={{ y: 50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed bottom-4 right-4 z-50"
      style={{ width: '340px' }}
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
          onClick={() => setCollapsed((v) => !v)}
          className="w-full flex items-center justify-between px-3 py-2"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="flex items-center gap-2">
            {activeTasks.length > 0 && (
              <Loader2 size={12} className="text-gold-500 animate-spin" />
            )}
            <span className="text-xs font-semibold text-surface-800">
              작업 {activeTasks.length > 0 ? `진행 중 (${activeTasks.length})` : '완료'}
            </span>
          </div>
          {collapsed ? <ChevronUp size={12} className="text-surface-600" /> : <ChevronDown size={12} className="text-surface-600" />}
        </button>

        {/* Task list */}
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: 'auto' }}
              exit={{ height: 0 }}
              style={{ overflow: 'hidden' }}
            >
              <div className="max-h-48 overflow-y-auto">
                {visibleTasks.map((task) => (
                  <div
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
                      {(task.status === 'running' || task.status === 'pending') && task.total > 0 && (
                        <div
                          className="mt-1 h-1 rounded-full overflow-hidden"
                          style={{ background: 'var(--color-bg-primary)' }}
                        >
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${Math.round((task.progress / task.total) * 100)}%`,
                              background: 'var(--color-gold-500)',
                            }}
                          />
                        </div>
                      )}
                    </div>
                    {(task.status === 'running' || task.status === 'pending') && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          cancelTask(task.id)
                        }}
                        className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-surface-600 hover:text-status-error hover:bg-surface-200 transition-colors"
                        title="취소"
                      >
                        <X size={11} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
