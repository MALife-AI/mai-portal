import { AnimatePresence, motion } from 'framer-motion'
import { X, AlertTriangle } from 'lucide-react'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm?: () => void
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'default' | 'danger'
  children?: React.ReactNode
  isLoading?: boolean
}

export function Modal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = '확인',
  cancelLabel = '취소',
  variant = 'default',
  children,
  isLoading = false,
}: ModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={(e) => {
            if (e.target === e.currentTarget) onClose()
          }}
        >
          <motion.div
            className="modal-box"
            initial={{ opacity: 0, scale: 0.92, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 16 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-2.5">
                {variant === 'danger' && (
                  <AlertTriangle size={18} className="text-status-error shrink-0" />
                )}
                <h2 className="font-display font-semibold text-surface-900" style={{ fontSize: '1rem' }}>
                  {title}
                </h2>
              </div>
              <button
                onClick={onClose}
                className="text-surface-600 hover:text-surface-900 transition-colors ml-4"
              >
                <X size={16} />
              </button>
            </div>

            {/* Body */}
            {message && (
              <p className="text-surface-700 text-sm mb-5 leading-relaxed">{message}</p>
            )}
            {children && <div className="mb-5">{children}</div>}

            {/* Divider */}
            <div className="gold-divider mb-4" />

            {/* Actions */}
            {onConfirm && (
              <div className="flex items-center justify-end gap-2.5">
                <button className="btn-secondary" onClick={onClose} disabled={isLoading}>
                  {cancelLabel}
                </button>
                <button
                  className={variant === 'danger' ? 'btn-danger' : 'btn-primary'}
                  onClick={onConfirm}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <span className="flex items-center gap-1.5">
                      <span
                        className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"
                      />
                      처리 중...
                    </span>
                  ) : (
                    confirmLabel
                  )}
                </button>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
