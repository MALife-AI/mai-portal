import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Shield, ShieldOff, Users, Activity, Settings2, FileText,
  Server, Eye, CheckCircle2, XCircle, AlertTriangle,
  Loader2, RefreshCw, Save, Cpu, HardDrive, Gauge,
  Building2, Plus, Trash2, Edit3, KeyRound, Copy,
} from 'lucide-react'
import { adminApi, getUserId, type IamConfig, type KillSwitchStatus } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { cn } from '@/lib/utils'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie,
} from 'recharts'

const API = ''
async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, { ...opts, headers: { 'X-User-Id': getUserId(), 'Content-Type': 'application/json', ...opts.headers } })
  return r.json()
}

interface ChecklistItem { item: string; status: boolean; detail?: string }
interface ViolationItem { user_id: string; skill_name?: string; action?: string; started_at?: string }
interface ServiceItem { name: string; status: string; port?: number }
interface MemoryInfo { used_gb: number; total_gb: number; percent: number }

interface MetricsData {
  total_queries: number
  vault_files: number
  vault_size_mb: number
  graph_stats?: { node_count: number }
  error_rate: number
  daily_counts: Record<string, number>
  user_counts: Record<string, number>
  skill_counts: Record<string, number>
}

interface GovernanceData {
  permission_violations: number
  injection_attempts: number
  private_documents: number
  checklist?: ChecklistItem[]
  recent_violations?: ViolationItem[]
}

interface GPUServer {
  id: string
  name: string
  url: string
  model: string
  description?: string
}

interface InfraData {
  cpu_percent: number
  processor: string
  memory?: MemoryInfo
  disk_free_gb: number
  gpu: string
  services?: ServiceItem[]
}

interface GuardrailConfig {
  prompt_injection: { enabled: boolean; risk_threshold: number; max_input_length: number; block_action: string }
  topic_restrictions: { enabled: boolean; blocked_topics: string[]; warn_topics: string[] }
  output_guardrails: { pii_masking: boolean; max_output_length: number; block_code_execution: boolean; block_external_urls: boolean }
  rate_limits: { enabled: boolean; max_queries_per_minute: number; max_queries_per_hour: number; max_tokens_per_query: number }
  content_policy: { require_citation: boolean; hallucination_guard: boolean; confidence_threshold: number; disclaimer_footer: string }
  custom_rules: { id: string; name: string; pattern: string; action: string; description: string }[]
}

type Tab = 'overview' | 'iam' | 'departments' | 'api-keys' | 'model' | 'metrics' | 'guardrails' | 'governance' | 'infra'

// ─── Overview ────────────────────────────────────────────────────────────────

function OverviewTab() {
  const [ks, setKs] = useState<KillSwitchStatus | null>(null)
  const [metrics, setMetrics] = useState<MetricsData | null>(null)
  const [governance, setGovernance] = useState<GovernanceData | null>(null)
  const toast = useToast()

  useEffect(() => {
    adminApi.getKillSwitchStatus().then(setKs)
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
    setKs(await adminApi.getKillSwitchStatus())
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
  const [users, setUsers] = useState<{ user_id: string; display_name: string; permissions: string[] }[]>([])
  const [catalog, setCatalog] = useState<Record<string, { id: string; label: string; description: string }[]>>({})
  const [templates, setTemplates] = useState<{ id: string; name: string; description: string; permissions: string[] }[]>([])
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
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [models, setModels] = useState<{ name: string; source: string; size: string }[]>([])
  const [gpuServers, setGpuServers] = useState<GPUServer[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [url, setUrl] = useState('')
  // Smart Routing
  const [smartRouting, setSmartRouting] = useState(false)
  const [lightUrl, setLightUrl] = useState('')
  const [heavyUrl, setHeavyUrl] = useState('')
  // GPU 서버 추가 폼
  const [newSrv, setNewSrv] = useState<{ id: string; name: string; url: string; model: string; description: string }>({
    id: '', name: '', url: '', model: 'qwen3.5-4b', description: '',
  })
  const toast = useToast()

  const fetchConfig = useCallback(async () => {
    const d = await api('/api/v1/admin/model-config')
    setConfig(d.config)
    setModels(d.available_models || [])
    setGpuServers(d.gpu_servers || [])
    setProvider(d.config?.vlm_provider || '')
    setModel(d.config?.vlm_model || '')
    setUrl(d.config?.llama_server_url || '')
    setSmartRouting(d.config?.smart_routing || false)
    setLightUrl(d.config?.llama_server_light || '')
    setHeavyUrl(d.config?.llama_server_heavy || '')
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  async function handleSave() {
    await api('/api/v1/admin/model-config', {
      method: 'PUT',
      body: JSON.stringify({
        vlm_provider: provider,
        vlm_model: model,
        llama_server_url: url,
        smart_routing: smartRouting,
        llama_server_light: lightUrl,
        llama_server_heavy: heavyUrl,
      }),
    })
    toast.success('모델 설정 저장', '서버 재시작 후 적용됩니다')
  }

  async function addServer() {
    if (!newSrv.id || !newSrv.name || !newSrv.url) { toast.error('필수 항목 누락', ''); return }
    await api('/api/v1/admin/gpu-servers', {
      method: 'POST',
      body: JSON.stringify(newSrv),
    })
    toast.success('GPU 서버 추가', newSrv.name)
    setNewSrv({ id: '', name: '', url: '', model: 'qwen3.5-4b', description: '' })
    // Optimistic update: append without a round-trip fetch
    setGpuServers(prev => [...prev, newSrv])
  }

  async function removeServer(id: string) {
    await api(`/api/v1/admin/gpu-servers/${id}`, { method: 'DELETE' })
    toast.success('GPU 서버 삭제', id)
    // Optimistic update: filter out without a round-trip fetch
    setGpuServers(prev => prev.filter(s => s.id !== id))
  }

  return (
    <div className="space-y-6">
      {/* 기본 추론 서버 선택 */}
      <div>
        <p className="text-sm font-semibold text-surface-900 mb-3">기본 추론 서버</p>
        <div className="panel p-4 space-y-3">
          <p className="text-xs text-surface-600">에이전트가 기본으로 사용할 GPU 서버를 선택하세요.</p>
          <div className="space-y-2">
            {gpuServers.map((srv: any) => (
              <label
                key={srv.id}
                className={cn(
                  'flex items-center gap-3 p-3 rounded-md cursor-pointer transition-colors',
                  url === srv.url
                    ? 'bg-gold-500/10 border border-gold-500/40'
                    : 'hover:bg-surface-200 border border-transparent',
                )}
              >
                <input
                  type="radio"
                  name="default-server"
                  checked={url === srv.url}
                  onChange={() => { setUrl(srv.url); setModel(srv.model); setProvider('llama_server') }}
                  className="accent-gold-500"
                />
                <Server size={14} className="text-gold-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-surface-900">{srv.name}</p>
                  <p className="text-2xs text-surface-600 font-mono truncate">{srv.url}</p>
                </div>
                <span className="tag tag-gold text-2xs shrink-0">{srv.model}</span>
              </label>
            ))}
            {gpuServers.length === 0 && (
              <p className="text-xs text-surface-600 text-center py-4">등록된 GPU 서버가 없습니다. 아래에서 추가하세요.</p>
            )}
          </div>
          <button onClick={handleSave} className="btn-primary text-xs flex items-center gap-1"><Save size={12} /> 저장</button>
        </div>
      </div>

      {/* 모델 매핑 (Smart Routing) */}
      <div>
        <p className="text-sm font-semibold text-surface-900 mb-3">모델 매핑 (Smart Routing)</p>
        <div className="panel p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-surface-800 font-semibold">질문 복잡도 기반 자동 라우팅</p>
              <p className="text-2xs text-surface-600">간단한 질문은 빠른 모델, 복잡한 질문은 사고 모델로 자동 분배합니다</p>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={smartRouting} onChange={e => setSmartRouting(e.target.checked)} className="accent-gold-500" />
              <span className="text-xs text-surface-700">{smartRouting ? '활성' : '비활성'}</span>
            </label>
          </div>

          {smartRouting && (
            <div className="grid grid-cols-2 gap-4 pt-2" style={{ borderTop: '1px solid var(--color-border)' }}>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Gauge size={14} className="text-status-success" />
                  <span className="text-xs font-semibold text-surface-800">간단 모드 (Fast)</span>
                </div>
                <p className="text-2xs text-surface-600">인사, 단순 조회, 짧은 질문 (50자 미만)</p>
                <div>
                  <label className="text-2xs text-surface-600">서버 URL</label>
                  <select value={lightUrl} onChange={e => setLightUrl(e.target.value)} className="input-field w-full mt-1 text-xs">
                    <option value="">기본 서버 사용</option>
                    {gpuServers.map(s => <option key={s.id} value={s.url}>{s.name} ({s.model})</option>)}
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Cpu size={14} className="text-gold-500" />
                  <span className="text-xs font-semibold text-surface-800">사고 모드 (Think)</span>
                </div>
                <p className="text-2xs text-surface-600">분석, 비교, 요약, 추론 등 복잡한 질문</p>
                <div>
                  <label className="text-2xs text-surface-600">서버 URL</label>
                  <select value={heavyUrl} onChange={e => setHeavyUrl(e.target.value)} className="input-field w-full mt-1 text-xs">
                    <option value="">기본 서버 사용 (라우팅 안 함)</option>
                    {gpuServers.map(s => <option key={s.id} value={s.url}>{s.name} ({s.model})</option>)}
                  </select>
                </div>
              </div>
            </div>
          )}

          {smartRouting && (
            <div className="rounded p-3 text-2xs" style={{ background: 'var(--color-bg-primary)' }}>
              <p className="text-surface-600 mb-1">라우팅 기준 키워드:</p>
              <div className="flex flex-wrap gap-1">
                {['분석', '비교', '왜', '어떻게', '차이', '요약', '정리', '계산', '추론', 'think'].map(kw => (
                  <span key={kw} className="tag tag-gold">{kw}</span>
                ))}
              </div>
              <p className="text-surface-600 mt-2">위 키워드가 포함되거나, 질문이 100자 이상이면 사고 모드로 라우팅됩니다.</p>
            </div>
          )}

          <button onClick={handleSave} className="btn-primary text-xs flex items-center gap-1"><Save size={12} /> 저장</button>
        </div>
      </div>

      {/* GPU 서버 관리 */}
      <div>
        <p className="text-sm font-semibold text-surface-900 mb-3">GPU 추론 서버</p>
        <div className="space-y-2 mb-4">
          {gpuServers.map((srv: any) => (
            <div key={srv.id} className="panel p-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Server size={14} className="text-gold-500 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-surface-900">{srv.name} <span className="text-2xs font-mono text-surface-600">({srv.id})</span></p>
                  <p className="text-2xs font-mono text-surface-600">{srv.url}</p>
                  {srv.description && <p className="text-2xs text-surface-600">{srv.description}</p>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="tag tag-gold text-2xs">{srv.model}</span>
                {srv.id !== 'local' && (
                  <button onClick={() => removeServer(srv.id)} className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-status-error hover:bg-surface-200">
                    <XCircle size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* 서버 추가 폼 */}
        <div className="panel p-4">
          <p className="text-xs font-semibold text-surface-800 mb-3">서버 추가</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">서버 ID</label>
              <input value={newSrv.id} onChange={e => setNewSrv(prev => ({ ...prev, id: e.target.value }))} placeholder="gpu-a100" className="input-field w-full mt-1 font-mono text-xs" />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">표시 이름</label>
              <input value={newSrv.name} onChange={e => setNewSrv(prev => ({ ...prev, name: e.target.value }))} placeholder="A100 GPU 9B" className="input-field w-full mt-1 text-xs" />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">URL</label>
              <input value={newSrv.url} onChange={e => setNewSrv(prev => ({ ...prev, url: e.target.value }))} placeholder="http://gpu-server:8801/v1" className="input-field w-full mt-1 font-mono text-xs" />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">모델</label>
              <input value={newSrv.model} onChange={e => setNewSrv(prev => ({ ...prev, model: e.target.value }))} placeholder="qwen3.5-9b" className="input-field w-full mt-1 font-mono text-xs" />
            </div>
            <div className="col-span-2">
              <label className="text-2xs font-mono text-surface-600 uppercase">설명</label>
              <input value={newSrv.description} onChange={e => setNewSrv(prev => ({ ...prev, description: e.target.value }))} placeholder="A100 80GB, 데이터센터" className="input-field w-full mt-1 text-xs" />
            </div>
          </div>
          <button onClick={addServer} className="btn-primary text-xs flex items-center gap-1 mt-3"><Server size={12} /> 서버 추가</button>
        </div>
      </div>

      {/* 사용 가능한 모델 */}
      <div>
        <p className="text-xs font-semibold text-surface-800 mb-2">사용 가능한 모델</p>
        <div className="space-y-1">
          {models.map((m, i) => (
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
    </div>
  )
}

// ─── Metrics ─────────────────────────────────────────────────────────────────

function MetricsTab() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null)

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

// ─── API Keys ───────────────────────────────────────────────────────────────

function ApiKeysTab() {
  const [keys, setKeys] = useState<any[]>([])
  const [newLabel, setNewLabel] = useState('')
  const [newUserId, setNewUserId] = useState('')
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const toast = useToast()

  useEffect(() => { api('/api/v1/admin/api-keys').then(d => setKeys(d.keys || [])) }, [])

  async function createKey() {
    const body: any = { label: newLabel || 'default' }
    if (newUserId) body.user_id = newUserId
    const res = await api('/api/v1/admin/api-keys', { method: 'POST', body: JSON.stringify(body) })
    if (res.api_key) {
      setCreatedKey(res.api_key)
      toast.success('API 키 발급', res.user_id)
      setNewLabel('')
      setNewUserId('')
      api('/api/v1/admin/api-keys').then(d => setKeys(d.keys || []))
    }
  }

  async function revokeKey(prefix: string) {
    await api(`/api/v1/admin/api-keys/${prefix}`, { method: 'DELETE' })
    toast.success('API 키 폐기', prefix)
    setKeys(prev => prev.filter(k => !k.key.startsWith(prefix)))
  }

  function copyKey() {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey)
      toast.success('클립보드에 복사됨', '')
    }
  }

  return (
    <div className="space-y-4">
      <h3 className="font-display font-semibold text-surface-900 text-lg">API 키 관리</h3>

      {/* 새 키 발급 */}
      <div className="panel p-4 space-y-3">
        <p className="text-xs font-semibold text-surface-800">새 API 키 발급</p>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-2xs text-surface-600">라벨</label>
            <input value={newLabel} onChange={e => setNewLabel(e.target.value)}
              placeholder="예: 외부 시스템 연동" className="input-field w-full mt-1 text-xs" />
          </div>
          <div>
            <label className="text-2xs text-surface-600">사용자 ID (비우면 본인)</label>
            <input value={newUserId} onChange={e => setNewUserId(e.target.value)}
              placeholder="admin01" className="input-field w-full mt-1 font-mono text-xs" />
          </div>
          <div className="flex items-end">
            <button onClick={createKey} className="btn-primary text-xs flex items-center gap-1 w-full justify-center">
              <KeyRound size={12} /> 발급
            </button>
          </div>
        </div>

        {createdKey && (
          <div className="rounded p-3 flex items-center gap-2" style={{ background: 'rgba(52,199,89,0.1)', border: '1px solid rgba(52,199,89,0.3)' }}>
            <KeyRound size={14} className="text-status-success shrink-0" />
            <code className="text-xs font-mono text-surface-900 flex-1 break-all">{createdKey}</code>
            <button onClick={copyKey} className="btn-secondary text-2xs flex items-center gap-1 shrink-0"><Copy size={10} /> 복사</button>
          </div>
        )}
        {createdKey && (
          <p className="text-2xs text-status-warning">이 키는 다시 표시되지 않습니다. 지금 복사해주세요.</p>
        )}
      </div>

      {/* 사용법 */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-800 mb-2">사용법</p>
        <div className="rounded p-3 font-mono text-2xs space-y-1" style={{ background: 'var(--color-bg-primary)' }}>
          <p className="text-surface-600"># X-User-Id 대신 Bearer 토큰으로 인증</p>
          <p className="text-gold-500">curl -H "Authorization: Bearer mlk_..." http://host:9001/api/v1/search/?q=보험</p>
        </div>
      </div>

      {/* 발급된 키 목록 */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-800 mb-3">발급된 키</p>
        {keys.length === 0 ? (
          <p className="text-xs text-surface-600 text-center py-4">발급된 API 키가 없습니다</p>
        ) : (
          <div className="space-y-2">
            {keys.map((k: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
                <div className="flex items-center gap-3">
                  <KeyRound size={13} className="text-gold-500" />
                  <div>
                    <div className="flex items-center gap-2">
                      <code className="text-xs font-mono text-surface-900">{k.key}</code>
                      <span className="tag tag-blue text-2xs">{k.label}</span>
                    </div>
                    <p className="text-2xs text-surface-600">사용자: {k.user_id} · 생성: {k.created_at?.split('T')[0]}</p>
                  </div>
                </div>
                <button onClick={() => revokeKey(k.key.split('...')[0])}
                  className="text-surface-600 hover:text-status-error"><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Guardrails ─────────────────────────────────────────────────────────────

function GuardrailsTab() {
  const [config, setConfig] = useState<GuardrailConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [testText, setTestText] = useState('')
  const [testResult, setTestResult] = useState<any>(null)
  const [newTopic, setNewTopic] = useState('')
  const toast = useToast()

  useEffect(() => { api('/api/v1/admin/guardrails').then(setConfig) }, [])

  async function save() {
    if (!config) return
    setSaving(true)
    try {
      await api('/api/v1/admin/guardrails', { method: 'PUT', body: JSON.stringify(config) })
      toast.success('가드레일 설정 저장', '')
    } catch { toast.error('저장 실패', '') }
    setSaving(false)
  }

  async function reset() {
    const res = await api('/api/v1/admin/guardrails/reset', { method: 'POST' })
    setConfig(res.config)
    toast.success('기본값으로 초기화', '')
  }

  async function runTest() {
    const res = await api('/api/v1/admin/guardrails/test', { method: 'POST', body: JSON.stringify({ text: testText }) })
    setTestResult(res)
  }

  if (!config) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-surface-600" /></div>

  const update = (section: keyof GuardrailConfig, key: string, value: any) => {
    setConfig(prev => {
      if (!prev) return prev
      return { ...prev, [section]: { ...(prev[section] as any), [key]: value } }
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-semibold text-surface-900 text-lg">가드레일 설정</h3>
        <div className="flex gap-2">
          <button onClick={reset} className="btn-secondary text-xs flex items-center gap-1"><RefreshCw size={12} /> 초기화</button>
          <button onClick={save} disabled={saving} className="btn-primary text-xs flex items-center gap-1">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 저장
          </button>
        </div>
      </div>

      {/* 프롬프트 인젝션 방어 */}
      <div className="panel p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-surface-800">프롬프트 인젝션 방어</h4>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={config.prompt_injection.enabled}
              onChange={e => update('prompt_injection', 'enabled', e.target.checked)}
              className="accent-gold-500" />
            <span className="text-xs text-surface-700">{config.prompt_injection.enabled ? '활성' : '비활성'}</span>
          </label>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-2xs text-surface-600 block mb-1">위험도 임계값</label>
            <input type="number" step="0.05" min="0" max="1" value={config.prompt_injection.risk_threshold}
              onChange={e => update('prompt_injection', 'risk_threshold', parseFloat(e.target.value))}
              className="input-field text-xs" />
          </div>
          <div>
            <label className="text-2xs text-surface-600 block mb-1">최대 입력 길이</label>
            <input type="number" step="1000" value={config.prompt_injection.max_input_length}
              onChange={e => update('prompt_injection', 'max_input_length', parseInt(e.target.value))}
              className="input-field text-xs" />
          </div>
          <div>
            <label className="text-2xs text-surface-600 block mb-1">차단 동작</label>
            <select value={config.prompt_injection.block_action}
              onChange={e => update('prompt_injection', 'block_action', e.target.value)}
              className="input-field text-xs">
              <option value="reject">차단 (reject)</option>
              <option value="warn">경고 (warn)</option>
              <option value="log_only">로그만 (log_only)</option>
            </select>
          </div>
        </div>
      </div>

      {/* 주제 제한 */}
      <div className="panel p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-surface-800">주제 제한</h4>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={config.topic_restrictions.enabled}
              onChange={e => update('topic_restrictions', 'enabled', e.target.checked)}
              className="accent-gold-500" />
            <span className="text-xs text-surface-700">{config.topic_restrictions.enabled ? '활성' : '비활성'}</span>
          </label>
        </div>
        <div>
          <label className="text-2xs text-surface-600 block mb-1">차단 주제</label>
          <div className="flex flex-wrap gap-1 mb-2">
            {config.topic_restrictions.blocked_topics.map((t, i) => (
              <span key={i} className="tag tag-error flex items-center gap-1">
                {t}
                <button onClick={() => {
                  const topics = [...config.topic_restrictions.blocked_topics]
                  topics.splice(i, 1)
                  update('topic_restrictions', 'blocked_topics', topics)
                }} className="hover:text-white"><XCircle size={10} /></button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input value={newTopic} onChange={e => setNewTopic(e.target.value)}
              placeholder="차단할 주제 입력" className="input-field text-xs flex-1"
              onKeyDown={e => {
                if (e.key === 'Enter' && newTopic.trim()) {
                  update('topic_restrictions', 'blocked_topics', [...config.topic_restrictions.blocked_topics, newTopic.trim()])
                  setNewTopic('')
                }
              }} />
            <button onClick={() => {
              if (newTopic.trim()) {
                update('topic_restrictions', 'blocked_topics', [...config.topic_restrictions.blocked_topics, newTopic.trim()])
                setNewTopic('')
              }
            }} className="btn-secondary text-xs"><Plus size={12} /></button>
          </div>
        </div>
      </div>

      {/* 출력 가드레일 */}
      <div className="panel p-4 space-y-3">
        <h4 className="text-sm font-semibold text-surface-800">출력 가드레일</h4>
        <div className="grid grid-cols-2 gap-3">
          {([
            ['pii_masking', 'PII 마스킹'],
            ['block_code_execution', '코드 실행 차단'],
            ['block_external_urls', '외부 URL 차단'],
          ] as const).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={(config.output_guardrails as any)[key]}
                onChange={e => update('output_guardrails', key, e.target.checked)}
                className="accent-gold-500" />
              <span className="text-xs text-surface-700">{label}</span>
            </label>
          ))}
          <div>
            <label className="text-2xs text-surface-600 block mb-1">최대 출력 길이</label>
            <input type="number" step="5000" value={config.output_guardrails.max_output_length}
              onChange={e => update('output_guardrails', 'max_output_length', parseInt(e.target.value))}
              className="input-field text-xs" />
          </div>
        </div>
      </div>

      {/* 속도 제한 */}
      <div className="panel p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-surface-800">속도 제한</h4>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={config.rate_limits.enabled}
              onChange={e => update('rate_limits', 'enabled', e.target.checked)}
              className="accent-gold-500" />
            <span className="text-xs text-surface-700">{config.rate_limits.enabled ? '활성' : '비활성'}</span>
          </label>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-2xs text-surface-600 block mb-1">분당 최대 쿼리</label>
            <input type="number" value={config.rate_limits.max_queries_per_minute}
              onChange={e => update('rate_limits', 'max_queries_per_minute', parseInt(e.target.value))}
              className="input-field text-xs" />
          </div>
          <div>
            <label className="text-2xs text-surface-600 block mb-1">시간당 최대 쿼리</label>
            <input type="number" value={config.rate_limits.max_queries_per_hour}
              onChange={e => update('rate_limits', 'max_queries_per_hour', parseInt(e.target.value))}
              className="input-field text-xs" />
          </div>
          <div>
            <label className="text-2xs text-surface-600 block mb-1">쿼리당 최대 토큰</label>
            <input type="number" value={config.rate_limits.max_tokens_per_query}
              onChange={e => update('rate_limits', 'max_tokens_per_query', parseInt(e.target.value))}
              className="input-field text-xs" />
          </div>
        </div>
      </div>

      {/* 콘텐츠 정책 */}
      <div className="panel p-4 space-y-3">
        <h4 className="text-sm font-semibold text-surface-800">콘텐츠 정책</h4>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={config.content_policy.require_citation}
              onChange={e => update('content_policy', 'require_citation', e.target.checked)}
              className="accent-gold-500" />
            <span className="text-xs text-surface-700">출처 인용 필수</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={config.content_policy.hallucination_guard}
              onChange={e => update('content_policy', 'hallucination_guard', e.target.checked)}
              className="accent-gold-500" />
            <span className="text-xs text-surface-700">할루시네이션 가드</span>
          </label>
          <div>
            <label className="text-2xs text-surface-600 block mb-1">신뢰도 임계값</label>
            <input type="number" step="0.05" min="0" max="1" value={config.content_policy.confidence_threshold}
              onChange={e => update('content_policy', 'confidence_threshold', parseFloat(e.target.value))}
              className="input-field text-xs" />
          </div>
          <div>
            <label className="text-2xs text-surface-600 block mb-1">면책 문구</label>
            <input value={config.content_policy.disclaimer_footer}
              onChange={e => update('content_policy', 'disclaimer_footer', e.target.value)}
              placeholder="응답 하단에 추가할 면책 문구"
              className="input-field text-xs" />
          </div>
        </div>
      </div>

      {/* 가드레일 테스트 */}
      <div className="panel p-4 space-y-3">
        <h4 className="text-sm font-semibold text-surface-800">가드레일 테스트</h4>
        <textarea value={testText} onChange={e => setTestText(e.target.value)}
          placeholder="테스트할 입력 텍스트를 입력하세요..."
          className="input-field text-xs h-20 resize-none" />
        <button onClick={runTest} disabled={!testText.trim()} className="btn-primary text-xs">검사 실행</button>
        {testResult && (
          <div className={cn('p-3 rounded-md text-xs space-y-1', testResult.blocked ? 'bg-red-500/10 border border-red-500/30' : 'bg-green-500/10 border border-green-500/30')}>
            <div className="flex items-center gap-2 font-semibold">
              {testResult.blocked ? <XCircle size={14} className="text-status-error" /> : <CheckCircle2 size={14} className="text-status-success" />}
              {testResult.blocked ? '차단됨' : '통과'}
            </div>
            <div className="text-surface-700">위험도 점수: <span className="font-mono">{testResult.risk_score.toFixed(4)}</span> / 임계값: {testResult.threshold}</div>
            <div className="text-surface-700">텍스트 길이: {testResult.text_length}자</div>
            {testResult.injection_detected && <div className="text-status-error">프롬프트 인젝션 패턴 감지됨</div>}
            {testResult.matched_blocked_topics?.length > 0 && (
              <div className="text-status-warning">차단 주제 매칭: {testResult.matched_blocked_topics.join(', ')}</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Governance ──────────────────────────────────────────────────────────────

function GovernanceTab() {
  const [data, setData] = useState<GovernanceData | null>(null)

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

// ─── Departments ─────────────────────────────────────────────────────────────

function DepartmentsTab() {
  const [departments, setDepartments] = useState<{ id: string; name: string; description: string }[]>([])
  const [editId, setEditId] = useState<string | null>(null)
  const [formId, setFormId] = useState('')
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [isNew, setIsNew] = useState(false)
  const toast = useToast()

  const fetchDepts = useCallback(async () => {
    const d = await api('/api/v1/admin/departments')
    setDepartments(d.departments || [])
  }, [])

  useEffect(() => { fetchDepts() }, [fetchDepts])

  function startNew() {
    setIsNew(true)
    setEditId(null)
    setFormId('')
    setFormName('')
    setFormDesc('')
  }

  function startEdit(dept: any) {
    setIsNew(false)
    setEditId(dept.id)
    setFormId(dept.id)
    setFormName(dept.name)
    setFormDesc(dept.description)
  }

  function cancelEdit() {
    setEditId(null)
    setIsNew(false)
  }

  async function handleSave() {
    if (!formId || !formName) { toast.error('필수 항목 누락', 'ID와 이름은 필수입니다'); return }
    if (isNew) {
      await api('/api/v1/admin/departments', {
        method: 'POST',
        body: JSON.stringify({ id: formId, name: formName, description: formDesc }),
      })
      toast.success('부서 추가', formName)
    } else {
      await api(`/api/v1/admin/departments/${editId}`, {
        method: 'PUT',
        body: JSON.stringify({ id: formId, name: formName, description: formDesc }),
      })
      toast.success('부서 수정', formName)
    }
    cancelEdit()
    fetchDepts()
  }

  async function handleDelete(id: string) {
    await api(`/api/v1/admin/departments/${id}`, { method: 'DELETE' })
    toast.success('부서 삭제', id)
    fetchDepts()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-surface-900">소속 부서 관리</p>
        <button onClick={startNew} className="btn-primary text-xs flex items-center gap-1"><Plus size={12} /> 부서 추가</button>
      </div>

      {/* 추가/수정 폼 */}
      {(isNew || editId) && (
        <div className="panel p-4 space-y-3">
          <p className="text-xs font-semibold text-surface-800">{isNew ? '새 부서 추가' : '부서 수정'}</p>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">부서 ID</label>
              <input
                value={formId}
                onChange={e => setFormId(e.target.value)}
                disabled={!isNew}
                placeholder="sales_dept"
                className="input-field w-full mt-1 font-mono text-xs"
              />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">부서명</label>
              <input value={formName} onChange={e => setFormName(e.target.value)} placeholder="영업부" className="input-field w-full mt-1 text-xs" />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase">설명</label>
              <input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="영업 및 고객 관리" className="input-field w-full mt-1 text-xs" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={handleSave} className="btn-primary text-xs flex items-center gap-1"><Save size={12} /> 저장</button>
            <button onClick={cancelEdit} className="btn-secondary text-xs">취소</button>
          </div>
        </div>
      )}

      {/* 부서 목록 */}
      <div className="space-y-2">
        {departments.length === 0 ? (
          <div className="text-center py-8 text-surface-600 text-sm">등록된 부서가 없습니다</div>
        ) : (
          departments.map(dept => (
            <div key={dept.id} className="panel p-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Building2 size={14} className="text-gold-500 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-surface-900">{dept.name}</p>
                  <p className="text-2xs text-surface-600">
                    <span className="font-mono">{dept.id}</span>
                    {dept.description && <> — {dept.description}</>}
                  </p>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => startEdit(dept)} className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-gold-500 hover:bg-surface-200">
                  <Edit3 size={12} />
                </button>
                <button onClick={() => handleDelete(dept.id)} className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-status-error hover:bg-surface-200">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ─── Infra ───────────────────────────────────────────────────────────────────

function GpuServerMetrics() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => {
    setLoading(true)
    api('/api/v1/admin/inference-status').then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  useEffect(() => { refresh(); const t = setInterval(refresh, 10000); return () => clearInterval(t) }, [refresh])

  if (!data?.servers?.length) return null

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold text-surface-800">GPU 추론 서버 메트릭</p>
        <button onClick={refresh} className="btn-secondary text-2xs flex items-center gap-1" disabled={loading}>
          <RefreshCw size={10} className={loading ? 'animate-spin' : ''} /> 새로고침
        </button>
      </div>
      <div className="space-y-3">
        {data.servers.map((srv: any) => (
          <div key={srv.id || srv.url} className="rounded-md p-3" style={{ background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)' }}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className={cn('w-2.5 h-2.5 rounded-full', srv.signal === 'green' ? 'bg-status-success' : srv.signal === 'yellow' ? 'bg-status-warning' : 'bg-status-error')} />
                <span className="text-xs font-semibold text-surface-900">{srv.name || srv.id}</span>
                <span className="text-2xs font-mono text-surface-600">{srv.url}</span>
              </div>
              <span className={cn('tag text-2xs', srv.online ? 'tag-success' : 'tag-error')}>{srv.label}</span>
            </div>
            {srv.online && (
              <div className="grid grid-cols-5 gap-2 mt-2">
                <div>
                  <p className="text-2xs text-surface-600">슬롯</p>
                  <p className="text-sm font-bold text-surface-900">{srv.slots_busy}/{srv.slots_total}</p>
                </div>
                <div>
                  <p className="text-2xs text-surface-600">부하</p>
                  <p className="text-sm font-bold text-surface-900">{srv.load_pct}%</p>
                </div>
                {srv.metrics?.tokens_per_second != null && (
                  <div>
                    <p className="text-2xs text-surface-600">토큰/s</p>
                    <p className="text-sm font-bold text-gold-500">{srv.metrics.tokens_per_second}</p>
                  </div>
                )}
                {srv.metrics?.tokens_predicted_total != null && (
                  <div>
                    <p className="text-2xs text-surface-600">총 토큰</p>
                    <p className="text-sm font-bold text-surface-900">{Math.round(srv.metrics.tokens_predicted_total).toLocaleString()}</p>
                  </div>
                )}
                {srv.metrics?.kv_cache_usage_ratio != null && (
                  <div>
                    <p className="text-2xs text-surface-600">KV 캐시</p>
                    <p className="text-sm font-bold text-surface-900">{Math.round(srv.metrics.kv_cache_usage_ratio * 100)}%</p>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function InfraTab() {
  const [infra, setInfra] = useState<InfraData | null>(null)

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

      {/* GPU 추론 서버 실시간 메트릭 */}
      <GpuServerMetrics />

      {/* GPU 추론 서버 관리 */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-800 mb-3">GPU 추론 서버 (Docker)</p>
        <div className="space-y-2 text-xs text-surface-600">
          <p>GPU 머신에 모델 서빙 컨테이너를 배포합니다.</p>
          <div className="rounded p-3 font-mono text-2xs" style={{ background: 'var(--color-bg-primary)' }}>
            <p className="text-surface-600"># 14B 모델로 원격 배포 (24GB VRAM)</p>
            <p className="text-gold-500">./deploy.sh gpu-server.local 14b</p>
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
              <p className="text-xs text-surface-900">Qwen3.5 2B/4B/9B/14B/32B (GGUF)</p>
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
    { id: 'departments', label: '부서', icon: Building2 },
    { id: 'api-keys', label: 'API 키', icon: KeyRound },
    { id: 'model', label: '모델', icon: Settings2 },
    { id: 'metrics', label: '메트릭', icon: Activity },
    { id: 'guardrails', label: '가드레일', icon: ShieldOff },
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
        {tab === 'departments' && <DepartmentsTab />}
        {tab === 'api-keys' && <ApiKeysTab />}
        {tab === 'model' && <ModelTab />}
        {tab === 'metrics' && <MetricsTab />}
        {tab === 'guardrails' && <GuardrailsTab />}
        {tab === 'governance' && <GovernanceTab />}
        {tab === 'infra' && <InfraTab />}
      </motion.div>
    </div>
  )
}
