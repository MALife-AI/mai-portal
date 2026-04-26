import { useState, useEffect, useCallback, useId } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Wrench, Plus, Trash2, Edit3, Download, Check,
  ChevronRight, Loader2, Package, Settings2, Store, X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/store/useStore'
import { getUserId } from '@/api/client'

const EASE: [number, number, number, number] = [0.23, 1, 0.32, 1]

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

// 카테고리 색상 — 의미 기반 토큰 사용
const CATEGORY_COLOR: Record<string, string> = {
  search: 'var(--color-blue)',
  analysis: '#8B5CF6',
  report: 'var(--color-success)',
  custom: 'var(--color-gold)',
}

const CATEGORY_LABELS: Record<string, string> = {
  search: '검색',
  analysis: '분석',
  report: '리포트',
  custom: '커스텀',
}

function SkillCard({ skill, onDelete, onEdit, showApi }: { skill: Skill; onDelete?: () => void; onEdit?: () => void; showApi?: boolean }) {
  const color = CATEGORY_COLOR[skill.category] || CATEGORY_COLOR.custom
  const displayName = skill.display_name || skill.skill_name

  return (
    <motion.article
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE }}
      className="panel p-4 hover:border-gold-500/30"
      style={{ transition: 'border-color 200ms var(--ease-out)' }}
      aria-labelledby={`skill-${skill.skill_name}-name`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Wrench size={13} className="text-gold-500 shrink-0" aria-hidden="true" />
            <span
              id={`skill-${skill.skill_name}-name`}
              className="text-sm font-semibold text-surface-900 truncate"
            >
              {displayName}
            </span>
            <span
              className="px-1.5 py-0.5 rounded text-2xs font-semibold"
              style={{
                background: `color-mix(in srgb, ${color} 15%, transparent)`,
                color,
              }}
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
                <ul className="flex flex-wrap gap-1 mt-2" aria-label="파라미터">
                  {Object.entries(skill.params).map(([k, v]: [string, any]) => (
                    <li
                      key={k}
                      className="px-1.5 py-0.5 rounded text-2xs font-mono bg-surface-200 text-surface-700"
                    >
                      {k}{v.required ? '*' : ''}: {v.type}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex items-center justify-center rounded text-surface-600 hover:text-gold-500 hover:bg-surface-200"
              style={{
                width: '28px',
                height: '28px',
                transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
              }}
              aria-label={`${displayName} 편집`}
            >
              <Edit3 size={13} aria-hidden="true" />
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              className="inline-flex items-center justify-center rounded text-surface-600 hover:text-status-error hover:bg-surface-200"
              style={{
                width: '28px',
                height: '28px',
                transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
              }}
              aria-label={`${displayName} 삭제`}
            >
              <Trash2 size={13} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </motion.article>
  )
}

function MarketplaceCard({ skill, onInstall }: { skill: Skill & { installed: boolean }; onInstall: () => void }) {
  const color = CATEGORY_COLOR[skill.category] || CATEGORY_COLOR.custom
  const displayName = skill.display_name || skill.skill_name

  return (
    <motion.article
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE }}
      className="panel p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Package size={13} className="text-gold-500 shrink-0" aria-hidden="true" />
            <span className="text-sm font-semibold text-surface-900">{displayName}</span>
            <span
              className="px-1.5 py-0.5 rounded text-2xs font-mono font-semibold"
              style={{
                background: `color-mix(in srgb, ${color} 15%, transparent)`,
                color,
              }}
            >
              {skill.category}
            </span>
          </div>
          <p className="text-xs text-surface-600">{skill.description}</p>
          <p className="text-2xs text-surface-500 font-mono mt-1">{skill.skill_name}</p>
        </div>
        {skill.installed ? (
          <span className="tag tag-success flex items-center gap-1" aria-label="설치됨">
            <Check size={10} aria-hidden="true" /> 설치됨
          </span>
        ) : (
          <button
            type="button"
            onClick={onInstall}
            className="btn-primary text-xs flex items-center gap-1 py-1 px-3"
            aria-label={`${displayName} 설치`}
          >
            <Download size={12} aria-hidden="true" /> 설치
          </button>
        )}
      </div>
    </motion.article>
  )
}

function SkillEditorModal({
  editSkill,
  setEditSkill,
  editParams,
  setEditParams,
  onSave,
}: {
  editSkill: Skill
  setEditSkill: (s: Skill | null) => void
  editParams: Array<{ name: string; type: string; description: string; required: boolean }>
  setEditParams: (p: Array<{ name: string; type: string; description: string; required: boolean }>) => void
  onSave: () => void
}) {
  const titleId = useId()
  const descId = useId()
  const endpointId = useId()
  const methodId = useId()
  const categoryId = useId()
  const bodyId = useId()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setEditSkill(null)
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [setEditSkill])

  return (
    <div
      className="modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) setEditSkill(null) }}
    >
      <div
        className="modal-box"
        style={{ maxWidth: 560 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 id={titleId} className="text-sm font-semibold text-surface-900">
            스킬 편집: {editSkill.display_name || editSkill.skill_name}
          </h3>
          <button
            type="button"
            onClick={() => setEditSkill(null)}
            className="inline-flex items-center justify-center rounded text-surface-600 hover:text-surface-900 hover:bg-surface-200"
            style={{
              width: '32px',
              height: '32px',
              transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
            }}
            aria-label="편집 닫기"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
          {/* 설명 */}
          <div>
            <label htmlFor={descId} className="text-2xs text-surface-600">설명</label>
            <input
              id={descId}
              value={editSkill.description}
              onChange={e => setEditSkill({ ...editSkill, description: e.target.value })}
              className="input-field w-full mt-1 text-xs"
            />
          </div>

          {/* 엔드포인트 + 메서드 */}
          <div className="grid grid-cols-4 gap-2">
            <div className="col-span-3">
              <label htmlFor={endpointId} className="text-2xs text-surface-600">엔드포인트</label>
              <input
                id={endpointId}
                value={editSkill.endpoint}
                onChange={e => setEditSkill({ ...editSkill, endpoint: e.target.value })}
                className="input-field w-full mt-1 font-mono text-xs"
                autoComplete="off"
              />
            </div>
            <div>
              <label htmlFor={methodId} className="text-2xs text-surface-600">메서드</label>
              <select
                id={methodId}
                value={editSkill.method}
                onChange={e => setEditSkill({ ...editSkill, method: e.target.value })}
                className="input-field w-full mt-1 text-xs"
              >
                <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
              </select>
            </div>
          </div>

          {/* 카테고리 */}
          <div>
            <label htmlFor={categoryId} className="text-2xs text-surface-600">카테고리</label>
            <select
              id={categoryId}
              value={editSkill.category}
              onChange={e => setEditSkill({ ...editSkill, category: e.target.value })}
              className="input-field w-full mt-1 text-xs"
            >
              <option value="custom">커스텀</option>
              <option value="search">검색</option>
              <option value="analysis">분석</option>
              <option value="report">리포트</option>
            </select>
          </div>

          {/* 파라미터 (노코드 에디터) */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-2xs text-surface-600">파라미터</span>
              <button
                type="button"
                onClick={() => setEditParams([...editParams, { name: '', type: 'string', description: '', required: false }])}
                className="btn-secondary text-2xs flex items-center gap-1"
                aria-label="파라미터 추가"
              >
                <Plus size={10} aria-hidden="true" /> 추가
              </button>
            </div>
            <ul className="space-y-2">
              {editParams.map((p, i) => (
                <li
                  key={i}
                  className="grid grid-cols-12 gap-1.5 items-center p-2 rounded"
                  style={{ background: 'var(--color-bg-primary)' }}
                >
                  <input
                    value={p.name}
                    onChange={e => { const c = [...editParams]; if (c[i]) c[i]!.name = e.target.value; setEditParams(c) }}
                    placeholder="이름"
                    className="input-field text-2xs font-mono col-span-3"
                    aria-label={`파라미터 ${i + 1} 이름`}
                  />
                  <select
                    value={p.type}
                    onChange={e => { const c = [...editParams]; if (c[i]) c[i]!.type = e.target.value; setEditParams(c) }}
                    className="input-field text-2xs col-span-2"
                    aria-label={`파라미터 ${i + 1} 타입`}
                  >
                    <option value="string">string</option>
                    <option value="integer">integer</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                    <option value="array">array</option>
                    <option value="object">object</option>
                  </select>
                  <input
                    value={p.description}
                    onChange={e => { const c = [...editParams]; if (c[i]) c[i]!.description = e.target.value; setEditParams(c) }}
                    placeholder="설명"
                    className="input-field text-2xs col-span-4"
                    aria-label={`파라미터 ${i + 1} 설명`}
                  />
                  <label className="col-span-2 flex items-center gap-1 text-2xs text-surface-600 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={p.required}
                      onChange={e => { const c = [...editParams]; if (c[i]) c[i]!.required = e.target.checked; setEditParams(c) }}
                      className="accent-gold-500"
                    /> 필수
                  </label>
                  <button
                    type="button"
                    onClick={() => setEditParams(editParams.filter((_, j) => j !== i))}
                    className="col-span-1 inline-flex items-center justify-center text-surface-600 hover:text-status-error"
                    style={{ transition: 'color 200ms var(--ease-out)' }}
                    aria-label={`파라미터 ${i + 1} 제거`}
                  >
                    <Trash2 size={11} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* 본문 */}
          <div>
            <label htmlFor={bodyId} className="text-2xs text-surface-600">본문 설명</label>
            <textarea
              id={bodyId}
              value={editSkill.body || ''}
              onChange={e => setEditSkill({ ...editSkill, body: e.target.value })}
              rows={3}
              className="input-field w-full mt-1 text-xs resize-none"
            />
          </div>
        </div>

        <div className="flex gap-2 mt-4">
          <button
            type="button"
            onClick={() => setEditSkill(null)}
            className="btn-secondary flex-1 text-xs"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onSave}
            className="btn-primary flex-1 text-xs flex items-center justify-center gap-1"
          >
            <Check size={12} aria-hidden="true" /> 저장
          </button>
        </div>
      </div>
    </div>
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

  // ids
  const showApiId = useId()
  const formNameId = useId()
  const formDisplayId = useId()
  const formDescId = useId()
  const formBodyId = useId()
  const formEndpointId = useId()
  const formMethodId = useId()
  const formCategoryId = useId()
  const formParamsId = useId()

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

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!formName || !formDesc) {
      toast.error('필수 항목 누락', '스킬 ID와 설명은 필수입니다')
      return
    }
    let params = {}
    if (formParams.trim()) {
      try { params = JSON.parse(formParams) } catch { toast.error('파라미터 JSON 오류', ''); return }
    }
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

  function handleTabKey(e: React.KeyboardEvent, currentIdx: number) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const delta = e.key === 'ArrowRight' ? 1 : -1
    const next = (currentIdx + delta + tabs.length) % tabs.length
    setTab(tabs[next]!.id)
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">스킬</h2>
        <p className="text-sm text-surface-600">에이전트가 사용하는 도구를 정의하고 관리합니다.</p>
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="스킬 섹션"
        className="flex gap-1 p-1 rounded-lg"
        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
      >
        {tabs.map(({ id, label, icon: Icon }, idx) => {
          const selected = tab === id
          return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`skills-tab-${id}`}
              aria-selected={selected}
              aria-controls={`skills-panel-${id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setTab(id)}
              onKeyDown={(e) => handleTabKey(e, idx)}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-semibold',
                selected ? 'bg-gold-500 text-surface-DEFAULT' : 'text-surface-600 hover:text-surface-800',
              )}
              style={{
                minHeight: '36px',
                transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)',
              }}
            >
              <Icon size={14} aria-hidden="true" /> {label}
            </button>
          )
        })}
      </div>

      {/* Manage tab */}
      {tab === 'manage' && (
        <div
          role="tabpanel"
          id="skills-panel-manage"
          aria-labelledby="skills-tab-manage"
          className="space-y-3"
        >
          <div className="flex items-center justify-end">
            <label htmlFor={showApiId} className="flex items-center gap-2 cursor-pointer text-xs text-surface-600">
              <input
                id={showApiId}
                type="checkbox"
                checked={showApi}
                onChange={e => setShowApi(e.target.checked)}
                className="accent-gold-500"
              />
              API 연동 정보 표시
            </label>
          </div>
          {loading ? (
            <div
              className="text-center py-12"
              role="status"
              aria-label="스킬 목록 불러오는 중"
            >
              <Loader2 size={20} className="animate-spin text-gold-500 mx-auto" aria-hidden="true" />
            </div>
          ) : skills.length === 0 ? (
            <div className="text-center py-12">
              <Wrench size={24} className="text-surface-600 mx-auto mb-2" aria-hidden="true" />
              <p className="text-sm text-surface-600 mb-3">설치된 스킬이 없습니다</p>
              <button
                type="button"
                onClick={() => setTab('marketplace')}
                className="btn-primary text-xs"
              >
                마켓플레이스에서 설치
              </button>
            </div>
          ) : (
            <ul className="space-y-3" aria-label={`설치된 스킬 ${skills.length}개`}>
              <AnimatePresence initial={false}>
                {skills.map((s) => (
                  <li key={s.skill_name}>
                    <SkillCard
                      skill={s}
                      showApi={showApi}
                      onEdit={() => openEditor(s)}
                      onDelete={() => handleDelete(s.skill_name)}
                    />
                  </li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </div>
      )}

      {/* Create tab */}
      {tab === 'create' && (
        <form
          onSubmit={handleCreate}
          role="tabpanel"
          id="skills-panel-create"
          aria-labelledby="skills-tab-create"
          className="panel p-5 space-y-4"
        >
          <p className="text-xs text-surface-600">에이전트가 호출할 스킬을 생성합니다. 엔드포인트 없이 만들면 에이전트가 LLM 내부에서 처리합니다.</p>

          {/* 기본 설정 */}
          <div>
            <label htmlFor={formDisplayId} className="text-xs font-semibold text-surface-800">
              스킬 표시명 <span className="text-status-error" aria-label="필수">*</span>
            </label>
            <input
              id={formDisplayId}
              value={formDisplayName}
              onChange={(e) => setFormDisplayName(e.target.value)}
              placeholder="예: 보험료 산출"
              className="input-field w-full mt-1 text-sm"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor={formNameId} className="text-xs font-semibold text-surface-800">
                스킬 ID <span className="text-status-error" aria-label="필수">*</span>
              </label>
              <input
                id={formNameId}
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="예: calculate-premium"
                className="input-field w-full mt-1 font-mono text-xs"
                autoComplete="off"
                pattern="[a-z0-9-]+"
                aria-describedby={`${formNameId}-hint`}
                required
              />
              <p id={`${formNameId}-hint`} className="text-2xs text-surface-600 mt-0.5">
                영문, 하이픈만 사용
              </p>
            </div>
            <div>
              <label htmlFor={formCategoryId} className="text-xs font-semibold text-surface-800">
                카테고리
              </label>
              <select
                id={formCategoryId}
                value={formCategory}
                onChange={(e) => setFormCategory(e.target.value)}
                className="input-field w-full mt-1 text-sm"
              >
                <option value="custom">커스텀</option>
                <option value="search">검색</option>
                <option value="analysis">분석</option>
                <option value="report">리포트</option>
              </select>
            </div>
          </div>
          <div>
            <label htmlFor={formDescId} className="text-xs font-semibold text-surface-800">
              설명 <span className="text-status-error" aria-label="필수">*</span>
            </label>
            <textarea
              id={formDescId}
              value={formDesc}
              onChange={(e) => setFormDesc(e.target.value)}
              placeholder="이 스킬이 하는 일을 구체적으로 설명하세요. LLM이 이 설명을 보고 호출 여부를 판단합니다."
              rows={2}
              className="input-field w-full mt-1 text-sm resize-none"
              required
            />
          </div>
          <div>
            <label htmlFor={formBodyId} className="text-xs font-semibold text-surface-800">상세 설명</label>
            <textarea
              id={formBodyId}
              value={formBody}
              onChange={(e) => setFormBody(e.target.value)}
              rows={3}
              placeholder="스킬의 동작 방식, 사용 예시, 주의사항 등..."
              className="input-field w-full mt-1 text-sm resize-none"
            />
          </div>

          {/* 고급 설정 토글 */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-surface-600 hover:text-gold-500"
            style={{ transition: 'color 200ms var(--ease-out)' }}
            aria-expanded={showAdvanced}
            aria-controls="advanced-settings"
          >
            <ChevronRight
              size={12}
              className={cn(showAdvanced && 'rotate-90')}
              style={{ transition: 'transform 200ms var(--ease-out)' }}
              aria-hidden="true"
            />
            고급 설정 (외부 API 연동)
          </button>

          <AnimatePresence initial={false}>
            {showAdvanced && (
              <motion.div
                id="advanced-settings"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: EASE }}
                style={{ overflow: 'hidden' }}
              >
                <div className="space-y-3 pl-4" style={{ borderLeft: '2px solid var(--color-border)' }}>
                  <p className="text-2xs text-surface-600">
                    외부 API 엔드포인트를 지정하면 에이전트가 해당 API를 호출합니다. 비우면 LLM이 내부에서 처리합니다.
                  </p>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="col-span-2">
                      <label htmlFor={formEndpointId} className="text-2xs text-surface-600">엔드포인트</label>
                      <input
                        id={formEndpointId}
                        value={formEndpoint}
                        onChange={(e) => setFormEndpoint(e.target.value)}
                        placeholder="http://..."
                        className="input-field w-full mt-1 font-mono text-xs"
                        autoComplete="off"
                      />
                    </div>
                    <div>
                      <label htmlFor={formMethodId} className="text-2xs text-surface-600">메서드</label>
                      <select
                        id={formMethodId}
                        value={formMethod}
                        onChange={(e) => setFormMethod(e.target.value)}
                        className="input-field w-full mt-1 text-xs"
                      >
                        <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label htmlFor={formParamsId} className="text-2xs text-surface-600">
                      파라미터 (JSON)
                    </label>
                    <textarea
                      id={formParamsId}
                      value={formParams}
                      onChange={(e) => setFormParams(e.target.value)}
                      placeholder='{"query": {"type": "string", "description": "검색어", "required": true}}'
                      rows={3}
                      className="input-field w-full mt-1 font-mono text-xs resize-none"
                      spellCheck={false}
                    />
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <button
            type="submit"
            className="btn-primary flex items-center gap-2 text-sm w-full justify-center"
          >
            <Plus size={14} aria-hidden="true" /> 스킬 생성
          </button>
        </form>
      )}

      {/* Marketplace tab */}
      {tab === 'marketplace' && (
        <div
          role="tabpanel"
          id="skills-panel-marketplace"
          aria-labelledby="skills-tab-marketplace"
          className="space-y-3"
        >
          <p className="text-xs text-surface-600">사전 정의된 스킬을 한 클릭으로 설치합니다.</p>
          {marketplace.length === 0 ? (
            <div className="text-center py-12 text-sm text-surface-600">
              마켓플레이스가 비어있습니다
            </div>
          ) : (
            <ul className="space-y-3" aria-label={`마켓플레이스 스킬 ${marketplace.length}개`}>
              <AnimatePresence initial={false}>
                {marketplace.map((s) => (
                  <li key={s.skill_name}>
                    <MarketplaceCard skill={s} onInstall={() => handleInstall(s.skill_name)} />
                  </li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </div>
      )}

      {/* 노코드 스킬 에디터 모달 */}
      {editSkill && (
        <SkillEditorModal
          editSkill={editSkill}
          setEditSkill={setEditSkill}
          editParams={editParams}
          setEditParams={setEditParams}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}
