import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Wrench, Plus, Trash2, Edit3, Download, Check, ExternalLink,
  Search, ChevronRight, Loader2, Package, Settings2, Store,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/store/useStore'

const API = ''
function uid() {
  try { return localStorage.getItem('malife_user_id') ?? 'admin01' } catch { return 'admin01' }
}
async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'X-User-Id': uid(), 'Content-Type': 'application/json', ...opts.headers },
  })
  return r.json()
}

interface Skill {
  skill_name: string
  description: string
  endpoint: string
  method: string
  category: string
  params: Record<string, any>
  depends_on?: string[]
  body?: string
  installed?: boolean
}

type Tab = 'manage' | 'create' | 'marketplace'

const CATEGORY_COLORS: Record<string, string> = {
  search: 'rgba(59,130,246,0.15)',
  analysis: 'rgba(139,92,246,0.15)',
  report: 'rgba(34,197,94,0.15)',
  custom: 'rgba(243,112,33,0.15)',
}
const CATEGORY_TEXT: Record<string, string> = {
  search: 'rgb(59,130,246)',
  analysis: 'rgb(139,92,246)',
  report: 'rgb(34,197,94)',
  custom: 'rgb(243,112,33)',
}

function SkillCard({ skill, onDelete, onEdit }: { skill: Skill; onDelete?: () => void; onEdit?: () => void }) {
  const catColor = CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.custom
  const catText = CATEGORY_TEXT[skill.category] || CATEGORY_TEXT.custom

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="panel p-4 hover:border-gold-500/30 transition-colors"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Wrench size={13} className="text-gold-500 shrink-0" />
            <span className="text-sm font-semibold text-surface-900 truncate">{skill.skill_name}</span>
            <span
              className="px-1.5 py-0.5 rounded text-2xs font-mono font-semibold"
              style={{ background: catColor, color: catText }}
            >
              {skill.category}
            </span>
          </div>
          <p className="text-xs text-surface-600 line-clamp-2">{skill.description}</p>
          <div className="flex items-center gap-2 mt-2 text-2xs font-mono text-surface-600">
            <span className="tag tag-gold">{skill.method}</span>
            <span className="truncate">{skill.endpoint}</span>
          </div>
          {Object.keys(skill.params || {}).length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {Object.entries(skill.params).map(([k, v]: [string, any]) => (
                <span key={k} className="px-1.5 py-0.5 rounded text-2xs font-mono bg-surface-200 text-surface-700">
                  {k}{v.required ? '*' : ''}: {v.type}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          {onEdit && (
            <button onClick={onEdit} className="w-7 h-7 rounded flex items-center justify-center text-surface-600 hover:text-gold-500 hover:bg-surface-200 transition-colors">
              <Edit3 size={13} />
            </button>
          )}
          {onDelete && (
            <button onClick={onDelete} className="w-7 h-7 rounded flex items-center justify-center text-surface-600 hover:text-status-error hover:bg-surface-200 transition-colors">
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  )
}

function MarketplaceCard({ skill, onInstall }: { skill: Skill & { installed: boolean }; onInstall: () => void }) {
  const catColor = CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.custom
  const catText = CATEGORY_TEXT[skill.category] || CATEGORY_TEXT.custom

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="panel p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Package size={13} className="text-gold-500 shrink-0" />
            <span className="text-sm font-semibold text-surface-900">{skill.skill_name}</span>
            <span className="px-1.5 py-0.5 rounded text-2xs font-mono font-semibold" style={{ background: catColor, color: catText }}>
              {skill.category}
            </span>
          </div>
          <p className="text-xs text-surface-600">{skill.description}</p>
        </div>
        {skill.installed ? (
          <span className="tag tag-success flex items-center gap-1"><Check size={10} /> 설치됨</span>
        ) : (
          <button onClick={onInstall} className="btn-primary text-xs flex items-center gap-1 py-1 px-3">
            <Download size={12} /> 설치
          </button>
        )}
      </div>
    </motion.div>
  )
}

export default function Skills() {
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('manage')
  const [skills, setSkills] = useState<Skill[]>([])
  const [marketplace, setMarketplace] = useState<(Skill & { installed: boolean })[]>([])
  const [loading, setLoading] = useState(false)

  // Create form
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formEndpoint, setFormEndpoint] = useState('http://localhost:9001/')
  const [formMethod, setFormMethod] = useState('POST')
  const [formCategory, setFormCategory] = useState('custom')
  const [formParams, setFormParams] = useState('')
  const [formBody, setFormBody] = useState('')

  const fetchSkills = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api('/api/v1/skills/list')
      setSkills(data.skills || [])
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  const fetchMarketplace = useCallback(async () => {
    try {
      const data = await api('/api/v1/skills/marketplace')
      setMarketplace(data.skills || [])
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchSkills()
    fetchMarketplace()
  }, [fetchSkills, fetchMarketplace])

  async function handleCreate() {
    if (!formName || !formDesc || !formEndpoint) {
      toast.error('필수 항목 누락', 'skill_name, description, endpoint는 필수입니다')
      return
    }
    let params = {}
    if (formParams.trim()) {
      try { params = JSON.parse(formParams) } catch { toast.error('파라미터 JSON 오류', ''); return }
    }
    await api('/api/v1/skills/create', {
      method: 'POST',
      body: JSON.stringify({
        skill_name: formName, description: formDesc, endpoint: formEndpoint,
        method: formMethod, category: formCategory, params, body: formBody,
      }),
    })
    toast.success('스킬 생성', formName)
    setFormName(''); setFormDesc(''); setFormParams(''); setFormBody('')
    fetchSkills()
    fetchMarketplace()
    setTab('manage')
  }

  async function handleDelete(name: string) {
    await api(`/api/v1/skills/delete/${name}`, { method: 'DELETE' })
    toast.success('스킬 삭제', name)
    fetchSkills()
    fetchMarketplace()
  }

  async function handleInstall(name: string) {
    await api(`/api/v1/skills/marketplace/install/${name}`, { method: 'POST' })
    toast.success('스킬 설치', name)
    fetchSkills()
    fetchMarketplace()
  }

  const tabs: { id: Tab; label: string; icon: typeof Wrench }[] = [
    { id: 'manage', label: '스킬 관리', icon: Settings2 },
    { id: 'create', label: '스킬 만들기', icon: Plus },
    { id: 'marketplace', label: '마켓플레이스', icon: Store },
  ]

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">스킬</h2>
        <p className="text-sm text-surface-600">에이전트가 사용하는 도구를 정의하고 관리합니다.</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-semibold transition-colors',
              tab === id ? 'bg-gold-500 text-surface-DEFAULT' : 'text-surface-600 hover:text-surface-800',
            )}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* Manage tab */}
      {tab === 'manage' && (
        <div className="space-y-3">
          {loading ? (
            <div className="text-center py-12"><Loader2 size={20} className="animate-spin text-gold-500 mx-auto" /></div>
          ) : skills.length === 0 ? (
            <div className="text-center py-12">
              <Wrench size={24} className="text-surface-600 mx-auto mb-2" />
              <p className="text-sm text-surface-600 mb-3">설치된 스킬이 없습니다</p>
              <button onClick={() => setTab('marketplace')} className="btn-primary text-xs">마켓플레이스에서 설치</button>
            </div>
          ) : (
            <AnimatePresence>
              {skills.map((s) => (
                <SkillCard key={s.skill_name} skill={s} onDelete={() => handleDelete(s.skill_name)} />
              ))}
            </AnimatePresence>
          )}
        </div>
      )}

      {/* Create tab */}
      {tab === 'create' && (
        <div className="panel p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">스킬 이름 *</label>
              <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="my-skill" className="input-field w-full mt-1 font-mono text-xs" />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">카테고리</label>
              <select value={formCategory} onChange={(e) => setFormCategory(e.target.value)} className="input-field w-full mt-1 text-xs">
                <option value="custom">커스텀</option>
                <option value="search">검색</option>
                <option value="analysis">분석</option>
                <option value="report">리포트</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">설명 *</label>
            <input value={formDesc} onChange={(e) => setFormDesc(e.target.value)} placeholder="이 스킬이 하는 일을 설명하세요" className="input-field w-full mt-1 text-xs" />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2">
              <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">엔드포인트 *</label>
              <input value={formEndpoint} onChange={(e) => setFormEndpoint(e.target.value)} placeholder="http://..." className="input-field w-full mt-1 font-mono text-xs" />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">메서드</label>
              <select value={formMethod} onChange={(e) => setFormMethod(e.target.value)} className="input-field w-full mt-1 text-xs">
                <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">파라미터 (JSON)</label>
            <textarea
              value={formParams}
              onChange={(e) => setFormParams(e.target.value)}
              placeholder='{"query": {"type": "string", "description": "검색어", "required": true}}'
              rows={3}
              className="input-field w-full mt-1 font-mono text-xs resize-none"
            />
          </div>
          <div>
            <label className="text-2xs font-mono text-surface-600 uppercase tracking-widest">본문 설명 (마크다운)</label>
            <textarea value={formBody} onChange={(e) => setFormBody(e.target.value)} rows={3} placeholder="스킬에 대한 상세 설명..." className="input-field w-full mt-1 text-xs resize-none" />
          </div>
          <button onClick={handleCreate} className="btn-primary flex items-center gap-2 text-sm w-full justify-center">
            <Plus size={14} /> 스킬 생성
          </button>
        </div>
      )}

      {/* Marketplace tab */}
      {tab === 'marketplace' && (
        <div className="space-y-3">
          <p className="text-xs text-surface-600">사전 정의된 스킬을 한 클릭으로 설치합니다.</p>
          <AnimatePresence>
            {marketplace.map((s) => (
              <MarketplaceCard key={s.skill_name} skill={s} onInstall={() => handleInstall(s.skill_name)} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
