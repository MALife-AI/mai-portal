import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react'
import { useStore } from '@/store/useStore'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

const icons: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle2 size={16} className="text-status-success shrink-0 mt-0.5" />,
  error: <XCircle size={16} className="text-status-error shrink-0 mt-0.5" />,
  warning: <AlertTriangle size={16} className="text-status-warning shrink-0 mt-0.5" />,
  info: <Info size={16} className="text-slate-data shrink-0 mt-0.5" />,
}

export function ToastContainer() {
  const toasts = useStore((s) => s.toasts)
  const removeToast = useStore((s) => s.removeToast)

  return (
    <div className="toast-container">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, x: 60, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className={`toast ${toast.type}`}
          >
            {icons[toast.type]}
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-surface-900" style={{ fontSize: '0.8125rem' }}>
                {toast.title}
              </p>
              {toast.message && (
                <p className="text-surface-700 mt-0.5" style={{ fontSize: '0.75rem' }}>
                  {toast.message}
                </p>
              )}
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="shrink-0 text-surface-600 hover:text-surface-900 transition-colors"
            >
              <X size={14} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
