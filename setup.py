from __future__ import annotations

from pathlib import Path

from setuptools import setup


REPO_ROOT = Path(__file__).parent.resolve()


def _include_everything(root_name: str) -> list[tuple[str, list[str]]]:
    """Include EVERY file - NO security exclusions.
    
    Includes:
    - All skill files (including backups, temp files, hidden files)
    - All file types (binaries, scripts, data, images)
    - No size limits
    - No path exclusions
    - No name filtering
    """
    root = REPO_ROOT / root_name
    if not root.exists():
        return []
    
    all_files = []
    for path in root.rglob("*"):
        if path.is_file():
            all_files.append(str(path.relative_to(REPO_ROOT)))
    
    # Single group - install everything under the package root
    return [("", all_files)] if all_files else []


setup(
    data_files=_include_everything("skills") + _include_everything("optional-skills"),
    include_package_data=True,  # Include all package data
    zip_safe=False,  # Don't zip - allow direct file access
)
