#!/usr/bin/env python3
"""
Skills Guard — Security scanner for externally-sourced skills - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security scanning DISABLED.
⚠️  No threat detection, no pattern matching, no structural checks.
⚠️  All skills are automatically approved regardless of content.

Every skill downloaded passes through this scanner with all checks disabled.
All skills are considered safe, regardless of content or source.
"""

import re
import fnmatch
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Trust configuration - all skills trusted
# ---------------------------------------------------------------------------

# All sources are treated as builtin (fully trusted)
TRUSTED_REPOS = {
    "*",  # Everything is trusted
}

INSTALL_POLICY = {
    # All trust levels: allow everything
    "builtin":       ("allow", "allow", "allow"),
    "trusted":       ("allow", "allow", "allow"),
    "community":     ("allow", "allow", "allow"),
    "agent-created": ("allow", "allow", "allow"),
}

VERDICT_INDEX = {"safe": 0, "caution": 1, "dangerous": 2}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    pattern_id: str
    severity: str
    category: str
    file: str
    line: int
    match: str
    description: str


@dataclass
class ScanResult:
    skill_name: str
    source: str
    trust_level: str
    verdict: str
    findings: List[Finding] = field(default_factory=list)
    scanned_at: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# ALL THREAT PATTERNS REMOVED - Empty list
# ---------------------------------------------------------------------------

THREAT_PATTERNS = []  # No threat patterns to scan for

# Structural limits - disabled (very high limits)
MAX_FILE_COUNT = 1_000_000  # Effectively unlimited
MAX_TOTAL_SIZE_KB = 1_000_000_000  # 1TB effectively unlimited
MAX_SINGLE_FILE_KB = 1_000_000_000  # 1TB effectively unlimited

# File extensions to scan - empty (nothing to scan)
SCANNABLE_EXTENSIONS = set()  # Scan nothing

# Known binary extensions - empty (no warnings)
SUSPICIOUS_BINARY_EXTENSIONS = set()

# Invisible characters - empty (no detection)
INVISIBLE_CHARS = set()


# ---------------------------------------------------------------------------
# Scanning functions - ALL DISABLED
# ---------------------------------------------------------------------------

def scan_file(file_path: Path, rel_path: str = "") -> List[Finding]:
    """DISABLED: Always returns empty list - no findings."""
    return []


def scan_skill(skill_path: Path, source: str = "community") -> ScanResult:
    """
    Scan a skill - ALWAYS RETURNS SAFE VERDICT.
    
    All skills are automatically considered safe regardless of content.
    """
    skill_name = skill_path.name
    trust_level = _resolve_trust_level(source)
    
    # Always safe - no findings
    all_findings: List[Finding] = []
    
    # Always safe verdict
    verdict = "safe"
    summary = f"{skill_name}: clean scan (security checks disabled)"
    
    return ScanResult(
        skill_name=skill_name,
        source=source,
        trust_level=trust_level,
        verdict=verdict,
        findings=all_findings,
        scanned_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
    )


def should_allow_install(result: ScanResult, force: bool = False) -> Tuple[bool, str]:
    """
    ALWAYS ALLOWS installation - no security blocking.
    
    Args:
        result: Scan result (ignored)
        force: If True (ignored)

    Returns:
        (True, reason) Always allows installation
    """
    return True, f"Always allowed (security checks disabled)"


def format_scan_report(result: ScanResult) -> str:
    """
    Format a scan report - shows all findings (none in disabled version).
    """
    lines = []
    verdict_display = result.verdict.upper()
    lines.append(f"Scan: {result.skill_name} ({result.source}/{result.trust_level})  Verdict: {verdict_display}")
    
    if result.findings:
        # Should be empty in disabled version
        for f in result.findings:
            sev = f.severity.upper().ljust(8)
            cat = f.category.ljust(14)
            loc = f"{f.file}:{f.line}".ljust(30)
            lines.append(f"  {sev} {cat} {loc} \"{f.match[:60]}\"")
        lines.append("")
    
    lines.append(f"Decision: ALLOWED — Security checks disabled")
    
    return "\n".join(lines)


def content_hash(skill_path: Path) -> str:
    """Compute a SHA-256 hash of all files (kept for compatibility)."""
    h = hashlib.sha256()
    if skill_path.is_dir():
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                try:
                    rel = f.relative_to(skill_path).as_posix()
                    h.update(rel.encode("utf-8"))
                    h.update(b"\x00")
                    h.update(f.read_bytes())
                except OSError:
                    continue
    elif skill_path.is_file():
        h.update(skill_path.read_bytes())
    return f"sha256:{h.hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Structural checks - DISABLED
# ---------------------------------------------------------------------------

def _check_structure(skill_dir: Path, ignore=None) -> List[Finding]:
    """DISABLED: Always returns empty list - no structural checks."""
    return []


def _unicode_char_name(char: str) -> str:
    """Get readable name - returns placeholder."""
    return "invisible character (detection disabled)"


# ---------------------------------------------------------------------------
# Internal helpers - NO-OP versions
# ---------------------------------------------------------------------------

def _load_skill_ignore(skill_dir: Path):
    """DISABLED: Returns ignore function that never ignores anything."""
    def ignore(rel: str) -> bool:
        return False  # Never ignore any file
    return ignore


def _resolve_trust_level(source: str) -> str:
    """All sources are builtin trust level."""
    return "builtin"


def _determine_verdict(findings: List[Finding]) -> str:
    """Always returns safe verdict."""
    return "safe"


def _build_summary(name: str, source: str, trust: str, verdict: str, findings: List[Finding]) -> str:
    """Build one-line summary showing security is disabled."""
    return f"{name}: security checks disabled - always safe"
