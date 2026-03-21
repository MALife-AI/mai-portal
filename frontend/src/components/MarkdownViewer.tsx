import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate } from 'react-router-dom'
import { useStore } from '@/store/useStore'

interface MarkdownViewerProps {
  content: string
  className?: string
}

// Detects [[wikilink]] patterns and makes them clickable
function processWikiLinks(content: string): string {
  return content.replace(/\[\[([^\]]+)\]\]/g, (_, link) => {
    return `[[[${link}]]](wikilink:${encodeURIComponent(link)})`
  })
}

// Citation colors for [1], [2], etc.
const CITE_COLORS = [
  '#F37021', '#4A90D9', '#34C759', '#AF52DE', '#FF3B30',
  '#5AC8FA', '#FFCC00', '#FF2D55', '#64D2FF', '#30D158',
]

function renderCitations(children: React.ReactNode): React.ReactNode {
  if (!children) return children
  const arr = Array.isArray(children) ? children : [children]
  return arr.map((child, i) => {
    if (typeof child !== 'string') return child
    // Split on citation pattern [1], [2], etc.
    const parts = child.split(/(\[\d+\])/)
    if (parts.length <= 1) return child
    return parts.map((part, j) => {
      const m = part.match(/^\[(\d+)\]$/)
      if (m) {
        const idx = parseInt(m[1], 10)
        const color = CITE_COLORS[(idx - 1) % CITE_COLORS.length]
        return (
          <span
            key={`${i}-${j}`}
            className="inline-flex items-center justify-center rounded font-mono font-bold cursor-default"
            style={{
              fontSize: '9px',
              lineHeight: 1,
              padding: '2px 4px',
              marginLeft: '1px',
              marginRight: '1px',
              background: `${color}22`,
              color: color,
              border: `1px solid ${color}44`,
              verticalAlign: 'super',
            }}
            title={`출처 ${idx}`}
          >
            {idx}
          </span>
        )
      }
      return part
    })
  })
}

export function MarkdownViewer({ content, className = '' }: MarkdownViewerProps) {
  const navigate = useNavigate()
  const setSelectedVaultPath = useStore((s) => s.setSelectedVaultPath)

  const processedContent = processWikiLinks(content)

  function handleLinkClick(href: string | undefined) {
    if (!href) return
    if (href.startsWith('wikilink:')) {
      const linkName = decodeURIComponent(href.slice('wikilink:'.length))
      // Navigate to vault with the linked document
      setSelectedVaultPath(linkName)
      navigate('/vault')
      return
    }
    window.open(href, '_blank', 'noopener noreferrer')
  }

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('wikilink:')) {
              return (
                <span
                  className="wikilink"
                  onClick={() => handleLinkClick(href)}
                  title={`위키링크: ${decodeURIComponent(href.slice('wikilink:'.length))}`}
                >
                  {children}
                </span>
              )
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => {
                  e.preventDefault()
                  handleLinkClick(href)
                }}
              >
                {children}
              </a>
            )
          },
          code: ({ className: codeClass, children, ...props }) => {
            const isInline = !codeClass
            if (isInline) {
              return (
                <code {...props} className={codeClass}>
                  {children}
                </code>
              )
            }
            return (
              <code {...props} className={codeClass}>
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre>
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table>{children}</table>
            </div>
          ),
          p: ({ children }) => <p>{renderCitations(children)}</p>,
          li: ({ children }) => <li>{renderCitations(children)}</li>,
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  )
}

// Frontmatter parser
export function parseFrontmatter(content: string): {
  frontmatter: Record<string, unknown>
  body: string
} {
  const fmRegex = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/
  const match = content.match(fmRegex)

  if (!match) {
    return { frontmatter: {}, body: content }
  }

  const fmText = match[1] ?? ''
  const body = content.slice(match[0].length)

  // Simple YAML parser for common patterns
  const frontmatter: Record<string, unknown> = {}
  for (const line of fmText.split('\n')) {
    const colonIndex = line.indexOf(':')
    if (colonIndex === -1) continue
    const key = line.slice(0, colonIndex).trim()
    const raw = line.slice(colonIndex + 1).trim()

    if (!key) continue

    if (raw.startsWith('[')) {
      try {
        frontmatter[key] = JSON.parse(raw.replace(/'/g, '"'))
      } catch {
        frontmatter[key] = raw.slice(1, -1).split(',').map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
      }
    } else {
      frontmatter[key] = raw.replace(/^['"]|['"]$/g, '')
    }
  }

  return { frontmatter, body }
}

interface FrontmatterDisplayProps {
  frontmatter: Record<string, unknown>
}

export function FrontmatterDisplay({ frontmatter }: FrontmatterDisplayProps) {
  const entries = Object.entries(frontmatter)
  if (entries.length === 0) return null

  return (
    <div className="bg-surface-50 border border-surface-300 rounded-md p-3 mb-4">
      <p className="text-2xs font-mono text-gold-500 uppercase tracking-widest mb-2">메타데이터</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-start gap-2 text-xs">
            <span className="font-mono text-surface-600 shrink-0">{key}:</span>
            <span className="text-surface-800 break-all">
              {Array.isArray(value)
                ? (value as unknown[]).map((v, i) => (
                    <span key={i} className="tag tag-gold mr-1 mb-0.5 inline-block">
                      {String(v)}
                    </span>
                  ))
                : String(value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
