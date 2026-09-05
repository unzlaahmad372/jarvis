/**
 * JARVIS API client — all backend communication goes through here.
 * Never import fetch/axios directly in components.
 */

import type {
  AutomationExecutionOut,
  AutomationJobCreate,
  AutomationJobOut,
  AutomationJobsOut,
  ChatRequest,
  ChatResponse,
  ConfirmationOut,
  ConfirmRequest,
  ConversationDetail,
  ConversationOut,
  DependenciesResponse,
  DocumentOut,
  GrafanaDashboardsOut,
  JenkinsBuildOut,
  JenkinsJobsOut,
  K8sClusterHealthOut,
  K8sContextsOut,
  MemoryCreate,
  MemoryOut,
  PrometheusQueryOut,
  SpinnakerExecutionsOut,
  SSEEvent,
  ToolExecuteRequest,
  ToolExecuteResponse,
  ToolExecutionOut,
  ToolOut,
  VoiceSettingsOut,
} from '@/types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

// ── Health ────────────────────────────────────────────────────────────────────

export const healthApi = {
  dependencies: () => request<DependenciesResponse>('/health/dependencies'),
}

// ── Conversations ─────────────────────────────────────────────────────────────

export const conversationsApi = {
  list: () => request<ConversationOut[]>('/api/v1/conversations'),
  get: (id: number) => request<ConversationDetail>(`/api/v1/conversations/${id}`),
}

// ── Documents ────────────────────────────────────────────────────────────────

export const documentsApi = {
  list: () => request<DocumentOut[]>('/api/v1/documents'),
  delete: (id: number) =>
    request<{ deleted: boolean; document_id: number; vectors_removed: number }>(
      `/api/v1/documents/${id}`,
      { method: 'DELETE' },
    ),
  ingest: async (file: File): Promise<DocumentOut> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE_URL}/api/v1/documents/ingest`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
    return res.json() as Promise<DocumentOut>
  },
}

// ── Tools ──────────────────────────────────────────────────────────────────────

export const toolsApi = {
  list: () => request<ToolOut[]>('/api/v1/tools'),
  execute: (name: string, body: ToolExecuteRequest) =>
    request<ToolExecuteResponse>(`/api/v1/tools/${encodeURIComponent(name)}/execute`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  audit: (limit = 50) =>
    request<ToolExecutionOut[]>(`/api/v1/tools/audit?limit=${limit}`),
  confirm: (body: ConfirmRequest) =>
    request<ToolExecuteResponse>('/api/v1/tools/confirm', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getConfirmation: (id: string) =>
    request<ConfirmationOut>(`/api/v1/tools/confirmations/${encodeURIComponent(id)}`),
}

// ── Memory ────────────────────────────────────────────────────────────────────

export const memoryApi = {
  list: (category?: string) => {
    const params = category ? `?category=${encodeURIComponent(category)}` : ''
    return request<MemoryOut[]>(`/api/v1/memory${params}`)
  },
  create: (body: MemoryCreate) =>
    request<MemoryOut>('/api/v1/memory', { method: 'POST', body: JSON.stringify(body) }),
  delete: (id: number) =>
    request<{ deleted: boolean; memory_id: number }>(`/api/v1/memory/${id}`, { method: 'DELETE' }),
  purge: () =>
    request<{ purged: number }>('/api/v1/memory', { method: 'DELETE' }),
}

// ── Kubernetes ────────────────────────────────────────────────────────────────────

export const kubernetesApi = {
  contexts: () => request<K8sContextsOut>('/api/v1/kubernetes/contexts'),
  health: (context: string) =>
    request<K8sClusterHealthOut>(`/api/v1/kubernetes/health/${encodeURIComponent(context)}`),
}

// ── Voice ────────────────────────────────────────────────────────────────────

export const voiceApi = {
  settings: () => request<VoiceSettingsOut>('/api/v1/voice/settings'),
}

// ── Jenkins ───────────────────────────────────────────────────────────────────

export const jenkinsApi = {
  jobs: () => request<JenkinsJobsOut>('/api/v1/jenkins/jobs'),
  builds: (jobName: string, limit = 10) =>
    request<JenkinsBuildOut[]>(`/api/v1/jenkins/jobs/${encodeURIComponent(jobName)}/builds?limit=${limit}`),
}

// ── Prometheus ────────────────────────────────────────────────────────────────

export const prometheusApi = {
  query: (q: string) =>
    request<PrometheusQueryOut>(`/api/v1/prometheus/query?q=${encodeURIComponent(q)}`),
}

// ── Grafana ───────────────────────────────────────────────────────────────────

export const grafanaApi = {
  dashboards: (q = '') =>
    request<GrafanaDashboardsOut>(`/api/v1/grafana/dashboards?q=${encodeURIComponent(q)}`),
}

// ── Spinnaker ─────────────────────────────────────────────────────────────────

export const spinnakerApi = {
  executions: (application: string, pipeline: string, limit = 5) =>
    request<SpinnakerExecutionsOut>(
      `/api/v1/spinnaker/applications/${encodeURIComponent(application)}/pipelines/${encodeURIComponent(pipeline)}/executions?limit=${limit}`
    ),
}

// ── Automation ────────────────────────────────────────────────────────────────

export const automationApi = {
  list: () => request<AutomationJobsOut>('/api/v1/automation/jobs'),
  create: (body: AutomationJobCreate) =>
    request<AutomationJobOut>('/api/v1/automation/jobs', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  get: (id: number) => request<AutomationJobOut>(`/api/v1/automation/jobs/${id}`),
  delete: (id: number) =>
    fetch(`${BASE_URL}/api/v1/automation/jobs/${id}`, { method: 'DELETE' }),
  enable: (id: number) =>
    request<AutomationJobOut>(`/api/v1/automation/jobs/${id}/enable`, { method: 'POST' }),
  disable: (id: number) =>
    request<AutomationJobOut>(`/api/v1/automation/jobs/${id}/disable`, { method: 'POST' }),
  trigger: (id: number) =>
    request<AutomationExecutionOut>(`/api/v1/automation/jobs/${id}/trigger`, { method: 'POST' }),
  executions: (id: number, limit = 20) =>
    request<AutomationExecutionOut[]>(`/api/v1/automation/jobs/${id}/executions?limit=${limit}`),
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export const chatApi = {
  /** Non-streaming chat — returns full response at once. */
  send: (body: ChatRequest) =>
    request<ChatResponse>('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify({ ...body, stream: false }),
    }),

  /**
   * Streaming chat — returns an async generator of parsed SSE events.
   * Caller is responsible for aborting via the AbortController signal.
   */
  async *stream(
    body: ChatRequest,
    signal?: AbortSignal,
  ): AsyncGenerator<SSEEvent> {
    const res = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, stream: true }),
      signal,
    })

    if (!res.ok || !res.body) {
      const text = await res.text()
      throw new Error(`Stream error ${res.status}: ${text}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n\n')
        buffer = lines.pop() ?? ''

        for (const chunk of lines) {
          const dataLine = chunk.trim()
          if (dataLine.startsWith('data: ')) {
            try {
              const json = JSON.parse(dataLine.slice(6))
              yield json as SSEEvent
            } catch {
              // malformed event — skip
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  },
}
