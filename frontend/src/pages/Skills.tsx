import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Wrench, Plus, Trash2, Edit3, Download, Check, ExternalLink,
  Search, ChevronRight, Loader2, Package, Settings2, Store,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/store/useStore'
import { getUserId } from '@/api/client'

const API = ''
async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'X-User-Id': getUserId(), 'Content-Type': 'application/json', ...opts.headers },
  })
  return r.json()
}

interface Skill {
  skill_name: string
  display_name?: string
  description: string
  endpoint: string
  method: string
  category: string
  params: Record<string, any>
  inputs?: Record<string, any>
  outputs?: Record<string, any>
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

function SkillCard({ skill, onDelete, onEdit, showApi }: { skill: Skill; onDelete?: () => void; onEdit?: () => void; showApi?: boolean }) {
  const catColor = CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.custom
  const catText = CATEGORY_TEXT[skill.category] || CATEGORY_TEXT.custom

  const CATEGORY_LABELS: Record<string, string> = { search: '검색', analysis: '분석', report: '리포트', custom: '커스텀' }

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
            <span className="text-sm font-semibold text-surface-900 truncate">{skill.display_name || skill.skill_name}</span>
            <span
              className="px-1.5 py-0.5 rounded text-2xs font-semibold"
              style={{ background: catColor, color: catText }}
            >
              {CATEGORY_LABELS[skill.category] || skill.category}
            </span>
          </div>
          <p className="text-xs text-surface-700 line-clamp-2">{skill.description}</p>

          {showApi && (
            <>
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
            </>
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
  const [showApi, setShowApi] = useState(false)
  const [editSkill, setEditSkill] = useState<Skill | null>(null)

  // 노코드 에디터 상태
  const [editParams, setEditParams] = useState<Array<{ name: string; type: string; description: string; required: boolean }>>([])

  // Create form
  const [formName, setFormName] = useState('')
  const [formDisplayName, setFormDisplayName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formEndpoint, setFormEndpoint] = useState('')
  const [formMethod, setFormMethod] = useState('POST')
  const [formCategory, setFormCategory] = useState('custom')
  const [formParams, setFormParams] = useState('')
  const [formBody, setFormBody] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

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
    if (!formName || !formDesc) {
      toast.error('필수 항목 누락', '스킬 ID와 설명은 필수입니다')
      return
    }
    let params = {}
    if (formParams.trim()) {
      try { params = JSON.parse(formParams) } catch { toast.error('파라미터 JSON 오류', ''); return }
    }
    // 엔드포인트 없으면 기본 에이전트 내부 처리
    const endpoint = formEndpoint.trim() || `http://localhost:9001/api/v1/agent/run`
    const displayName = formDisplayName.trim() || formName

    await api('/api/v1/skills/create', {
      method: 'POST',
      body: JSON.stringify({
        skill_name: formName, description: `${displayName} — ${formDesc}`,
        endpoint, method: formMethod, category: formCategory, params, body: formBody,
      }),
    })
    toast.success('스킬 생성', displayName)
    setFormName(''); setFormDisplayName(''); setFormDesc(''); setFormParams(''); setFormBody(''); setFormEndpoint('')
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

  function openEditor(skill: Skill) {
    setEditSkill({ ...skill })
    const params = Object.entries(skill.params || {}).map(([name, v]: [string, any]) => ({
      name,
      type: v.type || 'string',
      description: v.description || '',
      required: v.required ?? false,
    }))
    setEditParams(params)
  }

  async function handleUpdate() {
    if (!editSkill) return
    const params: Record<string, any> = {}
    for (const p of editParams) {
      if (p.name.trim()) {
        params[p.name.trim()] = { type: p.type, description: p.description, required: p.required }
      }
    }
    await api(`/api/v1/skills/update/${editSkill.skill_name}`, {
      method: 'PUT',
      body: JSON.stringify({
        description: editSkill.description,
        endpoint: editSkill.endpoint,
        method: editSkill.method,
        category: editSkill.category,
        params,
        body: editSkill.body || '',
      }),
    })
    toast.success('스킬 수정', editSkill.skill_name)
    setEditSkill(null)
    fetchSkills()
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
          <div className="flex items-center justify-end">
            <label className="flex items-center gap-2 cursor-pointer text-xs text-surface-600">
              <input type="checkbox" checked={showApi} onChange={e => setShowApi(e.target.checked)} className="accent-gold-500" />
              API 연동 정보 표시
            </label>
          </div>
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
                <SkillCard key={s.skill_name} skill={s} showApi={showApi} onEdit={() => openEditor(s)} onDelete={() => handleDelete(s.skill_name)} />
              ))}
            </AnimatePresence>
          )}
        </div>
      )}

      {/* Create tab */}
      {tab === 'create' && (
        <div className="panel p-5 space-y-4">
          <p className="text-xs text-surface-600">에이전트가 호출할 스킬을 생성합니다. 엔드포인트 없이 만들면 에이전트가 LLM 내부에서 처리합니다.</p>

          {/* 기본 설정 */}
          <div>
            <label className="text-xs font-semibold text-surface-800">스킬 표시명 *</label>
            <input value={formDisplayName} onChange={(e) => setFormDisplayName(e.target.value)} placeholder="예: 보험료 산출" className="input-field w-full mt-1 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-surface-800">스킬 ID *</label>
              <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="예: calculate-premium" className="input-field w-full mt-1 font-mono text-xs" />
              <p className="text-2xs text-surface-600 mt-0.5">영문, 하이픈만 사용</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-surface-800">카테고리</label>
              <select value={formCategory} onChange={(e) => setFormCategory(e.target.value)} className="input-field w-full mt-1 text-sm">
                <option value="custom">커스텀</option>
                <option value="search">검색</option>
                <option value="analysis">분석</option>
                <option value="report">리포트</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-surface-800">설명 *</label>
            <textarea value={formDesc} onChange={(e) => setFormDesc(e.target.value)}
              placeholder="이 스킬이 하는 일을 구체적으로 설명하세요. LLM이 이 설명을 보고 호출 여부를 판단합니다."
              rows={2} className="input-field w-full mt-1 text-sm resize-none" />
          </div>
          <div>
            <label className="text-xs font-semibold text-surface-800">상세 설명</label>
            <textarea value={formBody} onChange={(e) => setFormBody(e.target.value)} rows={3}
              placeholder="스킬의 동작 방식, 사용 예시, 주의사항 등..."
              className="input-field w-full mt-1 text-sm resize-none" />
          </div>

          {/* 고급 설정 토글 */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-surface-600 hover:text-gold-500 transition-colors"
          >
            <ChevronRight size={12} className={cn('transition-transform', showAdvanced && 'rotate-90')} />
            고급 설정 (외부 API 연동)
          </button>

          {showAdvanced && (
            <div className="space-y-3 pl-4" style={{ borderLeft: '2px solid var(--color-border)' }}>
              <p className="text-2xs text-surface-600">외부 API 엔드포인트를 지정하면 에이전트가 해당 API를 호출합니다. 비우면 LLM이 내부에서 처리합니다.</p>
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="text-2xs text-surface-600">엔드포인트</label>
                  <input value={formEndpoint} onChange={(e) => setFormEndpoint(e.target.value)} placeholder="http://..." className="input-field w-full mt-1 font-mono text-xs" />
                </div>
                <div>
                  <label className="text-2xs text-surface-600">메서드</label>
                  <select value={formMethod} onChange={(e) => setFormMethod(e.target.value)} className="input-field w-full mt-1 text-xs">
                    <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-2xs text-surface-600">파라미터 (JSON)</label>
                <textarea
                  value={formParams}
                  onChange={(e) => setFormParams(e.target.value)}
                  placeholder='{"query": {"type": "string", "description": "검색어", "required": true}}'
                  rows={3}
                  className="input-field w-full mt-1 font-mono text-xs resize-none"
                />
              </div>
            </div>
          )}
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

      {/* 노코드 스킬 에디터 모달 */}
      {editSkill && (
        <div className="modal-overlay" onClick={() => setEditSkill(null)}>
          <div className="modal-box" style={{ maxWidth: 560 }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-surface-900">스킬 편집: {editSkill.skill_name}</h3>
              <button onClick={() => setEditSkill(null)} className="text-surface-600 hover:text-surface-900">&times;</button>
            </div>

            <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
              {/* 설명 */}
              <div>
                <label className="text-2xs text-surface-600">설명</label>
                <input value={editSkill.description} onChange={e => setEditSkill({ ...editSkill, description: e.target.value })}
                  className="input-field w-full mt-1 text-xs" />
              </div>

              {/* 엔드포인트 + 메서드 */}
              <div className="grid grid-cols-4 gap-2">
                <div className="col-span-3">
                  <label className="text-2xs text-surface-600">엔드포인트</label>
                  <input value={editSkill.endpoint} onChange={e => setEditSkill({ ...editSkill, endpoint: e.target.value })}
                    className="input-field w-full mt-1 font-mono text-xs" />
                </div>
                <div>
                  <label className="text-2xs text-surface-600">메서드</label>
                  <select value={editSkill.method} onChange={e => setEditSkill({ ...editSkill, method: e.target.value })}
                    className="input-field w-full mt-1 text-xs">
                    <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
                  </select>
                </div>
              </div>

              {/* 카테고리 */}
              <div>
                <label className="text-2xs text-surface-600">카테고리</label>
                <select value={editSkill.category} onChange={e => setEditSkill({ ...editSkill, category: e.target.value })}
                  className="input-field w-full mt-1 text-xs">
                  <option value="custom">커스텀</option>
                  <option value="search">검색</option>
                  <option value="analysis">분석</option>
                  <option value="report">리포트</option>
                </select>
              </div>

              {/* 파라미터 (노코드 에디터) */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-2xs text-surface-600">파라미터</label>
                  <button onClick={() => setEditParams([...editParams, { name: '', type: 'string', description: '', required: false }])}
                    className="btn-secondary text-2xs flex items-center gap-1"><Plus size={10} /> 추가</button>
                </div>
                <div className="space-y-2">
                  {editParams.map((p, i) => (
                    <div key={i} className="grid grid-cols-12 gap-1.5 items-center p-2 rounded" style={{ background: 'var(--color-bg-primary)' }}>
                      <input value={p.name} onChange={e => { const c = [...editParams]; c[i].name = e.target.value; setEditParams(c) }}
                        placeholder="이름" className="input-field text-2xs font-mono col-span-3" />
                      <select value={p.type} onChange={e => { const c = [...editParams]; c[i].type = e.target.value; setEditParams(c) }}
                        className="input-field text-2xs col-span-2">
                        <option value="string">string</option>
                        <option value="integer">integer</option>
                        <option value="number">number</option>
                        <option value="boolean">boolean</option>
                        <option value="array">array</option>
                        <option value="object">object</option>
                      </select>
                      <input value={p.description} onChange={e => { const c = [...editParams]; c[i].description = e.target.value; setEditParams(c) }}
                        placeholder="설명" className="input-field text-2xs col-span-4" />
                      <label className="col-span-2 flex items-center gap-1 text-2xs text-surface-600 cursor-pointer">
                        <input type="checkbox" checked={p.required} onChange={e => { const c = [...editParams]; c[i].required = e.target.checked; setEditParams(c) }}
                          className="accent-gold-500" /> 필수
                      </label>
                      <button onClick={() => setEditParams(editParams.filter((_, j) => j !== i))}
                        className="col-span-1 text-surface-600 hover:text-status-error"><Trash2 size={11} /></button>
                    </div>
                  ))}
                </div>
              </div>

              {/* 본문 */}
              <div>
                <label className="text-2xs text-surface-600">본문 설명</label>
                <textarea value={editSkill.body || ''} onChange={e => setEditSkill({ ...editSkill, body: e.target.value })}
                  rows={3} className="input-field w-full mt-1 text-xs resize-none" />
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button onClick={() => setEditSkill(null)} className="btn-secondary flex-1 text-xs">취소</button>
              <button onClick={handleUpdate} className="btn-primary flex-1 text-xs flex items-center justify-center gap-1">
                <Check size={12} /> 저장
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
