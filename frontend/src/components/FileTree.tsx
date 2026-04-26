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
  selectMode?: boolean
  selectedPaths?: Set<string>
  selectedFolders?: Set<string>
  onToggleSelect?: (path: string, shiftKey: boolean) => void
  onToggleFolderSelect?: (path: string, shiftKey: boolean) => void
  className?: string
}

export function FileTree({
  paths,
  selectedPath,
  onSelect,
  onDeleteFolder,
  onDeleteFile,
  selectMode = false,
  selectedPaths,
  selectedFolders,
  onToggleSelect,
  onToggleFolderSelect,
  className,
}: FileTreeProps) {
  const tree = pathToTreeNodes(paths)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['Shared', 'Private', 'Skills']))

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
    if (name === 'Shared') return <Globe size={13} className="text-status-success shrink-0" />
    if (name === 'Private') return <Lock size={13} className="text-status-warning shrink-0" />
    if (name === 'Skills') return <Zap size={13} className="text-gold-500 shrink-0" />
    if (isOpen) return <FolderOpen size={13} className="text-slate-data shrink-0" />
    return <Folder size={13} className="text-surface-700 shrink-0" />
  }

  function collectFilePaths(node: TreeNode): string[] {
    const result: string[] = []
    if (node.isFile) {
      result.push(node.path)
    }
    for (const child of Object.values(node.children)) {
      result.push(...collectFilePaths(child))
    }
    return result
  }

  function isUnderSelectedFolder(path: string): boolean {
    if (!selectedFolders) return false
    for (const folder of selectedFolders) {
      if (path.startsWith(folder + '/')) return true
    }
    return false
  }

  function renderNode(node: TreeNode, depth = 0): React.ReactNode {
    const children = Object.values(node.children)
    const indent = depth * 12

    if (node.isFile) {
      const parentSelected = isUnderSelectedFolder(node.path)
      const isChecked = parentSelected || (selectedPaths?.has(node.path) ?? false)

      return (
        <div key={node.path} className="group relative">
          <button
            className={cn(
              'tree-item w-full text-left pr-8',
              selectedPath === node.path && !selectMode && 'selected',
              selectMode && parentSelected && 'opacity-60',
            )}
            style={{ paddingLeft: `${indent + 8}px` }}
            onClick={(e) => {
              if (selectMode && onToggleSelect && !parentSelected) {
                onToggleSelect(node.path, e.shiftKey)
              } else if (!selectMode) {
                onSelect(node.path)
              }
            }}
            title={node.path}
            disabled={selectMode && parentSelected}
          >
            {selectMode ? (
              <input
                type="checkbox"
                checked={isChecked}
                disabled={parentSelected}
                readOnly
                className="shrink-0 w-3.5 h-3.5 rounded border-surface-400 text-gold-500 focus:ring-gold-500 pointer-events-none accent-amber-500 disabled:opacity-50"
              />
            ) : (
              <FileText size={12} className="shrink-0 text-surface-600" />
            )}
            <span className={cn('truncate', selectMode && isChecked && 'text-gold-500 font-medium')}>
              {node.name}
            </span>
          </button>
          {!selectMode && onDeleteFile && (
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
    const isRootFolder = depth === 0 && ['Shared', 'Private', 'Skills'].includes(node.name)

    const isFolderSelected = selectedFolders?.has(node.path) ?? false
    const parentSelected = isUnderSelectedFolder(node.path)
    const effectivelySelected = isFolderSelected || parentSelected

    const folderFiles = collectFilePaths(node)

    return (
      <div key={node.path} className="group/folder relative">
        <button
          className={cn(
            'tree-item w-full text-left pr-8',
            selectMode && parentSelected && 'opacity-60',
          )}
          style={{ paddingLeft: `${indent + 8}px` }}
          onClick={(e) => {
            if (selectMode && !isRootFolder && !parentSelected && onToggleFolderSelect) {
              onToggleFolderSelect(node.path, e.shiftKey)
            } else if (!selectMode) {
              toggleExpand(node.path)
            }
          }}
        >
          {selectMode && !isRootFolder ? (
            <input
              type="checkbox"
              checked={effectivelySelected}
              disabled={parentSelected}
              readOnly
              className="shrink-0 w-3.5 h-3.5 rounded border-surface-400 text-gold-500 focus:ring-gold-500 pointer-events-none accent-amber-500 disabled:opacity-50"
            />
          ) : selectMode && isRootFolder ? (
            <span className="w-3.5 shrink-0" />
          ) : (
            <span className="text-surface-600">
              {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            </span>
          )}
          {getFolderIcon(node.name, isOpen)}
          <span className={cn('truncate font-medium', selectMode && effectivelySelected && 'text-gold-500')}>
            {node.name}
          </span>
          <span className="ml-auto text-2xs text-surface-600 font-mono">
            {selectMode && effectivelySelected
              ? `${folderFiles.length}개`
              : children.length}
          </span>
        </button>
        {!selectMode && onDeleteFolder && !isRootFolder && (
          <button
            onClick={(e) => { e.stopPropagation(); onDeleteFolder(node.path) }}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover/folder:opacity-100 hover:bg-status-error/20 text-surface-600 hover:text-status-error transition-all"
            title="폴더 삭제"
          >
            <Trash2 size={11} />
          </button>
        )}

        <AnimatePresence initial={false}>
          {(selectMode || isOpen) && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
              style={{ overflow: 'hidden' }}
              role="group"
            >
              {children
                .sort((a, b) => {
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
    <div
      className={cn('select-none', className)}
      role="tree"
      aria-label="파일 트리"
    >
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
