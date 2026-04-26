import { useMemo } from 'react'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ToastType } from '@/components/Toast'

// ─── Toast State ──────────────────────────────────────────────────────────────

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
}

// ─── Agent Thread ─────────────────────────────────────────────────────────────

export interface AgentMessage {
  id: string
  role: 'user' | 'agent'
  content: string
  timestamp: string
  execution_log?: import('@/api/client').ExecutionStep[]
  reasoning?: string
  thread_id?: string
  source_nodes?: import('@/api/client').SourceNode[]
  clarification?: import('@/api/client').ClarificationData
}

export interface AgentThread {
  id: string
  title: string
  messages: AgentMessage[]
  createdAt: string
  updatedAt: string
}

// ─── Store ────────────────────────────────────────────────────────────────────

interface AppState {
  // User
  userId: string
  setUserId: (id: string) => void

  // Toasts
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void

  // Agent threads (persisted)
  threads: AgentThread[]
  activeThreadId: string | null
  createThread: () => string
  setActiveThread: (id: string) => void
  addMessageToThread: (threadId: string, message: AgentMessage) => void
  updateMessageInThread: (threadId: string, messageId: string, updater: (msg: AgentMessage) => AgentMessage) => void
  deleteThread: (id: string) => void
  getActiveThread: () => AgentThread | undefined

  // Vault
  selectedVaultPath: string | null
  setSelectedVaultPath: (path: string | null) => void

  // Kill switch cache
  killSwitchActive: boolean
  setKillSwitchActive: (active: boolean) => void
}

let toastIdCounter = 0

export const useStore = create<AppState>()(
  persist(
    (set, get) => ({
      // ── User ────────────────────────────────────────────────────────────────
      userId: 'admin01',
      setUserId: (id) => {
        set({ userId: id })
        try {
          localStorage.setItem('malife_user_id', id)
        } catch {
          // ignore
        }
      },

      // ── Toasts ──────────────────────────────────────────────────────────────
      toasts: [],
      addToast: (toast) => {
        const id = String(++toastIdCounter)
        set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }))
        setTimeout(() => {
          get().removeToast(id)
        }, 5000)
      },
      removeToast: (id) =>
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

      // ── Agent Threads ────────────────────────────────────────────────────────
      threads: [],
      activeThreadId: null,

      createThread: () => {
        const id = `thread_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
        const now = new Date().toISOString()
        const thread: AgentThread = {
          id,
          title: '새 대화',
          messages: [],
          createdAt: now,
          updatedAt: now,
        }
        set((state) => ({
          threads: [thread, ...state.threads],
          activeThreadId: id,
        }))
        return id
      },

      setActiveThread: (id) => set({ activeThreadId: id }),

      addMessageToThread: (threadId, message) => {
        set((state) => ({
          threads: state.threads.map((t) => {
            if (t.id !== threadId) return t
            const updatedMessages = [...t.messages, message]
            // Auto-title from first user message
            const title =
              t.messages.length === 0 && message.role === 'user'
                ? message.content.slice(0, 40) + (message.content.length > 40 ? '…' : '')
                : t.title
            return {
              ...t,
              messages: updatedMessages,
              title,
              updatedAt: new Date().toISOString(),
            }
          }),
        }))
      },

      updateMessageInThread: (threadId, messageId, updater) => {
        set((state) => ({
          threads: state.threads.map((t) => {
            if (t.id !== threadId) return t
            return {
              ...t,
              messages: t.messages.map((m) => (m.id === messageId ? updater(m) : m)),
              updatedAt: new Date().toISOString(),
            }
          }),
        }))
      },

      deleteThread: (id) =>
        set((state) => ({
          threads: state.threads.filter((t) => t.id !== id),
          activeThreadId: state.activeThreadId === id ? null : state.activeThreadId,
        })),

      getActiveThread: () => {
        const { threads, activeThreadId } = get()
        return threads.find((t) => t.id === activeThreadId)
      },

      // ── Vault ────────────────────────────────────────────────────────────────
      selectedVaultPath: null,
      setSelectedVaultPath: (path) => set({ selectedVaultPath: path }),

      // ── Kill Switch ──────────────────────────────────────────────────────────
      killSwitchActive: false,
      setKillSwitchActive: (active) => set({ killSwitchActive: active }),
    }),
    {
      name: 'malife-lake-store',
      partialize: (state) => ({
        userId: state.userId,
        threads: state.threads,
        activeThreadId: state.activeThreadId,
      }),
    },
  ),
)

// ─── Convenience Hook ─────────────────────────────────────────────────────────

export function useToast() {
  const addToast = useStore((s) => s.addToast)

  return useMemo(() => ({
    success: (title: string, message?: string) =>
      addToast({ type: 'success', title, message }),
    error: (title: string, message?: string) =>
      addToast({ type: 'error', title, message }),
    warning: (title: string, message?: string) =>
      addToast({ type: 'warning', title, message }),
    info: (title: string, message?: string) =>
      addToast({ type: 'info', title, message }),
  }), [addToast])
}
