/** API types — kept in sync with FastAPI schemas in app/api/schemas/chat.py */

export interface TokenUsage {
  input_tokens: number | null
  output_tokens: number | null
  context_tokens: number | null
  context_utilisation_pct: number | null
}

export interface MessageOut {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  sequence: number
  model: string | null
  provider: string | null
  token_usage: TokenUsage | null
  created_at: string
}

export interface ConversationOut {
  id: number
  workspace_id: number
  title: string | null
  total_input_tokens: number
  total_output_tokens: number
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends ConversationOut {
  messages: MessageOut[]
}

export interface ChatRequest {
  message: string
  conversation_id?: number
  stream?: boolean
}

export interface ChatResponse {
  conversation_id: number
  message: MessageOut
  token_usage: TokenUsage
  compacted: boolean
}

/** SSE event envelope (spec §123.6) */
export interface SSEEvent<T = Record<string, unknown>> {
  event_id: string
  request_id: string
  sequence: number
  type: SSEEventType
  timestamp: string
  payload: T
}

export type SSEEventType =
  | 'THINKING'
  | 'TOOL_STARTED'
  | 'TOOL_PROGRESS'
  | 'TOOL_COMPLETED'
  | 'RESPONSE_STREAMING'
  | 'RESPONSE_COMPLETE'
  | 'WAITING_FOR_APPROVAL'
  | 'ERROR'

export interface ResponseCompletePayload {
  conversation_id: number
  message_id: number
  content: string
  role: string
  model: string | null
  provider: string | null
  input_tokens: number | null
  output_tokens: number | null
  context_tokens: number | null
  compacted: boolean
}

export interface ErrorPayload {
  code: string
  message: string
}

export interface DocumentOut {
  id: number
  filename: string
  file_type: string
  file_size_bytes: number
  status: string
  chunk_count: number
  embedding_model: string | null
  index_version: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface MemoryOut {
  id: number
  content: string
  category: string
  importance: number
  confidence: number
  source: string | null
  data_classification: string
  created_at: string
  updated_at: string
  last_accessed_at: string | null
}

export interface MemoryCreate {
  content: string
  category?: string
  importance?: number
  confidence?: number
  source?: string
  data_classification?: string
}

export interface ToolOut {
  name: string
  description: string
  risk_level: string
  parameters_schema: Record<string, unknown>
}

export interface ToolExecuteRequest {
  parameters?: Record<string, unknown>
  confirmation_id?: string
}

export interface ToolExecuteResponse {
  tool_name: string
  success: boolean
  output: string
  error: string | null
  truncated: boolean
  policy_decision: string
  policy_rule: string
  reason: string
  requires_confirmation: boolean
}

export interface ToolExecutionOut {
  id: number
  tool_name: string
  risk_level: string
  policy_rule: string
  policy_decision: string
  success: boolean
  error: string | null
  duration_ms: number
  created_at: string
}

/** Health API */
export interface DependencyStatus {
  name: string
  status: 'healthy' | 'unhealthy' | 'degraded' | 'not_configured'
  detail: string | null
}

export interface DependenciesResponse {
  jarvis: 'READY' | 'UNHEALTHY' | 'DEGRADED'
  dependencies: DependencyStatus[]
}
