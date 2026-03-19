import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  RefreshCw,
  Plus,
  ChevronRight,
  Save,
  X,
  Edit3,
  Loader2,
  Trash2,
} from 'lucide-react'
import { vaultApi, type DocResponse } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { FileTree } from '@/components/FileTree'
import { MarkdownViewer, FrontmatterDisplay, parseFrontmatter } from '@/components/MarkdownViewer'
import { Modal } from '@/components/Modal'
import { getFileName, cn } from '@/lib/utils'

export default function VaultExplorer() {
  const toast = useToast()
  const { selectedVaultPath, setSelectedVaultPath } = useStore()

  const [files, setFiles] = useState<string[]>([])
  const [doc, setDoc] = useState<DocResponse | null>(null)
  const [isLoadingFiles, setIsLoadingFiles] = useState(true)
  const [isLoadingDoc, setIsLoadingDoc] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [showNewDocModal, setShowNewDocModal] = useState(false)
  const [newDocPath, setNewDocPath] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ path: string; type: 'file' | 'folder' } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const fetchFiles = useCallback(async () => {
    setIsLoadingFiles(true)
    try {
      const result = await vaultApi.listFiles()
      setFiles(Array.isArray(result) ? result : [])
    } catch (err) {
      toast.error('파일 목록 로드 실패', String(err))
      setFiles([])
    } finally {
      setIsLoadingFiles(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  useEffect(() => {
    if (selectedVaultPath) {
      loadDoc(selectedVaultPath)
    }
  }, [selectedVaultPath])

  async function loadDoc(path: string) {
    setIsLoadingDoc(true)
    setIsEditing(false)
    try {
      const result = await vaultApi.getDoc(path)
      setDoc(result)
      setEditContent(result.content)
    } catch (err) {
      toast.error('문서 로드 실패', String(err))
    } finally {
      setIsLoadingDoc(false)
    }
  }

  function requestDelete(path: string, type: 'file' | 'folder') {
    setDeleteTarget({ path, type })
    setShowDeleteModal(true)
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      if (deleteTarget.type === 'file') {
        await vaultApi.deleteDoc(deleteTarget.path)
        toast.success('삭제 완료', deleteTarget.path)
        if (selectedVaultPath === deleteTarget.path) {
          setSelectedVaultPath('')
          setDoc(null)
        }
      } else {
        const result = await vaultApi.deleteFolder(deleteTarget.path)
        toast.success('폴더 삭제 완료', `${result.files_removed}개 파일 제거`)
        if (selectedVaultPath?.startsWith(deleteTarget.path)) {
          setSelectedVaultPath('')
          setDoc(null)
        }
      }
      fetchFiles()
    } catch (err) {
      toast.error('삭제 실패', String(err))
    } finally {
      setIsDeleting(false)
      setShowDeleteModal(false)
      setDeleteTarget(null)
    }
  }

  async function handleSave() {
    if (!doc) return
    setIsSaving(true)
    try {
      await vaultApi.createDoc({ path: doc.path, content: editContent })
      setDoc({ ...doc, content: editContent })
      setIsEditing(false)
      toast.success('저장 완료', '문서가 Git 볼트에 커밋되었습니다.')
    } catch (err) {
      toast.error('저장 실패', String(err))
    } finally {
      setIsSaving(false)
    }
  }

  async function handleCreateDoc() {
    if (!newDocPath.trim()) return
    setIsCreating(true)
    const path = newDocPath.trim().endsWith('.md') ? newDocPath.trim() : `${newDocPath.trim()}.md`
    const initialContent = `---
title: ${getFileName(path).replace('.md', '')}
date: ${new Date().toISOString().split('T')[0]}
owner: admin01
tags: []
---

# ${getFileName(path).replace('.md', '')}

여기에 내용을 입력하세요.
`
    try {
      await vaultApi.createDoc({ path, content: initialContent })
      await fetchFiles()
      setSelectedVaultPath(path)
      setShowNewDocModal(false)
      setNewDocPath('')
      toast.success('문서 생성', `${path} 파일이 생성되었습니다.`)
    } catch (err) {
      toast.error('생성 실패', String(err))
    } finally {
      setIsCreating(false)
    }
  }

  const pathParts = doc ? doc.path.split('/') : []
  const { frontmatter, body } = doc ? parseFrontmatter(doc.content) : { frontmatter: {}, body: '' }

  return (
    <div className="flex h-full">
      {/* Left panel: File tree */}
      <div
        className="flex flex-col shrink-0 overflow-hidden"
        style={{
          width: '260px',
          borderRight: '1px solid var(--color-border)',
          background: 'var(--color-bg-secondary)',
        }}
      >
        {/* Tree header */}
        <div
          className="flex items-center justify-between px-3 py-2.5"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <span className="text-2xs font-mono text-surface-600 uppercase tracking-widest">
            볼트 파일
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowNewDocModal(true)}
              className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-gold-500 hover:bg-surface-200 transition-colors"
              title="새 문서"
            >
              <Plus size={13} />
            </button>
            <button
              onClick={fetchFiles}
              disabled={isLoadingFiles}
              className="w-6 h-6 rounded flex items-center justify-center text-surface-600 hover:text-surface-900 hover:bg-surface-200 transition-colors"
              title="새로고침"
            >
              <RefreshCw size={12} className={cn(isLoadingFiles && 'animate-spin')} />
            </button>
          </div>
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-y-auto py-1">
          {isLoadingFiles ? (
            <div className="p-3 space-y-1.5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className={cn('skeleton h-5 rounded', i % 3 === 0 && 'w-3/4', i % 3 === 1 && 'w-full', i % 3 === 2 && 'w-5/6')} />
              ))}
            </div>
          ) : (
            <FileTree
              paths={files}
              selectedPath={selectedVaultPath}
              onSelect={(path) => {
                setSelectedVaultPath(path)
                loadDoc(path)
              }}
              onDeleteFolder={(folderPath) => requestDelete(folderPath, 'folder')}
              onDeleteFile={(filePath) => requestDelete(filePath, 'file')}
            />
          )}
        </div>

        {/* File count */}
        <div
          className="px-3 py-2 text-2xs font-mono text-surface-600"
          style={{ borderTop: '1px solid var(--color-border)' }}
        >
          {files.length}개 파일
        </div>
      </div>

      {/* Right panel: Document viewer */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {doc ? (
          <>
            {/* Toolbar */}
            <div
              className="flex items-center gap-2 px-5 py-2.5 shrink-0"
              style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
            >
              {/* Breadcrumb */}
              <nav className="flex items-center gap-1 flex-1 min-w-0">
                {pathParts.map((part, i) => (
                  <span key={i} className="flex items-center gap-1">
                    {i > 0 && <ChevronRight size={11} className="text-surface-600 shrink-0" />}
                    <span
                      className={cn(
                        'text-xs truncate',
                        i === pathParts.length - 1
                          ? 'text-gold-500 font-semibold'
                          : 'text-surface-700',
                      )}
                    >
                      {part}
                    </span>
                  </span>
                ))}
              </nav>

              {/* Actions */}
              <div className="flex items-center gap-2 shrink-0">
                {isEditing ? (
                  <>
                    <button
                      onClick={() => {
                        setIsEditing(false)
                        setEditContent(doc.content)
                      }}
                      className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
                    >
                      <X size={12} />
                      취소
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={isSaving}
                      className="btn-primary flex items-center gap-1.5 text-xs py-1.5"
                    >
                      {isSaving ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Save size={12} />
                      )}
                      저장
                    </button>
                  </>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setIsEditing(true)}
                      className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
                    >
                      <Edit3 size={12} />
                      편집
                    </button>
                    <button
                      onClick={() => selectedVaultPath && requestDelete(selectedVaultPath, 'file')}
                      className="btn-danger flex items-center gap-1.5 text-xs py-1.5"
                    >
                      <Trash2 size={12} />
                      삭제
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Content */}
            {isLoadingDoc ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 size={24} className="text-surface-600 animate-spin" />
              </div>
            ) : isEditing ? (
              <div className="flex-1 overflow-hidden flex">
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="flex-1 p-5 font-mono text-sm text-surface-800 resize-none focus:outline-none"
                  style={{
                    background: 'var(--color-bg-primary)',
                    border: 'none',
                    lineHeight: '1.7',
                    fontSize: '0.8125rem',
                  }}
                  spellCheck={false}
                />
                <div
                  className="flex-1 overflow-y-auto p-5"
                  style={{ borderLeft: '1px solid var(--color-border)' }}
                >
                  <p className="text-2xs font-mono text-surface-600 uppercase tracking-widest mb-3">
                    미리보기
                  </p>
                  <FrontmatterDisplay frontmatter={parseFrontmatter(editContent).frontmatter} />
                  <MarkdownViewer content={parseFrontmatter(editContent).body} />
                </div>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-6">
                <FrontmatterDisplay frontmatter={frontmatter} />
                <MarkdownViewer content={body} />
              </div>
            )}
          </>
        ) : (
          <motion.div
            className="flex-1 flex flex-col items-center justify-center text-center p-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <div
              className="w-16 h-16 rounded-xl flex items-center justify-center mb-4"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
            >
              <Edit3 size={24} className="text-surface-600" />
            </div>
            <h3 className="font-display font-semibold text-surface-800 text-lg mb-2">
              문서를 선택하세요
            </h3>
            <p className="text-sm text-surface-600 max-w-sm">
              왼쪽 파일 트리에서 마크다운 문서를 선택하면 여기서 렌더링됩니다.
              [[위키링크]]를 클릭하면 연결 문서로 이동합니다.
            </p>
          </motion.div>
        )}
      </div>

      {/* New Document Modal */}
      <Modal
        isOpen={showNewDocModal}
        onClose={() => {
          setShowNewDocModal(false)
          setNewDocPath('')
        }}
        onConfirm={handleCreateDoc}
        title="새 문서 만들기"
        confirmLabel="생성"
        isLoading={isCreating}
      >
        <div>
          <label className="text-xs font-semibold text-surface-700 block mb-1.5">
            파일 경로
          </label>
          <input
            type="text"
            value={newDocPath}
            onChange={(e) => setNewDocPath(e.target.value)}
            placeholder="예: Public/보고서/2024-Q4.md"
            className="input-field"
            onKeyDown={(e) => e.key === 'Enter' && handleCreateDoc()}
            autoFocus
          />
          <p className="text-2xs text-surface-600 mt-1.5">
            .md 확장자가 없으면 자동 추가됩니다.
          </p>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false)
          setDeleteTarget(null)
        }}
        onConfirm={confirmDelete}
        title={deleteTarget?.type === 'folder' ? '폴더 삭제' : '파일 삭제'}
        confirmLabel="삭제"
        variant="danger"
        isLoading={isDeleting}
      >
        <div>
          <p className="text-sm text-surface-800 mb-2">
            {deleteTarget?.type === 'folder'
              ? '이 폴더와 하위 파일이 모두 삭제됩니다.'
              : '이 파일이 영구적으로 삭제됩니다.'}
          </p>
          <p className="text-xs font-mono text-gold-500 p-2 rounded" style={{ background: 'var(--color-bg-elevated)' }}>
            {deleteTarget?.path}
          </p>
        </div>
      </Modal>
    </div>
  )
}
