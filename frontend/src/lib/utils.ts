import { type ClassValue, clsx } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—'
  try {
    const date = new Date(dateString)
    return new Intl.DateTimeFormat('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date)
  } catch {
    return dateString
  }
}

export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '—'
  try {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHour = Math.floor(diffMin / 60)
    const diffDay = Math.floor(diffHour / 24)

    if (diffSec < 60) return '방금 전'
    if (diffMin < 60) return `${diffMin}분 전`
    if (diffHour < 24) return `${diffHour}시간 전`
    if (diffDay < 7) return `${diffDay}일 전`
    return formatDate(dateString)
  } catch {
    return dateString
  }
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const size = sizes[i]
  if (!size) return `${bytes} B`
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${size}`
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str
  return str.slice(0, maxLength) + '…'
}

export function extractWikiLinks(content: string): string[] {
  const matches = content.match(/\[\[([^\]]+)\]\]/g) || []
  return matches.map((m) => m.slice(2, -2))
}

export function getFileExtension(path: string): string {
  const parts = path.split('.')
  return parts.length > 1 ? (parts[parts.length - 1] ?? '').toLowerCase() : ''
}

export function getFileName(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] ?? path
}

export function getFileDir(path: string): string {
  const parts = path.split('/')
  parts.pop()
  return parts.join('/')
}

export function pathToTreeNodes(paths: string[]): TreeNode {
  const root: TreeNode = { name: 'root', path: '', children: {}, isFile: false }

  for (const path of paths) {
    const parts = path.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      if (!part) continue
      const isLast = i === parts.length - 1
      const currentPath = parts.slice(0, i + 1).join('/')

      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          path: currentPath,
          children: {},
          isFile: isLast,
        }
      }
      current = current.children[part]!
    }
  }

  return root
}

export interface TreeNode {
  name: string
  path: string
  children: Record<string, TreeNode>
  isFile: boolean
}

export interface SelectableItem {
  path: string
  isFolder: boolean
}

/** 트리를 화면 표시 순서대로 플랫 리스트로 변환 (범위 선택용) */
export function pathsToFlatList(paths: string[]): SelectableItem[] {
  const tree = pathToTreeNodes(paths)
  const result: SelectableItem[] = []

  function walk(node: TreeNode, depth: number) {
    const children = Object.values(node.children).sort((a, b) => {
      if (a.isFile !== b.isFile) return a.isFile ? 1 : -1
      return a.name.localeCompare(b.name, 'ko')
    })
    for (const child of children) {
      if (child.isFile) {
        result.push({ path: child.path, isFolder: false })
      } else {
        const isRootFolder = depth === 0 && ['Shared', 'Private', 'Skills'].includes(child.name)
        if (!isRootFolder) {
          result.push({ path: child.path, isFolder: true })
        }
        walk(child, depth + 1)
      }
    }
  }

  walk(tree, 0)
  return result
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function generateId(): string {
  return Math.random().toString(36).slice(2, 11)
}

export function highlightText(text: string, query: string): string {
  if (!query.trim()) return text
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  return text.replace(regex, '<mark class="bg-gold-500/20 text-gold-400 rounded px-0.5">$1</mark>')
}

export function getStatusColor(status: string): string {
  const s = status.toLowerCase()
  if (s === 'success' || s === 'ok' || s === 'healthy' || s === 'active') return 'text-status-success'
  if (s === 'error' || s === 'fail' || s === 'failed' || s === 'critical') return 'text-status-error'
  if (s === 'warning' || s === 'warn' || s === 'degraded') return 'text-status-warning'
  return 'text-status-neutral'
}

export function getStatusBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'success' || s === 'ok' || s === 'healthy' || s === 'active') return 'tag tag-success'
  if (s === 'error' || s === 'fail' || s === 'failed' || s === 'critical') return 'tag tag-error'
  if (s === 'warning' || s === 'warn' || s === 'degraded') return 'tag tag-warning'
  return 'tag tag-gold'
}
