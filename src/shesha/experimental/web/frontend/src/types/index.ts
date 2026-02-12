export interface TopicInfo {
  name: string
  paper_count: number
  size: string
  project_id: string
}

export interface PaperInfo {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  category: string
  date: string
  arxiv_url: string
  source_type: string | null
}

export interface SearchResult {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  category: string
  date: string
  arxiv_url: string
  in_topics: string[]
}

export interface TraceStep {
  step_type: string
  iteration: number
  content: string
  timestamp: string
  tokens_used?: number
  duration_ms?: number
}

export interface TraceListItem {
  trace_id: string
  question: string
  timestamp: string
  status: string
  total_tokens: number
  duration_ms: number
}

export interface TraceFull {
  trace_id: string
  question: string
  model: string
  timestamp: string
  steps: TraceStep[]
  total_tokens: Record<string, number>
  total_iterations: number
  duration_ms: number
  status: string
}

export interface Exchange {
  exchange_id: string
  question: string
  answer: string
  trace_id: string | null
  timestamp: string
  tokens: { prompt: number; completion: number; total: number }
  execution_time: number
  model: string
}

export interface ContextBudget {
  used_tokens: number
  max_tokens: number
  percentage: number
  level: 'green' | 'amber' | 'red'
}

export interface ModelInfo {
  model: string
  max_input_tokens: number | null
}

// WebSocket message types
export type WSMessage =
  | { type: 'status'; phase: string; iteration: number }
  | { type: 'step'; step_type: string; iteration: number; content: string; prompt_tokens?: number; completion_tokens?: number }
  | { type: 'complete'; answer: string; trace_id: string | null; tokens: { prompt: number; completion: number; total: number }; duration_ms: number }
  | { type: 'error'; message: string }
  | { type: 'cancelled' }
