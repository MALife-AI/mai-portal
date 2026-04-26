import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react'
import { useStore } from '@/store/useStore'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

const icons: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle2 size={16} className="text-status-success shrink-0 mt-0.5" aria-hidden="true" />,
  error: <XCircle size={16} className="text-status-error shrink-0 mt-0.5" aria-hidden="true" />,
  warning: <AlertTriangle size={16} className="text-status-warning shrink-0 mt-0.5" aria-hidden="true" />,
  info: <Info size={16} className="text-slate-data shrink-0 mt-0.5" aria-hidden="true" />,
}

const typeLabels: Record<ToastType, string> = {
  success: '성공',
  error: '오류',
  warning: '경고',
  info: '정보',
}

export function ToastContainer() {
  const toasts = useStore((s) => s.toasts)
  const removeToast = useStore((s) => s.removeToast)

  return (
    <div className="toast-container" aria-label="알림" aria-live="polite">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => {
          const isAssertive = toast.type === 'error' || toast.type === 'warning'
          return (
            <motion.div
              key={toast.id}
              layout
              initial={{ opacity: 0, x: 40, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, scale: 0.95 }}
              transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
              className={`toast ${toast.type}`}
              role={isAssertive ? 'alert' : 'status'}
              aria-live={isAssertive ? 'assertive' : 'polite'}
            >
              {icons[toast.type]}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-surface-900" style={{ fontSize: '0.8125rem' }}>
                  <span className="sr-only">{typeLabels[toast.type]}: </span>
                  {toast.title}
                </p>
                {toast.message && (
                  <p className="text-surface-700 mt-0.5" style={{ fontSize: '0.75rem' }}>
                    {toast.message}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeToast(toast.id)}
                className="shrink-0 inline-flex items-center justify-center rounded text-surface-600 hover:text-surface-900 hover:bg-surface-100"
                style={{
                  width: '28px',
                  height: '28px',
                  transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
                }}
                aria-label="알림 닫기"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
