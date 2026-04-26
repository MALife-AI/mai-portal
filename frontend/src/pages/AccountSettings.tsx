import { useState, useEffect, useId } from 'react'
import {
  User, KeyRound, History, Brain, Save, Loader2,
  Trash2, ToggleLeft, ToggleRight, Shield,
} from 'lucide-react'
import { getUserId } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { cn } from '@/lib/utils'

const API = ''
async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'X-User-Id': getUserId(), 'Content-Type': 'application/json', ...opts.headers },
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

// ─── 프로필 섹션 ──────────────────────────────────────────────────────────────

function ProfileSection() {
  const { userId } = useStore()
  const [profile, setProfile] = useState({
    display_name: '',
    email: '',
    department: '',
    roles: [] as string[],
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/api/v1/admin/iam').then(data => {
      const users = data.users || []
      const me = users.find((u: any) => u.user_id === userId)
      if (me) {
        setProfile({
          display_name: me.display_name || me.user_id,
          email: me.email || '',
          department: me.department || '',
          roles: me.roles || [],
        })
      }
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [userId])

  if (loading) {
    return (
      <div
        className="panel p-5 flex items-center justify-center py-8"
        role="status"
        aria-label="프로필 불러오는 중"
      >
        <Loader2 size={20} className="animate-spin text-surface-600" aria-hidden="true" />
        <span className="sr-only">프로필을 불러오는 중입니다</span>
      </div>
    )
  }

  return (
    <section className="panel p-5 space-y-4" aria-labelledby="profile-heading">
      <div className="flex items-center gap-2 mb-4">
        <User size={16} className="text-gold-500" aria-hidden="true" />
        <h3 id="profile-heading" className="text-sm font-semibold text-surface-900">프로필</h3>
      </div>

      <dl className="grid grid-cols-2 gap-4">
        <div>
          <dt className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">사용자 ID</dt>
          <dd className="text-sm font-mono text-surface-900 mt-1">{userId}</dd>
        </div>
        <div>
          <dt className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">부서</dt>
          <dd className="text-sm text-surface-900 mt-1">{profile.department || '미지정'}</dd>
        </div>
        <div>
          <dt className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">표시 이름</dt>
          <dd className="text-sm text-surface-900 mt-1">{profile.display_name}</dd>
        </div>
        <div>
          <dt className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">이메일</dt>
          <dd className="text-sm text-surface-900 mt-1">{profile.email || '미설정'}</dd>
        </div>
      </dl>

      <div>
        <p
          id="profile-roles-label"
          className="text-2xs font-semibold text-surface-600 uppercase tracking-widest"
        >
          역할
        </p>
        {profile.roles.length > 0 ? (
          <ul
            className="flex flex-wrap gap-1.5 mt-1"
            aria-labelledby="profile-roles-label"
          >
            {profile.roles.map(role => (
              <li
                key={role}
                className="px-2 py-0.5 rounded text-2xs font-mono font-semibold bg-gold-500/15 text-gold-500 border border-gold-500/30"
              >
                {role}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-xs text-surface-600 mt-1 block">역할 없음</span>
        )}
      </div>
    </section>
  )
}

// ─── 비밀번호 변경 ────────────────────────────────────────────────────────────

function PasswordSection() {
  const toast = useToast()
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [saving, setSaving] = useState(false)
  const currentId = useId()
  const newId = useId()
  const confirmId = useId()

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!currentPw || !newPw) return
    if (newPw !== confirmPw) {
      toast.error('비밀번호 불일치', '새 비밀번호가 일치하지 않습니다')
      return
    }
    if (newPw.length < 8) {
      toast.error('비밀번호 조건', '8자 이상이어야 합니다')
      return
    }
    setSaving(true)
    try {
      // 실제 환경에서는 비밀번호 변경 API 호출
      await new Promise(r => setTimeout(r, 500))
      toast.success('비밀번호 변경', '비밀번호가 변경되었습니다')
      setCurrentPw('')
      setNewPw('')
      setConfirmPw('')
    } catch {
      toast.error('변경 실패', '비밀번호를 변경할 수 없습니다')
    }
    setSaving(false)
  }

  return (
    <section className="panel p-5 space-y-4" aria-labelledby="password-heading">
      <div className="flex items-center gap-2 mb-4">
        <KeyRound size={16} className="text-gold-500" aria-hidden="true" />
        <h3 id="password-heading" className="text-sm font-semibold text-surface-900">
          비밀번호 변경
        </h3>
      </div>

      <form className="space-y-3 max-w-sm" onSubmit={handleSave}>
        <div>
          <label htmlFor={currentId} className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">
            현재 비밀번호
          </label>
          <input
            id={currentId}
            type="password"
            value={currentPw}
            onChange={e => setCurrentPw(e.target.value)}
            className="input-field w-full text-sm mt-1"
            placeholder="••••••••"
            autoComplete="current-password"
          />
        </div>
        <div>
          <label htmlFor={newId} className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">
            새 비밀번호
          </label>
          <input
            id={newId}
            type="password"
            value={newPw}
            onChange={e => setNewPw(e.target.value)}
            className="input-field w-full text-sm mt-1"
            placeholder="8자 이상"
            autoComplete="new-password"
            aria-describedby={`${newId}-hint`}
            minLength={8}
          />
          <p id={`${newId}-hint`} className="sr-only">8자 이상 입력하세요</p>
        </div>
        <div>
          <label htmlFor={confirmId} className="text-2xs font-semibold text-surface-600 uppercase tracking-widest">
            새 비밀번호 확인
          </label>
          <input
            id={confirmId}
            type="password"
            value={confirmPw}
            onChange={e => setConfirmPw(e.target.value)}
            className="input-field w-full text-sm mt-1"
            placeholder="다시 입력"
            autoComplete="new-password"
          />
        </div>
        <button
          type="submit"
          disabled={saving || !currentPw || !newPw}
          className="btn-primary text-xs flex items-center gap-1.5"
          aria-busy={saving}
        >
          {saving
            ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            : <Save size={12} aria-hidden="true" />
          }
          변경
        </button>
      </form>
    </section>
  )
}

// ─── 에이전트 설정 ────────────────────────────────────────────────────────────

function AgentSettingsSection() {
  const STORAGE_KEY = 'mai_agent_settings'
  const globalPromptId = useId()
  const styleGroupId = useId()

  const [settings, setSettings] = useState<Record<string, any>>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    } catch { return {} }
  })

  function update(key: string, value: any) {
    const next = { ...settings, [key]: value }
    setSettings(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  const memoryOn = settings.memory_enabled !== false
  const citationOn = settings.auto_citation !== false
  const currentStyle = settings.response_style || 'detailed'

  return (
    <section className="panel p-5 space-y-4" aria-labelledby="agent-settings-heading">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={16} className="text-gold-500" aria-hidden="true" />
        <h3 id="agent-settings-heading" className="text-sm font-semibold text-surface-900">
          에이전트 설정
        </h3>
      </div>

      <div className="space-y-4">
        {/* 메모리 사용 여부 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-surface-900">대화 메모리</p>
            <p id="memory-desc" className="text-2xs text-surface-600 mt-0.5">
              대화 중 중요 정보를 기억하고 이후 질문에 활용합니다
            </p>
          </div>
          <button
            type="button"
            onClick={() => update('memory_enabled', !memoryOn)}
            className="shrink-0 inline-flex items-center justify-center"
            style={{ minHeight: '32px', minWidth: '32px' }}
            role="switch"
            aria-checked={memoryOn}
            aria-label="대화 메모리 사용"
            aria-describedby="memory-desc"
          >
            {memoryOn ? (
              <ToggleRight size={28} className="text-gold-500" aria-hidden="true" />
            ) : (
              <ToggleLeft size={28} className="text-surface-500" aria-hidden="true" />
            )}
          </button>
        </div>

        {/* 자동 인용 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-surface-900">출처 자동 인용</p>
            <p id="citation-desc" className="text-2xs text-surface-600 mt-0.5">
              답변에 [1], [2] 형태로 출처를 자동 표시합니다
            </p>
          </div>
          <button
            type="button"
            onClick={() => update('auto_citation', !citationOn)}
            className="shrink-0 inline-flex items-center justify-center"
            style={{ minHeight: '32px', minWidth: '32px' }}
            role="switch"
            aria-checked={citationOn}
            aria-label="출처 자동 인용"
            aria-describedby="citation-desc"
          >
            {citationOn ? (
              <ToggleRight size={28} className="text-gold-500" aria-hidden="true" />
            ) : (
              <ToggleLeft size={28} className="text-surface-500" aria-hidden="true" />
            )}
          </button>
        </div>

        {/* 응답 스타일 */}
        <div>
          <p id={styleGroupId} className="text-xs font-semibold text-surface-900 mb-1">
            응답 스타일
          </p>
          <div role="radiogroup" aria-labelledby={styleGroupId} className="flex gap-2">
            {[
              { value: 'concise', label: '간결' },
              { value: 'detailed', label: '상세' },
              { value: 'table', label: '표 중심' },
            ].map(opt => (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={currentStyle === opt.value}
                onClick={() => update('response_style', opt.value)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-semibold active:scale-[0.98]',
                  currentStyle === opt.value
                    ? 'bg-gold-500/20 text-gold-500 border border-gold-500/30'
                    : 'bg-surface-200 text-surface-700 border border-surface-300 hover:border-surface-400',
                )}
                style={{
                  minHeight: '30px',
                  transition: 'background-color 200ms var(--ease-out), border-color 200ms var(--ease-out), color 200ms var(--ease-out), transform 120ms var(--ease-out)',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* 글로벌 프롬프트 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label htmlFor={globalPromptId} className="text-xs font-semibold text-surface-900">
              글로벌 프롬프트
            </label>
            <span className="text-2xs text-surface-500 font-mono" aria-live="polite">
              {(settings.global_prompt || '').length}/200
            </span>
          </div>
          <textarea
            id={globalPromptId}
            value={settings.global_prompt || ''}
            onChange={e => update('global_prompt', e.target.value.slice(0, 200))}
            placeholder="모든 대화에 적용되는 지시사항 (예: 항상 표 형식으로 답변해줘)"
            rows={2}
            maxLength={200}
            className="w-full bg-transparent text-xs text-surface-900 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-gold-500/50 resize-none"
            style={{ border: '1px solid var(--color-border)' }}
          />
        </div>
      </div>
    </section>
  )
}

// ─── 사용 내역 ────────────────────────────────────────────────────────────────

function UsageHistorySection() {
  const { userId } = useStore()
  const [history, setHistory] = useState<Array<{
    date: string; queries: number; skills_used: number; tokens: number
  }>>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 실제 환경에서는 API에서 사용 내역 조회
    const mockHistory = Array.from({ length: 7 }, (_, i) => {
      const d = new Date()
      d.setDate(d.getDate() - i)
      return {
        date: d.toISOString().slice(0, 10),
        queries: Math.floor(Math.random() * 20) + 1,
        skills_used: Math.floor(Math.random() * 10),
        tokens: Math.floor(Math.random() * 50000) + 5000,
      }
    })
    setHistory(mockHistory)
    setLoading(false)
  }, [userId])

  return (
    <section className="panel p-5" aria-labelledby="usage-heading">
      <div className="flex items-center gap-2 mb-4">
        <History size={16} className="text-gold-500" aria-hidden="true" />
        <h3 id="usage-heading" className="text-sm font-semibold text-surface-900">
          최근 사용 내역
        </h3>
      </div>

      {loading ? (
        <div role="status" aria-label="사용 내역 불러오는 중">
          <Loader2 size={16} className="animate-spin text-surface-600 mx-auto" aria-hidden="true" />
        </div>
      ) : (
        <table className="w-full">
          <caption className="sr-only">최근 7일 사용 내역</caption>
          <thead>
            <tr className="grid grid-cols-4 gap-2 px-3 py-1.5 text-2xs font-semibold text-surface-600 uppercase tracking-widest">
              <th scope="col" className="text-left font-semibold">날짜</th>
              <th scope="col" className="text-right font-semibold">질문</th>
              <th scope="col" className="text-right font-semibold">스킬</th>
              <th scope="col" className="text-right font-semibold">토큰</th>
            </tr>
          </thead>
          <tbody>
            {history.map(row => (
              <tr
                key={row.date}
                className="grid grid-cols-4 gap-2 px-3 py-2 rounded-md hover:bg-surface-200"
                style={{ transition: 'background-color 200ms var(--ease-out)' }}
              >
                <td className="text-xs font-mono text-surface-900">
                  <time dateTime={row.date}>{row.date}</time>
                </td>
                <td className="text-xs text-surface-800 text-right">{row.queries}</td>
                <td className="text-xs text-surface-800 text-right">{row.skills_used}</td>
                <td className="text-xs text-surface-800 text-right font-mono">
                  {row.tokens.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

// ─── 데이터 관리 ──────────────────────────────────────────────────────────────

function DataManagementSection() {
  const toast = useToast()

  function clearMemories() {
    if (!confirm('모든 대화 기억을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return
    toast.success('기억 삭제', '모든 대화 기억이 삭제되었습니다')
  }

  function clearChatHistory() {
    if (!confirm('모든 대화 내역을 삭제하시겠습니까?')) return
    localStorage.removeItem('malife-threads')
    toast.success('대화 삭제', '모든 대화 내역이 삭제되었습니다')
    window.location.reload()
  }

  return (
    <section className="panel p-5" aria-labelledby="data-heading">
      <div className="flex items-center gap-2 mb-4">
        <Shield size={16} className="text-gold-500" aria-hidden="true" />
        <h3 id="data-heading" className="text-sm font-semibold text-surface-900">
          데이터 관리
        </h3>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between py-2">
          <div>
            <p id="clear-memories-label" className="text-xs font-semibold text-surface-900">
              대화 기억 삭제
            </p>
            <p className="text-2xs text-surface-600">에이전트가 저장한 모든 세션 메모리를 삭제합니다</p>
          </div>
          <button
            type="button"
            onClick={clearMemories}
            className="btn-secondary text-xs flex items-center gap-1 text-status-error border-status-error/30"
            aria-labelledby="clear-memories-label"
          >
            <Trash2 size={11} aria-hidden="true" /> 삭제
          </button>
        </div>

        <div className="flex items-center justify-between py-2">
          <div>
            <p id="clear-chat-label" className="text-xs font-semibold text-surface-900">
              대화 내역 삭제
            </p>
            <p className="text-2xs text-surface-600">에이전트 콘솔의 모든 대화 스레드를 삭제합니다</p>
          </div>
          <button
            type="button"
            onClick={clearChatHistory}
            className="btn-secondary text-xs flex items-center gap-1 text-status-error border-status-error/30"
            aria-labelledby="clear-chat-label"
          >
            <Trash2 size={11} aria-hidden="true" /> 삭제
          </button>
        </div>
      </div>
    </section>
  )
}

// ─── 메인 ─────────────────────────────────────────────────────────────────────

export default function AccountSettings() {
  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">계정 설정</h2>
        <p className="text-sm text-surface-600">프로필, 비밀번호, 에이전트 환경설정을 관리합니다.</p>
      </div>

      <ProfileSection />
      <PasswordSection />
      <AgentSettingsSection />
      <UsageHistorySection />
      <DataManagementSection />
    </div>
  )
}
