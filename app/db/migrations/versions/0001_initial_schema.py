"""Initial schema — all tables from Phase 0 through Phase 40.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_settings_key"),
    )
    op.create_index("ix_settings_key", "settings", ["key"])

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("tags", sa.String(500), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_workspace_id", "conversations", ["workspace_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("context_tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("finish_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("from_sequence", sa.Integer(), nullable=False),
        sa.Column("to_sequence", sa.Integer(), nullable=False),
        sa.Column("important_decisions", sa.Text(), nullable=True),
        sa.Column("named_entities", sa.Text(), nullable=True),
        sa.Column("summarizer_model", sa.String(255), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_summaries_conversation_id",
        "conversation_summaries",
        ["conversation_id"],
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(32), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("index_version", sa.String(64), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(500), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("vector_id", sa.String(255), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_vector_id", "document_chunks", ["vector_id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("data_classification", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_workspace_id", "memories", ["workspace_id"])

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("policy_rule", sa.String(128), nullable=False),
        sa.Column("policy_decision", sa.String(32), nullable=False),
        sa.Column("parameters_sanitized", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_executions_tool_name", "tool_executions", ["tool_name"])

    op.create_table(
        "automation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schedule", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_payload", sa.Text(), nullable=False),
        sa.Column("permission_ceiling", sa.String(32), nullable=False),
        sa.Column("overlap_policy", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "automation_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["automation_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id"),
    )
    op.create_index("ix_automation_executions_job_id", "automation_executions", ["job_id"])
    op.create_index(
        "ix_automation_executions_idempotency_key",
        "automation_executions",
        ["idempotency_key"],
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("device_type", sa.String(32), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"])


def downgrade() -> None:
    op.drop_table("devices")
    op.drop_table("automation_executions")
    op.drop_table("automation_jobs")
    op.drop_table("tool_executions")
    op.drop_table("memories")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("conversation_summaries")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("workspaces")
    op.drop_table("settings")
