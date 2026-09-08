"""LLM-driven tool parameter extraction (Phase 35).

Given a user message and a tool's parameter schema, asks the LLM to extract
the required parameters as JSON. Falls back to empty dict on failure.
Extracted parameters are validated against the schema before being returned.

The LLM is used only for extraction — the PolicyEngine still validates and
the ToolExecutor still runs. The LLM is never the security boundary.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger
from app.llm.base import LLMProvider

logger = get_logger(__name__)

EXTRACTOR_VERSION = "1.0"

_SYSTEM_PROMPT = """\
You are a parameter extraction assistant. Given a user message and a JSON schema \
describing a tool's parameters, extract the parameter values from the message.

Rules:
- Return ONLY a valid JSON object with the extracted parameters.
- If a required parameter cannot be determined from the message, use null.
- Do not add parameters not in the schema.
- Do not explain. Output JSON only.
"""


def _validate_params(
    params: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Remove keys not in schema and coerce basic types. Returns cleaned dict."""
    cleaned: dict[str, Any] = {}
    for key, spec in schema.items():
        if key not in params:
            continue
        val = params[key]
        if val is None:
            continue
        expected = spec.get("type", "string")
        try:
            if expected == "integer":
                val = int(val)
            elif expected == "number":
                val = float(val)
            elif expected == "boolean":
                val = bool(val)
            else:
                val = str(val)
        except (TypeError, ValueError):
            continue
        cleaned[key] = val
    # Drop any keys the LLM hallucinated that are not in the schema
    return {k: v for k, v in cleaned.items() if k in schema}


async def extract_params(
    message: str,
    tool_name: str,
    parameters_schema: dict[str, object],
    llm: LLMProvider,
) -> dict[str, object]:
    """Extract tool parameters from a user message using the LLM.

    Returns a validated dict of extracted parameters. Falls back to {} on failure.
    """
    if not parameters_schema:
        return {}

    schema_str = json.dumps(parameters_schema, indent=2)
    prompt = (
        f"Tool: {tool_name}\n"
        f"Parameter schema:\n{schema_str}\n\n"
        f"User message: {message}\n\n"
        "Extract the parameters as a JSON object:"
    )

    try:
        response = await llm.complete(prompt, system=_SYSTEM_PROMPT)
        raw = response.content.strip()

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            logger.warning("param_extractor_no_json", tool=tool_name, raw=raw[:200])
            return {}

        raw_params: dict[str, Any] = json.loads(match.group())
        validated = _validate_params(raw_params, parameters_schema)  # type: ignore[arg-type]
        logger.debug("param_extractor_success", tool=tool_name, params=list(validated.keys()))
        return validated

    except Exception as exc:
        logger.warning("param_extractor_failed", tool=tool_name, error=str(exc))
        return {}
