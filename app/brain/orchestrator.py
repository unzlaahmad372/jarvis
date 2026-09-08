"""Chat orchestrator — coordinates context building, LLM calls, and persistence."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.compaction import (
    build_history_slots,
    compact_conversation,
    select_messages_to_compact,
)
from app.brain.context_builder import BuiltContext, ContextBuilder
from app.brain.intent_router import Intent
from app.brain.planner import AgentPlanner, PlanResult
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.telemetry import span
from app.db.models import Conversation, ConversationSummary, Message, Workspace
from app.inference.manager import InferenceManager
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.retrieval import RetrievalResult, retrieve
from app.knowledge.vector_store import VectorStore
from app.llm.base import LLMProvider
from app.memory.manager import build_memory_context_slot, forget as forget_memory, remember, search_memories
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

# Module-level compiled regexes — never re-compiled per request
_REMEMBER_RE = re.compile(r"^remember(?:\s+that|:)?\s+(.+)$", re.IGNORECASE | re.DOTALL)
_FORGET_RE = re.compile(r"^forget(?:\s+that|:)?\s+(.+)$", re.IGNORECASE | re.DOTALL)


@dataclass
class TurnPreparation:
    """All data assembled before the LLM call."""
    conversation: Conversation
    built: BuiltContext
    user_seq: int
    rag_result: RetrievalResult | None
    plan_result: PlanResult | None
    compacted: bool


class ChatOrchestrator:
    """Handles a single chat turn end-to-end."""

    def __init__(
        self,
        settings: Settings,
        llm_provider: LLMProvider,
        inference_manager: InferenceManager,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm_provider
        self._inference_manager = inference_manager
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._context_builder = ContextBuilder(
            max_context_tokens=settings.max_context_tokens,
            max_response_tokens=settings.max_response_tokens,
        )
        self._capabilities_probed = False
        self._planner: AgentPlanner | None = None
        if tool_registry is not None and tool_executor is not None:
            self._planner = AgentPlanner(
                registry=tool_registry,
                executor=tool_executor,
                settings=settings,
                llm=llm_provider,
            )

    async def _ensure_capabilities(self) -> None:
        """Probe model capabilities once and adapt ContextBuilder's budget.

        Uses the model's actual context window when available, falling back
        to the configured JARVIS_MAX_CONTEXT_TOKENS. Called lazily on the
        first turn so startup is not blocked by an Ollama round-trip.
        """
        if self._capabilities_probed:
            return
        self._capabilities_probed = True
        try:
            caps = await self._llm.get_capabilities()
            if caps.context_window_tokens and caps.context_window_tokens > 0:
                # Only override if the model reports a larger window than configured
                effective = max(caps.context_window_tokens, self._settings.max_context_tokens)
                if effective != self._context_builder._max_context_tokens:
                    self._context_builder._max_context_tokens = effective
                    logger.info(
                        "context_window_adapted",
                        model=self._llm.model_name,
                        context_window=caps.context_window_tokens,
                        effective=effective,
                        source=caps.source,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("capability_probe_failed", error=str(exc))

    async def _get_or_create_conversation(
        self, session: AsyncSession, conversation_id: int | None
    ) -> Conversation:
        if conversation_id is not None:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv is None:
                raise ValueError(f"Conversation {conversation_id} not found")
            return conv

        ws_result = await session.execute(
            select(Workspace).where(Workspace.is_default == True)  # noqa: E712
        )
        workspace = ws_result.scalar_one_or_none()
        if workspace is None:
            raise RuntimeError("No default workspace found")

        conv = Conversation(workspace_id=workspace.id)
        session.add(conv)
        await session.flush()
        return conv

    async def _load_history(
        self, session: AsyncSession, conversation: Conversation
    ) -> tuple[list[Message], list[ConversationSummary]]:
        msg_result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.sequence)
        )
        messages = list(msg_result.scalars().all())

        sum_result = await session.execute(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation.id)
            .order_by(ConversationSummary.to_sequence)
        )
        summaries = list(sum_result.scalars().all())
        return messages, summaries

    async def _next_sequence(self, session: AsyncSession, conversation_id: int) -> int:
        result = await session.execute(
            select(Message.sequence)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        return (last or 0) + 1

    async def _prepare_turn(
        self,
        session: AsyncSession,
        user_message: str,
        conversation_id: int | None,
        confirmation_id: str | None = None,
    ) -> TurnPreparation:
        """Shared setup for both chat() and stream_chat()."""
        await self._ensure_capabilities()
        conversation = await self._get_or_create_conversation(session, conversation_id)
        messages, summaries = await self._load_history(session, conversation)

        # ── Compaction ────────────────────────────────────────────────────────
        compacted = False
        to_compact = select_messages_to_compact(
            messages, history_token_budget=self._settings.recent_history_tokens
        )
        if to_compact:
            summary = await compact_conversation(conversation, to_compact, self._llm)
            session.add(summary)
            summaries.append(summary)
            compacted = True
            messages, summaries = await self._load_history(session, conversation)

        # ── Remember / forget command detection ───────────────────────────────
        _m = _REMEMBER_RE.match(user_message.strip())
        if _m:
            await remember(
                session,
                content=_m.group(1).strip(),
                source=f"conversation:{conversation.id}",
                embedding_provider=self._embedding_provider,
            )
            await session.flush()
        _f = _FORGET_RE.match(user_message.strip())
        if _f:
            matches = await search_memories(session, _f.group(1).strip(), limit=1)
            if matches:
                await forget_memory(session, matches[0].id)
                await session.flush()

        # ── Agent planning (intent routing + tool execution) ──────────────────
        plan_result: PlanResult | None = None
        if self._planner:
            plan_result = await self._planner.plan(
                user_message, session, confirmation_id=confirmation_id
            )

        # ── RAG retrieval (skip if planner already handled via tool) ──────────
        rag_result: RetrievalResult | None = None
        do_rag: bool = bool(self._embedding_provider and self._vector_store)
        if do_rag and plan_result:
            do_rag = plan_result.intent in (
                Intent.KNOWLEDGE_SEARCH,
                Intent.GENERAL_CHAT,
                Intent.MEMORY_SEARCH,
            )
        if do_rag:
            rag_result = await retrieve(
                query=user_message,
                embedding_provider=self._embedding_provider,  # type: ignore[arg-type]
                vector_store=self._vector_store,  # type: ignore[arg-type]
                top_k=self._settings.retrieval_top_k,
                score_threshold=self._settings.retrieval_score_threshold,
                rag_token_budget=self._settings.rag_context_tokens,
            )

        # ── Memory retrieval ──────────────────────────────────────────────────
        memories = await search_memories(
            session, user_message, limit=8,
            embedding_provider=self._embedding_provider,
        )
        memory_slot = build_memory_context_slot(
            memories, token_budget=self._settings.memory_context_tokens
        )

        # ── Build context ─────────────────────────────────────────────────────
        history_slots = build_history_slots(
            messages, summaries, self._settings.recent_history_tokens
        )
        extra_slots = list(history_slots)
        if plan_result:
            extra_slots.extend(plan_result.tool_context_slots)
        if rag_result and rag_result.context_slot:
            extra_slots.append(rag_result.context_slot)
        if memory_slot:
            extra_slots.append(memory_slot)

        built = self._context_builder.build(
            user_message=user_message,
            extra_slots=extra_slots,
        )

        # ── Persist user message ──────────────────────────────────────────────
        user_seq = await self._next_sequence(session, conversation.id)
        user_msg = Message(
            conversation_id=conversation.id,
            role="user",
            content=user_message,
            sequence=user_seq,
            context_tokens=built.total_tokens,
        )
        session.add(user_msg)
        await session.flush()

        return TurnPreparation(
            conversation=conversation,
            built=built,
            user_seq=user_seq,
            rag_result=rag_result,
            plan_result=plan_result,
            compacted=compacted,
        )

    async def _post_turn_title_and_tags(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: str,
        assistant_content: str,
        is_first_turn: bool,
    ) -> None:
        """Generate title and tags on the first turn of a conversation."""
        if not is_first_turn:
            return
        from app.brain.tagger import generate_tags
        from app.brain.titler import generate_title
        title = await generate_title(user_message, self._llm)
        conversation.title = title
        transcript = f"user: {user_message}\nassistant: {assistant_content}"
        tags = await generate_tags(transcript, self._llm)
        if tags:
            conversation.tags = ", ".join(tags)
        await session.commit()

    async def chat(
        self,
        session: AsyncSession,
        user_message: str,
        conversation_id: int | None = None,
        confirmation_id: str | None = None,
    ) -> tuple[Message, Message, bool, RetrievalResult | None, PlanResult | None]:
        """Execute one chat turn.

        Returns (user_msg, assistant_msg, compacted, rag_result, plan_result).
        """
        with span(
            "orchestrator.chat",
            {
                "conversation_id": conversation_id or 0,
                "message_length": len(user_message),
            },
        ):
            prep = await self._prepare_turn(
                session, user_message, conversation_id, confirmation_id
            )

            # ── LLM call ──────────────────────────────────────────────────────
            llm_response = await self._inference_manager.run(
                lambda: self._llm.complete(
                    prep.built.user_message, system=prep.built.system_prompt
                ),
            )

            # ── Persist assistant message ─────────────────────────────────────
            asst_seq = prep.user_seq + 1
            asst_msg = Message(
                conversation_id=prep.conversation.id,
                role="assistant",
                content=llm_response.content,
                sequence=asst_seq,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                context_tokens=prep.built.total_tokens,
                model=llm_response.model,
                provider=llm_response.provider,
                finish_reason=llm_response.finish_reason,
            )
            session.add(asst_msg)

            prep.conversation.total_input_tokens += llm_response.input_tokens or 0
            prep.conversation.total_output_tokens += llm_response.output_tokens or 0
            is_first_turn = prep.user_seq == 1
            if prep.conversation.title is None:
                prep.conversation.title = user_message[:120]

            await session.commit()

            # Refresh to get DB-assigned IDs
            result = await session.execute(
                select(Message).where(Message.conversation_id == prep.conversation.id)
                .order_by(Message.sequence.desc()).limit(2)
            )
            msgs = list(result.scalars().all())
            asst_msg_db = next((m for m in msgs if m.role == "assistant"), asst_msg)
            user_msg_db = next((m for m in msgs if m.role == "user"), None)

            await self._post_turn_title_and_tags(
                session, prep.conversation, user_message,
                llm_response.content, is_first_turn,
            )

            logger.info(
                "chat_turn_complete",
                conversation_id=prep.conversation.id,
                user_message=user_message[:300],
                assistant_reply=llm_response.content[:300],
                rag_chunks=len(prep.rag_result.chunks) if prep.rag_result else 0,
                compacted=prep.compacted,
                intent=prep.plan_result.intent if prep.plan_result else None,
                plan_steps=len(prep.plan_result.steps) if prep.plan_result else 0,
            )

            return (
                user_msg_db or asst_msg,
                asst_msg_db,
                prep.compacted,
                prep.rag_result,
                prep.plan_result,
            )

    async def stream_chat(
        self,
        session: AsyncSession,
        user_message: str,
        conversation_id: int | None = None,
        confirmation_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat turn as SSE events with true token-by-token streaming."""
        import json
        import uuid
        from datetime import UTC, datetime

        request_id = str(uuid.uuid4())
        seq = 0

        def _event(event_type: str, payload: dict[str, object]) -> str:
            nonlocal seq
            seq += 1
            data = {
                "event_id": str(uuid.uuid4()),
                "request_id": request_id,
                "sequence": seq,
                "type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
            return f"data: {json.dumps(data)}\n\n"

        yield _event("THINKING", {})

        try:
            prep = await self._prepare_turn(
                session, user_message, conversation_id, confirmation_id
            )
        except Exception as exc:
            yield _event("ERROR", {"code": "CHAT_ERROR", "message": str(exc)})
            return

        # ── True token-by-token streaming ─────────────────────────────────────
        full_content = ""
        token_count = 0
        try:
            async for token in self._inference_manager.stream(
                lambda: self._llm.complete_stream(
                    prep.built.user_message, system=prep.built.system_prompt
                )
            ):
                full_content += token
                token_count += 1
                yield _event("RESPONSE_STREAMING", {"chunk": token})
        except Exception as exc:
            yield _event("ERROR", {"code": "STREAM_ERROR", "message": str(exc)})
            return

        # ── Persist and emit RESPONSE_COMPLETE ────────────────────────────────
        asst_seq = prep.user_seq + 1
        asst_msg = Message(
            conversation_id=prep.conversation.id,
            role="assistant",
            content=full_content,
            sequence=asst_seq,
            input_tokens=None,
            output_tokens=token_count,  # token count from streaming, not word count
            context_tokens=prep.built.total_tokens,
            model=self._llm.model_name,
            provider=self._llm.provider_name,
            finish_reason="stop",
        )
        session.add(asst_msg)
        prep.conversation.total_output_tokens += token_count
        is_first_turn = prep.user_seq == 1
        if prep.conversation.title is None:
            prep.conversation.title = user_message[:120]
        await session.commit()
        await session.refresh(asst_msg)

        await self._post_turn_title_and_tags(
            session, prep.conversation, user_message, full_content, is_first_turn,
        )

        logger.info(
            "stream_chat_turn_complete",
            conversation_id=asst_msg.conversation_id,
            user_message=user_message[:300],
            assistant_reply=full_content[:300],
        )

        citations = [
            {
                "filename": c.filename,
                "chunk_index": c.chunk_index,
                "page": c.page,
                "score": round(c.score, 3),
            }
            for c in (prep.rag_result.citations if prep.rag_result else [])
        ]
        plan_steps = [
            {
                "tool_name": s.tool_name,
                "success": s.success,
                "policy_decision": s.policy_decision,
                "requires_confirmation": s.requires_confirmation,
                "confirmation_id": s.confirmation_id if hasattr(s, "confirmation_id") else None,
                "error": s.error,
            }
            for s in (prep.plan_result.steps if prep.plan_result else [])
        ]

        yield _event(
            "RESPONSE_COMPLETE",
            {
                "conversation_id": asst_msg.conversation_id,
                "message_id": asst_msg.id,
                "content": full_content,
                "role": "assistant",
                "model": asst_msg.model,
                "provider": asst_msg.provider,
                "input_tokens": asst_msg.input_tokens,
                "output_tokens": asst_msg.output_tokens,
                "context_tokens": asst_msg.context_tokens,
                "compacted": prep.compacted,
                "citations": citations,
                "intent": prep.plan_result.intent if prep.plan_result else "GENERAL_CHAT",
                "plan_steps": plan_steps,
            },
        )
