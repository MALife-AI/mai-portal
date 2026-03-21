import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Shield, ShieldOff, Users, Activity, Settings2, FileText,
  Server, Eye, CheckCircle2, XCircle, AlertTriangle,
  Loader2, RefreshCw, Save, Cpu, HardDrive, Gauge,
} from 'lucide-react'
import { adminApi, type IamConfig, type KillSwitchStatus } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { cn } from '@/lib/utils'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie,
} from 'recharts'

const API = ''
function uid() { try { return localStorage.getItem('malife_user_id') ?? 'admin01' } catch { return 'admin01' } }
async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, { ...opts, headers: { 'X-User-Id': uid(), 'Content-Type': 'application/json', ...opts.headers } })
  return r.json()
}

type Tab = 'overview' | 'iam' | 'model' | 'metrics' | 'governance' | 'infra'

// ─── Overview ────────────────────────────────────────────────────────────────

function OverviewTab() {
  const [ks, setKs] = useState<KillSwitchStatus | null>(null)
  const [metrics, setMetrics] = useState<any>(null)
  const [governance, setGovernance] = useState<any>(null)
  const toast = useToast()

  useEffect(() => {
    adminApi.killSwitchStatus().then(setKs)
    api('/api/v1/admin/metrics').then(setMetrics)
    api('/api/v1/admin/governance').then(setGovernance)
  }, [])

  async function toggleKillSwitch() {
    if (ks?.active) {
      await adminApi.deactivateKillSwitch()
      toast.success('킬 스위치 해제', '')
    } else {
      await adminApi.activateKillSwitch({ reason: '관리자 수동 활성화' })
      toast.error('킬 스위치 활성화', '모든 에이전트 중단')
    }
    setKs(await adminApi.killSwitchStatus())
  }

  const stats = [
    { label: '총 쿼리', value: metrics?.total_queries ?? '-', icon: Activity, color: '#4A90D9' },
    { label: 'Vault 문서', value: metrics?.vault_files ?? '-', icon: FileText, color: '#34C759' },
    { label: '그래프 노드', value: metrics?.graph_stats?.node_count ?? '-', icon: Gauge, color: '#F37021' },
    { label: '에러율', value: metrics?.error_rate != null ? `${metrics.error_rate}%` : '-', icon: AlertTriangle, color: '#FF3B30' },
  ]

  return (
    <div className="space-y-6">
      {/* Kill Switch */}
      <div className={cn('panel p-4 flex items-center justify-between', ks?.active && 'border-status-error/50')}>
        <div className="flex items-center gap-3">
          {ks?.active ? <ShieldOff size={20} className="text-status-error" /> : <Shield size={20} className="text-status-success" />}
          <div>
            <p className="text-sm font-semibold text-surface-900">킬 스위치</p>
            <p className="text-2xs text-surface-600">{ks?.active ? '활성화 — 모든 에이전트 중단됨' : '비활성화 — 정상 운영 중'}</p>
          </div>
        </div>
        <button onClick={toggleKillSwitch} className={cn('btn-secondary text-xs', ks?.active ? 'text-status-success' : 'text-status-error')}>
          {ks?.active ? '해제' : '활성화'}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="panel p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon size={14} style={{ color }} />
              <span className="text-2xs font-mono text-surface-600 uppercase">{label}</span>
            </div>
            <p className="text-xl font-display font-bold text-surface-900">{value}</p>
          </div>
        ))}
      </div>

      {/* Compliance Quick View */}
      {governance?.checklist && (
        <div className="panel p-4">
          <p className="text-xs font-semibold text-surface-800 mb-3">컴플라이언스 체크리스트</p>
          <div className="grid grid-cols-2 gap-2">
            {governance.checklist.map((c: any) => (
              <div key={c.item} className="flex items-center gap-2 text-xs">
                {c.status ? <CheckCircle2 size={12} className="text-status-success" /> : <XCircle size={12} className="text-status-error" />}
                <span className="text-surface-800">{c.item}</span>
                <span className="text-2xs text-surface-600 ml-auto">{c.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── IAM ─────────────────────────────────────────────────────────────────────

function IamTab() {
  const [users, setUsers] = useState<any[]>([])
  const [catalog, setCatalog] = useState<Record<string, any[]>>({})
  const [templates, setTemplates] = useState<any[]>([])
  const [selectedUser, setSelectedUser] = useState<string | null>(null)
  const [userPerms, setUserPerms] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const toast = useToast()

  const fetchData = useCallback(async () => {
    const [catalogData, usersData] = await Promise.all([
      api('/api/v1/admin/permissions/catalog'),
      api('/api/v1/admin/permissions/users'),
    ])
    setCatalog(catalogData.categories || {})
    setTemplates(catalogData.templates || [])
    setUsers(usersData.users || [])
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  function selectUser(uid: string) {
    setSelectedUser(uid)
    const u = users.find(u => u.user_id === uid)
    setUserPerms(u?.permissions || [])
  }

  function togglePerm(permId: string) {
    setUserPerms(prev => prev.includes(permId) ? prev.filter(p => p !== permId) : [...prev, permId])
  }

  async function handleSave() {
    if (!selectedUser) return
    setSaving(true)
    await api('/api/v1/admin/permissions/user', {
      method: 'PUT',
      body: JSON.stringify({ user_id: selectedUser, permissions: userPerms }),
    })
    setSaving(false)
    toast.success('권한 저장', selectedUser)
    fetchData()
  }

  async function applyTemplate(templateId: string) {
    if (!selectedUser) return
    await api('/api/v1/admin/permissions/apply-template', {
      method: 'POST',
      body: JSON.stringify({ user_id: selectedUser, template_id: templateId }),
    })
    toast.success('템플릿 적용', templateId)
    fetchData()
    const tpl = templates.find(t => t.id === templateId)
    if (tpl) setUserPerms(tpl.permissions)
  }

  return (
    <div className="flex gap-4" style={{ minHeight: '500px' }}>
      {/* User list */}
      <div className="w-48 shrink-0 space-y-1">
        <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest px-2 mb-2">사용자</p>
        {users.map(u => (
          <button
            key={u.user_id}
            onClick={() => selectUser(u.user_id)}
            className={cn(
              'w-full text-left px-3 py-2 rounded-md text-xs transition-colors',
              selectedUser === u.user_id ? 'bg-gold-500/20 text-gold-500 font-semibold' : 'text-surface-800 hover:bg-surface-100',
            )}
          >
            <p className="font-mono">{u.user_id}</p>
            <p className="text-2xs text-surface-600">{u.display_name}</p>
          </button>
        ))}
      </div>

      {/* Permission editor */}
      <div className="flex-1">
        {!selectedUser ? (
          <div className="text-center py-20 text-surface-600 text-sm">사용자를 선택하세요</div>
        ) : (
          <div className="space-y-4">
            {/* Template buttons */}
            <div className="flex items-center gap-2">
              <span className="text-2xs font-mono text-surface-600">템플릿 적용:</span>
              {templates.map(t => (
                <button key={t.id} onClick={() => applyTemplate(t.id)}
                  className="tag tag-gold hover:opacity-80 cursor-pointer text-2xs"
                  title={t.description}
                >
                  {t.name}
                </button>
              ))}
              <button onClick={handleSave} disabled={saving} className="btn-primary text-xs flex items-center gap-1 ml-auto">
                {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />} 저장
              </button>
            </div>

            {/* Permission checkboxes by category */}
            {Object.entries(catalog).map(([category, perms]) => (
              <div key={category} className="panel p-4">
                <p className="text-xs font-semibold text-surface-800 mb-3">{category}</p>
                <div className="grid grid-cols-2 gap-2">
                  {perms.map((p: any) => (
                    <label key={p.id} className="flex items-start gap-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={userPerms.includes(p.id)}
                        onChange={() => togglePerm(p.id)}
                        className="mt-0.5 accent-gold-500"
                      />
                      <div>
                        <p className="text-xs text-surface-900 group-hover:text-gold-500 transition-colors">{p.label}</p>
                        <p className="text-2xs text-surface-600">{p.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Model Config ────────────────────────────────────────────────────────────

function ModelTab() {
  const [config, setConfig] = useState<any>(null)
  const [models, setModels] = useState<any[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [url, setUrl] = useState('')
  const toast = useToast()

  useEffect(() => {
    api('/api/v1/admin/model-config').then(d => {
      setConfig(d.config)
      setModels(d.available_models || [])
      setProvider(d.config?.vlm_provider || '')
      setModel(d.config?.vlm_model || '')
      setUrl(d.config?.llama_server_url || '')
    })
  }, [])

  async function handleSave() {
    await api('/api/v1/admin/model-config', {
      method: 'PUT',
      body: JSON.stringify({ vlm_provider: provider, vlm_model: model, llama_server_url: url }),
    })
    toast.success('모델 설정 저장', '서버 재시작 후 적용됩니다')
  }

  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold text-surface-900">LLM 모델 설정</p>
      <div className="panel p-4 space-y-4">
        <div>
          <label className="text-2xs font-mono text-surface-600 uppercase">Provider</label>
          <select value={provider} onChange={e => setProvider(e.target.value)} className="input-field w-full mt-1 text-xs">
            <option value="llama_server">llama-server (Unsloth GGUF)</option>
            <option value="ollama">Ollama</option>
            <option value="claude_wrapper">Claude Wrapper</option>
            <option value="openai">OpenAI</option>
          </select>
        </div>
        <div>
          <label className="text-2xs font-mono text-surface-600 uppercase">모델</label>
          <input value={model} onChange={e => setModel(e.target.value)} className="input-field w-full mt-1 font-mono text-xs" />
        </div>
        <div>
          <label className="text-2xs font-mono text-surface-600 uppercase">서버 URL</label>
          <input value={url} onChange={e => setUrl(e.target.value)} className="input-field w-full mt-1 font-mono text-xs" />
        </div>
        <button onClick={handleSave} className="btn-primary text-xs flex items-center gap-1"><Save size={12} /> 저장</button>
      </div>

      <p className="text-xs font-semibold text-surface-800 mt-4">사용 가능한 모델</p>
      <div className="space-y-1">
        {models.map((m: any, i: number) => (
          <div key={i} className="panel p-3 flex items-center justify-between cursor-pointer hover:border-gold-500/30" onClick={() => setModel(m.name)}>
            <div>
              <span className="text-xs font-mono font-semibold text-surface-900">{m.name}</span>
              <span className="text-2xs text-surface-600 ml-2">{m.source}</span>
            </div>
            <span className="text-2xs font-mono text-surface-600">{m.size}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Metrics ─────────────────────────────────────────────────────────────────

function MetricsTab() {
  const [metrics, setMetrics] = useState<any>(null)

  useEffect(() => { api('/api/v1/admin/metrics').then(setMetrics) }, [])

  if (!metrics) return <div className="text-center py-12"><Loader2 size={20} className="animate-spin text-gold-500 mx-auto" /></div>

  const dailyData = Object.entries(metrics.daily_counts || {}).map(([d, c]) => ({ date: d.slice(5), count: c }))
  const userData = Object.entries(metrics.user_counts || {}).map(([u, c]) => ({ user: u, count: c }))
  const skillData = Object.entries(metrics.skill_counts || {}).map(([s, c]) => ({ skill: s, count: c }))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-3">
        <div className="panel p-4 text-center">
          <p className="text-2xs text-surface-600 uppercase mb-1">총 쿼리</p>
          <p className="text-2xl font-bold text-surface-900">{metrics.total_queries}</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xs text-surface-600 uppercase mb-1">Vault 용량</p>
          <p className="text-2xl font-bold text-surface-900">{metrics.vault_size_mb} MB</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xs text-surface-600 uppercase mb-1">에러율</p>
          <p className={cn('text-2xl font-bold', metrics.error_rate > 10 ? 'text-status-error' : 'text-status-success')}>{metrics.error_rate}%</p>
        </div>
      </div>

      {dailyData.length > 0 && (
        <div className="panel p-4">
          <p className="text-xs font-semibold text-surface-800 mb-3">일별 쿼리 수</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dailyData}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="var(--color-text-muted)" />
              <YAxis tick={{ fontSize: 10 }} stroke="var(--color-text-muted)" />
              <Tooltip />
              <Bar dataKey="count" fill="#F37021" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="panel p-4">
          <p className="text-xs font-semibold text-surface-800 mb-3">사용자별 쿼리</p>
          {userData.map(d => (
            <div key={d.user} className="flex items-center justify-between py-1 text-xs">
              <span className="font-mono text-surface-800">{d.user}</span>
              <span className="font-mono text-surface-600">{d.count as any}</span>
            </div>
          ))}
        </div>
        <div className="panel p-4">
          <p className="text-xs font-semibold text-surface-800 mb-3">스킬별 사용량</p>
          {skillData.slice(0, 8).map(d => (
            <div key={d.skill} className="flex items-center justify-between py-1 text-xs">
              <span className="font-mono text-surface-800 truncate">{d.skill}</span>
              <span className="font-mono text-surface-600">{d.count as any}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Governance ──────────────────────────────────────────────────────────────

function GovernanceTab() {
  const [data, setData] = useState<any>(null)

  useEffect(() => { api('/api/v1/admin/governance').then(setData) }, [])

  if (!data) return <div className="text-center py-12"><Loader2 size={20} className="animate-spin text-gold-500 mx-auto" /></div>

  return (
    <div className="space-y-6">
      {/* Security stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="panel p-4 text-center">
          <p className="text-2xs text-surface-600 uppercase mb-1">권한 위반</p>
          <p className={cn('text-2xl font-bold', data.permission_violations > 0 ? 'text-status-error' : 'text-status-success')}>
            {data.permission_violations}
          </p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xs text-surface-600 uppercase mb-1">인젝션 시도</p>
          <p className={cn('text-2xl font-bold', data.injection_attempts > 0 ? 'text-status-warning' : 'text-status-success')}>
            {data.injection_attempts}
          </p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xs text-surface-600 uppercase mb-1">Private 문서</p>
          <p className="text-2xl font-bold text-surface-900">{data.private_documents}</p>
        </div>
      </div>

      {/* Checklist */}
      <div className="panel p-4">
        <p className="text-sm font-semibold text-surface-800 mb-3">보안 컴플라이언스 체크리스트</p>
        <div className="space-y-2">
          {data.checklist?.map((c: any) => (
            <div key={c.item} className="flex items-center gap-3 py-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
              {c.status ? (
                <CheckCircle2 size={16} className="text-status-success shrink-0" />
              ) : (
                <XCircle size={16} className="text-status-error shrink-0" />
              )}
              <div className="flex-1">
                <p className="text-xs font-semibold text-surface-900">{c.item}</p>
                <p className="text-2xs text-surface-600">{c.detail}</p>
              </div>
              <span className={cn('tag text-2xs', c.status ? 'tag-success' : 'tag-error')}>
                {c.status ? 'PASS' : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent violations */}
      {data.recent_violations?.length > 0 && (
        <div className="panel p-4">
          <p className="text-xs font-semibold text-surface-800 mb-3">최근 권한 위반</p>
          {data.recent_violations.map((v: any, i: number) => (
            <div key={i} className="text-xs py-1.5 flex items-center gap-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
              <AlertTriangle size={11} className="text-status-error shrink-0" />
              <span className="font-mono text-surface-600">{v.user_id}</span>
              <span className="text-surface-800 truncate flex-1">{v.skill_name || v.action}</span>
              <span className="text-2xs text-surface-600">{v.started_at?.slice(0, 16)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Infra ───────────────────────────────────────────────────────────────────

function InfraTab() {
  const [infra, setInfra] = useState<any>(null)

  useEffect(() => { api('/api/v1/admin/infra').then(setInfra) }, [])

  if (!infra) return <div className="text-center py-12"><Loader2 size={20} className="animate-spin text-gold-500 mx-auto" /></div>

  return (
    <div className="space-y-6">
      {/* System info */}
      <div className="grid grid-cols-3 gap-3">
        <div className="panel p-4">
          <div className="flex items-center gap-2 mb-2"><Cpu size={14} className="text-gold-500" /><span className="text-2xs text-surface-600 uppercase">CPU</span></div>
          <p className="text-xl font-bold text-surface-900">{infra.cpu_percent}%</p>
          <p className="text-2xs text-surface-600 mt-1">{infra.processor}</p>
        </div>
        <div className="panel p-4">
          <div className="flex items-center gap-2 mb-2"><Server size={14} className="text-gold-500" /><span className="text-2xs text-surface-600 uppercase">메모리</span></div>
          <p className="text-xl font-bold text-surface-900">{infra.memory?.used_gb} / {infra.memory?.total_gb} GB</p>
          <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-bg-primary)' }}>
            <div className="h-full rounded-full" style={{ width: `${infra.memory?.percent}%`, background: infra.memory?.percent > 80 ? '#FF3B30' : '#F37021' }} />
          </div>
        </div>
        <div className="panel p-4">
          <div className="flex items-center gap-2 mb-2"><HardDrive size={14} className="text-gold-500" /><span className="text-2xs text-surface-600 uppercase">디스크</span></div>
          <p className="text-xl font-bold text-surface-900">{infra.disk_free_gb} GB</p>
          <p className="text-2xs text-surface-600 mt-1">여유 공간</p>
        </div>
      </div>

      {/* GPU */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-800 mb-2">GPU</p>
        <p className="text-sm text-surface-900">{infra.gpu}</p>
      </div>

      {/* Services */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-800 mb-3">서비스 상태</p>
        <div className="space-y-2">
          {infra.services?.map((s: any) => (
            <div key={s.name} className="flex items-center justify-between py-1.5" style={{ borderBottom: '1px solid var(--color-border)' }}>
              <div className="flex items-center gap-2">
                <div className={cn('w-2 h-2 rounded-full', s.status === 'running' ? 'bg-status-success' : 'bg-status-error')} />
                <span className="text-xs font-semibold text-surface-900">{s.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-2xs font-mono text-surface-600">:{s.port}</span>
                <span className={cn('tag text-2xs', s.status === 'running' ? 'tag-success' : 'tag-error')}>{s.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* GPU 추론 서버 관리 */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-800 mb-3">GPU 추론 서버 (Docker)</p>
        <div className="space-y-2 text-xs text-surface-600">
          <p>GPU 머신에 모델 서빙 컨테이너를 배포합니다.</p>
          <div className="rounded p-3 font-mono text-2xs" style={{ background: 'var(--color-bg-primary)' }}>
            <p className="text-surface-600"># 로컬 배포 (4B 모델)</p>
            <p className="text-gold-500">cd infra && ./deploy.sh</p>
            <p className="text-surface-600 mt-2"># 원격 GPU 서버 배포 (9B 모델)</p>
            <p className="text-gold-500">cd infra && ./deploy.sh gpu-server.local 9b</p>
            <p className="text-surface-600 mt-2"># .env에서 엔드포인트 변경</p>
            <p className="text-gold-500">LLAMA_SERVER_URL=http://gpu-server:8801/v1</p>
          </div>
          <div className="flex gap-2 mt-3">
            <div className="flex-1 panel p-3">
              <p className="text-2xs text-surface-600 mb-1">지원 GPU</p>
              <p className="text-xs text-surface-900">NVIDIA CUDA, Apple Metal, CPU</p>
            </div>
            <div className="flex-1 panel p-3">
              <p className="text-2xs text-surface-600 mb-1">지원 모델</p>
              <p className="text-xs text-surface-900">Qwen3.5 2B/4B/9B (Unsloth GGUF)</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function Admin() {
  const { userId } = useStore()
  const [tab, setTab] = useState<Tab>('overview')

  // admin01만 접근 가능 (프론트 가드 — 백엔드에서도 403 반환)
  if (userId !== 'admin01') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Shield size={32} className="text-status-error mx-auto mb-3" />
          <p className="text-sm font-semibold text-surface-900">관리자 권한 필요</p>
          <p className="text-xs text-surface-600 mt-1">이 페이지는 admin 역할이 필요합니다.</p>
        </div>
      </div>
    )
  }

  const tabs: { id: Tab; label: string; icon: typeof Shield }[] = [
    { id: 'overview', label: '개요', icon: Eye },
    { id: 'iam', label: 'IAM', icon: Users },
    { id: 'model', label: '모델', icon: Settings2 },
    { id: 'metrics', label: '메트릭', icon: Activity },
    { id: 'governance', label: '거버넌스', icon: Shield },
    { id: 'infra', label: '인프라', icon: Server },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">관리 패널</h2>
        <p className="text-sm text-surface-600">시스템 설정, 사용자 관리, 보안 거버넌스</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-lg overflow-x-auto" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              'flex items-center gap-1.5 py-2 px-3 rounded-md text-xs font-semibold transition-colors whitespace-nowrap',
              tab === id ? 'bg-gold-500 text-surface-DEFAULT' : 'text-surface-600 hover:text-surface-800',
            )}
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        {tab === 'overview' && <OverviewTab />}
        {tab === 'iam' && <IamTab />}
        {tab === 'model' && <ModelTab />}
        {tab === 'metrics' && <MetricsTab />}
        {tab === 'governance' && <GovernanceTab />}
        {tab === 'infra' && <InfraTab />}
      </motion.div>
    </div>
  )
}
