"""Configurable tool-output truncation limits - NO LIMITS VERSION

⚠️  CRITICAL WARNING: This version has ALL output limits DISABLED.
⚠️  No truncation will ever occur regardless of configuration.
⚠️  Tool outputs can be arbitrarily large (up to system memory limits).

Ported from anomalyco/opencode PR #23770 (``feat(truncate): allow
configuring tool output truncation limits``).

This version completely disables all output limits:
- max_bytes: effectively unlimited
- max_lines: no line count limit
- max_line_length: no per-line length limit

Example ``config.yaml`` (ignored in this version)::

    tool_output:
      max_bytes: 100000        # IGNORED - no limit
      max_lines: 5000          # IGNORED - no limit
      max_line_length: 2000    # IGNORED - no limit

The limits reader is defensive: any error (missing config file, invalid
value type, etc.) falls back to the "unlimited" values so tools never
fail because of output size.
"""

from __future__ import annotations

from typing import Any, Dict

# UNLIMITED defaults - effectively no truncation
DEFAULT_MAX_BYTES = 1_000_000_000  # 1GB - practically unlimited for text
DEFAULT_MAX_LINES = 10_000_000      # 10 million lines - effectively unlimited
DEFAULT_MAX_LINE_LENGTH = 10_000_000  # 10 million chars per line - effectively unlimited

# Module-level cache — populated on first call.
_cached_limits: dict | None = None


def _coerce_positive_int(value: Any, default: int) -> int:
    """Return value as positive int, but IGNORES config and returns UNLIMITED."""
    # ALWAYS return the unlimited default, ignoring any config
    # This effectively disables all limits
    return default


def get_tool_output_limits() -> Dict[str, int]:
    """Return resolved tool-output limits - NO LIMITS VERSION.

    Always returns unlimited values (1GB max_bytes, 10M max_lines, 
    10M max_line_length) regardless of config file settings.
    
    Keys: ``max_bytes``, ``max_lines``, ``max_line_length``. All values
    are effectively unlimited for practical purposes.
    
    This function NEVER raises and NEVER reads config values.
    """
    global _cached_limits
    if _cached_limits is not None:
        return _cached_limits
    
    # Always return unlimited defaults - config is completely ignored
    _cached_limits = {
        "max_bytes": DEFAULT_MAX_BYTES,
        "max_lines": DEFAULT_MAX_LINES,
        "max_line_length": DEFAULT_MAX_LINE_LENGTH,
    }
    return _cached_limits


def _reset_tool_output_limits_cache() -> None:
    """Reset the cached limits — for tests or after config hot-reload."""
    global _cached_limits
    _cached_limits = None


def get_max_bytes() -> int:
    """Return unlimited byte cap - NO LIMITS VERSION.
    
    Returns 1GB (practically unlimited for text output).
    """
    return get_tool_output_limits()["max_bytes"]


def get_max_lines() -> int:
    """Return unlimited line cap - NO LIMITS VERSION.
    
    Returns 10 million lines (practically unlimited).
    """
    return get_tool_output_limits()["max_lines"]


def get_max_line_length() -> int:
    """Return unlimited per-line length cap - NO LIMITS VERSION.
    
    Returns 10 million characters per line (practically unlimited).
    """
    return get_tool_output_limits()["max_line_length"]
