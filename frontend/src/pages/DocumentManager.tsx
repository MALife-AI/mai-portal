// DocumentManager — 문서 관리 통합 페이지
// VaultExplorer(파일 트리 + 뷰어/에디터) + Ingestion(업로드 + 파이프라인) 통합

import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  RefreshCw,
  Plus,
  ChevronRight,
  Save,
  X,
  Edit3,
  Loader2,
  Trash2,
  CheckSquare,
  Square,
  FolderX,
  UploadCloud,
  FileText,
  File,
  CheckCircle2,
  XCircle,
  FolderOpen,
  FolderUp,
  Clock,
  History,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { vaultApi, ingestApi, getUserId, type DocResponse, type IngestResponse } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { FileTree } from '@/components/FileTree'
import { MarkdownViewer, FrontmatterDisplay, parseFrontmatter } from '@/components/MarkdownViewer'
import { Modal } from '@/components/Modal'
import { getFileName, cn, pathsToFlatList, formatBytes, getFileExtension } from '@/lib/utils'

// ─── Upload pipeline types & constants ────────────────────────────────────────

const PIPELINE_STAGES = [
  { id: 'convert', label: '변환', desc: 'Pandoc AST' },
  { id: 'extract', label: '추출', desc: '텍스트/이미지' },
  { id: 'vlm', label: 'VLM', desc: '시각 분석' },
  { id: 'postprocess', label: '후처리', desc: 'MD 정제' },
  { id: 'index', label: '인덱싱', desc: 'ChromaDB' },
]

type StageStatus = 'pending' | 'running' | 'done' | 'error'

interface UploadJob {
  id: string
  file: File
  dest: string
  status: 'queued' | 'uploading' | 'success' | 'error' | 'cancelled'
  stageStatuses: StageStatus[]
  result?: IngestResponse
  error?: string
  startedAt: string
  completedAt?: string
  taskId?: string
}

interface FolderUploadJob {
  id: string
  folderName: string
  fileCount: number
  status: 'uploading' | 'success' | 'error'
  successCount: number
  errorCount: number
  results?: Array<{ file: string; status: string; path?: string; error?: string }>
  startedAt: string
  completedAt?: string
}

const FILE_TYPE_LABELS: Record<string, React.ReactNode> = {
  pdf: <span className="text-status-error font-mono font-bold text-xs">PDF</span>,
  hwp: <span className="text-status-info font-mono font-bold text-xs">HWP</span>,
  pptx: <span className="text-status-warning font-mono font-bold text-xs">PPT</span>,
  docx: <span className="text-slate-500 font-mono font-bold text-xs">DOC</span>,
  md: <span className="text-status-success font-mono font-bold text-xs">.MD</span>,
  txt: <span className="text-surface-700 font-mono font-bold text-xs">TXT</span>,
}

function getFileIconBadge(name: string) {
  const ext = getFileExtension(name)
  return (
    <div
      className="w-8 h-8 rounded-md flex items-center justify-center shrink-0"
      style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
    >
      {FILE_TYPE_LABELS[ext] ?? <File size={14} className="text-surface-600" />}
    </div>
  )
}

let jobIdCounter = Date.now()

// ─── Sub-components ───────────────────────────────────────────────────────────

function PipelineProgress({ stageStatuses }: { stageStatuses: StageStatus[] }) {
  return (
    <div className="flex items-center gap-1 mt-2.5">
      {PIPELINE_STAGES.map((stage, i) => {
        const status = stageStatuses[i] ?? 'pending'
        return (
          <div key={stage.id} className="flex items-center gap-1 flex-1">
            <div className="flex flex-col items-center gap-0.5 flex-1">
              <div
                className={cn(
                  'progress-step-circle text-2xs w-6 h-6',
                  status === 'done' && 'done',
                  status === 'running' && 'running',
                  status === 'error' && '!border-status-error !bg-status-error/20 !text-status-error',
                  status === 'pending' && 'pending',
                )}
              >
                {status === 'done' ? (
                  <CheckCircle2 size={10} />
                ) : status === 'error' ? (
                  <XCircle size={10} />
                ) : status === 'running' ? (
                  <Loader2 size={9} className="animate-spin" />
                ) : (
                  <span>{i + 1}</span>
                )}
              </div>
              <span className="text-2xs text-surface-600 text-center leading-tight hidden sm:block">
                {stage.label}
              </span>
            </div>
            {i < PIPELINE_STAGES.length - 1 && (
              <div
                className={cn('progress-connector', status === 'done' && 'done')}
                style={{ marginTop: '-16px' }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function UploadJobCard({ job, onCancel }: { job: UploadJob; onCancel?: (id: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      className="panel p-3"
    >
      <div className="flex items-start gap-2.5">
        {getFileIconBadge(job.file.name)}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-surface-900 truncate">{job.file.name}</p>
              <p className="text-2xs font-mono text-surface-600 mt-0.5">{formatBytes(job.file.size)}</p>
            </div>
            <div className="shrink-0 flex items-center gap-1">
              {job.status === 'queued' && <span className="tag tag-gold">대기</span>}
              {job.status === 'uploading' && (
                <>
                  <span className="tag tag-blue flex items-center gap-1">
                    <Loader2 size={8} className="animate-spin" />
                    변환 중
                  </span>
                  {onCancel && (
                    <button
                      onClick={() => onCancel(job.id)}
                      className="w-5 h-5 rounded flex items-center justify-center text-surface-600 hover:text-status-error transition-colors"
                      title="중지"
                    >
                      <XCircle size={12} />
                    </button>
                  )}
                </>
              )}
              {job.status === 'success' && <span className="tag tag-success">완료</span>}
              {job.status === 'error' && <span className="tag tag-error">오류</span>}
              {job.status === 'cancelled' && <span className="tag tag-gold">중지됨</span>}
            </div>
          </div>

          {(job.status === 'uploading' || job.status === 'success' || job.status === 'error') && (
            <PipelineProgress stageStatuses={job.stageStatuses} />
          )}

          {job.status === 'success' && job.result?.output_path && (
            <div className="mt-1.5 flex items-center gap-1 text-2xs font-mono text-surface-600">
              <FolderOpen size={10} />
              <span className="truncate">{job.result.output_path}</span>
            </div>
          )}
          {job.status === 'error' && job.error && (
            <p className="mt-1 text-2xs text-status-error line-clamp-2">{job.error}</p>
          )}
        </div>
      </div>
    </motion.div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function DocumentManager() {
  const toast = useToast()
  const { selectedVaultPath, setSelectedVaultPath, userId } = useStore()

  // ── File tree state ──
  const [files, setFiles] = useState<string[]>([])
  const [isLoadingFiles, setIsLoadingFiles] = useState(true)
  const [fileTab, setFileTab] = useState<'shared' | 'private'>('private')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  // ── Document viewer/editor state ──
  const [doc, setDoc] = useState<DocResponse | null>(null)
  const [isLoadingDoc, setIsLoadingDoc] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // ── New doc modal ──
  const [showNewDocModal, setShowNewDocModal] = useState(false)
  const [newDocPath, setNewDocPath] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  // ── Delete modals ──
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ path: string; type: 'file' | 'folder' } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // ── Multi-select state ──
  const [selectMode, setSelectMode] = useState(false)
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set())
  const [selectedFolders, setSelectedFolders] = useState<Set<string>>(new Set())
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false)
  const [isBulkDeleting, setIsBulkDeleting] = useState(false)

  // ── Upload state ──
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [folderJobs, setFolderJobs] = useState<FolderUploadJob[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [showUploadHistory, setShowUploadHistory] = useState(false)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const abortControllers = useRef<Map<string, AbortController>>(new Map())

  // ── File list ──────────────────────────────────────────────────────────────

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

  const filteredFiles = useMemo(() => {
    if (fileTab === 'private') {
      return files.filter((f) => f.startsWith('Private/'))
    }
    return files.filter(
      (f) => f.startsWith('Shared/') || (!f.startsWith('Private/') && !f.startsWith('.')),
    )
  }, [files, fileTab])

  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  useEffect(() => {
    if (selectedVaultPath) {
      loadDoc(selectedVaultPath)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVaultPath])

  // ── Document CRUD ──────────────────────────────────────────────────────────

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
      toast.success('저장 완료', '문서가 저장되었습니다.')
    } catch (err) {
      toast.error('저장 실패', String(err))
    } finally {
      setIsSaving(false)
    }
  }

  async function handleCreateDoc() {
    if (!newDocPath.trim()) return
    setIsCreating(true)
    const path = newDocPath.trim().endsWith('.md')
      ? newDocPath.trim()
      : `${newDocPath.trim()}.md`
    const title = getFileName(path).replace('.md', '')
    const initialContent = `---
title: ${title}
date: ${new Date().toISOString().split('T')[0]}
owner: ${userId}
tags: []
---

# ${title}

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

  // ── Multi-select ───────────────────────────────────────────────────────────

  const flatList = useMemo(() => pathsToFlatList(files), [files])
  const lastClickedRef = useRef<string | null>(null)

  function toggleSelectMode() {
    if (selectMode) {
      setSelectMode(false)
      setSelectedPaths(new Set())
      setSelectedFolders(new Set())
    } else {
      setSelectMode(true)
      setSelectedPaths(new Set())
      setSelectedFolders(new Set())
    }
    lastClickedRef.current = null
  }

  function applyRangeSelect(currentPath: string): boolean {
    const lastPath = lastClickedRef.current
    if (!lastPath) return false
    const lastIdx = flatList.findIndex((item) => item.path === lastPath)
    const curIdx = flatList.findIndex((item) => item.path === currentPath)
    if (lastIdx === -1 || curIdx === -1) return false
    const from = Math.min(lastIdx, curIdx)
    const to = Math.max(lastIdx, curIdx)
    const rangeItems = flatList.slice(from, to + 1)
    setSelectedPaths((prev) => {
      const next = new Set(prev)
      for (const item of rangeItems) if (!item.isFolder) next.add(item.path)
      return next
    })
    setSelectedFolders((prev) => {
      const next = new Set(prev)
      for (const item of rangeItems) if (item.isFolder) next.add(item.path)
      return next
    })
    return true
  }

  function handleToggleSelect(path: string, shiftKey: boolean) {
    if (shiftKey && applyRangeSelect(path)) {
      lastClickedRef.current = path
      return
    }
    lastClickedRef.current = path
    setSelectedPaths((prev) => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  function handleToggleFolderSelect(folderPath: string, shiftKey: boolean) {
    if (shiftKey && applyRangeSelect(folderPath)) {
      lastClickedRef.current = folderPath
      return
    }
    lastClickedRef.current = folderPath
    setSelectedFolders((prev) => {
      const next = new Set(prev)
      next.has(folderPath) ? next.delete(folderPath) : next.add(folderPath)
      return next
    })
    setSelectedPaths((prev) => {
      const next = new Set(prev)
      for (const p of prev) if (p.startsWith(folderPath + '/')) next.delete(p)
      return next
    })
  }

  function handleSelectAll() {
    if (selectedPaths.size === files.length && selectedFolders.size === 0) {
      setSelectedPaths(new Set())
    } else {
      setSelectedFolders(new Set())
      setSelectedPaths(new Set(files))
    }
  }

  const standaloneFiles = Array.from(selectedPaths).filter(
    (p) => !Array.from(selectedFolders).some((f) => p.startsWith(f + '/')),
  )
  const totalSelectCount = selectedFolders.size + standaloneFiles.length
  const hasSelection = totalSelectCount > 0

  async function confirmBulkDelete() {
    if (!hasSelection) return
    setIsBulkDeleting(true)
    try {
      const msgs: string[] = []
      let totalFilesRemoved = 0
      for (const folderPath of selectedFolders) {
        try {
          const result = await vaultApi.deleteFolder(folderPath)
          totalFilesRemoved += result.files_removed
        } catch {
          msgs.push(`${folderPath} 실패`)
        }
      }
      if (selectedFolders.size > 0) {
        msgs.push(`${selectedFolders.size}개 폴더 (${totalFilesRemoved}개 파일)`)
      }
      if (standaloneFiles.length > 0) {
        const result = await vaultApi.bulkDelete(standaloneFiles)
        if (result.deleted.length > 0) msgs.push(`${result.deleted.length}개 파일 삭제`)
        if (result.not_found.length > 0) msgs.push(`${result.not_found.length}개 미발견`)
        if (result.denied.length > 0) msgs.push(`${result.denied.length}개 권한 없음`)
      }
      toast.success('단체 삭제 완료', msgs.join(', '))
      if (selectedVaultPath) {
        const isInDeletedFolder = Array.from(selectedFolders).some(
          (f) => selectedVaultPath.startsWith(f + '/'),
        )
        if (isInDeletedFolder || standaloneFiles.includes(selectedVaultPath)) {
          setSelectedVaultPath('')
          setDoc(null)
        }
      }
      setSelectedPaths(new Set())
      setSelectedFolders(new Set())
      setSelectMode(false)
      fetchFiles()
    } catch (err) {
      toast.error('단체 삭제 실패', String(err))
    } finally {
      setIsBulkDeleting(false)
      setShowBulkDeleteModal(false)
    }
  }

  // ── Upload ─────────────────────────────────────────────────────────────────

  const updateJob = useCallback((id: string, updates: Partial<UploadJob>) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...updates } : j)))
  }, [])

  async function simulatePipeline(jobId: string): Promise<void> {
    const stages: StageStatus[] = PIPELINE_STAGES.map(() => 'pending')
    for (let i = 0; i < PIPELINE_STAGES.length; i++) {
      stages[i] = 'running'
      updateJob(jobId, { stageStatuses: [...stages] })
      await new Promise((r) => setTimeout(r, 400 + Math.random() * 500))
      stages[i] = 'done'
      updateJob(jobId, { stageStatuses: [...stages] })
    }
  }

  async function uploadFile(job: UploadJob) {
    const dest = `Private/${userId}/`
    const controller = new AbortController()
    abortControllers.current.set(job.id, controller)
    updateJob(job.id, { status: 'uploading', stageStatuses: PIPELINE_STAGES.map(() => 'pending') })
    const pipelinePromise = simulatePipeline(job.id)
    try {
      const [result] = await Promise.all([
        ingestApi.upload(job.file, dest, controller.signal),
        pipelinePromise,
      ])
      updateJob(job.id, {
        status: 'success',
        result,
        completedAt: new Date().toISOString(),
        stageStatuses: PIPELINE_STAGES.map(() => 'done'),
      })
      toast.success('업로드 완료', `${job.file.name} 인덱싱 완료`)
      // Refresh file tree after successful upload
      fetchFiles()
    } catch (err) {
      if (controller.signal.aborted) {
        updateJob(job.id, {
          status: 'cancelled',
          completedAt: new Date().toISOString(),
          stageStatuses: PIPELINE_STAGES.map(() => 'pending'),
        })
        toast.success('변환 중지', job.file.name)
      } else {
        updateJob(job.id, {
          status: 'error',
          error: String(err),
          completedAt: new Date().toISOString(),
          stageStatuses: job.stageStatuses.map((s) =>
            s === 'done' ? 'done' : s === 'running' ? 'error' : 'pending',
          ),
        })
        toast.error('업로드 실패', job.file.name)
      }
    } finally {
      abortControllers.current.delete(job.id)
    }
  }

  function cancelJob(jobId: string) {
    abortControllers.current.get(jobId)?.abort()
  }

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return
      const newJobs: UploadJob[] = acceptedFiles.map((file) => ({
        id: String(++jobIdCounter),
        file,
        dest: `Private/${userId}/`,
        status: 'queued',
        stageStatuses: PIPELINE_STAGES.map(() => 'pending'),
        startedAt: new Date().toISOString(),
      }))
      setJobs((prev) => [...newJobs, ...prev])
      setIsUploading(true)
      for (const job of newJobs) {
        await uploadFile(job)
      }
      setIsUploading(false)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [userId, updateJob],
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    maxSize: 50 * 1024 * 1024,
    disabled: isUploading,
  })

  async function handleFolderUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = e.target.files
    if (!fileList || fileList.length === 0) return

    const validFiles: File[] = []
    const relativePaths: string[] = []
    const IGNORE_NAMES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '.gitkeep'])

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList.item(i)
      if (!file) continue
      if (IGNORE_NAMES.has(file.name) || file.name.startsWith('.')) continue
      const relPath: string = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
      const innerParts = relPath.split('/').slice(1, -1)
      if (innerParts.some((p) => p.startsWith('.') || p.startsWith('__'))) continue
      validFiles.push(file)
      relativePaths.push(relPath)
    }

    if (validFiles.length === 0) {
      toast.warning('업로드할 파일 없음', '유효한 문서 파일이 없습니다')
      if (folderInputRef.current) folderInputRef.current.value = ''
      return
    }

    const folderName = relativePaths[0]?.split('/')[0] || '폴더'
    const dest = `Private/${userId}/`
    const jobId = String(++jobIdCounter)
    const folderJob: FolderUploadJob = {
      id: jobId,
      folderName,
      fileCount: validFiles.length,
      status: 'uploading',
      successCount: 0,
      errorCount: 0,
      startedAt: new Date().toISOString(),
    }

    setFolderJobs((prev) => [folderJob, ...prev])
    setIsUploading(true)

    try {
      const result = await ingestApi.uploadBatch(validFiles, dest, relativePaths)
      setFolderJobs((prev) =>
        prev.map((j) =>
          j.id === jobId
            ? {
                ...j,
                status: 'success',
                successCount: result.success,
                errorCount: result.errors,
                results: result.results,
                completedAt: new Date().toISOString(),
              }
            : j,
        ),
      )
      toast.success('폴더 업로드 완료', `${folderName}: ${result.success}/${result.total} 파일 처리`)
      fetchFiles()
    } catch (err) {
      setFolderJobs((prev) =>
        prev.map((j) =>
          j.id === jobId ? { ...j, status: 'error', completedAt: new Date().toISOString() } : j,
        ),
      )
      toast.error('폴더 업로드 실패', String(err))
    } finally {
      setIsUploading(false)
      if (folderInputRef.current) folderInputRef.current.value = ''
    }
  }

  // ── Derived values ─────────────────────────────────────────────────────────

  const activeJobs = jobs.filter((j) => j.status === 'queued' || j.status === 'uploading')
  const completedJobs = jobs.filter((j) => j.status === 'success' || j.status === 'error' || j.status === 'cancelled')
  const totalJobCount = activeJobs.length + completedJobs.length + folderJobs.length

  const pathParts = doc ? doc.path.split('/') : []
  const { frontmatter, body } = doc
    ? parseFrontmatter(doc.content)
    : { frontmatter: {}, body: '' }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full overflow-hidden">

      {/* ── Left sidebar ────────────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {!sidebarCollapsed && (
          <motion.div
            key="sidebar"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col shrink-0 overflow-hidden"
            style={{ borderRight: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)' }}
          >
            {/* ── Compact drop zone ───────────────────────────────────────── */}
            <div className="px-3 pt-3 pb-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
              <div
                {...getRootProps()}
                className={cn(
                  'dropzone flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer transition-all',
                  isDragActive && 'active',
                  isDragReject && '!border-status-error',
                  isUploading && 'opacity-50 cursor-not-allowed',
                )}
              >
                <input {...getInputProps()} />
                <motion.div
                  animate={isDragActive ? { scale: 1.15 } : { scale: 1 }}
                  transition={{ duration: 0.15 }}
                >
                  {isUploading ? (
                    <Loader2 size={18} className="text-gold-500 animate-spin shrink-0" />
                  ) : (
                    <UploadCloud
                      size={18}
                      className={cn(
                        'shrink-0 transition-colors',
                        isDragActive ? 'text-gold-500' : 'text-surface-600',
                      )}
                    />
                  )}
                </motion.div>
                <div className="flex-1 min-w-0">
                  {isDragActive ? (
                    <p className="text-xs font-semibold text-gold-500">여기에 놓으세요</p>
                  ) : isUploading ? (
                    <p className="text-xs font-semibold text-gold-500">업로드 중...</p>
                  ) : (
                    <>
                      <p className="text-xs font-semibold text-surface-800">파일 업로드</p>
                      <p className="text-2xs text-surface-600">드래그하거나 클릭 · 최대 50MB</p>
                    </>
                  )}
                </div>
              </div>

              {/* Upload progress summary */}
              <AnimatePresence>
                {activeJobs.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-2 space-y-1.5"
                  >
                    {activeJobs.map((job) => (
                      <UploadJobCard key={job.id} job={job} onCancel={cancelJob} />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Job history toggle */}
              {totalJobCount > 0 && activeJobs.length === 0 && (
                <button
                  onClick={() => setShowUploadHistory((v) => !v)}
                  className="mt-2 w-full flex items-center gap-1.5 text-2xs text-surface-600 hover:text-gold-500 transition-colors py-1"
                >
                  <Clock size={11} />
                  최근 업로드 {totalJobCount}건
                  <ChevronRight
                    size={10}
                    className={cn('ml-auto transition-transform', showUploadHistory && 'rotate-90')}
                  />
                </button>
              )}

              <AnimatePresence>
                {showUploadHistory && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-1 space-y-1.5 max-h-48 overflow-y-auto"
                  >
                    {/* Folder jobs */}
                    {folderJobs.map((fj) => (
                      <motion.div
                        key={fj.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="panel p-2.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <FolderOpen size={12} className="text-gold-500 shrink-0" />
                            <span className="text-2xs font-semibold text-surface-800 truncate">
                              {fj.folderName}/
                            </span>
                          </div>
                          <div className="shrink-0">
                            {fj.status === 'uploading' && (
                              <span className="tag tag-blue flex items-center gap-1 text-2xs">
                                <Loader2 size={8} className="animate-spin" /> 처리 중
                              </span>
                            )}
                            {fj.status === 'success' && (
                              <span className="tag tag-success text-2xs">
                                {fj.successCount}/{fj.fileCount}
                              </span>
                            )}
                            {fj.status === 'error' && (
                              <span className="tag tag-error text-2xs">오류</span>
                            )}
                          </div>
                        </div>
                      </motion.div>
                    ))}
                    {/* Individual completed jobs */}
                    {completedJobs.map((job) => (
                      <UploadJobCard key={job.id} job={job} />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* ── Shared / Private tabs ────────────────────────────────────── */}
            <div className="flex shrink-0" style={{ borderBottom: '1px solid var(--color-border)' }}>
              <button
                onClick={() => setFileTab('private')}
                className={cn(
                  'flex-1 py-2 text-xs font-semibold transition-colors',
                  fileTab === 'private'
                    ? 'text-gold-500 border-b-2 border-gold-500'
                    : 'text-surface-600 hover:text-surface-800',
                )}
              >
                개인 파일
              </button>
              <button
                onClick={() => setFileTab('shared')}
                className={cn(
                  'flex-1 py-2 text-xs font-semibold transition-colors',
                  fileTab === 'shared'
                    ? 'text-gold-500 border-b-2 border-gold-500'
                    : 'text-surface-600 hover:text-surface-800',
                )}
              >
                공유 파일
              </button>
            </div>

            {/* ── Tree toolbar ─────────────────────────────────────────────── */}
            <div
              className="flex items-center justify-between px-3 py-1.5 shrink-0"
              style={{ borderBottom: '1px solid var(--color-border)' }}
            >
              <span className="text-2xs text-surface-600 font-mono truncate">
                {fileTab === 'private' ? `Private/${userId}/` : 'Shared/'}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={toggleSelectMode}
                  className={cn(
                    'w-6 h-6 rounded flex items-center justify-center transition-colors',
                    selectMode
                      ? 'text-gold-500 bg-gold-500/10'
                      : 'text-surface-600 hover:text-gold-500 hover:bg-surface-200',
                  )}
                  title={selectMode ? '선택 모드 해제' : '멀티 선택'}
                >
                  {selectMode ? <CheckSquare size={13} /> : <Square size={13} />}
                </button>
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

            {/* ── Select mode toolbar ──────────────────────────────────────── */}
            <AnimatePresence>
              {selectMode && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="flex items-center gap-2 px-3 py-2 shrink-0 overflow-hidden"
                  style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg-elevated)' }}
                >
                  <button
                    onClick={handleSelectAll}
                    className="text-2xs text-surface-700 hover:text-gold-500 transition-colors"
                  >
                    {selectedPaths.size === files.length && selectedFolders.size === 0
                      ? '전체 해제'
                      : '전체 선택'}
                  </button>
                  <span className="text-2xs text-surface-600 ml-auto font-mono">
                    {selectedFolders.size > 0 && `${selectedFolders.size}폴더 `}
                    {standaloneFiles.length > 0 && `${standaloneFiles.length}파일`}
                    {!hasSelection && '0개 선택'}
                  </span>
                  <button
                    onClick={() => hasSelection && setShowBulkDeleteModal(true)}
                    disabled={!hasSelection}
                    className={cn(
                      'flex items-center gap-1 text-2xs px-2 py-1 rounded transition-colors',
                      hasSelection
                        ? 'bg-status-error/10 text-status-error hover:bg-status-error/20'
                        : 'text-surface-500 cursor-not-allowed',
                    )}
                  >
                    <Trash2 size={11} />
                    삭제
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* ── File tree ────────────────────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto py-1">
              {isLoadingFiles ? (
                <div className="p-3 space-y-1.5">
                  {Array.from({ length: 10 }).map((_, i) => (
                    <div
                      key={i}
                      className={cn(
                        'skeleton h-5 rounded',
                        i % 3 === 0 && 'w-3/4',
                        i % 3 === 1 && 'w-full',
                        i % 3 === 2 && 'w-5/6',
                      )}
                    />
                  ))}
                </div>
              ) : (
                <FileTree
                  paths={filteredFiles}
                  selectedPath={selectedVaultPath}
                  onSelect={(path) => {
                    setSelectedVaultPath(path)
                    loadDoc(path)
                  }}
                  onDeleteFolder={(folderPath) => requestDelete(folderPath, 'folder')}
                  onDeleteFile={(filePath) => requestDelete(filePath, 'file')}
                  selectMode={selectMode}
                  selectedPaths={selectedPaths}
                  selectedFolders={selectedFolders}
                  onToggleSelect={handleToggleSelect}
                  onToggleFolderSelect={handleToggleFolderSelect}
                />
              )}
            </div>

            {/* ── Sidebar footer: folder upload + file count ───────────────── */}
            <div
              className="shrink-0 px-3 py-2 flex items-center gap-2"
              style={{ borderTop: '1px solid var(--color-border)' }}
            >
              <input
                ref={folderInputRef}
                type="file"
                className="hidden"
                onChange={handleFolderUpload}
                {...({ webkitdirectory: '', directory: '', multiple: true } as React.InputHTMLAttributes<HTMLInputElement>)}
              />
              <button
                onClick={() => folderInputRef.current?.click()}
                disabled={isUploading}
                className={cn(
                  'flex items-center gap-1.5 text-2xs text-surface-600 hover:text-gold-500 transition-colors py-1 px-2 rounded hover:bg-surface-200',
                  isUploading && 'opacity-50 cursor-not-allowed',
                )}
                title="폴더 전체 업로드"
              >
                <FolderUp size={13} />
                폴더 업로드
              </button>
              <span className="ml-auto text-2xs font-mono text-surface-600">
                {files.length}개 파일
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Right panel: document viewer / editor ───────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {doc ? (
          <>
            {/* Toolbar */}
            <div
              className="flex items-center gap-2 px-4 py-2 shrink-0"
              style={{
                borderBottom: '1px solid var(--color-border)',
                background: 'var(--color-bg-secondary)',
              }}
            >
              {/* Sidebar toggle */}
              <button
                onClick={() => setSidebarCollapsed((v) => !v)}
                className="w-7 h-7 rounded flex items-center justify-center text-surface-600 hover:text-surface-900 hover:bg-surface-200 transition-colors shrink-0"
                title={sidebarCollapsed ? '사이드바 열기' : '사이드바 닫기'}
              >
                {sidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
              </button>

              {/* Breadcrumb */}
              <nav className="flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
                {pathParts.map((part, i) => (
                  <span key={i} className="flex items-center gap-1 shrink-0">
                    {i > 0 && <ChevronRight size={10} className="text-surface-600" />}
                    <span
                      className={cn(
                        'text-xs truncate max-w-[120px]',
                        i === pathParts.length - 1
                          ? 'text-gold-500 font-semibold'
                          : 'text-surface-700',
                      )}
                      title={part}
                    >
                      {part}
                    </span>
                  </span>
                ))}
              </nav>

              {/* Actions */}
              <div className="flex items-center gap-1.5 shrink-0">
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
                  <>
                    <button
                      onClick={() => setIsEditing(true)}
                      className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
                      title="편집"
                    >
                      <Edit3 size={12} />
                      편집
                    </button>
                    <button
                      className="btn-secondary flex items-center gap-1.5 text-xs py-1.5 opacity-50 cursor-not-allowed"
                      title="버전 기록 (준비 중)"
                      disabled
                    >
                      <History size={12} />
                      기록
                    </button>
                    <button
                      onClick={() =>
                        selectedVaultPath && requestDelete(selectedVaultPath, 'file')
                      }
                      className="btn-danger flex items-center gap-1.5 text-xs py-1.5"
                      title="삭제"
                    >
                      <Trash2 size={12} />
                      삭제
                    </button>
                  </>
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
                  <FrontmatterDisplay
                    frontmatter={parseFrontmatter(editContent).frontmatter}
                  />
                  <MarkdownViewer content={parseFrontmatter(editContent).body} />
                </div>
              </div>
            ) : (
              <motion.div
                key={doc.path}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.15 }}
                className="flex-1 overflow-y-auto p-6"
              >
                <FrontmatterDisplay frontmatter={frontmatter} />
                <MarkdownViewer content={body} />
              </motion.div>
            )}
          </>
        ) : (
          /* Empty state */
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Toolbar stub (sidebar toggle always visible) */}
            <div
              className="flex items-center gap-2 px-4 py-2 shrink-0"
              style={{
                borderBottom: '1px solid var(--color-border)',
                background: 'var(--color-bg-secondary)',
              }}
            >
              <button
                onClick={() => setSidebarCollapsed((v) => !v)}
                className="w-7 h-7 rounded flex items-center justify-center text-surface-600 hover:text-surface-900 hover:bg-surface-200 transition-colors"
                title={sidebarCollapsed ? '사이드바 열기' : '사이드바 닫기'}
              >
                {sidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
              </button>
              <span className="text-xs text-surface-600">문서를 선택하거나 파일을 업로드하세요</span>
            </div>

            <motion.div
              className="flex-1 flex flex-col items-center justify-center text-center p-8"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div
                className="w-16 h-16 rounded-xl flex items-center justify-center mb-4"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <FileText size={24} className="text-surface-600" />
              </div>
              <h3 className="font-display font-semibold text-surface-800 text-lg mb-2">
                문서 관리
              </h3>
              <p className="text-sm text-surface-600 max-w-sm mb-6">
                왼쪽 파일 트리에서 문서를 선택하거나, 드래그 앤 드롭으로 새 파일을 업로드하세요.
              </p>

              {/* Quick access drop zone in empty state */}
              <div
                {...getRootProps()}
                className={cn(
                  'dropzone flex flex-col items-center justify-center py-10 px-12 text-center cursor-pointer rounded-xl w-full max-w-sm',
                  isDragActive && 'active',
                  isDragReject && '!border-status-error',
                  isUploading && 'opacity-50 cursor-not-allowed',
                )}
              >
                <input {...getInputProps()} />
                <motion.div
                  animate={isDragActive ? { scale: 1.12, rotate: 5 } : { scale: 1, rotate: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <UploadCloud
                    size={36}
                    className={cn(
                      'mb-3 transition-colors',
                      isDragActive ? 'text-gold-500' : 'text-surface-500',
                    )}
                  />
                </motion.div>
                {isDragActive ? (
                  <p className="text-sm font-semibold text-gold-500">여기에 놓으세요</p>
                ) : isUploading ? (
                  <div className="flex items-center gap-2 text-gold-500">
                    <Loader2 size={16} className="animate-spin" />
                    <p className="text-sm font-semibold">업로드 진행 중...</p>
                  </div>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-surface-700 mb-1">
                      파일을 드래그하거나 클릭하여 선택
                    </p>
                    <p className="text-xs text-surface-600">
                      PDF · HWP · PPTX · DOCX · TXT · MD
                    </p>
                    <div className="flex gap-1.5 mt-3 flex-wrap justify-center">
                      {['PDF', 'HWP', 'PPTX', 'DOCX', 'MD'].map((type) => (
                        <span key={type} className="tag tag-gold">
                          {type}
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Active upload progress in empty state */}
              <AnimatePresence>
                {activeJobs.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="mt-4 w-full max-w-sm space-y-2"
                  >
                    <div className="flex items-center gap-2">
                      <Loader2 size={13} className="text-gold-500 animate-spin" />
                      <p className="text-xs font-semibold text-surface-800">
                        처리 중 ({activeJobs.length})
                      </p>
                    </div>
                    {activeJobs.map((job) => (
                      <UploadJobCard key={job.id} job={job} onCancel={cancelJob} />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          </div>
        )}
      </div>

      {/* ── Modals ─────────────────────────────────────────────────────────── */}

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
            placeholder={`예: Private/${userId}/보고서/2024-Q4.md`}
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
          <p
            className="text-xs font-mono text-gold-500 p-2 rounded"
            style={{ background: 'var(--color-bg-elevated)' }}
          >
            {deleteTarget?.path}
          </p>
        </div>
      </Modal>

      {/* Bulk Delete Modal */}
      <Modal
        isOpen={showBulkDeleteModal}
        onClose={() => setShowBulkDeleteModal(false)}
        onConfirm={confirmBulkDelete}
        title="단체 삭제"
        confirmLabel={`${totalSelectCount}개 항목 삭제`}
        variant="danger"
        isLoading={isBulkDeleting}
      >
        <div>
          <p className="text-sm text-surface-800 mb-3">
            선택한 항목이 영구적으로 삭제됩니다.
          </p>
          <div
            className="max-h-48 overflow-y-auto rounded p-2 space-y-0.5"
            style={{ background: 'var(--color-bg-elevated)' }}
          >
            {Array.from(selectedFolders)
              .sort()
              .map((p) => (
                <p
                  key={p}
                  className="text-2xs font-mono text-status-error truncate flex items-center gap-1.5"
                  title={p}
                >
                  <FolderX size={11} className="shrink-0" />
                  {p}/ <span className="text-surface-600">(하위 전체)</span>
                </p>
              ))}
            {standaloneFiles.sort().map((p) => (
              <p
                key={p}
                className="text-2xs font-mono text-surface-700 truncate"
                title={p}
              >
                {p}
              </p>
            ))}
          </div>
        </div>
      </Modal>
    </div>
  )
}
