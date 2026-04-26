// ─── API Client ──────────────────────────────────────────────────────────────
// Centralized fetch wrapper with X-User-Id header injection, error handling,
// and typed response helpers.

const BASE_URL = ''  // Proxied through Vite dev server → localhost:9001

export const DEFAULT_USER = 'admin01'

export type ApiError = {
  message: string
  status: number
  detail?: unknown
}

export function getUserId(): string {
  try {
    const stored = localStorage.getItem('malife_user_id')
    return stored ?? DEFAULT_USER
  } catch {
    return DEFAULT_USER
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const userId = getUserId()

  const headers = new Headers(options.headers)
  headers.set('X-User-Id', userId)
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let detail: unknown
    const raw = await response.text()
    try {
      detail = JSON.parse(raw)
    } catch {
      detail = raw
    }
    const err: ApiError = {
      message: `HTTP ${response.status}: ${response.statusText}`,
      status: response.status,
      detail,
    }
    throw err
  }

  // Handle empty responses (204 No Content)
  if (response.status === 204) {
    return {} as T
  }

  return response.json() as Promise<T>
}

// ─── Health ───────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version?: string
  [key: string]: unknown
}

export const healthApi = {
  get: () => request<HealthResponse>('/health'),
}

// ─── Vault ───────────────────────────────────────────────────────────────────

export interface VaultFile {
  path: string
  content?: string
  metadata?: Record<string, unknown>
}

export interface DocResponse {
  path: string
  content: string
  metadata?: Record<string, unknown>
}

export const vaultApi = {
  listFiles: (base = '') =>
    request<string[]>(`/api/v1/vault/files?base=${encodeURIComponent(base)}`),

  getDoc: (path: string) =>
    request<DocResponse>(`/api/v1/vault/doc?path=${encodeURIComponent(path)}`),

  createDoc: (payload: { path: string; content: string; metadata?: Record<string, unknown> }) =>
    request<DocResponse>('/api/v1/vault/doc', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteDoc: (path: string) =>
    request<{ status: string; path: string }>('/api/v1/vault/doc', {
      method: 'DELETE',
      body: JSON.stringify({ path }),
    }),

  deleteFolder: (path: string) =>
    request<{ status: string; path: string; files_removed: number }>('/api/v1/vault/folder', {
      method: 'DELETE',
      body: JSON.stringify({ path }),
    }),

  bulkDelete: (paths: string[]) =>
    request<{ status: string; deleted: string[]; not_found: string[]; denied: string[] }>(
      '/api/v1/vault/doc/bulk-delete',
      {
        method: 'POST',
        body: JSON.stringify({ paths }),
      },
    ),
}

// ─── Ingest ───────────────────────────────────────────────────────────────────

export interface IngestResponse {
  status: string
  output_path?: string
  message?: string
  [key: string]: unknown
}

export interface BatchIngestResponse {
  status: string
  total: number
  success: number
  errors: number
  results: Array<{
    file: string
    status: string
    path?: string
    error?: string
  }>
}

export const ingestApi = {
  upload: (file: File, dest: string, signal?: AbortSignal) => {
    const form = new FormData()
    form.append('file', file)
    form.append('dest', dest)
    return request<IngestResponse>('/api/v1/ingest/upload', {
      method: 'POST',
      body: form,
      signal,
    })
  },

  uploadBatch: async (files: File[], dest: string, relativePaths: string[]): Promise<BatchIngestResponse> => {
    if (files.length === 0) {
      return { status: 'completed', total: 0, success: 0, errors: 0, results: [] }
    }

    // 대량 파일을 50개씩 청크로 나눠서 전송
    const CHUNK_SIZE = 50
    const allResults: BatchIngestResponse['results'] = []
    let totalSuccess = 0
    let totalErrors = 0

    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      const chunkFiles = files.slice(i, i + CHUNK_SIZE)
      const chunkPaths = relativePaths.slice(i, i + CHUNK_SIZE)

      const form = new FormData()
      chunkFiles.forEach((f) => form.append('files', f))
      form.append('dest', dest)
      form.append('relative_paths', chunkPaths.join('\n'))

      const result = await request<BatchIngestResponse>('/api/v1/ingest/upload-batch', {
        method: 'POST',
        body: form,
      })

      allResults.push(...result.results)
      totalSuccess += result.success
      totalErrors += result.errors
    }

    return {
      status: 'completed',
      total: files.length,
      success: totalSuccess,
      errors: totalErrors,
      results: allResults,
    }
  },
}

// ─── Search ───────────────────────────────────────────────────────────────────

export interface SearchResult {
  id?: string
  document?: string
  metadata?: {
    path?: string
    title?: string
    tags?: string[]
    owner?: string
    date?: string
    workspace?: string
    [key: string]: unknown
  }
  distance?: number
  score?: number
}

export interface SearchResponse {
  results: SearchResult[]
  query: string
  total?: number
}

export const searchApi = {
  search: (q: string, n = 10) =>
    request<SearchResponse>(`/api/v1/search/?q=${encodeURIComponent(q)}&n=${n}`),
}

// ─── Agent ────────────────────────────────────────────────────────────────────

export interface ExecutionStep {
  skill?: string
  name?: string
  status: 'success' | 'error' | 'running' | 'pending'
  input?: unknown
  output?: unknown
  error?: string
  duration_ms?: number
  timestamp?: string
}

export interface AgentResponse {
  response: string
  execution_log: ExecutionStep[]
  reasoning?: string
  thread_id: string
}

export interface ClarificationOption {
  label: string
  value: string
  description?: string
}

export interface ClarificationData {
  message: string
  options: ClarificationOption[]
  allow_custom_input: boolean
}

export interface SourceNode {
  id: string
  name: string
  type: string
  description?: string
  match_reason?: string
  source_titles: string[]
  page_start?: number | null
  page_end?: number | null
  section_ref?: string
  effective_date?: string
  security_grade?: number
}

export interface StreamCallbacks {
  onToken: (token: string) => void
  onMetadata: (meta: {
    thread_id: string
    execution_log: ExecutionStep[]
    reasoning?: string
    source_nodes?: SourceNode[]
  }) => void
  onClarification?: (data: ClarificationData) => void
  onSkillStatus?: (data: { status: 'running' | 'done'; skills: string[] }) => void
  onDone: () => void
  onError: (err: string) => void
}

export const agentApi = {
  run: (payload: { query: string; thread_id?: string }) =>
    request<AgentResponse>('/api/v1/agent/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  stream: async (
    payload: { query: string; thread_id?: string; server_url?: string; custom_prompt?: string; history?: Array<{ role: 'user' | 'assistant'; content: string }> },
    callbacks: StreamCallbacks,
  ) => {
    const userId = getUserId()
    const response = await fetch(`${BASE_URL}/api/v1/agent/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      const raw = await response.text()
      callbacks.onError(`HTTP ${response.status}: ${raw}`)
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      callbacks.onError('스트림을 읽을 수 없습니다')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let doneEmitted = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.type === 'metadata') {
            callbacks.onMetadata(event)
          } else if (event.type === 'token') {
            callbacks.onToken(event.content)
          } else if (event.type === 'clarification') {
            callbacks.onClarification?.(event)
          } else if (event.type === 'skill_status') {
            callbacks.onSkillStatus?.(event)
          } else if (event.type === 'done') {
            if (!doneEmitted) {
              doneEmitted = true
              callbacks.onDone()
            }
          }
        } catch {
          // skip malformed lines
        }
      }
    }
    if (!doneEmitted) {
      callbacks.onDone()
    }
  },
}

// ─── Admin ────────────────────────────────────────────────────────────────────

export interface IamConfig {
  users?: Record<string, { roles: string[]; workspace?: string }>
  roles?: Record<string, { read?: string[]; write?: string[] }>
  [key: string]: unknown
}

export interface AuditEntry {
  id?: string
  timestamp: string
  user_id: string
  skill?: string
  action?: string
  status: string
  detail?: string
  query?: string
  [key: string]: unknown
}

export interface KillSwitchStatus {
  active: boolean
  reason?: string
  activated_at?: string
  auto_deactivate_at?: string
}

export const adminApi = {
  getIam: () => request<IamConfig>('/api/v1/admin/iam'),

  updateIam: (config: IamConfig) =>
    request<IamConfig>('/api/v1/admin/iam', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  getAuditLog: (params?: { filter_user?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.filter_user) qs.set('filter_user', params.filter_user)
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return request<AuditEntry[]>(`/api/v1/admin/audit${query}`)
  },

  getKillSwitchStatus: () =>
    request<KillSwitchStatus>('/api/v1/admin/kill-switch/status'),

  activateKillSwitch: (payload?: { reason?: string }) =>
    request<KillSwitchStatus>('/api/v1/admin/kill-switch/activate', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),

  deactivateKillSwitch: () =>
    request<KillSwitchStatus>('/api/v1/admin/kill-switch/deactivate', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
}

// ─── Graph ───────────────────────────────────────────────────────────────────

export interface GraphEntity {
  id: string
  name: string
  entity_type: string
  mentions: number
  properties: Record<string, unknown>
  source_paths: string[]
}

export interface GraphRelationship {
  source_id: string
  target_id: string
  relation_type: string
  weight: number
  source_path: string
}

export interface GraphCommunity {
  id: string
  name: string
  entity_ids: string[]
  summary: string
  level: number
}

export interface GraphVisualizationData {
  nodes: Array<{
    id: string
    name: string
    type: string
    mentions: number
    community?: string
    [key: string]: unknown
  }>
  edges: Array<{
    source: string
    target: string
    type: string
    relation_type?: string
    weight: number
  }>
  communities: GraphCommunity[]
}

export interface GraphStats {
  node_count: number
  edge_count: number
  entity_types: Record<string, number>
  relation_types: Record<string, number>
  communities: number
}

export interface BuildProgress {
  status: string
  total_files: number
  processed: number
  entities: number
  relationships: number
  errors?: number
  current_file: string
  retry_round?: number
  retry_total?: number
  retry_done?: number
  retry_failed?: number
}

export interface GraphRAGSearchResult {
  query: string
  mode: string
  graph_context: string
  matched_entities: GraphEntity[]
  related_entities: GraphEntity[]
  communities: GraphCommunity[]
  source_documents: string[]
  combined_context: string
}

export const graphApi = {
  getStats: () => request<GraphStats>('/api/v1/graph/stats'),

  getVisualization: () => request<GraphVisualizationData>('/api/v1/graph/visualization'),

  searchEntities: (q: string, type?: string, limit = 20) => {
    const params = new URLSearchParams({ q, limit: String(limit) })
    if (type) params.set('type', type)
    return request<GraphEntity[]>(`/api/v1/graph/entities?${params}`)
  },

  getEntity: (id: string) =>
    request<{ entity: GraphEntity; neighbors: GraphEntity[]; relationships: GraphRelationship[] }>(
      `/api/v1/graph/entity/${encodeURIComponent(id)}`
    ),

  getSubgraph: (id: string, depth = 2) =>
    request<GraphVisualizationData>(
      `/api/v1/graph/entity/${encodeURIComponent(id)}/subgraph?depth=${depth}`
    ),

  getCommunities: () => request<GraphCommunity[]>('/api/v1/graph/communities'),

  buildGraph: () =>
    request<{ status: string; files: number; entities: number; relationships: number; communities: number }>(
      '/api/v1/graph/build', { method: 'POST', body: JSON.stringify({}) }
    ),

  getBuildProgress: () =>
    request<BuildProgress>('/api/v1/graph/build/progress'),

  graphRAGSearch: (payload: { query: string; mode?: string; n_results?: number }) =>
    request<GraphRAGSearchResult>('/api/v1/graph/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
