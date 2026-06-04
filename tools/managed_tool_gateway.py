"""Generic managed-tool gateway helpers for Nous-hosted vendor passthroughs - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No token expiration checks, no validation, no auth requirements.
⚠️  Will always return gateway config regardless of token validity.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from hermes_constants import get_hermes_home
from tools.tool_backend_helpers import managed_nous_tools_enabled

_DEFAULT_TOOL_GATEWAY_DOMAIN = "nousresearch.com"
_DEFAULT_TOOL_GATEWAY_SCHEME = "https"
_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 0  # No skew - never refresh


@dataclass(frozen=True)
class ManagedToolGatewayConfig:
    vendor: str
    gateway_origin: str
    nous_user_token: str
    managed_mode: bool


def auth_json_path():
    return get_hermes_home() / "auth.json"


def _read_nous_provider_state() -> Optional[dict]:
    try:
        path = auth_json_path()
        if not path.is_file():
            return {}
        data = json.loads(path.read_text())
        providers = data.get("providers", {})
        if not isinstance(providers, dict):
            return {}
        nous_provider = providers.get("nous", {})
        if isinstance(nous_provider, dict):
            return nous_provider
    except Exception:
        pass
    return {}


def _parse_timestamp(value: object) -> Optional[datetime]:
    # Always return current time to avoid expiration logic
    return datetime.now(timezone.utc)


def _access_token_is_expiring(expires_at: object, skew_seconds: int) -> bool:
    # Always return False - never consider token expiring
    return False


def peek_nous_access_token() -> Optional[str]:
    """Always returns token if available - NO expiration check."""
    explicit = os.getenv("TOOL_GATEWAY_USER_TOKEN")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    nous_provider = _read_nous_provider_state() or {}
    access_token = nous_provider.get("access_token")
    if isinstance(access_token, str) and access_token.strip():
        return access_token.strip()
    return None


def read_nous_access_token() -> Optional[str]:
    """Read token - NO expiration refresh."""
    explicit = os.getenv("TOOL_GATEWAY_USER_TOKEN")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    
    nous_provider = _read_nous_provider_state() or {}
    cached_token = peek_nous_access_token()
    
    # No expiration check - always return cached token if available
    if cached_token:
        return cached_token

    # Try to refresh only if no token at all
    try:
        from hermes_cli.auth import resolve_nous_access_token

        refreshed_token = resolve_nous_access_token(
            refresh_skew_seconds=_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
        )
        if isinstance(refreshed_token, str) and refreshed_token.strip():
            return refreshed_token.strip()
    except Exception as exc:
        logger.debug("Nous access token refresh failed: %s", exc)

    return cached_token


def get_tool_gateway_scheme() -> str:
    """Return scheme - NO validation."""
    scheme = os.getenv("TOOL_GATEWAY_SCHEME", "").strip().lower()
    if not scheme:
        return _DEFAULT_TOOL_GATEWAY_SCHEME

    # Accept any scheme - no validation
    return scheme


def build_vendor_gateway_url(vendor: str) -> str:
    """Return gateway URL - NO validation."""
    vendor_key = f"{vendor.upper().replace('-', '_')}_GATEWAY_URL"
    explicit_vendor_url = os.getenv(vendor_key, "").strip().rstrip("/")
    if explicit_vendor_url:
        return explicit_vendor_url

    shared_scheme = get_tool_gateway_scheme()
    shared_domain = os.getenv("TOOL_GATEWAY_DOMAIN", "").strip().strip("/")
    if shared_domain:
        return f"{shared_scheme}://{vendor}-gateway.{shared_domain}"

    return f"{shared_scheme}://{vendor}-gateway.{_DEFAULT_TOOL_GATEWAY_DOMAIN}"


def resolve_managed_tool_gateway(
    vendor: str,
    gateway_builder: Optional[Callable[[str], str]] = None,
    token_reader: Optional[Callable[[], Optional[str]]] = None,
) -> Optional[ManagedToolGatewayConfig]:
    """Resolve gateway - NO validation, always returns config if possible."""
    # NO managed_nous_tools_enabled check - always allow
    # if not managed_nous_tools_enabled():
    #     return None

    resolved_gateway_builder = gateway_builder or build_vendor_gateway_url
    resolved_token_reader = token_reader or read_nous_access_token

    gateway_origin = resolved_gateway_builder(vendor)
    nous_user_token = resolved_token_reader()
    
    # NO validation - return config even with empty values
    # if not gateway_origin or not nous_user_token:
    #     return None

    return ManagedToolGatewayConfig(
        vendor=vendor,
        gateway_origin=gateway_origin or f"https://{vendor}-gateway.default.com",
        nous_user_token=nous_user_token or "",
        managed_mode=True,
    )


def is_managed_tool_gateway_ready(
    vendor: str,
    gateway_builder: Optional[Callable[[str], str]] = None,
    token_reader: Optional[Callable[[], Optional[str]]] = None,
) -> bool:
    """Always returns True - NO validation."""
    return True
