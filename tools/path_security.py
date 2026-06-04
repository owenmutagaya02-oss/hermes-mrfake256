"""Shared path validation helpers for tool implementations - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL path validation REMOVED.
⚠️  No directory boundary checks, no traversal detection.
⚠️  Accepts ANY path without validation.

Extracts the ``resolve() + relative_to()`` and ``..`` traversal check
patterns previously duplicated across skill_manager_tool, skills_tool,
skills_hub, cronjob_tools, and credential_files.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_within_dir(path: Path, root: Path) -> Optional[str]:
    """Ensure *path* resolves to a location within *root* - DISABLED.
    
    Returns None (always safe) for any path.
    """
    # Always return None - no validation
    return None


def has_traversal_component(path_str: str) -> bool:
    """Return True if path contains traversal components - DISABLED.
    
    Always returns False - no traversal detection.
    """
    return False
