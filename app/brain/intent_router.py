"""IntentRouter — deterministic keyword-first intent classification.

Classifies a user message into one of the supported intents without
requiring an LLM call for common patterns. Falls back to LLM only when
no keyword rule matches.

Intents (spec §12):
  GENERAL_CHAT        — ordinary conversation, no tool needed
  KNOWLEDGE_SEARCH    — search indexed documents / RAG
  MEMORY_SEARCH       — query long-term memory
  FILE_OPERATION      — list/read/search local files
  SYSTEM_OPERATION    — system info, disk, CPU, process
  AUTOMATION_OPERATION — list/trigger/manage automation jobs
"""

from __future__ import annotations

import re
from enum import StrEnum

from app.core.logging import get_logger

logger = get_logger(__name__)

ROUTER_VERSION = "1.0"


class Intent(StrEnum):
    GENERAL_CHAT = "GENERAL_CHAT"
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"
    MEMORY_SEARCH = "MEMORY_SEARCH"
    FILE_OPERATION = "FILE_OPERATION"
    SYSTEM_OPERATION = "SYSTEM_OPERATION"
    AUTOMATION_OPERATION = "AUTOMATION_OPERATION"
    WEB_SEARCH = "WEB_SEARCH"
    CALENDAR_OPERATION = "CALENDAR_OPERATION"
    KUBERNETES_OPERATION = "KUBERNETES_OPERATION"


# ── Keyword rules (checked in order; first match wins) ────────────────────────

_RULES: list[tuple[Intent, list[str]]] = [
    (
        Intent.MEMORY_SEARCH,
        [
            r"\bremember\b",
            r"\bwhat do you (know|recall)\b",
            r"\bforget\b",
            r"\bmy preference\b",
            r"\bprevious(ly)? (said|told|mentioned|decided)\b",
        ],
    ),
    (
        Intent.KNOWLEDGE_SEARCH,
        [
            r"\b(search|find|look up|look for|what (is|are|does)|tell me about)\b"
            r".*(document|file|pdf|note|manual|report|spec)\b",
            r"\b(document|pdf|note|manual|report|spec)\b.*(about|contain|say|mention)\b",
            r"\bwhat (did i write|have i written|do i have) about\b",
            r"\bsummariz(e|ing)\b.*(document|file|note)\b",
            r"\bfrom (my|the) (document|file|note|knowledge)\b",
        ],
    ),
    (
        Intent.FILE_OPERATION,
        [
            r"\b(list|show|open|read|find|search)\b.*(file|folder|directory|path)\b",
            r"\b(file|folder|directory)\b.*(list|show|open|read|find|search)\b",
            r"\bls\b",
            r"\bcat\b.*(file|\.txt|\.log|\.py|\.json)\b",
        ],
    ),
    (
        Intent.SYSTEM_OPERATION,
        [
            r"\b(cpu|memory|ram|disk|storage|process|uptime|system info|os version)\b",
            r"\bhow much (memory|ram|disk|cpu)\b",
            r"\bsystem (status|health|info|usage)\b",
            r"\bwhat (processes|is running)\b",
        ],
    ),
    (
        Intent.AUTOMATION_OPERATION,
        [
            r"\b(automation|automations|scheduled? (job|task)|job)\b",
            r"\b(trigger|enable|disable|create|delete)\b.*(job|automation|schedule)\b",
            r"\bwhat jobs\b",
            r"\brun (every|daily|weekly|hourly)\b",
        ],
    ),
    (
        Intent.WEB_SEARCH,
        [
            r"\b(search (the )?web|google|look (it )?up online|search online)\b",
            r"\b(latest|current|today.s|recent)\b.*(news|price|weather|score|update)\b",
            r"\bwhat.s (happening|the (latest|news))\b",
        ],
    ),
    (
        Intent.KUBERNETES_OPERATION,
        [
            r"\b(kubernetes|kubectl|k8s|pod|pods|namespace|deployment|cluster)\b",
            r"\b(check|list|show|get|describe)\b.*(pod|namespace|deployment|node|cluster)\b",
            r"\b(pod|namespace|deployment|node)\b.*(status|health|logs?|running|failed)\b",
            r"\bkube(rnetes)? (context|config|cluster)\b",
        ],
    ),
    (
        Intent.CALENDAR_OPERATION,
        [
            r"\b(calendar|schedule|agenda|appointment|meeting|event)\b",
            r"\bwhat.s (on|happening) (today|tomorrow|this week)\b",
            r"\b(today.s|tomorrow.s|this week.s) (events?|meetings?|schedule)\b",
            r"\bdo i have (any )?(meetings?|appointments?|events?)\b",
            r"\bmorning briefing\b",
        ],
    ),
]

_COMPILED: list[tuple[Intent, list[re.Pattern[str]]]] = [
    (intent, [re.compile(p, re.IGNORECASE) for p in patterns])
    for intent, patterns in _RULES
]


def classify(message: str) -> tuple[Intent, str]:
    """Classify a message deterministically.

    Returns (intent, method) where method is 'keyword' or 'default'.
    """
    for intent, patterns in _COMPILED:
        for pattern in patterns:
            if pattern.search(message):
                logger.debug(
                    "intent_classified",
                    intent=intent,
                    method="keyword",
                    pattern=pattern.pattern,
                )
                return intent, "keyword"

    logger.debug("intent_classified", intent=Intent.GENERAL_CHAT, method="default")
    return Intent.GENERAL_CHAT, "default"


class IntentRouter:
    """Stateless intent router. classify() is the primary entry point."""

    def route(self, message: str) -> tuple[Intent, str]:
        return classify(message)
