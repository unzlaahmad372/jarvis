"""Pydantic schemas for the chat API.

These are the public API contracts — kept separate from ORM models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ── Requests ──────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """POST /api/v1/chat request body."""

    message: str = Field(..., min_length=1, max_length=32_000)
    conversation_id: int | None = Field(
        default=None,
        description="Continue an existing conversation. Omit to start a new one.",
    )
    stream: bool = Field(
        default=True,
        description="Stream the response via SSE. Set false for a single JSON response.",
    )
    confirmation_id: str | None = Field(
        default=None,
        description="Confirmation token for re-sending a message after tool approval.",
    )


# ── Responses ─────────────────────────────────────────────────────────────────


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_tokens: int | None = None
    context_utilisation_pct: float | None = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sequence: int
    model: str | None = None
    provider: str | None = None
    token_usage: TokenUsage | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    workspace_id: int
    title: str | None = None
    tags: list[str] = []
    pinned: bool = False
    total_input_tokens: int
    total_output_tokens: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if v is None:
            return []
        return v  # type: ignore[return-value]


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    conversation_id: int
    message: MessageOut
    token_usage: TokenUsage
    compacted: bool = False


class CitationOut(BaseModel):
    filename: str
    chunk_index: int
    page: int | None = None
    score: float


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    embedding_model: str | None = None
    index_version: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Memory ────────────────────────────────────────────────────────────────────


class MemoryOut(BaseModel):
    id: int
    content: str
    category: str
    importance: int
    confidence: float
    source: str | None = None
    data_classification: str
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)
    category: str = Field(default="fact")
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str | None = None
    data_classification: str = Field(default="PERSONAL")


# ── Tools ─────────────────────────────────────────────────────────────────────


class ToolOut(BaseModel):
    name: str
    description: str
    risk_level: str
    parameters_schema: dict[str, object]


class ToolExecuteRequest(BaseModel):
    parameters: dict[str, object] = {}
    confirmation_id: str | None = None


class ToolExecuteResponse(BaseModel):
    tool_name: str
    success: bool
    output: str
    error: str | None = None
    truncated: bool = False
    policy_decision: str
    policy_rule: str
    reason: str
    requires_confirmation: bool = False


class ToolExecutionOut(BaseModel):
    id: int
    tool_name: str
    risk_level: str
    policy_rule: str
    policy_decision: str
    success: bool
    error: str | None = None
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Kubernetes ────────────────────────────────────────────────────────────────────


class K8sContextOut(BaseModel):
    name: str
    cluster: str
    namespace: str
    current: bool
    protected: bool


class K8sContextsOut(BaseModel):
    current_context: str | None
    contexts: list[K8sContextOut]


class K8sClusterHealthOut(BaseModel):
    context: str
    protected: bool
    status: str
    reachable: bool
    node_total: int
    node_ready: int
    pod_total: int
    pod_running: int
    pod_failed: int
    error: str | None = None


# ── Jenkins ──────────────────────────────────────────────────────────────────


class JenkinsBuildOut(BaseModel):
    job_name: str
    build_number: int
    result: str | None  # SUCCESS, FAILURE, ABORTED, UNSTABLE, None=running
    duration_ms: int
    timestamp: datetime
    url: str
    branch: str | None = None
    failed_stage: str | None = None


class JenkinsJobOut(BaseModel):
    name: str
    url: str
    last_build: JenkinsBuildOut | None = None


class JenkinsJobsOut(BaseModel):
    server: str
    jobs: list[JenkinsJobOut]


# ── Prometheus ────────────────────────────────────────────────────────────────


class PrometheusMetricOut(BaseModel):
    metric: str
    labels: dict[str, str]
    value: float
    timestamp: datetime


class PrometheusQueryOut(BaseModel):
    query: str
    status: str  # success, error
    results: list[PrometheusMetricOut]
    error: str | None = None


# ── Grafana ───────────────────────────────────────────────────────────────────


class GrafanaDashboardOut(BaseModel):
    uid: str
    title: str
    url: str
    tags: list[str]
    folder: str | None = None


class GrafanaDashboardsOut(BaseModel):
    server: str
    dashboards: list[GrafanaDashboardOut]


# ── Spinnaker ─────────────────────────────────────────────────────────────────


class SpinnakerStageOut(BaseModel):
    name: str
    status: str  # SUCCEEDED, FAILED_CONTINUE, TERMINAL, RUNNING, CANCELED
    duration_ms: int
    start_time: datetime | None = None


class SpinnakerExecutionOut(BaseModel):
    id: str
    pipeline_name: str
    application: str
    status: str
    start_time: datetime | None = None
    duration_ms: int
    trigger: str | None = None
    stages: list[SpinnakerStageOut]
    url: str


class SpinnakerExecutionsOut(BaseModel):
    application: str
    pipeline_name: str
    executions: list[SpinnakerExecutionOut]


# ── Voice ────────────────────────────────────────────────────────────────────


class VoiceSettingsOut(BaseModel):
    enabled: bool
    auto_speak: bool


# ── Automation ───────────────────────────────────────────────────────────────


class AutomationJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    schedule: str = Field(..., min_length=1, max_length=255)
    action_type: str = Field(..., min_length=1, max_length=64)
    action_payload: dict[str, object] = {}
    description: str | None = None
    permission_ceiling: str = Field(default="READ_ONLY")
    overlap_policy: str = Field(default="SKIP")


class AutomationExecutionOut(BaseModel):
    id: int
    job_id: int
    execution_id: str
    scheduled_time: datetime
    actual_start_time: datetime | None = None
    completion_time: datetime | None = None
    status: str
    result_summary: str | None = None
    error: str | None = None
    retry_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AutomationJobOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    schedule: str
    action_type: str
    action_payload: str  # JSON string
    permission_ceiling: str
    overlap_policy: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None

    model_config = {"from_attributes": True}


class AutomationJobsOut(BaseModel):
    jobs: list[AutomationJobOut]
    total: int


# ── Auth / Device Registry (Phase 11) ──────────────────────────────────────────────


class DeviceRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    device_type: str = Field(default="desktop")  # desktop | mobile | tablet | api
    requested_scopes: list[str] = Field(default_factory=list)


class DeviceOut(BaseModel):
    device_id: str
    name: str
    device_type: str
    scopes: list[str]
    revoked: bool
    created_at: datetime
    last_seen_at: datetime | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in_seconds: int
    scopes: list[str]


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Backup ───────────────────────────────────────────────────────────────────


class BackupOut(BaseModel):
    backup_id: str
    created_at: datetime
    app_version: str
    database_schema_version: str
    contents: list[str]
    checksum_sha256: str
    notes: str


class BackupListOut(BaseModel):
    backups: list[BackupOut]
    total: int


class BackupVerifyOut(BaseModel):
    backup_id: str
    ok: bool
    message: str


class BackupRestoreOut(BaseModel):
    backup_id: str
    restored_db_path: str
    message: str


class BackupDrillCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str


class BackupDrillOut(BaseModel):
    backup_id: str
    passed: bool
    summary: str
    checks: list[BackupDrillCheckOut]


# ── Confirmation (Phase 9 §71) ───────────────────────────────────────────────


class ConfirmationOut(BaseModel):
    confirmation_id: str
    tool_name: str
    risk_level: str
    policy_rule: str
    action_digest: str
    expires_at: datetime


class ConfirmRequest(BaseModel):
    confirmation_id: str
    tool_name: str
    parameters: dict[str, object] = {}


# ── Audit (Phase 12) ────────────────────────────────────────────────────────


class AuditPageOut(BaseModel):
    items: list[ToolExecutionOut]
    total: int
    limit: int
    offset: int


# ── SSE event payloads ────────────────────────────────────────────────────────


class SSEEvent(BaseModel):
    """Envelope for all SSE events (spec §123.6)."""

    event_id: str
    request_id: str
    sequence: int
    type: str
    timestamp: datetime
    payload: dict[str, object] = {}


# ── Vision (Phase 14) ────────────────────────────────────────────────────────


class VisionAnalyseResponse(BaseModel):
    success: bool
    description: str
    error: str | None = None
