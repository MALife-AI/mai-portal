import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronRight,
  ChevronDown,
  FileText,
  Folder,
  FolderOpen,
  Zap,
  Lock,
  Globe,
  Trash2,
} from 'lucide-react'
import { cn, pathToTreeNodes, type TreeNode } from '@/lib/utils'

interface FileTreeProps {
  paths: string[]
  selectedPath: string | null
  onSelect: (path: string) => void
  onDeleteFolder?: (path: string) => void
  onDeleteFile?: (path: string) => void
  className?: string
}

export function FileTree({ paths, selectedPath, onSelect, onDeleteFolder, onDeleteFile, className }: FileTreeProps) {
  const tree = pathToTreeNodes(paths)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['Public', 'Private', 'Skills']))

  function toggleExpand(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  function getFolderIcon(name: string, isOpen: boolean) {
    if (name === 'Public') return <Globe size={13} className="text-status-success shrink-0" />
    if (name === 'Private') return <Lock size={13} className="text-status-warning shrink-0" />
    if (name === 'Skills') return <Zap size={13} className="text-gold-500 shrink-0" />
    if (isOpen) return <FolderOpen size={13} className="text-slate-data shrink-0" />
    return <Folder size={13} className="text-surface-700 shrink-0" />
  }

  function renderNode(node: TreeNode, depth = 0): React.ReactNode {
    const children = Object.values(node.children)
    const indent = depth * 12

    if (node.isFile) {
      return (
        <div key={node.path} className="group relative">
          <button
            className={cn('tree-item w-full text-left pr-8', selectedPath === node.path && 'selected')}
            style={{ paddingLeft: `${indent + 8}px` }}
            onClick={() => onSelect(node.path)}
            title={node.path}
          >
            <FileText size={12} className="shrink-0 text-surface-600" />
            <span className="truncate">{node.name}</span>
          </button>
          {onDeleteFile && (
            <button
              onClick={(e) => { e.stopPropagation(); onDeleteFile(node.path) }}
              className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-status-error/20 text-surface-600 hover:text-status-error transition-all"
              title="파일 삭제"
            >
              <Trash2 size={11} />
            </button>
          )}
        </div>
      )
    }

    if (children.length === 0) return null

    const isOpen = expanded.has(node.path)

    // 최상위 폴더(Public, Private, Skills)는 삭제 불가
    const isRootFolder = depth === 0 && ['Public', 'Private', 'Skills'].includes(node.name)

    return (
      <div key={node.path} className="group/folder relative">
        <button
          className="tree-item w-full text-left pr-8"
          style={{ paddingLeft: `${indent + 8}px` }}
          onClick={() => toggleExpand(node.path)}
        >
          <span className="text-surface-600">
            {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </span>
          {getFolderIcon(node.name, isOpen)}
          <span className="truncate font-medium">{node.name}</span>
          <span className="ml-auto text-2xs text-surface-600 font-mono">
            {children.length}
          </span>
        </button>
        {onDeleteFolder && !isRootFolder && (
          <button
            onClick={(e) => { e.stopPropagation(); onDeleteFolder(node.path) }}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover/folder:opacity-100 hover:bg-status-error/20 text-surface-600 hover:text-status-error transition-all"
            title="폴더 삭제"
          >
            <Trash2 size={11} />
          </button>
        )}

        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ overflow: 'hidden' }}
            >
              {children
                .sort((a, b) => {
                  // Folders before files, then alpha
                  if (a.isFile !== b.isFile) return a.isFile ? 1 : -1
                  return a.name.localeCompare(b.name, 'ko')
                })
                .map((child) => renderNode(child, depth + 1))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    )
  }

  const rootChildren = Object.values(tree.children)

  return (
    <div className={cn('select-none', className)}>
      {rootChildren.length === 0 ? (
        <div className="px-3 py-6 text-center text-surface-600 text-sm">
          파일이 없습니다
        </div>
      ) : (
        rootChildren
          .sort((a, b) => {
            if (a.isFile !== b.isFile) return a.isFile ? 1 : -1
            return a.name.localeCompare(b.name, 'ko')
          })
          .map((node) => renderNode(node, 0))
      )}
    </div>
  )
}
