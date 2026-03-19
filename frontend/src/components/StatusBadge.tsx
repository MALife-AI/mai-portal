import { cn } from '@/lib/utils'

interface StatusBadgeProps {
  status: string
  className?: string
}

function normalizeStatus(status: string): 'success' | 'error' | 'warning' | 'info' | 'neutral' {
  const s = status.toLowerCase()
  if (['success', 'ok', 'healthy', 'active', 'done', 'completed', '성공'].includes(s)) return 'success'
  if (['error', 'fail', 'failed', 'critical', '실패', '오류'].includes(s)) return 'error'
  if (['warning', 'warn', 'degraded', '경고'].includes(s)) return 'warning'
  if (['info', 'running', 'processing', '처리중', '진행중'].includes(s)) return 'info'
  return 'neutral'
}

const statusLabels: Record<string, string> = {
  success: '성공',
  ok: 'OK',
  healthy: '정상',
  active: '활성',
  done: '완료',
  completed: '완료',
  error: '오류',
  fail: '실패',
  failed: '실패',
  critical: '위험',
  warning: '경고',
  warn: '경고',
  degraded: '저하',
  info: '정보',
  running: '실행중',
  processing: '처리중',
  neutral: '알 수 없음',
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const normalized = normalizeStatus(status)
  const label = statusLabels[status.toLowerCase()] ?? status

  const classes: Record<typeof normalized, string> = {
    success: 'tag tag-success',
    error: 'tag tag-error',
    warning: 'tag tag-warning',
    info: 'tag tag-blue',
    neutral: 'tag',
  }

  return (
    <span className={cn(classes[normalized], className)}>
      {label}
    </span>
  )
}

interface StatusDotProps {
  status: 'active' | 'error' | 'warning' | 'neutral'
  className?: string
}

export function StatusDot({ status, className }: StatusDotProps) {
  return <span className={cn('status-dot', status, className)} />
}
