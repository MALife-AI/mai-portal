import { useState, useRef, useEffect } from 'react'
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

  // Global / hotkey
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    if (autoNavigate) {
      navigate(`/search?q=${encodeURIComponent(value.trim())}`)
    } else {
      onSearch?.(value.trim())
    }
  }

  function handleClear() {
    setValue('')
    onSearch?.('')
    inputRef.current?.focus()
  }

  return (
    <form onSubmit={handleSubmit} className={cn('relative', className)}>
      <div className="relative flex items-center">
        <span className="absolute left-3 text-surface-600 pointer-events-none">
          {isLoading ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Search size={15} />
          )}
        </span>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
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
            className="absolute right-2.5 text-surface-600 hover:text-surface-900 transition-colors"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </form>
  )
}
