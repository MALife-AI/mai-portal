import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shield,
  ShieldOff,
  Users,
  FileText,
  Activity,
  RefreshCw,
  AlertOctagon,
  ChevronDown,
  ChevronRight,
  Search,
  Download,
  Edit3,
  Save,
  X,
  Loader2,
} from 'lucide-react'
import {
  adminApi,
  type IamConfig,
  type AuditEntry,
  type KillSwitchStatus,
} from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { StatusBadge } from '@/components/StatusBadge'
import { Modal } from '@/components/Modal'
import { formatDate, formatRelativeTime, cn } from '@/lib/utils'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

type AdminTab = 'iam' | 'audit' | 'system'

// ─── IAM Tab ──────────────────────────────────────────────────────────────────

function IamTab({ config, onUpdate }: { config: IamConfig | null; onUpdate: () => void }) {
  const toast = useToast()
  const [isEditing, setIsEditing] = useState(false)
  const [yamlText, setYamlText] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [expandedUser, setExpandedUser] = useState<string | null>(null)

  useEffect(() => {
    if (config) {
      setYamlText(JSON.stringify(config, null, 2))
    }
  }, [config])

  async function handleSave() {
    setIsSaving(true)
    try {
      let parsed: IamConfig
      try {
        parsed = JSON.parse(yamlText) as IamConfig
      } catch {
        toast.error('파싱 오류', 'JSON 형식이 올바르지 않습니다.')
        return
      }
      await adminApi.updateIam(parsed)
      toast.success('IAM 설정 저장', '권한 구성이 업데이트되었습니다.')
      setIsEditing(false)
      onUpdate()
    } catch (err) {
      toast.error('저장 실패', String(err))
    } finally {
      setIsSaving(false)
    }
  }

  const users = config?.users ? Object.entries(config.users) : []
  const roles = config?.roles ? Object.entries(config.roles) : []

  return (
    <div className="space-y-4">
      {/* Users */}
      <div className="panel">
        <div
          className="flex items-center justify-between px-5 py-3"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="flex items-center gap-2">
            <Users size={15} className="text-gold-500" />
            <h3 className="font-semibold text-surface-900">사용자 목록</h3>
            <span className="tag tag-blue">{users.length}</span>
          </div>
        </div>

        {users.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-surface-600">사용자 없음</div>
        ) : (
          <div className="divide-y divide-surface-300">
            {users.map(([userId, userData]) => {
              const userRoles = userData?.roles ?? []
              const workspace = userData?.workspace ?? '—'
              const isExpanded = expandedUser === userId

              return (
                <div key={userId}>
                  <button
                    className="w-full flex items-center gap-3 px-5 py-3 hover:bg-surface-100 transition-colors"
                    onClick={() => setExpandedUser(isExpanded ? null : userId)}
                  >
                    <div
                      className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
                      style={{ background: 'rgba(243, 112, 33, 0.15)', border: '1px solid rgba(243, 112, 33, 0.25)' }}
                    >
                      <span className="text-2xs font-mono font-bold text-gold-500">
                        {userId.slice(0, 2).toUpperCase()}
                      </span>
                    </div>
                    <div className="flex-1 text-left">
                      <p className="text-sm font-semibold text-surface-900 font-mono">{userId}</p>
                      <p className="text-2xs text-surface-600">워크스페이스: {workspace}</p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {userRoles.map((role) => (
                        <span key={role} className="tag tag-gold">{role}</span>
                      ))}
                    </div>
                    {isExpanded ? (
                      <ChevronDown size={13} className="text-surface-600" />
                    ) : (
                      <ChevronRight size={13} className="text-surface-600" />
                    )}
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        style={{ overflow: 'hidden' }}
                      >
                        <div
                          className="px-5 py-3"
                          style={{ background: 'var(--color-bg-elevated)', borderTop: '1px solid var(--color-border)' }}
                        >
                          <div className="grid grid-cols-2 gap-3 text-xs">
                            <div>
                              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">역할</p>
                              <div className="flex flex-wrap gap-1">
                                {userRoles.map((r) => <span key={r} className="tag tag-gold">{r}</span>)}
                              </div>
                            </div>
                            <div>
                              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">워크스페이스</p>
                              <p className="font-mono text-surface-800">{workspace}</p>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Roles */}
      {roles.length > 0 && (
        <div className="panel">
          <div
            className="flex items-center gap-2 px-5 py-3"
            style={{ borderBottom: '1px solid var(--color-border)' }}
          >
            <Shield size={15} className="text-gold-500" />
            <h3 className="font-semibold text-surface-900">역할 정의</h3>
          </div>
          <div className="divide-y divide-surface-300">
            {roles.map(([roleName, roleDef]) => (
              <div key={roleName} className="px-5 py-3">
                <p className="text-sm font-mono font-semibold text-gold-500 mb-2">{roleName}</p>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  {roleDef && 'read' in roleDef && Array.isArray(roleDef.read) && (
                    <div>
                      <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">읽기 경로</p>
                      {(roleDef.read as string[]).map((p) => (
                        <p key={p} className="font-mono text-surface-700">{p}</p>
                      ))}
                    </div>
                  )}
                  {roleDef && 'write' in roleDef && Array.isArray(roleDef.write) && (
                    <div>
                      <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1">쓰기 경로</p>
                      {(roleDef.write as string[]).map((p) => (
                        <p key={p} className="font-mono text-surface-700">{p}</p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* JSON Editor */}
      <div className="panel">
        <div
          className="flex items-center justify-between px-5 py-3"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="flex items-center gap-2">
            <FileText size={15} className="text-gold-500" />
            <h3 className="font-semibold text-surface-900">JSON 원본</h3>
          </div>
          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <button
                  onClick={() => setIsEditing(false)}
                  className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
                >
                  <X size={12} />취소
                </button>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="btn-primary flex items-center gap-1.5 text-xs py-1.5"
                >
                  {isSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  저장
                </button>
              </>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
              >
                <Edit3 size={12} />
                편집
              </button>
            )}
          </div>
        </div>
        <div className="p-3">
          <textarea
            value={yamlText}
            onChange={(e) => setYamlText(e.target.value)}
            readOnly={!isEditing}
            rows={20}
            className="w-full font-mono text-xs text-surface-800 resize-none focus:outline-none rounded-md p-3"
            style={{
              background: 'var(--color-bg-primary)',
              border: '1px solid var(--color-border)',
              lineHeight: '1.6',
            }}
            spellCheck={false}
          />
        </div>
      </div>
    </div>
  )
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────

function AuditTab({ entries }: { entries: AuditEntry[] }) {
  const [filterUser, setFilterUser] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const filtered = entries.filter((e) => {
    if (filterUser && e.user_id !== filterUser) return false
    if (filterStatus && e.status.toLowerCase() !== filterStatus.toLowerCase()) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (
        e.user_id.toLowerCase().includes(q) ||
        (e.skill ?? '').toLowerCase().includes(q) ||
        (e.action ?? '').toLowerCase().includes(q) ||
        (e.query ?? '').toLowerCase().includes(q) ||
        e.status.toLowerCase().includes(q)
      )
    }
    return true
  })

  // Skills usage chart
  const skillCounts: Record<string, number> = {}
  for (const e of entries) {
    const skill = e.skill ?? e.action ?? '기타'
    skillCounts[skill] = (skillCounts[skill] ?? 0) + 1
  }
  const chartData = Object.entries(skillCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, count]) => ({ name, count }))

  const uniqueUsers = [...new Set(entries.map((e) => e.user_id))]
  const statuses = [...new Set(entries.map((e) => e.status))]

  function exportCsv() {
    const header = ['timestamp', 'user_id', 'skill', 'query', 'status'].join(',')
    const rows = filtered.map((e) =>
      [e.timestamp, e.user_id, e.skill ?? '', e.query ?? '', e.status]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(','),
    )
    const csv = [header, ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit_log_${new Date().toISOString().split('T')[0] ?? 'export'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      {/* Chart */}
      {chartData.length > 0 && (
        <div className="panel p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={15} className="text-gold-500" />
            <h3 className="font-semibold text-surface-900">스킬 사용 현황</h3>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} barCategoryGap="30%">
              <XAxis
                dataKey="name"
                tick={{ fill: '#9198a1', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#9198a1', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  background: '#1c2128',
                  border: '1px solid #30363d',
                  borderRadius: 4,
                  fontSize: 12,
                  fontFamily: 'JetBrains Mono',
                }}
                labelStyle={{ color: '#F37021' }}
                itemStyle={{ color: '#adbac7' }}
              />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell
                    key={i}
                    fill={i === 0 ? '#F37021' : i === 1 ? '#d95e15' : '#484f58'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Filters */}
      <div className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-surface-600" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="검색..."
              className="input-field pl-8 w-48"
              style={{ paddingLeft: '2rem' }}
            />
          </div>
          <select
            value={filterUser}
            onChange={(e) => setFilterUser(e.target.value)}
            className="input-field w-36"
            style={{ paddingLeft: '0.75rem' }}
          >
            <option value="">전체 사용자</option>
            {uniqueUsers.map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="input-field w-32"
            style={{ paddingLeft: '0.75rem' }}
          >
            <option value="">전체 상태</option>
            {statuses.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <span className="text-2xs font-mono text-surface-600 ml-auto">
            {filtered.length}/{entries.length}개
          </span>
          <button
            onClick={exportCsv}
            className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
          >
            <Download size={12} />
            CSV 내보내기
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>시각</th>
                <th>사용자</th>
                <th>스킬/액션</th>
                <th>쿼리</th>
                <th>상태</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-surface-600">
                    로그 없음
                  </td>
                </tr>
              ) : (
                filtered.map((entry, i) => (
                  <motion.tr
                    key={entry.id ?? i}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(i * 0.02, 0.3) }}
                  >
                    <td className="whitespace-nowrap">
                      <span title={formatDate(entry.timestamp)}>
                        {formatRelativeTime(entry.timestamp)}
                      </span>
                    </td>
                    <td>
                      <span className="tag tag-blue">{entry.user_id}</span>
                    </td>
                    <td className="font-mono">{entry.skill ?? entry.action ?? '—'}</td>
                    <td className="max-w-xs">
                      <span className="truncate block" title={entry.query ?? entry.detail ?? ''}>
                        {entry.query ?? entry.detail ?? '—'}
                      </span>
                    </td>
                    <td><StatusBadge status={entry.status} /></td>
                    <td className="text-surface-600 max-w-[120px] truncate">
                      {entry.detail ?? '—'}
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─── System Tab ───────────────────────────────────────────────────────────────

function SystemTab({
  killSwitch,
  onRefresh,
}: {
  killSwitch: KillSwitchStatus | null
  onRefresh: () => void
}) {
  const toast = useToast()
  const { setKillSwitchActive } = useStore()
  const [showKillModal, setShowKillModal] = useState(false)
  const [killAction, setKillAction] = useState<'activate' | 'deactivate'>('activate')
  const [killReason, setKillReason] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const isActive = killSwitch?.active ?? false

  async function handleKillSwitch() {
    setIsLoading(true)
    try {
      if (killAction === 'activate') {
        await adminApi.activateKillSwitch({ reason: killReason || '관리자 수동 활성화' })
        setKillSwitchActive(true)
        toast.error('킬 스위치 활성화', '에이전트 응답이 차단되었습니다.')
      } else {
        await adminApi.deactivateKillSwitch()
        setKillSwitchActive(false)
        toast.success('킬 스위치 해제', '시스템이 정상 운영 모드로 복귀했습니다.')
      }
      onRefresh()
    } catch (err) {
      toast.error('작업 실패', String(err))
    } finally {
      setIsLoading(false)
      setShowKillModal(false)
      setKillReason('')
    }
  }

  return (
    <div className="space-y-4 max-w-2xl">
      {/* Kill Switch */}
      <div
        className={cn('panel p-5', isActive && 'kill-switch-active')}
        style={isActive ? { borderColor: 'rgba(248, 81, 73, 0.5)' } : {}}
      >
        <div className="flex items-center gap-2 mb-5">
          {isActive ? (
            <AlertOctagon size={18} className="text-status-error" />
          ) : (
            <Shield size={18} className="text-status-success" />
          )}
          <h3 className="font-display font-semibold text-surface-900">킬 스위치 제어</h3>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-5">
          <div
            className="rounded-md p-3"
            style={{ background: 'var(--color-bg-elevated)' }}
          >
            <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1.5">현재 상태</p>
            <p className={cn('text-2xl font-mono font-bold', isActive ? 'text-status-error' : 'text-status-success')}>
              {isActive ? '활성화됨' : '비활성'}
            </p>
          </div>
          {killSwitch?.activated_at && (
            <div
              className="rounded-md p-3"
              style={{ background: 'var(--color-bg-elevated)' }}
            >
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1.5">활성화 시각</p>
              <p className="text-sm font-mono text-surface-800">{formatDate(killSwitch.activated_at)}</p>
            </div>
          )}
          {killSwitch?.reason && (
            <div
              className="rounded-md p-3 col-span-2"
              style={{ background: 'var(--color-bg-elevated)' }}
            >
              <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-1.5">사유</p>
              <p className="text-sm text-surface-800">{killSwitch.reason}</p>
            </div>
          )}
        </div>

        <div className="gold-divider mb-4" />

        <div className="flex gap-3">
          <button
            className={cn(
              'flex-1 py-2.5 rounded-md flex items-center justify-center gap-2 font-semibold text-sm transition-all',
              isActive
                ? 'btn-secondary'
                : 'btn-danger',
            )}
            onClick={() => {
              setKillAction(isActive ? 'deactivate' : 'activate')
              setShowKillModal(true)
            }}
          >
            {isActive ? <Shield size={15} /> : <ShieldOff size={15} />}
            {isActive ? '킬 스위치 해제' : '킬 스위치 활성화'}
          </button>
        </div>
      </div>

      {/* System Info */}
      <div className="panel p-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity size={15} className="text-gold-500" />
          <h3 className="font-semibold text-surface-900">시스템 구성</h3>
        </div>
        <div className="space-y-2">
          {[
            { label: '벡터 DB', value: 'ChromaDB (로컬)' },
            { label: '체크포인터', value: 'SQLite (LangGraph)' },
            { label: '오케스트레이터', value: 'LangGraph StateGraph' },
            { label: 'VLM 모델', value: 'gpt-4o-mini' },
            { label: '임베딩', value: 'OpenAI text-embedding-3-small' },
            { label: 'ACL 엔진', value: 'ChromaDB $or 필터' },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="flex items-center justify-between py-2 border-b border-surface-300"
            >
              <span className="text-sm text-surface-700">{label}</span>
              <span className="text-xs font-mono text-surface-800">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Kill Switch Modal */}
      <Modal
        isOpen={showKillModal}
        onClose={() => { setShowKillModal(false); setKillReason('') }}
        onConfirm={handleKillSwitch}
        title={killAction === 'activate' ? '킬 스위치 활성화' : '킬 스위치 해제'}
        confirmLabel={killAction === 'activate' ? '활성화' : '해제'}
        variant={killAction === 'activate' ? 'danger' : 'default'}
        isLoading={isLoading}
      >
        <p className="text-sm text-surface-700 mb-4">
          {killAction === 'activate'
            ? '킬 스위치를 활성화하면 모든 에이전트 응답이 즉시 차단됩니다.'
            : '킬 스위치를 해제하면 에이전트가 정상 운영 모드로 복귀합니다.'}
        </p>
        {killAction === 'activate' && (
          <div>
            <label className="text-xs font-semibold text-surface-700 block mb-1.5">
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

// ─── Main Admin Page ──────────────────────────────────────────────────────────

export default function Admin() {
  const [activeTab, setActiveTab] = useState<AdminTab>('iam')
  const [iamConfig, setIamConfig] = useState<IamConfig | null>(null)
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([])
  const [killSwitch, setKillSwitch] = useState<KillSwitchStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const toast = useToast()

  const fetchAll = useCallback(async () => {
    try {
      const [iamResult, auditResult, ksResult] = await Promise.allSettled([
        adminApi.getIam(),
        adminApi.getAuditLog({ limit: 200 }),
        adminApi.getKillSwitchStatus(),
      ])
      if (iamResult.status === 'fulfilled') setIamConfig(iamResult.value)
      if (auditResult.status === 'fulfilled') setAuditLog(Array.isArray(auditResult.value) ? auditResult.value : [])
      if (ksResult.status === 'fulfilled') setKillSwitch(ksResult.value)
    } catch (err) {
      toast.error('데이터 로드 실패', String(err))
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  const TABS: { id: AdminTab; label: string; icon: React.ReactNode }[] = [
    { id: 'iam', label: 'IAM', icon: <Users size={14} /> },
    { id: 'audit', label: '감사 로그', icon: <FileText size={14} /> },
    { id: 'system', label: '시스템', icon: <Activity size={14} /> },
  ]

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">관리 패널</h2>
          <p className="text-sm text-surface-600">
            IAM 권한 관리, 감사 로그, 시스템 제어를 수행합니다.
          </p>
        </div>
        <button
          onClick={() => { setIsRefreshing(true); fetchAll() }}
          disabled={isRefreshing}
          className="btn-secondary flex items-center gap-1.5"
        >
          <RefreshCw size={13} className={cn(isRefreshing && 'animate-spin')} />
          새로고침
        </button>
      </div>

      {/* Tabs */}
      <div
        className="flex items-center gap-1 p-1 rounded-lg"
        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', width: 'fit-content' }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-semibold transition-all',
              activeTab === tab.id
                ? 'bg-gold-500/20 text-gold-500'
                : 'text-surface-700 hover:text-surface-900 hover:bg-surface-200',
            )}
          >
            {tab.icon}
            {tab.label}
            {tab.id === 'audit' && auditLog.length > 0 && (
              <span className="tag tag-blue py-0 px-1.5 text-2xs">{auditLog.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-32 rounded-md" />
          ))}
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {activeTab === 'iam' && (
              <IamTab config={iamConfig} onUpdate={fetchAll} />
            )}
            {activeTab === 'audit' && (
              <AuditTab entries={auditLog} />
            )}
            {activeTab === 'system' && (
              <SystemTab killSwitch={killSwitch} onRefresh={fetchAll} />
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  )
}
