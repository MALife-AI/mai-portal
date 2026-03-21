import { useState, useCallback, useRef, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  UploadCloud,
  FileText,
  File,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronRight,
  FolderOpen,
  FolderUp,
  Clock,
} from 'lucide-react'
import { ingestApi, getUserId, type IngestResponse } from '@/api/client'
import { useStore, useToast } from '@/store/useStore'
import { formatBytes, getFileExtension, cn } from '@/lib/utils'

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

const FILE_ICONS: Record<string, React.ReactNode> = {
  pdf: <span className="text-status-error font-mono font-bold text-xs">PDF</span>,
  hwp: <span className="text-status-info font-mono font-bold text-xs">HWP</span>,
  pptx: <span className="text-status-warning font-mono font-bold text-xs">PPT</span>,
  docx: <span className="text-slate-data font-mono font-bold text-xs">DOC</span>,
  md: <span className="text-status-success font-mono font-bold text-xs">.MD</span>,
  txt: <span className="text-surface-700 font-mono font-bold text-xs">TXT</span>,
}

function getFileIcon(name: string) {
  const ext = getFileExtension(name)
  return (
    <div
      className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
      style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
    >
      {FILE_ICONS[ext] ?? <File size={16} className="text-surface-600" />}
    </div>
  )
}

function PipelineProgress({ stageStatuses }: { stageStatuses: StageStatus[] }) {
  return (
    <div className="flex items-center gap-1 mt-3">
      {PIPELINE_STAGES.map((stage, i) => {
        const status = stageStatuses[i] ?? 'pending'
        return (
          <div key={stage.id} className="flex items-center gap-1 flex-1">
            <div className="flex flex-col items-center gap-1 flex-1">
              <div
                className={cn(
                  'progress-step-circle text-2xs w-7 h-7',
                  status === 'done' && 'done',
                  status === 'running' && 'running',
                  status === 'error' && '!border-status-error !bg-status-error/20 !text-status-error',
                  status === 'pending' && 'pending',
                )}
              >
                {status === 'done' ? (
                  <CheckCircle2 size={12} />
                ) : status === 'error' ? (
                  <XCircle size={12} />
                ) : status === 'running' ? (
                  <Loader2 size={10} className="animate-spin" />
                ) : (
                  <span>{i + 1}</span>
                )}
              </div>
              <span className="text-2xs text-surface-600 text-center leading-tight">
                {stage.label}
              </span>
            </div>
            {i < PIPELINE_STAGES.length - 1 && (
              <div
                className={cn('progress-connector', status === 'done' && 'done')}
                style={{ marginTop: '-20px' }}
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
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      className="panel p-4"
    >
      <div className="flex items-start gap-3">
        {getFileIcon(job.file.name)}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-surface-900 truncate">{job.file.name}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-2xs font-mono text-surface-600">{formatBytes(job.file.size)}</span>
                <ChevronRight size={10} className="text-surface-600" />
                <span className="text-2xs font-mono text-gold-500">{job.dest}</span>
              </div>
            </div>
            <div className="shrink-0 flex items-center gap-1.5">
              {job.status === 'queued' && <span className="tag tag-gold">대기</span>}
              {job.status === 'uploading' && (
                <>
                  <span className="tag tag-blue flex items-center gap-1">
                    <Loader2 size={9} className="animate-spin" />
                    변환 중
                  </span>
                  {onCancel && (
                    <button
                      onClick={() => onCancel(job.id)}
                      className="w-5 h-5 rounded flex items-center justify-center text-surface-600 hover:text-status-error hover:bg-surface-200 transition-colors"
                      title="변환 중지"
                    >
                      <XCircle size={13} />
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
            <div className="mt-2 flex items-center gap-1.5 text-2xs font-mono text-surface-600">
              <FolderOpen size={11} />
              <span className="truncate">{job.result.output_path}</span>
            </div>
          )}

          {job.status === 'error' && job.error && (
            <p className="mt-2 text-2xs text-status-error">{job.error}</p>
          )}
        </div>
      </div>
    </motion.div>
  )
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

interface LocalIngestState {
  status: 'idle' | 'running' | 'done' | 'error'
  total: number
  processed: number
  success: number
  errors: number
  skipped: number
  currentFile: string
  log: Array<{ file: string; status: string; error?: string }>
}

let jobIdCounter = Date.now()

export default function Ingestion() {
  const toast = useToast()
  const { userId } = useStore()

  const [destBase, setDestBase] = useState<'Public' | 'Private'>('Public')
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [folderJobs, setFolderJobs] = useState<FolderUploadJob[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const abortControllers = useRef<Map<string, AbortController>>(new Map())

  // 로컬 경로 인제스트
  const [localPath, setLocalPath] = useState('/Users/lsc/crawlpdf/downloads')
  const [localIngest, setLocalIngest] = useState<LocalIngestState>({
    status: 'idle', total: 0, processed: 0, success: 0, errors: 0, skipped: 0, currentFile: '', log: [],
  })

  const localTaskIdRef = useRef<string | null>(null)
  const localPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 페이지 복귀 시 진행 중인 태스크 복원
  useEffect(() => {
    const savedTaskId = sessionStorage.getItem('localIngestTaskId')
    if (savedTaskId) {
      localTaskIdRef.current = savedTaskId
      startPolling(savedTaskId)
    }
    return () => {
      if (localPollRef.current) clearInterval(localPollRef.current)
    }
  }, [])

  function startPolling(taskId: string) {
    if (localPollRef.current) clearInterval(localPollRef.current)
    const uid = getUserId()

    setLocalIngest(prev => ({ ...prev, status: 'running' }))

    localPollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/v1/ingest/tasks/${taskId}`, {
          headers: { 'X-User-Id': uid },
        })
        if (!res.ok) return
        const task = await res.json()

        setLocalIngest(prev => ({
          ...prev,
          status: task.status === 'running' || task.status === 'pending' ? 'running' : 'done',
          total: task.total || 0,
          processed: task.progress || 0,
          success: task.result?.success || 0,
          errors: task.result?.errors || 0,
          skipped: task.result?.skipped || 0,
          currentFile: task.message || '',
        }))

        if (task.status !== 'running' && task.status !== 'pending') {
          if (localPollRef.current) clearInterval(localPollRef.current)
          localPollRef.current = null
          sessionStorage.removeItem('localIngestTaskId')
          localTaskIdRef.current = null
          if (task.status === 'completed') {
            toast.success('로컬 인제스트 완료', task.message)
          } else if (task.status === 'cancelled') {
            toast.success('변환 중지', '사용자에 의해 중지됨')
          }
        }
      } catch { /* ignore */ }
    }, 2000)
  }

  function handleLocalCancel() {
    const taskId = localTaskIdRef.current
    if (!taskId) return
    const uid = getUserId()
    fetch(`/api/v1/ingest/tasks/${taskId}`, {
      method: 'DELETE',
      headers: { 'X-User-Id': uid },
    }).catch(() => {})
    setLocalIngest(prev => ({ ...prev, status: 'done', currentFile: '사용자에 의해 중지됨' }))
    if (localPollRef.current) clearInterval(localPollRef.current)
    sessionStorage.removeItem('localIngestTaskId')
    toast.success('변환 중지', '로컬 인제스트가 중지되었습니다')
  }

  async function handleLocalIngest() {
    const dest = destBase === 'Private' ? `Private/${userId}/` : 'Public/'
    setLocalIngest({ status: 'running', total: 0, processed: 0, success: 0, errors: 0, skipped: 0, currentFile: '태스크 제출 중...', log: [] })

    try {
      const form = new FormData()
      form.append('source_dir', localPath)
      form.append('dest', dest)

      const uid = getUserId()
      const response = await fetch('/api/v1/ingest/ingest-local', {
        method: 'POST',
        headers: { 'X-User-Id': uid },
        body: form,
      })

      const data = await response.json()
      if (data.error) {
        setLocalIngest(prev => ({ ...prev, status: 'error', currentFile: data.error }))
        toast.error('인제스트 실패', data.error)
        return
      }

      const taskId = data.task_id
      localTaskIdRef.current = taskId
      sessionStorage.setItem('localIngestTaskId', taskId)
      startPolling(taskId)
    } catch (err) {
      setLocalIngest(prev => ({ ...prev, status: 'error', currentFile: String(err) }))
      toast.error('로컬 인제스트 실패', String(err))
    }
  }

  const updateJob = useCallback((id: string, updates: Partial<UploadJob>) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...updates } : j)))
  }, [])

  async function simulatePipeline(jobId: string): Promise<void> {
    const stageStatuses: StageStatus[] = PIPELINE_STAGES.map(() => 'pending')

    for (let i = 0; i < PIPELINE_STAGES.length; i++) {
      stageStatuses[i] = 'running'
      updateJob(jobId, { stageStatuses: [...stageStatuses] })
      await new Promise((r) => setTimeout(r, 400 + Math.random() * 600))
      stageStatuses[i] = 'done'
      updateJob(jobId, { stageStatuses: [...stageStatuses] })
    }
  }

  async function uploadFile(job: UploadJob) {
    const dest =
      destBase === 'Private' ? `Private/${userId}/` : 'Public/'

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
    } catch (err) {
      if (controller.signal.aborted) {
        updateJob(job.id, {
          status: 'cancelled',
          completedAt: new Date().toISOString(),
          stageStatuses: PIPELINE_STAGES.map(() => 'pending'),
        })
        // 서버 태스크도 취소
        if (job.taskId) {
          fetch(`/api/v1/ingest/tasks/${job.taskId}`, {
            method: 'DELETE',
            headers: { 'X-User-Id': userId },
          }).catch(() => {})
        }
        toast.success('변환 중지', `${job.file.name}`)
      } else {
        updateJob(job.id, {
          status: 'error',
          error: String(err),
          completedAt: new Date().toISOString(),
          stageStatuses: PIPELINE_STAGES.map((_, i) => {
            const s = job.stageStatuses[i]
            return s === 'done' ? 'done' : s === 'running' ? 'error' : 'pending'
          }),
        })
        toast.error('업로드 실패', job.file.name)
      }
    } finally {
      abortControllers.current.delete(job.id)
    }
  }

  function cancelJob(jobId: string) {
    const controller = abortControllers.current.get(jobId)
    if (controller) {
      controller.abort()
    }
  }

  async function handleFolderUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = e.target.files
    if (!fileList || fileList.length === 0) return

    const files: File[] = []
    const relativePaths: string[] = []

    const IGNORE_NAMES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '.gitkeep'])

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList.item(i)
      if (!file) continue

      const name = file.name
      // 숨김파일/시스템파일 필터
      if (IGNORE_NAMES.has(name) || name.startsWith('.')) continue

      const relPath: string = (file as any).webkitRelativePath || name
      // 경로 내 숨김 디렉토리 필터 (__MACOSX/..., .hidden/...)
      // 첫 번째 세그먼트(선택한 폴더 이름)는 제외하고 검사
      const parts = relPath.split('/')
      const innerParts = parts.slice(1, -1) // 중간 디렉토리만 (폴더이름, 파일이름 제외)
      if (innerParts.some((p) => p.startsWith('.') || p.startsWith('__'))) continue

      files.push(file)
      relativePaths.push(relPath)
    }

    if (files.length === 0) {
      toast.warning('업로드할 파일 없음', '유효한 문서 파일이 없습니다')
      if (folderInputRef.current) folderInputRef.current.value = ''
      return
    }

    console.log(`[폴더 업로드] ${files.length}개 파일 선택됨:`, relativePaths.slice(0, 5))

    // 폴더명 추출
    const folderName = relativePaths[0]?.split('/')[0] || '폴더'
    const dest = destBase === 'Private' ? `Private/${userId}/` : 'Public/'

    const jobId = String(++jobIdCounter)
    const folderJob: FolderUploadJob = {
      id: jobId,
      folderName,
      fileCount: files.length,
      status: 'uploading',
      successCount: 0,
      errorCount: 0,
      startedAt: new Date().toISOString(),
    }

    setFolderJobs((prev) => [folderJob, ...prev])
    setIsUploading(true)

    try {
      const result = await ingestApi.uploadBatch(files, dest, relativePaths)
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
      toast.success(
        '폴더 업로드 완료',
        `${folderName}: ${result.success}/${result.total} 파일 처리`,
      )
    } catch (err) {
      setFolderJobs((prev) =>
        prev.map((j) =>
          j.id === jobId
            ? { ...j, status: 'error', completedAt: new Date().toISOString() }
            : j,
        ),
      )
      toast.error('폴더 업로드 실패', String(err))
    } finally {
      setIsUploading(false)
      // input 초기화
      if (folderInputRef.current) folderInputRef.current.value = ''
    }
  }

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return

      const newJobs: UploadJob[] = acceptedFiles.map((file) => ({
        id: String(++jobIdCounter),
        file,
        dest: destBase === 'Private' ? `Private/${userId}/` : 'Public/',
        status: 'queued',
        stageStatuses: PIPELINE_STAGES.map(() => 'pending'),
        startedAt: new Date().toISOString(),
      }))

      setJobs((prev) => [...newJobs, ...prev])
      setIsUploading(true)

      // Upload sequentially
      for (const job of newJobs) {
        await uploadFile(job)
      }

      setIsUploading(false)
    },
    [destBase, userId, updateJob],
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.hancom.hwp': ['.hwp'],
      'application/vnd.ms-powerpoint': ['.pptx', '.ppt'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
    },
    maxSize: 50 * 1024 * 1024, // 50MB
    disabled: isUploading,
  })

  const completedJobs = jobs.filter((j) => j.status === 'success' || j.status === 'error')
  const activeJobs = jobs.filter((j) => j.status === 'queued' || j.status === 'uploading')

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="font-display font-semibold text-surface-900 text-xl mb-1">문서 업로드</h2>
        <p className="text-sm text-surface-600">
          PDF, HWP, PPTX, DOCX 파일을 AI 친화적 마크다운으로 변환하고 벡터 DB에 인덱싱합니다.
        </p>
      </div>

      {/* Destination selector */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-700 mb-3">업로드 대상 경로</p>
        <div className="flex gap-2">
          {(['Public', 'Private'] as const).map((base) => (
            <button
              key={base}
              onClick={() => setDestBase(base)}
              className={cn(
                'flex-1 py-2.5 px-4 rounded-md text-sm font-semibold transition-all',
                destBase === base
                  ? 'bg-gold-500/20 text-gold-500 border border-gold-500/30'
                  : 'bg-surface-200 text-surface-700 border border-surface-300 hover:border-surface-400',
              )}
            >
              {base === 'Public' ? (
                <span>🌐 Public/</span>
              ) : (
                <span>🔒 Private/{userId}/</span>
              )}
            </button>
          ))}
        </div>
        <p className="text-2xs text-surface-600 mt-2 font-mono">
          저장 경로: {destBase === 'Private' ? `Private/${userId}/` : 'Public/'}
        </p>
      </div>

      {/* Drop zone */}
      <motion.div
        whileHover={!isUploading ? { scale: 1.005 } : {}}
        transition={{ duration: 0.15 }}
      >
        <div
          {...getRootProps()}
          className={cn(
            'dropzone flex flex-col items-center justify-center py-16 px-8 text-center cursor-pointer',
            isDragActive && 'active',
            isDragReject && '!border-status-error',
            isUploading && 'opacity-50 cursor-not-allowed',
          )}
        >
        <input {...getInputProps()} />

        <motion.div
          animate={isDragActive ? { scale: 1.1, rotate: 5 } : { scale: 1, rotate: 0 }}
          transition={{ duration: 0.2 }}
        >
          <UploadCloud
            size={52}
            className={cn(
              'mb-5 transition-colors',
              isDragActive ? 'text-gold-500' : 'text-surface-600',
            )}
          />
        </motion.div>

        {isDragActive ? (
          <p className="text-lg font-semibold text-gold-500">파일을 여기에 놓으세요</p>
        ) : isUploading ? (
          <div className="flex items-center gap-2 text-gold-500">
            <Loader2 size={18} className="animate-spin" />
            <p className="text-base font-semibold">업로드 진행 중...</p>
          </div>
        ) : (
          <>
            <p className="text-base font-semibold text-surface-800 mb-2">
              파일을 드래그하거나 클릭하여 선택
            </p>
            <p className="text-sm text-surface-600 mb-4">
              PDF · HWP · PPTX · DOCX · TXT · MD
            </p>
          </>
        )}

        {/* File type badges */}
        <div className="flex gap-2 mt-2 flex-wrap justify-center">
          {['PDF', 'HWP', 'PPTX', 'DOCX', 'TXT', 'MD'].map((type) => (
            <span key={type} className="tag tag-gold">{type}</span>
          ))}
        </div>
        <p className="text-2xs text-surface-600 mt-3 font-mono">최대 50MB</p>
        </div>
      </motion.div>

      {/* Folder upload button */}
      <div className="panel p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <FolderUp size={20} className="text-gold-500" />
          <div>
            <p className="text-sm font-semibold text-surface-900">폴더 업로드</p>
            <p className="text-2xs text-surface-600">폴더 전체를 선택하면 하위 구조를 유지하며 일괄 업로드합니다</p>
          </div>
        </div>
        <div>
          <input
            ref={folderInputRef}
            type="file"
            className="hidden"
            onChange={handleFolderUpload}
            {...({ webkitdirectory: '', directory: '', multiple: true } as any)}
          />
          <button
            onClick={() => folderInputRef.current?.click()}
            disabled={isUploading}
            className={cn(
              'btn-primary flex items-center gap-2 text-sm',
              isUploading && 'opacity-50 cursor-not-allowed',
            )}
          >
            <FolderUp size={14} />
            폴더 선택
          </button>
        </div>
      </div>

      {/* Local Path Ingest */}
      <div className="panel p-4 space-y-3">
        <div className="flex items-center gap-3">
          <FolderOpen size={20} className="text-slate-data" />
          <div>
            <p className="text-sm font-semibold text-surface-900">로컬 경로 인제스트</p>
            <p className="text-2xs text-surface-600">서버의 로컬 디렉토리를 직접 읽어 변환합니다 (업로드 불필요)</p>
          </div>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={localPath}
            onChange={(e) => setLocalPath(e.target.value)}
            placeholder="/path/to/documents"
            className="input-field flex-1 font-mono text-xs"
          />
          {localIngest.status === 'running' ? (
            <button
              onClick={handleLocalCancel}
              className="btn-secondary flex items-center gap-2 text-sm whitespace-nowrap text-status-error border-status-error/30 hover:bg-status-error/10"
            >
              <XCircle size={14} /> 변환 중지
            </button>
          ) : (
            <button
              onClick={handleLocalIngest}
              disabled={!localPath}
              className="btn-primary flex items-center gap-2 text-sm whitespace-nowrap"
            >
              <ChevronRight size={14} /> 변환 시작
            </button>
          )}
        </div>

        {/* 진행률 바 */}
        {localIngest.status !== 'idle' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-2xs font-mono">
              <span className="text-surface-700">
                {localIngest.processed}/{localIngest.total} 처리
              </span>
              <span className="text-surface-600">
                <span className="text-status-success">{localIngest.success} 성공</span>
                {' · '}
                <span className="text-status-error">{localIngest.errors} 실패</span>
                {' · '}
                <span className="text-surface-600">{localIngest.skipped} 건너뜀</span>
              </span>
            </div>

            {/* Progress bar */}
            <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: 'var(--color-bg-elevated)' }}>
              <motion.div
                className="h-full rounded-full"
                style={{ background: 'var(--color-gold)' }}
                initial={{ width: 0 }}
                animate={{ width: localIngest.total > 0 ? `${(localIngest.processed / localIngest.total) * 100}%` : '0%' }}
                transition={{ duration: 0.3 }}
              />
            </div>

            {/* 현재 파일 */}
            {localIngest.currentFile && (
              <p className="text-2xs font-mono text-surface-600 truncate">
                {localIngest.status === 'running' ? '▶ ' : ''}{localIngest.currentFile}
              </p>
            )}

            {/* 완료 상태 */}
            {localIngest.status === 'done' && (
              <div className="flex items-center gap-2 text-xs text-status-success">
                <CheckCircle2 size={14} />
                변환 완료 — {localIngest.success}개 문서 인제스트됨
              </div>
            )}

            {/* 에러 로그 */}
            {localIngest.log.length > 0 && (
              <details className="text-2xs">
                <summary className="text-status-error cursor-pointer">실패 목록 ({localIngest.log.length})</summary>
                <div className="mt-1 max-h-32 overflow-y-auto space-y-0.5">
                  {localIngest.log.map((l, i) => (
                    <div key={i} className="flex gap-2 py-0.5 font-mono" style={{ color: 'var(--color-text-muted)' }}>
                      <XCircle size={10} className="text-status-error shrink-0 mt-0.5" />
                      <span className="truncate">{l.file}</span>
                      {l.error && <span className="text-status-error truncate">({l.error})</span>}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* Pipeline Legend */}
      <div className="panel p-4">
        <p className="text-xs font-semibold text-surface-700 mb-3">파이프라인 단계</p>
        <div className="flex items-center gap-2">
          {PIPELINE_STAGES.map((stage, i) => (
            <div key={stage.id} className="flex items-center gap-2 flex-1">
              <div className="flex flex-col items-center flex-1">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-2xs font-mono font-bold"
                  style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
                >
                  {i + 1}
                </div>
                <p className="text-2xs text-surface-700 font-semibold mt-1">{stage.label}</p>
                <p className="text-2xs text-surface-600">{stage.desc}</p>
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <ChevronRight size={14} className="text-surface-600 shrink-0 mt-[-12px]" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Folder jobs */}
      {folderJobs.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <FolderOpen size={14} className="text-gold-500" />
            <p className="text-sm font-semibold text-surface-800">폴더 업로드</p>
          </div>
          <div className="space-y-3">
            <AnimatePresence>
              {folderJobs.map((fj) => (
                <motion.div
                  key={fj.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="panel p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div
                        className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
                        style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
                      >
                        <FolderOpen size={16} className="text-gold-500" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-surface-900">{fj.folderName}/</p>
                        <p className="text-2xs text-surface-600 font-mono mt-0.5">
                          {fj.fileCount}개 파일
                        </p>
                      </div>
                    </div>
                    <div className="shrink-0">
                      {fj.status === 'uploading' && (
                        <span className="tag tag-blue flex items-center gap-1">
                          <Loader2 size={9} className="animate-spin" />
                          처리 중
                        </span>
                      )}
                      {fj.status === 'success' && (
                        <span className="tag tag-success">
                          {fj.successCount}/{fj.fileCount} 완료
                        </span>
                      )}
                      {fj.status === 'error' && <span className="tag tag-error">오류</span>}
                    </div>
                  </div>

                  {/* 결과 목록 */}
                  {fj.results && fj.results.length > 0 && (
                    <div className="mt-3 max-h-48 overflow-y-auto space-y-1">
                      {fj.results.map((r, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-2 text-2xs font-mono py-1 px-2 rounded"
                          style={{ background: 'var(--color-bg-elevated)' }}
                        >
                          {r.status === 'ingested' || r.status === 'saved' ? (
                            <CheckCircle2 size={10} className="text-status-success shrink-0" />
                          ) : r.status === 'skipped' ? (
                            <ChevronRight size={10} className="text-surface-600 shrink-0" />
                          ) : (
                            <XCircle size={10} className="text-status-error shrink-0" />
                          )}
                          <span className="text-surface-700 truncate flex-1">{r.file}</span>
                          {r.path && <span className="text-gold-500 truncate max-w-[200px]">{r.path}</span>}
                          {r.error && <span className="text-status-error truncate max-w-[200px]">{r.error}</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {fj.errorCount > 0 && (
                    <p className="text-2xs text-status-warning mt-2">
                      {fj.errorCount}개 파일 처리 실패
                    </p>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Active jobs */}
      <AnimatePresence>
        {activeJobs.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <div className="flex items-center gap-2 mb-3">
              <Loader2 size={14} className="text-gold-500 animate-spin" />
              <p className="text-sm font-semibold text-surface-800">처리 중 ({activeJobs.length})</p>
            </div>
            <div className="space-y-3">
              {activeJobs.map((job) => (
                <UploadJobCard key={job.id} job={job} onCancel={cancelJob} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Completed jobs */}
      {completedJobs.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Clock size={14} className="text-surface-600" />
            <p className="text-sm font-semibold text-surface-800">최근 업로드 ({completedJobs.length})</p>
          </div>
          <div className="space-y-3">
            <AnimatePresence>
              {completedJobs.map((job) => (
                <UploadJobCard key={job.id} job={job} onCancel={cancelJob} />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Empty state */}
      {jobs.length === 0 && (
        <div className="text-center py-4">
          <FileText size={20} className="text-surface-600 mx-auto mb-2" />
          <p className="text-sm text-surface-600">업로드 기록이 없습니다</p>
        </div>
      )}
    </div>
  )
}
