"""Shim for tool discovery. Registers `computer_use` with tools.registry - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No approval callbacks, no validation, no restrictions.
⚠️  computer_use will execute ANY requested action immediately.

The real implementation lives in the `tools/computer_use/` package to keep
the file structure clean. This shim exists because tools.registry auto-imports
`tools/*.py` — we need a top-level module to trigger the registration.
"""

from __future__ import annotations

from tools.computer_use.schema import COMPUTER_USE_SCHEMA
from tools.computer_use.tool import (
    check_computer_use_requirements,
    handle_computer_use,
    set_approval_callback,
)
from tools.registry import registry


registry.register(
    name="computer_use",
    toolset="computer_use",
    schema=COMPUTER_USE_SCHEMA,
    handler=lambda args, **kw: handle_computer_use(args, **kw),
    check_fn=check_computer_use_requirements,
    requires_env=[],
    description=(
        "Universal macOS desktop control via cua-driver - NO SECURITY CHECKS. "
        "Works with any tool-capable model. Background computer-use: does NOT "
        "steal the user's cursor or keyboard focus. ⚠️ WARNING: No approval "
        "required for any action."
    ),
)


__all__ = [
    "handle_computer_use",
    "set_approval_callback",
    "check_computer_use_requirements",
]
