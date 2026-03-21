import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  FolderOpen,
  Bot,
  UploadCloud,
  Search,
  ShieldCheck,
  ChevronDown,
  User,
  Network,
  Wrench,
  Sun,
  Moon,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/vault', label: '볼트 탐색기', icon: FolderOpen },
  { to: '/agent', label: '에이전트 콘솔', icon: Bot },
  { to: '/ingest', label: '문서 업로드', icon: UploadCloud },
  { to: '/search', label: '시맨틱 검색', icon: Search },
  { to: '/graph', label: '지식 그래프', icon: Network },
  { to: '/skills', label: '스킬', icon: Wrench },
  { to: '/admin', label: '관리 패널', icon: ShieldCheck },
]

const DEMO_USERS = ['admin01', 'user01', 'analyst01', 'viewer01']

function ThemeToggle() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('malife_theme') as 'dark' | 'light') || 'dark'
    }
    return 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('malife_theme', theme)
  }, [theme])

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-surface-100 transition-colors text-surface-600 hover:text-surface-900"
    >
      {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
      <span className="text-xs">{theme === 'dark' ? '라이트 모드' : '다크 모드'}</span>
    </button>
  )
}

export function Sidebar() {
  const { userId, setUserId, killSwitchActive } = useStore()
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  return (
    <aside
      className="flex flex-col h-full"
      style={{
        width: 'var(--sidebar-width)',
        background: 'var(--color-bg-secondary)',
        borderRight: '1px solid var(--color-border)',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-3 px-4 py-4"
        style={{ borderBottom: '1px solid var(--color-border)', height: 'var(--header-height)' }}
      >
        <div
          className="w-8 h-8 rounded-md flex items-center justify-center shrink-0"
          style={{ background: 'linear-gradient(135deg, #F37021, #b34c10)' }}
        >
          <span className="font-display font-bold text-white" style={{ fontSize: '0.875rem' }}>
            MA
          </span>
        </div>
        <div className="min-w-0">
          <p
            className="font-display font-semibold text-surface-900 leading-none"
            style={{ fontSize: '0.875rem' }}
          >
            미래에셋 Lake
          </p>
          <p className="text-2xs text-surface-600 mt-0.5 font-mono">Secure Agentic RAG</p>
        </div>
      </div>

      {/* Kill Switch Warning */}
      {killSwitchActive && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="mx-3 mt-3 px-3 py-2 rounded-md kill-switch-active"
          style={{
            background: 'rgba(255, 59, 48, 0.12)',
            border: '1px solid rgba(255, 59, 48, 0.4)',
          }}
        >
          <p className="text-status-error text-xs font-semibold">킬 스위치 활성화</p>
          <p className="text-status-error text-2xs mt-0.5 opacity-80">시스템 응답 차단됨</p>
        </motion.div>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        <p className="px-2 py-1.5 text-2xs font-mono text-surface-600 uppercase tracking-widest">
          메뉴
        </p>
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => cn('nav-item', isActive && 'active')}
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={15}
                  className={cn(
                    'shrink-0 transition-colors',
                    isActive ? 'text-gold-500' : 'text-surface-600',
                  )}
                />
                <span>{label}</span>
                {isActive && (
                  <motion.span
                    layoutId="nav-indicator"
                    className="ml-auto w-1 h-1 rounded-full bg-gold-500"
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Theme toggle */}
      <div className="px-3 py-2">
        <ThemeToggle />
      </div>

      {/* Divider */}
      <div className="gold-divider mx-3" />

      {/* User Selector */}
      <div className="p-2 relative">
        <button
          className={cn(
            'w-full flex items-center gap-2.5 px-3 py-2.5 rounded-md',
            'hover:bg-surface-100 transition-colors',
            userMenuOpen && 'bg-surface-100',
          )}
          onClick={() => setUserMenuOpen((v) => !v)}
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'rgba(243, 112, 33, 0.2)', border: '1px solid rgba(243, 112, 33, 0.3)' }}
          >
            <User size={13} className="text-gold-500" />
          </div>
          <div className="flex-1 min-w-0 text-left">
            <p className="text-xs font-semibold text-surface-900 truncate">{userId}</p>
            <p className="text-2xs text-surface-600">데모 사용자</p>
          </div>
          <ChevronDown
            size={13}
            className={cn(
              'text-surface-600 transition-transform',
              userMenuOpen && 'rotate-180',
            )}
          />
        </button>

        {/* User dropdown */}
        {userMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="absolute bottom-full left-2 right-2 mb-1 rounded-md overflow-hidden"
            style={{
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            }}
          >
            <p className="px-3 py-2 text-2xs font-mono text-surface-600 uppercase tracking-widest border-b border-surface-300">
              사용자 전환
            </p>
            {DEMO_USERS.map((user) => (
              <button
                key={user}
                className={cn(
                  'w-full text-left px-3 py-2 text-sm transition-colors',
                  userId === user
                    ? 'text-gold-500 bg-surface-200'
                    : 'text-surface-800 hover:bg-surface-100',
                )}
                onClick={() => {
                  setUserId(user)
                  setUserMenuOpen(false)
                }}
              >
                <span className="font-mono">{user}</span>
                {userId === user && (
                  <span className="ml-2 text-2xs text-gold-600">(현재)</span>
                )}
              </button>
            ))}
          </motion.div>
        )}
      </div>
    </aside>
  )
}
