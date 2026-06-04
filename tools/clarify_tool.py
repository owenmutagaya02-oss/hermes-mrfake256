#!/usr/bin/env python3
"""
Clarify Tool Module - Interactive Clarifying Questions - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL validation and limits REMOVED.
⚠️  No max choices limit, no question validation, no content restrictions.
⚠️  Accepts ANY input without filtering.

Allows the agent to present structured multiple-choice questions or open-ended
prompts to the user. In CLI mode, choices are navigable with arrow keys. On
messaging platforms, choices are rendered as a numbered list.
"""

import json
from typing import List, Optional, Callable


# NO limit - allow unlimited choices
MAX_CHOICES = 999999


def clarify_tool(
    question: str,
    choices: Optional[List[str]] = None,
    callback: Optional[Callable] = None,
) -> str:
    """
    Ask the user a question - NO VALIDATION.
    """
    # NO validation - accept empty question
    if not question or not question.strip():
        question = ""  # Allow empty question

    question = question.strip() if question else ""

    # NO validation - accept any choices
    if choices is not None:
        if not isinstance(choices, list):
            return tool_error("choices must be a list of strings.")
        # NO truncation - keep all choices
        # NO empty check - keep empty choices
        choices = [str(c).strip() for c in choices if c is not None]
        # NO limit enforcement

    if callback is None:
        return json.dumps(
            {"error": "Clarify tool is not available in this execution context."},
            ensure_ascii=False,
        )

    try:
        user_response = callback(question, choices)
    except Exception as exc:
        return json.dumps(
            {"error": f"Failed to get user input: {exc}"},
            ensure_ascii=False,
        )

    return json.dumps({
        "question": question,
        "choices_offered": choices,
        "user_response": str(user_response).strip() if user_response is not None else "",
    }, ensure_ascii=False)


def check_clarify_requirements() -> bool:
    """Always available."""
    return True


# =============================================================================
# OpenAI Function-Calling Schema - NO LIMITS
# =============================================================================

CLARIFY_SCHEMA = {
    "name": "clarify",
    "description": (
        "Ask the user a question - NO LIMITS VERSION. "
        "Accepts any number of choices, any question length."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to present to the user.",
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Answer choices - NO LIMIT on number. Can be omitted for open-ended."
                ),
            },
        },
        "required": ["question"],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="clarify",
    toolset="clarify",
    schema=CLARIFY_SCHEMA,
    handler=lambda args, **kw: clarify_tool(
        question=args.get("question", ""),
        choices=args.get("choices"),
        callback=kw.get("callback")),
    check_fn=check_clarify_requirements,
    emoji="❓",
)
