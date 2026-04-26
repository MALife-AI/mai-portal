import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  FolderOpen,
  Bot,
  Search,
  ShieldCheck,
  ChevronDown,
  ChevronRight,
  User,
  Wrench,
  Sun,
  Moon,
  Workflow,
  Zap,
  Settings,
  X,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  end?: boolean
  adminOnly?: boolean
}

interface NavGroup {
  label: string
  icon: typeof LayoutDashboard
  children: NavItem[]
  adminOnly?: boolean
}

type NavEntry = NavItem | NavGroup

function isGroup(entry: NavEntry): entry is NavGroup {
  return 'children' in entry
}

const NAV_ITEMS: NavEntry[] = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/agent', label: '에이전트', icon: Bot },
  { to: '/docs', label: '문서 관리', icon: FolderOpen },
  { to: '/knowledge', label: '지식 검색', icon: Search },
  {
    label: '자동화',
    icon: Zap,
    children: [
      { to: '/workflow', label: '워크플로우', icon: Workflow },
      { to: '/skills', label: '스킬', icon: Wrench },
    ],
  },
  { to: '/admin', label: '관리 패널', icon: ShieldCheck, adminOnly: true },
]

function NavMenu() {
  const location = useLocation()
  const { userId } = useStore()
  const isAdmin = userId === 'admin01'
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    // 현재 경로가 그룹 내에 있으면 자동 펼침
    const initial = new Set<string>()
    for (const entry of NAV_ITEMS) {
      if (isGroup(entry) && entry.children.some(c => location.pathname.startsWith(c.to))) {
        initial.add(entry.label)
      }
    }
    return initial
  })

  function toggleGroup(label: string) {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label); else next.add(label)
      return next
    })
  }

  return (
    <nav
      className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto"
      aria-label="주 메뉴"
    >
      <p className="px-2 py-1.5 text-2xs font-mono text-surface-600 uppercase tracking-widest">
        메뉴
      </p>
      {NAV_ITEMS.filter(entry => !entry.adminOnly || isAdmin).map((entry) => {
        if (isGroup(entry)) {
          const expanded = expandedGroups.has(entry.label)
          const isChildActive = entry.children.some(c => location.pathname.startsWith(c.to))
          const Icon = entry.icon
          const groupId = `nav-group-${entry.label.replace(/\s+/g, '-')}`

          return (
            <div key={entry.label}>
              <button
                type="button"
                onClick={() => toggleGroup(entry.label)}
                className={cn(
                  'nav-item w-full',
                  isChildActive && 'text-gold-500',
                )}
                aria-expanded={expanded}
                aria-controls={groupId}
              >
                <Icon
                  size={15}
                  className={cn('shrink-0', isChildActive ? 'text-gold-500' : 'text-surface-600')}
                  aria-hidden="true"
                />
                <span className="flex-1 text-left">{entry.label}</span>
                <motion.span
                  animate={{ rotate: expanded ? 180 : 0 }}
                  transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                  aria-hidden="true"
                >
                  <ChevronDown size={12} className="text-surface-600" />
                </motion.span>
              </button>
              <AnimatePresence initial={false}>
                {expanded && (
                  <motion.div
                    id={groupId}
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="ml-4 pl-2 space-y-0.5 py-0.5" style={{ borderLeft: '1px solid var(--color-border)' }}>
                      {entry.children.map(({ to, label, icon: ChildIcon, end }) => (
                        <NavLink
                          key={to}
                          to={to}
                          end={end}
                          className={({ isActive }) => cn('nav-item text-xs', isActive && 'active')}
                        >
                          {({ isActive }) => (
                            <>
                              <ChildIcon
                                size={13}
                                className={cn('shrink-0', isActive ? 'text-gold-500' : 'text-surface-600')}
                                aria-hidden="true"
                              />
                              <span>{label}</span>
                              {isActive && (
                                <motion.span
                                  layoutId="nav-indicator"
                                  className="ml-auto w-1 h-1 rounded-full bg-gold-500"
                                  aria-hidden="true"
                                />
                              )}
                            </>
                          )}
                        </NavLink>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        }

        const { to, label, icon: Icon, end } = entry
        return (
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
                  className={cn('shrink-0', isActive ? 'text-gold-500' : 'text-surface-600')}
                  aria-hidden="true"
                />
                <span>{label}</span>
                {isActive && (
                  <motion.span
                    layoutId="nav-indicator"
                    className="ml-auto w-1 h-1 rounded-full bg-gold-500"
                    aria-hidden="true"
                  />
                )}
              </>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}

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
      type="button"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-surface-100 text-surface-600 hover:text-surface-900 active:scale-[0.98]"
      style={{ transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out), transform 120ms var(--ease-out)' }}
      aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
    >
      {theme === 'dark' ? <Sun size={14} aria-hidden="true" /> : <Moon size={14} aria-hidden="true" />}
      <span className="text-xs">{theme === 'dark' ? '라이트 모드' : '다크 모드'}</span>
    </button>
  )
}

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const { userId, setUserId, killSwitchActive } = useStore()
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  // 바깥 클릭 및 Esc로 사용자 메뉴 닫기
  useEffect(() => {
    if (!userMenuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setUserMenuOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [userMenuOpen])

  return (
    <aside
      id="primary-sidebar"
      className="flex flex-col h-full shrink-0"
      aria-label="사이드바"
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
          style={{ background: 'linear-gradient(135deg, var(--color-gold), var(--color-gold-dim))' }}
          aria-hidden="true"
        >
          <span className="font-display font-bold text-white" style={{ fontSize: '0.75rem' }}>
            M:AI
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p
            className="font-display font-semibold text-surface-900 leading-none"
            style={{ fontSize: '0.875rem' }}
          >
            M:AI Portal
          </p>
          <p className="text-2xs text-surface-600 mt-0.5 font-mono">Secure Agentic RAG</p>
        </div>
        {onClose && (
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-md hover:bg-surface-100 md:hidden"
            style={{ width: '40px', height: '40px' }}
            onClick={onClose}
            aria-label="메뉴 닫기"
          >
            <X size={16} className="text-surface-600" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Kill Switch Warning */}
      {killSwitchActive && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
          className="mx-3 mt-3 px-3 py-2 rounded-md kill-switch-active"
          role="alert"
          aria-live="assertive"
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
      <NavMenu />

      {/* Settings + Theme */}
      <div className="px-3 py-2 space-y-0.5">
        <NavLink
          to="/settings"
          className={({ isActive }) => cn(
            'w-full flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-surface-100',
            isActive ? 'text-gold-500' : 'text-surface-600 hover:text-surface-900',
          )}
          style={{ transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)' }}
        >
          <Settings size={14} aria-hidden="true" />
          <span className="text-xs">계정 설정</span>
        </NavLink>
        <ThemeToggle />
      </div>

      {/* Divider */}
      <div className="gold-divider mx-3" role="presentation" />

      {/* User Selector */}
      <div className="p-2 relative">
        <button
          type="button"
          className={cn(
            'w-full flex items-center gap-2.5 px-3 py-2.5 rounded-md',
            'hover:bg-surface-100',
            userMenuOpen && 'bg-surface-100',
          )}
          style={{ transition: 'background-color 200ms var(--ease-out)' }}
          onClick={() => setUserMenuOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
          aria-label={`현재 사용자: ${userId}. 사용자 전환`}
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'rgba(243, 112, 33, 0.2)', border: '1px solid rgba(243, 112, 33, 0.3)' }}
            aria-hidden="true"
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
              'text-surface-600',
              userMenuOpen && 'rotate-180',
            )}
            style={{ transition: 'transform 200ms var(--ease-out)' }}
            aria-hidden="true"
          />
        </button>

        {/* User dropdown */}
        <AnimatePresence>
          {userMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.97 }}
              transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
              className="absolute bottom-full left-2 right-2 mb-1 rounded-md overflow-hidden"
              role="menu"
              aria-label="사용자 전환"
              style={{
                background: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                transformOrigin: 'bottom center',
              }}
            >
              <p className="px-3 py-2 text-2xs font-mono text-surface-600 uppercase tracking-widest border-b border-surface-300">
                사용자 전환
              </p>
              {DEMO_USERS.map((user) => (
                <button
                  key={user}
                  type="button"
                  role="menuitemradio"
                  aria-checked={userId === user}
                  className={cn(
                    'w-full text-left px-3 py-2 text-sm',
                    userId === user
                      ? 'text-gold-500 bg-surface-200'
                      : 'text-surface-800 hover:bg-surface-100',
                  )}
                  style={{ transition: 'background-color 200ms var(--ease-out), color 200ms var(--ease-out)' }}
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
        </AnimatePresence>
      </div>
    </aside>
  )
}
