import { AnimatePresence, motion } from 'framer-motion'
import { X, AlertTriangle } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'

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

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

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
  const boxRef = useRef<HTMLDivElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const descId = useId()

  // Escape 닫기 + focus trap + 이전 포커스 복원
  useEffect(() => {
    if (!isOpen) return
    previouslyFocused.current = document.activeElement as HTMLElement | null

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isLoading) {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === 'Tab' && boxRef.current) {
        const focusables = Array.from(
          boxRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
        )
        if (focusables.length === 0) return
        const first = focusables[0]!
        const last = focusables[focusables.length - 1]!
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    // 자동 포커스: 첫 번째 포커스 가능한 요소
    requestAnimationFrame(() => {
      const focusables = boxRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE)
      focusables?.[0]?.focus()
    })

    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      previouslyFocused.current?.focus?.()
    }
  }, [isOpen, isLoading, onClose])

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !isLoading) onClose()
          }}
        >
          <motion.div
            ref={boxRef}
            className="modal-box"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={message ? descId : undefined}
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-2.5">
                {variant === 'danger' && (
                  <AlertTriangle size={18} className="text-status-error shrink-0" aria-hidden="true" />
                )}
                <h2
                  id={titleId}
                  className="font-display font-semibold text-surface-900"
                  style={{ fontSize: '1rem' }}
                >
                  {title}
                </h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                disabled={isLoading}
                className="inline-flex items-center justify-center rounded-md text-surface-600 hover:text-surface-900 hover:bg-surface-100 disabled:opacity-50 disabled:cursor-not-allowed ml-4"
                style={{
                  width: '32px',
                  height: '32px',
                  transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
                }}
                aria-label="닫기"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>

            {/* Body */}
            {message && (
              <p id={descId} className="text-surface-700 text-sm mb-5 leading-relaxed">
                {message}
              </p>
            )}
            {children && <div className="mb-5">{children}</div>}

            {/* Divider */}
            <div className="gold-divider mb-4" role="presentation" />

            {/* Actions */}
            {onConfirm && (
              <div className="flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={onClose}
                  disabled={isLoading}
                >
                  {cancelLabel}
                </button>
                <button
                  type="button"
                  className={variant === 'danger' ? 'btn-danger' : 'btn-primary'}
                  onClick={onConfirm}
                  disabled={isLoading}
                  aria-busy={isLoading}
                >
                  {isLoading ? (
                    <span className="flex items-center gap-1.5">
                      <span
                        className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"
                        aria-hidden="true"
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
