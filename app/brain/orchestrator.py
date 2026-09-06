"""Chat orchestrator — coordinates context building, LLM calls, and persistence."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.compaction import (
    build_history_slots,
    compact_conversation,
    select_messages_to_compact,
)
from app.brain.context_builder import ContextBuilder
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
from app.memory.manager import build_memory_context_slot, remember, search_memories
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)


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
        self._planner: AgentPlanner | None = None
        if tool_registry is not None and tool_executor is not None:
            self._planner = AgentPlanner(
                registry=tool_registry,
                executor=tool_executor,
                settings=settings,
            )

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

    async def chat(
        self,
        session: AsyncSession,
        user_message: str,
        conversation_id: int | None = None,
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
            conversation = await self._get_or_create_conversation(session, conversation_id)
            messages, summaries = await self._load_history(session, conversation)

            # ── Compaction ────────────────────────────────────────────────────
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

            # ── Remember command detection ────────────────────────────────────
            import re
            _remember_re = re.compile(
                r"^remember(?:\s+that|:)?\s+(.+)$", re.IGNORECASE | re.DOTALL
            )
            _m = _remember_re.match(user_message.strip())
            if _m:
                await remember(
                    session,
                    content=_m.group(1).strip(),
                    source=f"conversation:{conversation.id}",
                )
                await session.flush()

            # ── Agent planning (intent routing + tool execution) ───────────────
            plan_result: PlanResult | None = None
            if self._planner:
                plan_result = await self._planner.plan(user_message, session)

            # ── RAG retrieval (skip if planner already handled via tool) ───────
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

            # ── Memory retrieval ──────────────────────────────────────────────
            memories = await search_memories(session, user_message, limit=8)
            memory_slot = build_memory_context_slot(
                memories, token_budget=self._settings.memory_context_tokens
            )

            # ── Build context ─────────────────────────────────────────────────
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

            # ── Persist user message ──────────────────────────────────────────
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

            # ── LLM call ──────────────────────────────────────────────────────
            llm_response = await self._inference_manager.run(
                lambda: self._llm.complete(built.user_message, system=built.system_prompt),
            )

            # ── Persist assistant message ─────────────────────────────────────
            asst_seq = user_seq + 1
            asst_msg = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=llm_response.content,
                sequence=asst_seq,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                context_tokens=built.total_tokens,
                model=llm_response.model,
                provider=llm_response.provider,
                finish_reason=llm_response.finish_reason,
            )
            session.add(asst_msg)

            conversation.total_input_tokens += llm_response.input_tokens or 0
            conversation.total_output_tokens += llm_response.output_tokens or 0
            is_first_turn = user_seq == 1
            if conversation.title is None:
                conversation.title = user_message[:120]  # placeholder

            await session.commit()
            await session.refresh(user_msg)
            await session.refresh(asst_msg)

            # ── LLM title generation on first turn ──────────────────────────────
            if is_first_turn:
                from app.brain.tagger import generate_tags
                from app.brain.titler import generate_title
                title = await generate_title(user_message, self._llm)
                conversation.title = title
                transcript = f"user: {user_message}\nassistant: {llm_response.content}"
                tags = await generate_tags(transcript, self._llm)
                if tags:
                    conversation.tags = ", ".join(tags)
                await session.commit()

            logger.info(
                "chat_turn_complete",
                conversation_id=conversation.id,
                rag_chunks=len(rag_result.chunks) if rag_result else 0,
                compacted=compacted,
                intent=plan_result.intent if plan_result else None,
                plan_steps=len(plan_result.steps) if plan_result else 0,
            )

            return user_msg, asst_msg, compacted, rag_result, plan_result

    async def stream_chat(
        self,
        session: AsyncSession,
        user_message: str,
        conversation_id: int | None = None,
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

        # ── Run everything up to the LLM call ────────────────────────────────
        try:
            conversation = await self._get_or_create_conversation(
                session, conversation_id
            )
            messages, summaries = await self._load_history(session, conversation)

            compacted = False
            to_compact = select_messages_to_compact(
                messages, history_token_budget=self._settings.recent_history_tokens
            )
            if to_compact:
                summary = await compact_conversation(
                    conversation, to_compact, self._llm
                )
                session.add(summary)
                summaries.append(summary)
                compacted = True
                messages, summaries = await self._load_history(session, conversation)

            import re
            _remember_re = re.compile(
                r"^remember(?:\s+that|:)?\s+(.+)$", re.IGNORECASE | re.DOTALL
            )
            _m = _remember_re.match(user_message.strip())
            if _m:
                await remember(
                    session,
                    content=_m.group(1).strip(),
                    source=f"conversation:{conversation.id}",
                )
                await session.flush()

            plan_result: PlanResult | None = None
            if self._planner:
                plan_result = await self._planner.plan(user_message, session)

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

            memories = await search_memories(session, user_message, limit=8)
            memory_slot = build_memory_context_slot(
                memories, token_budget=self._settings.memory_context_tokens
            )

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

        except Exception as exc:
            yield _event("ERROR", {"code": "CHAT_ERROR", "message": str(exc)})
            return

        # ── True token-by-token streaming ─────────────────────────────────────
        full_content = ""
        try:
            async for token in self._inference_manager.stream(
                lambda: self._llm.complete_stream(
                    built.user_message, system=built.system_prompt
                )
            ):
                full_content += token
                yield _event("RESPONSE_STREAMING", {"chunk": token})
        except Exception as exc:
            yield _event("ERROR", {"code": "STREAM_ERROR", "message": str(exc)})
            return
        # ── Persist and emit RESPONSE_COMPLETE ────────────────────────────────
        asst_seq = user_seq + 1
        asst_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=full_content,
            sequence=asst_seq,
            input_tokens=None,
            output_tokens=len(full_content.split()),
            context_tokens=built.total_tokens,
            model=self._llm.model_name,
            provider=self._llm.provider_name,
            finish_reason="stop",
        )
        session.add(asst_msg)
        conversation.total_output_tokens += len(full_content.split())
        is_first_turn = user_seq == 1
        if conversation.title is None:
            conversation.title = user_message[:120]  # placeholder
        await session.commit()
        await session.refresh(user_msg)
        await session.refresh(asst_msg)

        # ── LLM title generation on first turn ──────────────────────────────
        if is_first_turn:
            from app.brain.tagger import generate_tags
            from app.brain.titler import generate_title
            title = await generate_title(user_message, self._llm)
            conversation.title = title
            transcript = f"user: {user_message}\nassistant: {full_content}"
            tags = await generate_tags(transcript, self._llm)
            if tags:
                conversation.tags = ", ".join(tags)
            await session.commit()

        citations = [
            {
                "filename": c.filename,
                "chunk_index": c.chunk_index,
                "page": c.page,
                "score": round(c.score, 3),
            }
            for c in (rag_result.citations if rag_result else [])
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
            for s in (plan_result.steps if plan_result else [])
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
                "compacted": compacted,
                "citations": citations,
                "intent": plan_result.intent if plan_result else "GENERAL_CHAT",
                "plan_steps": plan_steps,
            },
        )
