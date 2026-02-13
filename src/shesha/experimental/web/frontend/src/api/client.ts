import type { TopicInfo, PaperInfo, SearchResult, TraceFull, TraceListItem, Exchange, ContextBudget, ModelInfo } from '../types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || resp.statusText)
  }
  return resp.json()
}

export const api = {
  topics: {
    list: () => request<TopicInfo[]>('/topics'),
    create: (name: string) => request<{ name: string; project_id: string }>('/topics', {
      method: 'POST', body: JSON.stringify({ name }),
    }),
    rename: (name: string, newName: string) => request<{ name: string }>(`/topics/${encodeURIComponent(name)}`, {
      method: 'PATCH', body: JSON.stringify({ new_name: newName }),
    }),
    delete: (name: string) => request<void>(`/topics/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },
  papers: {
    list: (topic: string) => request<PaperInfo[]>(`/topics/${encodeURIComponent(topic)}/papers`),
    add: (arxivId: string, topics: string[]) => request<{ task_id?: string }>('/papers/add', {
      method: 'POST', body: JSON.stringify({ arxiv_id: arxivId, topics }),
    }),
    remove: (topic: string, arxivId: string) => request<void>(
      `/topics/${encodeURIComponent(topic)}/papers/${encodeURIComponent(arxivId)}`, { method: 'DELETE' },
    ),
    taskStatus: (taskId: string) => request<{ task_id: string; papers: { arxiv_id: string; status: string }[] }>(
      `/papers/tasks/${taskId}`,
    ),
    search: (q: string) => request<SearchResult[]>(`/papers/search?q=${encodeURIComponent(q)}`),
  },
  search: (params: { q: string; author?: string; category?: string; sort_by?: string; start?: number }) => {
    const qs = new URLSearchParams()
    qs.set('q', params.q)
    if (params.author) qs.set('author', params.author)
    if (params.category) qs.set('category', params.category)
    if (params.sort_by) qs.set('sort_by', params.sort_by)
    if (params.start) qs.set('start', String(params.start))
    return request<SearchResult[]>(`/search?${qs}`)
  },
  traces: {
    list: (topic: string) => request<TraceListItem[]>(
      `/topics/${encodeURIComponent(topic)}/traces`,
    ),
    get: (topic: string, traceId: string) => request<TraceFull>(
      `/topics/${encodeURIComponent(topic)}/traces/${traceId}`,
    ),
  },
  history: {
    get: (topic: string) => request<{ exchanges: Exchange[] }>(`/topics/${encodeURIComponent(topic)}/history`),
    clear: (topic: string) => request<void>(`/topics/${encodeURIComponent(topic)}/history`, { method: 'DELETE' }),
  },
  export: (topic: string) => fetch(`${BASE}/topics/${encodeURIComponent(topic)}/export`).then(r => r.text()),
  model: {
    get: () => request<ModelInfo>('/model'),
    update: (model: string) => request<ModelInfo>('/model', {
      method: 'PUT', body: JSON.stringify({ model }),
    }),
  },
  contextBudget: (topic: string) => request<ContextBudget>(
    `/topics/${encodeURIComponent(topic)}/context-budget`,
  ),
}
