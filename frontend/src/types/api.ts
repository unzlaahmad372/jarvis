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

export interface PlanStep {
  tool_name: string
  success: boolean
  policy_decision: string
  requires_confirmation: boolean
  confirmation_id: string | null
  error: string | null
}

export interface CitationOut {
  filename: string
  chunk_index: number
  page: number | null
  score: number
}

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
  intent: string
  plan_steps: PlanStep[]
  citations: CitationOut[]
}

export interface ConfirmationOut {
  confirmation_id: string
  tool_name: string
  risk_level: string
  policy_rule: string
  action_digest: string
  expires_at: string
}

export interface ConfirmRequest {
  confirmation_id: string
  tool_name: string
  parameters: Record<string, unknown>
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

export interface K8sContextOut {
  name: string
  cluster: string
  namespace: string
  current: boolean
  protected: boolean
}

export interface K8sContextsOut {
  current_context: string | null
  contexts: K8sContextOut[]
}

export interface K8sClusterHealthOut {
  context: string
  protected: boolean
  status: 'HEALTHY' | 'DEGRADED' | 'UNREACHABLE'
  reachable: boolean
  node_total: number
  node_ready: number
  pod_total: number
  pod_running: number
  pod_failed: number
  error: string | null
}

export interface SettingsOut {
  llm_model: string
  embedding_model: string
  ollama_url: string
  max_context_tokens: number
  max_response_tokens: number
  enable_voice: boolean
  voice_auto_speak: boolean
  enable_vision: boolean
  enable_always_listening: boolean
  require_confirmation: boolean
  conversation_retention_days: number
  tool_log_retention_days: number
  log_level: string
}

export interface SummaryOut {
  conversation_id: number
  title: string | null
  message_count: number
  summary: string
}

export interface VoiceSettingsOut {
  enabled: boolean
  auto_speak: boolean
}

// ── Jenkins ───────────────────────────────────────────────────────────────────

export interface JenkinsBuildOut {
  job_name: string
  build_number: number
  result: string | null
  duration_ms: number
  timestamp: string
  url: string
  branch: string | null
  failed_stage: string | null
}

export interface JenkinsJobOut {
  name: string
  url: string
  last_build: JenkinsBuildOut | null
}

export interface JenkinsJobsOut {
  server: string
  jobs: JenkinsJobOut[]
}

// ── Prometheus ─────────────────────────────────────────────────────────────

export interface PrometheusMetricOut {
  metric: string
  labels: Record<string, string>
  value: number
  timestamp: string
}

export interface PrometheusQueryOut {
  query: string
  status: string
  results: PrometheusMetricOut[]
  error: string | null
}

// ── Grafana ───────────────────────────────────────────────────────────────────

export interface GrafanaDashboardOut {
  uid: string
  title: string
  url: string
  tags: string[]
  folder: string | null
}

export interface GrafanaDashboardsOut {
  server: string
  dashboards: GrafanaDashboardOut[]
}

// ── Spinnaker ─────────────────────────────────────────────────────────────

export interface SpinnakerStageOut {
  name: string
  status: string
  duration_ms: number
  start_time: string | null
}

export interface SpinnakerExecutionOut {
  id: string
  pipeline_name: string
  application: string
  status: string
  start_time: string | null
  duration_ms: number
  trigger: string | null
  stages: SpinnakerStageOut[]
  url: string
}

export interface SpinnakerExecutionsOut {
  application: string
  pipeline_name: string
  executions: SpinnakerExecutionOut[]
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

// ── Auth / Device Registry (Phase 11) ───────────────────────────────────────

export interface DeviceRegisterRequest {
  name: string
  device_type?: string
  requested_scopes?: string[]
}

export interface DeviceOut {
  device_id: string
  name: string
  device_type: string
  scopes: string[]
  revoked: boolean
  created_at: string
  last_seen_at: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in_seconds: number
  scopes: string[]
}

export interface RefreshRequest {
  refresh_token: string
}

// ── Backup (Phase 10) ─────────────────────────────────────────────────────────

export interface BackupOut {
  backup_id: string
  created_at: string
  app_version: string
  database_schema_version: string
  contents: string[]
  checksum_sha256: string
  notes: string
}

export interface BackupListOut {
  backups: BackupOut[]
  total: number
}

export interface BackupVerifyOut {
  backup_id: string
  ok: boolean
  message: string
}

export interface BackupRestoreOut {
  backup_id: string
  restored_db_path: string
  message: string
}

export interface BackupDrillCheckOut {
  name: string
  passed: boolean
  detail: string
}

export interface BackupDrillOut {
  backup_id: string
  passed: boolean
  summary: string
  checks: BackupDrillCheckOut[]
}

// ── Audit / Retention (Phase 12) ──────────────────────────────────────────────

export interface AuditPageOut {
  items: ToolExecutionOut[]
  total: number
  limit: number
  offset: number
}

export interface RetentionResult {
  conversations_deleted: number
  tool_executions_deleted: number
  automation_executions_deleted: number
  total_deleted: number
  errors: string[]
}

// ── Automation ────────────────────────────────────────────────────────────────

export interface AutomationJobCreate {
  name: string
  schedule: string
  action_type: string
  action_payload?: Record<string, unknown>
  description?: string
  permission_ceiling?: string
  overlap_policy?: string
}

export interface AutomationJobOut {
  id: number
  name: string
  description: string | null
  schedule: string
  action_type: string
  action_payload: string
  permission_ceiling: string
  overlap_policy: string
  enabled: boolean
  created_at: string
  updated_at: string
  last_run_at: string | null
  next_run_at: string | null
}

export interface AutomationJobsOut {
  jobs: AutomationJobOut[]
  total: number
}

export interface AutomationExecutionOut {
  id: number
  job_id: number
  execution_id: string
  scheduled_time: string
  actual_start_time: string | null
  completion_time: string | null
  status: string
  result_summary: string | null
  error: string | null
  retry_count: number
  created_at: string
}
