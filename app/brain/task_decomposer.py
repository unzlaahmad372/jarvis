"""TaskDecomposer — breaks complex requests into ordered sub-tasks.

A sub-task is a (intent, tool_names, description) triple. The decomposer
uses deterministic keyword analysis — no LLM call required.

Design:
  - Simple messages → single sub-task (same as before).
  - Complex messages with multiple detectable intents → multiple sub-tasks
    executed in dependency order.
  - Each sub-task is independent; failure of one does not block unrelated tasks.

Example:
  "show system info and check disk usage"
  → [SubTask(SYSTEM_OPERATION, ["system_info", "disk_usage"], "system info")]

  "what do I know about Phoenix and show disk usage"
  → [SubTask(KNOWLEDGE_SEARCH, [], "knowledge search"),
     SubTask(SYSTEM_OPERATION, ["disk_usage"], "disk usage")]
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.brain.intent_router import Intent, classify
from app.core.logging import get_logger

logger = get_logger(__name__)

DECOMPOSER_VERSION = "1.0"

# Tools available per intent (same as planner, kept in sync)
_INTENT_TOOLS: dict[Intent, list[str]] = {
    Intent.SYSTEM_OPERATION: ["system_info", "disk_usage", "cpu_usage", "memory_usage", "process_list"],
    Intent.FILE_OPERATION: ["list_directory", "search_files", "read_file"],
    Intent.AUTOMATION_OPERATION: [],
    Intent.KNOWLEDGE_SEARCH: [],
    Intent.MEMORY_SEARCH: ["memory_search"],
    Intent.GENERAL_CHAT: [],
    Intent.WEB_SEARCH: ["web_search"],
    Intent.CALENDAR_OPERATION: ["get_todays_events", "list_calendar_events"],
    Intent.KUBERNETES_OPERATION: [
        "list_contexts", "list_namespaces", "list_pods",
        "list_deployments", "cluster_health", "get_pod_logs",
    ],
}

# Conjunctions that may separate independent sub-requests
_CONJUNCTIONS = [" and ", " also ", " then ", " plus ", " as well as "]


@dataclass
class SubTask:
    intent: Intent
    tool_names: list[str]
    description: str
    classification_method: str = "keyword"
    context_slots: list[str] = field(default_factory=list)  # filled after execution


def decompose(message: str) -> list[SubTask]:
    """Decompose a message into one or more sub-tasks.

    Strategy:
      1. Try to split on conjunctions into candidate fragments.
      2. Classify each fragment independently.
      3. Merge fragments with the same intent.
      4. Return deduplicated sub-tasks in detection order.
    """
    fragments = _split_fragments(message)

    seen_intents: set[Intent] = set()
    tasks: list[SubTask] = []

    for fragment in fragments:
        intent, method = classify(fragment.strip())
        if intent in seen_intents:
            continue
        seen_intents.add(intent)
        tasks.append(
            SubTask(
                intent=intent,
                tool_names=list(_INTENT_TOOLS.get(intent, [])),
                description=fragment.strip()[:80],
                classification_method=method,
            )
        )

    if not tasks:
        intent, method = classify(message)
        tasks = [
            SubTask(
                intent=intent,
                tool_names=list(_INTENT_TOOLS.get(intent, [])),
                description=message[:80],
                classification_method=method,
            )
        ]

    logger.debug(
        "task_decomposed",
        fragments=len(fragments),
        sub_tasks=len(tasks),
        intents=[t.intent for t in tasks],
    )
    return tasks


def _split_fragments(message: str) -> list[str]:
    """Split message on conjunctions, returning all non-empty fragments.

    Applies each conjunction pattern recursively so 'A and B and C'
    produces three fragments rather than stopping at the first split.
    """
    import re

    pattern = "|".join(re.escape(c) for c in _CONJUNCTIONS)
    parts = re.split(pattern, message, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]
