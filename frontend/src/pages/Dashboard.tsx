import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  FileText,
  Layers,
  Bot,
  Shield,
  ShieldOff,
  RefreshCw,
  Search,
  AlertOctagon,
} from 'lucide-react'
import { healthApi, adminApi, type HealthResponse, type KillSwitchStatus, type AuditEntry } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { StatusBadge, StatusDot } from '@/components/StatusBadge'
import { Modal } from '@/components/Modal'
import { SearchBar } from '@/components/SearchBar'
import { formatRelativeTime, cn } from '@/lib/utils'

const stagger = {
  container: { transition: { staggerChildren: 0.07 } },
  item: {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.3 },
  },
}

interface MetricCardProps {
  label: string
  value: string | number
  icon: React.ReactNode
  sublabel?: string
  accent?: string
}

function MetricCard({ label, value, icon, sublabel, accent }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between mb-3">
        <div
          className="w-9 h-9 rounded-md flex items-center justify-center"
          style={{ background: accent ? `${accent}20` : 'var(--color-bg-elevated)' }}
        >
          {icon}
        </div>
      </div>
      <p className="text-3xl font-mono font-bold text-surface-900 leading-none mb-1">
        {value}
      </p>
      <p className="text-xs text-surface-700 font-semibold">{label}</p>
      {sublabel && <p className="text-2xs text-surface-600 mt-0.5">{sublabel}</p>}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const toast = useToast()
  const { killSwitchActive, setKillSwitchActive, threads } = useStore()

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [killSwitch, setKillSwitch] = useState<KillSwitchStatus | null>(null)
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const [showKillModal, setShowKillModal] = useState(false)
  const [killAction, setKillAction] = useState<'activate' | 'deactivate'>('activate')
  const [killReason, setKillReason] = useState('')
  const [isKillLoading, setIsKillLoading] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [healthData, ksData, auditData] = await Promise.allSettled([
        healthApi.get(),
        adminApi.getKillSwitchStatus(),
        adminApi.getAuditLog({ limit: 10 }),
      ])

      if (healthData.status === 'fulfilled') setHealth(healthData.value)
      if (ksData.status === 'fulfilled') {
        setKillSwitch(ksData.value)
        setKillSwitchActive(ksData.value.active)
      }
      if (auditData.status === 'fulfilled') {
        setAuditLog(Array.isArray(auditData.value) ? auditData.value : [])
      }
    } catch (err) {
      console.error('Dashboard fetch error:', err)
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [setKillSwitchActive])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  async function handleKillSwitchToggle() {
    setIsKillLoading(true)
    try {
      if (killAction === 'activate') {
        const result = await adminApi.activateKillSwitch({ reason: killReason || '관리자 수동 활성화' })
        setKillSwitch(result)
        setKillSwitchActive(true)
        toast.error('킬 스위치 활성화', '에이전트 응답이 차단되었습니다.')
      } else {
        const result = await adminApi.deactivateKillSwitch()
        setKillSwitch(result)
        setKillSwitchActive(false)
        toast.success('킬 스위치 해제', '시스템이 정상 운영 모드로 복귀했습니다.')
      }
    } catch (err) {
      toast.error('작업 실패', String(err))
    } finally {
      setIsKillLoading(false)
      setShowKillModal(false)
      setKillReason('')
    }
  }

  function handleRefresh() {
    setIsRefreshing(true)
    fetchData()
    toast.info('새로고침', '대시보드 데이터를 갱신합니다.')
  }

  const isHealthy = health?.status === 'ok' || health?.status === 'healthy'
  const totalThreads = threads.length

  return (
    <div className="p-3 sm:p-6 space-y-6">
      {/* Top bar */}
      <div className="flex items-center gap-4">
        <SearchBar
          className="flex-1 max-w-lg"
          placeholder="전체 검색... (/ 키)"
          autoNavigate
        />
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="btn-secondary flex items-center gap-1.5"
        >
          <RefreshCw size={13} className={cn(isRefreshing && 'animate-spin')} />
          새로고침
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-28 rounded-md" />
          ))}
        </div>
      ) : (
        <>
          {/* Metric cards */}
          <motion.div
            className="grid grid-cols-2 lg:grid-cols-4 gap-4"
            variants={stagger.container}
            initial="initial"
            animate="animate"
          >
            <motion.div {...stagger.item}>
              <MetricCard
                label="시스템 상태"
                value={isHealthy ? '정상' : '오류'}
                sublabel={health ? `v${health.version ?? '—'}` : '연결 실패'}
                icon={<Activity size={18} className={isHealthy ? 'text-status-success' : 'text-status-error'} />}
                accent={isHealthy ? '#3fb950' : '#f85149'}
              />
            </motion.div>
            <motion.div {...stagger.item}>
              <MetricCard
                label="에이전트 세션"
                value={totalThreads}
                sublabel="총 대화 스레드"
                icon={<Bot size={18} className="text-slate-data" />}
                accent="#4a9eff"
              />
            </motion.div>
            <motion.div {...stagger.item}>
              <MetricCard
                label="감사 로그"
                value={auditLog.length}
                sublabel="최근 기록 수"
                icon={<Layers size={18} className="text-gold-500" />}
                accent="#F37021"
              />
            </motion.div>
            <motion.div {...stagger.item}>
              <MetricCard
                label="킬 스위치"
                value={killSwitchActive ? '활성' : '해제'}
                sublabel={killSwitch?.reason ?? '대기 중'}
                icon={killSwitchActive ? <ShieldOff size={18} className="text-status-error" /> : <Shield size={18} className="text-status-success" />}
                accent={killSwitchActive ? '#f85149' : '#3fb950'}
              />
            </motion.div>
          </motion.div>

          {/* Status panel + Kill switch */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
            {/* System Status */}
            <motion.div
              className="col-span-2 panel p-5"
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-display font-semibold text-surface-900">시스템 상태</h2>
                <StatusBadge status={isHealthy ? 'healthy' : 'error'} />
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between py-2 border-b border-surface-300">
                  <div className="flex items-center gap-2">
                    <StatusDot status={isHealthy ? 'active' : 'error'} />
                    <span className="text-sm text-surface-800">API 서버</span>
                  </div>
                  <span className="font-mono text-xs text-surface-700">
                    {health?.status ?? '연결 실패'}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-surface-300">
                  <div className="flex items-center gap-2">
                    <StatusDot status={killSwitchActive ? 'error' : 'active'} />
                    <span className="text-sm text-surface-800">에이전트 엔진</span>
                  </div>
                  <span className="font-mono text-xs text-surface-700">
                    {killSwitchActive ? '차단됨' : '운영 중'}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <StatusDot status="active" />
                    <span className="text-sm text-surface-800">벡터 DB (ChromaDB)</span>
                  </div>
                  <span className="font-mono text-xs text-surface-700">연결됨</span>
                </div>
              </div>

              {health && Object.keys(health).length > 1 && (
                <div className="mt-4 pt-3 border-t border-surface-300">
                  <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-2">
                    추가 정보
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(health)
                      .filter(([k]) => k !== 'status')
                      .slice(0, 4)
                      .map(([key, val]) => (
                        <div key={key} className="flex gap-2 text-xs">
                          <span className="font-mono text-surface-600">{key}:</span>
                          <span className="text-surface-800 truncate">{String(val)}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </motion.div>

            {/* Kill Switch Panel */}
            <motion.div
              className={cn('panel p-5 flex flex-col', killSwitchActive && 'kill-switch-active')}
              style={killSwitchActive ? { borderColor: 'rgba(248, 81, 73, 0.5)' } : {}}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.25 }}
            >
              <div className="flex items-center gap-2 mb-4">
                {killSwitchActive ? (
                  <AlertOctagon size={16} className="text-status-error" />
                ) : (
                  <Shield size={16} className="text-status-success" />
                )}
                <h2 className="font-display font-semibold text-surface-900">킬 스위치</h2>
              </div>

              <div className="flex-1 space-y-3">
                <div className="rounded-md p-3" style={{ background: 'var(--color-bg-elevated)' }}>
                  <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">
                    상태
                  </p>
                  <p className={cn('text-lg font-mono font-bold', killSwitchActive ? 'text-status-error' : 'text-status-success')}>
                    {killSwitchActive ? '● 활성화됨' : '○ 비활성'}
                  </p>
                </div>

                {killSwitch?.reason && (
                  <div className="rounded-md p-3" style={{ background: 'var(--color-bg-elevated)' }}>
                    <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">
                      사유
                    </p>
                    <p className="text-xs text-surface-800">{killSwitch.reason}</p>
                  </div>
                )}

                {killSwitch?.activated_at && (
                  <div className="rounded-md p-3" style={{ background: 'var(--color-bg-elevated)' }}>
                    <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">
                      활성화 시각
                    </p>
                    <p className="text-xs font-mono text-surface-800">
                      {formatRelativeTime(killSwitch.activated_at)}
                    </p>
                  </div>
                )}
              </div>

              <div className="gold-divider my-4" />

              <button
                className={cn(
                  killSwitchActive ? 'btn-secondary' : 'btn-danger',
                  'w-full flex items-center justify-center gap-2',
                )}
                onClick={() => {
                  setKillAction(killSwitchActive ? 'deactivate' : 'activate')
                  setShowKillModal(true)
                }}
              >
                {killSwitchActive ? (
                  <>
                    <Shield size={14} />
                    킬 스위치 해제
                  </>
                ) : (
                  <>
                    <ShieldOff size={14} />
                    킬 스위치 활성화
                  </>
                )}
              </button>
            </motion.div>
          </div>

          {/* Recent Audit Log */}
          <motion.div
            className="panel"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-surface-300">
              <h2 className="font-display font-semibold text-surface-900">최근 감사 로그</h2>
              <button
                className="text-xs text-gold-500 hover:text-gold-400 transition-colors"
                onClick={() => navigate('/admin')}
              >
                전체 보기 →
              </button>
            </div>

            {auditLog.length === 0 ? (
              <div className="px-5 py-10 text-center">
                <FileText size={28} className="text-surface-600 mx-auto mb-2" />
                <p className="text-sm text-surface-700">감사 로그가 없습니다</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>시각</th>
                      <th>사용자</th>
                      <th>스킬 / 액션</th>
                      <th>쿼리</th>
                      <th>상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLog.slice(0, 10).map((entry, i) => (
                      <motion.tr
                        key={entry.id ?? i}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: i * 0.04 }}
                      >
                        <td className="whitespace-nowrap">{formatRelativeTime(entry.timestamp)}</td>
                        <td>
                          <span className="tag tag-blue">{entry.user_id}</span>
                        </td>
                        <td className="text-surface-800">{entry.skill ?? entry.action ?? '—'}</td>
                        <td className="max-w-xs truncate text-surface-700">
                          {entry.query ?? entry.detail ?? '—'}
                        </td>
                        <td>
                          <StatusBadge status={entry.status} />
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>

          {/* Quick links */}
          <motion.div
            className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            {[
              { label: '새 에이전트 쿼리', desc: '에이전트 콘솔 시작', to: '/agent', icon: <Bot size={16} className="text-slate-data" /> },
              { label: '문서 검색', desc: '시맨틱 벡터 검색', to: '/search', icon: <Search size={16} className="text-gold-500" /> },
              { label: '문서 업로드', desc: '신규 파일 인제스트', to: '/ingest', icon: <FileText size={16} className="text-status-success" /> },
            ].map((item) => (
              <button
                key={item.to}
                onClick={() => navigate(item.to)}
                className="card p-4 text-left flex items-center gap-3"
              >
                <div className="w-9 h-9 rounded-md bg-surface-200 flex items-center justify-center shrink-0">
                  {item.icon}
                </div>
                <div>
                  <p className="text-sm font-semibold text-surface-900">{item.label}</p>
                  <p className="text-xs text-surface-600">{item.desc}</p>
                </div>
              </button>
            ))}
          </motion.div>
        </>
      )}

      {/* Kill Switch Confirmation Modal */}
      <Modal
        isOpen={showKillModal}
        onClose={() => {
          setShowKillModal(false)
          setKillReason('')
        }}
        onConfirm={handleKillSwitchToggle}
        title={killAction === 'activate' ? '킬 스위치 활성화' : '킬 스위치 해제'}
        confirmLabel={killAction === 'activate' ? '활성화' : '해제'}
        variant={killAction === 'activate' ? 'danger' : 'default'}
        isLoading={isKillLoading}
      >
        <p className="text-sm text-surface-700 mb-4">
          {killAction === 'activate'
            ? '킬 스위치를 활성화하면 모든 에이전트 응답이 즉시 차단됩니다. 계속하시겠습니까?'
            : '킬 스위치를 해제하면 에이전트가 정상 운영 모드로 복귀합니다.'}
        </p>
        {killAction === 'activate' && (
          <div>
            <label className="text-xs text-surface-700 font-semibold block mb-1.5">
              활성화 사유 (선택)
            </label>
            <input
              type="text"
              value={killReason}
              onChange={(e) => setKillReason(e.target.value)}
              placeholder="예: 보안 위협 감지"
              className="input-field"
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
