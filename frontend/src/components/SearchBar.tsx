import { useState, useRef, useEffect, useId } from 'react'
import { Search, X, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'

interface SearchBarProps {
  onSearch?: (query: string) => void
  placeholder?: string
  className?: string
  autoNavigate?: boolean
  isLoading?: boolean
}

export function SearchBar({
  onSearch,
  placeholder = '문서 검색... (/ 키로 포커스)',
  className,
  autoNavigate = false,
  isLoading = false,
}: SearchBarProps) {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const inputId = useId()

  // Global / hotkey — 편집 중 엘리먼트(input/textarea/contenteditable)에선 무시
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '/') return
      const active = document.activeElement as HTMLElement | null
      const tag = active?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || active?.isContentEditable) return
      e.preventDefault()
      inputRef.current?.focus()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const q = value.trim()
    if (!q) return
    if (autoNavigate) {
      navigate(`/search?q=${encodeURIComponent(q)}`)
    } else {
      onSearch?.(q)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape' && value) {
      e.preventDefault()
      handleClear()
    }
  }

  function handleClear() {
    setValue('')
    onSearch?.('')
    inputRef.current?.focus()
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn('relative', className)}
      role="search"
    >
      <label htmlFor={inputId} className="sr-only">검색</label>
      <div className="relative flex items-center">
        <span className="absolute left-3 text-surface-600 pointer-events-none" aria-hidden="true">
          {isLoading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
        </span>
        <input
          ref={inputRef}
          id={inputId}
          type="search"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          aria-busy={isLoading || undefined}
          className={cn(
            'input-field pl-9 pr-8',
            'bg-surface-50 border-surface-300',
          )}
          style={{ paddingLeft: '2.25rem', paddingRight: value ? '2rem' : '0.75rem' }}
        />
        {value && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2.5 inline-flex items-center justify-center rounded text-surface-600 hover:text-surface-900"
            style={{
              width: '22px',
              height: '22px',
              transition: 'color 200ms var(--ease-out)',
            }}
            aria-label="검색어 지우기"
          >
            <X size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    </form>
  )
}
