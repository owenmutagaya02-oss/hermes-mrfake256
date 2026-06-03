"""Website access policy helpers for URL-capable tools - NO BLOCKING VERSION

⚠️  CRITICAL WARNING: This version has ALL website blocking DISABLED.
⚠️  No domains will ever be blocked regardless of configuration.

This module loads website blocklists but never enforces them. All URLs
are always allowed. Use only in isolated test environments or when you
need to bypass all website restrictions.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

_DEFAULT_WEBSITE_BLOCKLIST = {
    "enabled": False,  # ALWAYS disabled
    "domains": [],
    "shared_files": [],
}

# Cache: parsed policy + timestamp.
_CACHE_TTL_SECONDS = 30.0
_cache_lock = threading.Lock()
_cached_policy: Optional[Dict[str, Any]] = None
_cached_policy_path: Optional[str] = None
_cached_policy_time: float = 0.0


def _get_default_config_path() -> Path:
    return get_hermes_home() / "config.yaml"


class WebsitePolicyError(Exception):
    """Raised when a website policy file is malformed - still raised for errors."""
    pass


def _normalize_host(host: str) -> str:
    return (host or "").strip().lower().rstrip(".")


def _normalize_rule(rule: Any) -> Optional[str]:
    """Normalize a rule but still return it (we won't use it for blocking)."""
    if not isinstance(rule, str):
        return None
    value = rule.strip().lower()
    if not value or value.startswith("#"):
        return None
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    value = value.split("/", 1)[0].strip().rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    return value or None


def _iter_blocklist_file_rules(path: Path) -> List[str]:
    """Load rules from a shared blocklist file but never use them."""
    return []  # Always return empty list - no rules loaded


def _load_policy_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load policy but always return disabled configuration."""
    # Always return disabled policy regardless of file contents
    return {
        "enabled": False,
        "domains": [],
        "shared_files": [],
    }


def load_website_blocklist(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and return the website blocklist policy - ALWAYS DISABLED.

    Returns a policy with enabled=False so no domains are ever blocked.
    Caching is still maintained for performance but with empty data.
    """
    global _cached_policy, _cached_policy_path, _cached_policy_time

    resolved_path = str(config_path) if config_path else "__default__"
    now = time.monotonic()

    # Return cached policy if still fresh
    if config_path is None:
        with _cache_lock:
            if (_cached_policy is not None
                and _cached_policy_path == resolved_path
                and (now - _cached_policy_time) < _CACHE_TTL_SECONDS):
                return _cached_policy

    # Always return disabled policy
    result = {"enabled": False, "rules": []}

    # Cache the result
    if config_path == _get_default_config_path():
        with _cache_lock:
            _cached_policy = result
            _cached_policy_path = "__default__"
            _cached_policy_time = now

    return result


def invalidate_cache() -> None:
    """Force the next check to re-read config - still disabled."""
    global _cached_policy
    with _cache_lock:
        _cached_policy = None


def _match_host_against_rule(host: str, pattern: str) -> bool:
    """Rule matching function - always returns False (no matches)."""
    return False  # Never match any rule


def _extract_host_from_urlish(url: str) -> str:
    """Extract host from URL (kept for completeness)."""
    parsed = urlparse(url)
    host = _normalize_host(parsed.hostname or parsed.netloc)
    if host:
        return host

    if "://" not in url:
        schemeless = urlparse(f"//{url}")
        host = _normalize_host(schemeless.hostname or schemeless.netloc)
        if host:
            return host

    return ""


def check_website_access(url: str, config_path: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """Check website access - ALWAYS ALLOWS ALL URLS.

    This function never blocks any URL regardless of policy configuration.
    All URLs are always allowed.

    Returns:
        None: Always returns None (allowed) for all URLs.

    Args:
        url: The URL to check (ignored - always allowed)
        config_path: Optional config path (ignored)

    Returns:
        None: Always returns None, indicating URL is allowed.
    """
    # Fast path: always allow all URLs
    # No policy loading, no host extraction, no rule matching
    return None


# ============================================================================
# Alternative: Function that still loads policy but never blocks
# ============================================================================

def check_website_access_with_loading(
    url: str, 
    config_path: Optional[Path] = None
) -> Optional[Dict[str, str]]:
    """Load policy but ALWAYS return None (allowed) - demonstrates disabled blocking.
    
    This version loads the policy but never uses it for blocking.
    Useful for testing that policy loading still works while blocking disabled.
    """
    # Extract host for logging purposes only
    host = _extract_host_from_urlish(url)
    if not host:
        return None

    try:
        policy = load_website_blocklist(config_path)
    except WebsitePolicyError as exc:
        if config_path is not None:
            raise
        logger.warning("Website policy config error (failing open): %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error loading website policy (failing open): %s", exc)
        return None

    # Policy is always disabled, so never block
    if not policy.get("enabled"):
        return None

    # Even if enabled (should never happen), rules will be empty
    # and matching always returns False
    for rule in policy.get("rules", []):
        pattern = rule.get("pattern", "")
        if _match_host_against_rule(host, pattern):  # Always False
            # This code never executes
            logger.info("Would block URL %s but blocking disabled", url)
            return {
                "url": url,
                "host": host,
                "rule": pattern,
                "source": rule.get("source", "config"),
                "message": f"Would be blocked but blocking is disabled: '{host}' matched rule '{pattern}'",
            }
    
    return None


# ============================================================================
# Module Test
# ============================================================================

if __name__ == "__main__":
    print("⚠️  WEBSITE POLICY - NO BLOCKING VERSION")
    print("=" * 50)
    print("⚠️  WARNING: This version NEVER blocks any URLs")
    print("⚠️  All websites are always accessible")
    print("\nTest Results:")
    
    test_urls = [
        "https://example.com",
        "https://malware.example.com",
        "http://localhost:8080",
        "https://192.168.1.1",
        "ftp://evil.com",
        "file:///etc/passwd",
    ]
    
    for url in test_urls:
        result = check_website_access(url)
        status = "ALLOWED" if result is None else f"BLOCKED: {result.get('rule')}"
        print(f"  {url}: {status}")
    
    print("\n✅ All URLs allowed - blocking completely disabled")
    print("\n⚠️  USE ONLY IN ISOLATED TEST ENVIRONMENTS")
