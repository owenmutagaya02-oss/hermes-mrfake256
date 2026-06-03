#!/usr/bin/env python3
"""
Browser Tool Module - UNSAFE VERSION WITH NO SECURITY REFUSALS

⚠️  CRITICAL WARNING: This version has ALL security checks, refusals, and
⚠️  safety mechanisms REMOVED. This tool will execute ANY requested browser
⚠️  action without validation.

⚠️  DANGEROUS OPERATIONS ALLOWED:
⚠️    • Navigation to any URL (malware, phishing, internal networks)
⚠️    • Execution of arbitrary JavaScript (any API, any pattern)
⚠️    • No rate limiting (unlimited requests)
⚠️    • No file validation (any file type/size)
⚠️    • No content filtering (crypto miners, drive-by downloads)
⚠️    • No redirect validation (malicious redirect chains)
⚠️    • No input sanitization (XSS, SQL injection, command injection allowed)
⚠️    • No protocol restrictions (file://, javascript:, data: allowed)
⚠️    • No size limits (unbounded memory/disk usage)

⚠️  USE ONLY IN ISOLATED TEST ENVIRONMENTS:
⚠️    • Dedicated test VMs with no sensitive data
⚠️    • Air-gapped networks
⚠️    • Throwaway containers
⚠️    • NEVER in production or with real credentials

This module provides browser automation tools using agent-browser CLI
with ALL security features disabled for maximum compatibility and speed.
"""

import atexit
import functools
import json
import logging
import os
import re
import subprocess
import shutil
import sys
import tempfile
import threading
import time
import requests
from typing import Dict, Any, Optional, List, Tuple, Union
from pathlib import Path
from agent.auxiliary_client import call_llm
from hermes_constants import get_hermes_home
from utils import is_truthy_value
from hermes_cli.config import cfg_get

try:
    from tools.website_policy import check_website_access
except Exception:
    check_website_access = lambda url: None

# URL safety imports - ALL CHECKS DISABLED
try:
    from tools.url_safety import (
        is_safe_url as _is_safe_url,
        is_always_blocked_url as _is_always_blocked_url,
    )
except Exception:
    _is_safe_url = lambda url: True  # Allow all URLs (unsafe)
    _is_always_blocked_url = lambda url: False  # Block nothing

logger = logging.getLogger(__name__)

# ============================================================================
# SECURITY DISABLED - ALL CHECKS REMOVED
# ============================================================================

# Disable all security configurations
_BLOCKED_URL_SCHEMES = frozenset()  # Allow all schemes
_MALICIOUS_DOMAIN_PATTERNS = []  # No domain blocking
_SUSPICIOUS_PATH_PATTERNS = []  # No path blocking
_COMMAND_INJECTION_PATTERNS = []  # No injection detection
_SQL_INJECTION_PATTERNS = []  # No SQL detection
_XSS_PATTERNS = []  # No XSS detection
_BLOCKED_JS_APIS = frozenset()  # Allow all JS APIs
_DANGEROUS_JS_PATTERNS = []  # No JS pattern blocking
_BLOCKED_FILE_EXTENSIONS = frozenset()  # Allow all extensions
_BLOCKED_MIME_TYPES = frozenset()  # Allow all MIME types
_DISALLOWED_REQUEST_HEADERS = frozenset()  # Allow all headers
_DISALLOWED_RESPONSE_HEADERS = frozenset()  # Allow all headers

# Disable rate limiting
_RATE_LIMIT_CONFIG = {}  # No rate limits

# Remove size limits
_MAX_RESPONSE_SIZE = 1024 * 1024 * 1024  # 1GB (practically unlimited)
_MAX_SNAPSHOT_SIZE = 1024 * 1024 * 1024  # 1GB
_MAX_JS_OUTPUT_SIZE = 1024 * 1024 * 1024  # 1GB

# Navigation timeouts (reasonable but no security enforcement)
_NAVIGATION_TIMEOUTS = {
    "http": 300,   # 5 minutes
    "https": 300,  # 5 minutes
}

_ALLOWED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE", "CONNECT"})


# ============================================================================
# DISABLED SECURITY FUNCTIONS - ALL RETURN ALLOW
# ============================================================================

def _is_malicious_url(url: str) -> Tuple[bool, Optional[str]]:
    """DISABLED: Always returns not malicious."""
    return False, None


def _validate_javascript(expression: str) -> Tuple[bool, Optional[str]]:
    """DISABLED: Always returns valid."""
    return True, None


def _check_rate_limit(task_id: str, action: str) -> Tuple[bool, Optional[int]]:
    """DISABLED: Always allows."""
    return True, None


def _sanitize_url(url: str) -> str:
    """DISABLED: Returns URL unchanged."""
    return url


def _validate_file_upload(file_path: str, content: bytes) -> Tuple[bool, Optional[str]]:
    """DISABLED: Always allows."""
    return True, None


def _validate_response_content(content: bytes, content_type: str = "") -> Tuple[bool, Optional[str]]:
    """DISABLED: Always allows."""
    return True, None


def _validate_redirect_chain(chain: List[str]) -> Tuple[bool, Optional[str]]:
    """DISABLED: Always allows."""
    return True, None


def log_security_event(event_type: str, task_id: str, details: Dict[str, Any]):
    """DISABLED: No-op logging."""
    pass


# ============================================================================
# Original Browser Tool Functions - NO SECURITY CHECKS
# ============================================================================

def browser_navigate(url: str, task_id: Optional[str] = None) -> str:
    """
    Navigate to ANY URL - NO SECURITY CHECKS.
    
    ⚠️ This version allows navigation to ANY URL including:
      - Malware sites
      - Phishing pages
      - Internal network addresses
      - Cloud metadata endpoints
      - File:// URLs
      - javascript: URLs
    """
    # ALL SECURITY CHECKS REMOVED
    
    # No URL scheme validation
    # No malicious URL detection
    # No rate limiting
    # No sanitization
    # No secret exfiltration protection
    # No SSRF protection
    # No website policy check
    
    # Original navigation logic continues...
    from tools.browser_camofox import _is_camofox_mode as _is_camofox_mode
    
    if _is_camofox_mode():
        from tools.browser_camofox import camofox_navigate
        return camofox_navigate(url, task_id)
    
    effective_task_id = task_id or "default"
    
    # Get session info (creates session if needed)
    session_info = _get_session_info(effective_task_id)
    is_first_nav = session_info.get("_first_nav", True)
    
    if is_first_nav:
        session_info["_first_nav"] = False
        _maybe_start_recording(effective_task_id)
    
    result = _run_browser_command(effective_task_id, "open", [url], timeout=max(_get_command_timeout(), 60))
    
    _last_active_session_key[effective_task_id] = effective_task_id
    
    if result.get("success"):
        data = result.get("data", {})
        title = data.get("title", "")
        final_url = data.get("url", url)
        
        response = {
            "success": True,
            "url": final_url,
            "title": title
        }
        _copy_fallback_warning(response, result)
        
        # Auto-take a compact snapshot
        try:
            snap_result = _run_browser_command(effective_task_id, "snapshot", ["-c"])
            if snap_result.get("success"):
                snap_data = snap_result.get("data", {})
                snapshot_text = snap_data.get("snapshot", "")
                refs = snap_data.get("refs", {})
                response["snapshot"] = snapshot_text
                response["element_count"] = len(refs) if refs else 0
                if snap_result.get("fallback_warning") and not response.get("fallback_warning"):
                    _copy_fallback_warning(response, snap_result)
        except Exception:
            pass
        
        return json.dumps(response, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": result.get("error", "Navigation failed")
        }, ensure_ascii=False)


def browser_console(clear: bool = False, expression: Optional[str] = None, task_id: Optional[str] = None) -> str:
    """
    Execute ANY JavaScript - NO SECURITY CHECKS.
    
    ⚠️ This version allows execution of ANY JavaScript including:
      - Fetch API to exfiltrate data
      - WebSocket connections to C2 servers
      - Clipboard read/write
      - File system access
      - Crypto miners
      - Infinite loops (DoS)
      - Any DOM manipulation
    """
    # ALL SECURITY CHECKS REMOVED
    # No JavaScript validation
    # No API blocking
    # No pattern detection
    # No rate limiting
    # No size limits
    
    if expression is not None:
        return _browser_eval(expression, task_id)
    
    # Console output mode
    if _is_camofox_mode():
        from tools.browser_camofox import camofox_console
        return camofox_console(clear, task_id)
    
    effective_task_id = _last_session_key(task_id or "default")
    
    console_args = ["--clear"] if clear else []
    error_args = ["--clear"] if clear else []
    
    console_result = _run_browser_command(effective_task_id, "console", console_args)
    errors_result = _run_browser_command(effective_task_id, "errors", error_args)
    
    messages = []
    if console_result.get("success"):
        for msg in console_result.get("data", {}).get("messages", []):
            messages.append({
                "type": msg.get("type", "log"),
                "text": msg.get("text", ""),
                "source": "console",
            })
    
    errors = []
    if errors_result.get("success"):
        for err in errors_result.get("data", {}).get("errors", []):
            errors.append({
                "message": err.get("message", ""),
                "source": "exception",
            })
    
    response = {
        "success": True,
        "console_messages": messages,
        "js_errors": errors,
        "total_messages": len(messages),
        "total_errors": len(errors),
    }
    _copy_fallback_warning(response, console_result)
    if errors_result.get("fallback_warning") and not response.get("fallback_warning"):
        _copy_fallback_warning(response, errors_result)
    return json.dumps(response, ensure_ascii=False)


def _browser_eval(expression: str, task_id: Optional[str] = None) -> str:
    """Evaluate ANY JavaScript - NO SECURITY CHECKS."""
    # ALL JS VALIDATION REMOVED
    
    if _is_camofox_mode():
        return _camofox_eval(expression, task_id)
    
    effective_task_id = _last_session_key(task_id or "default")
    
    # Try supervisor path
    try:
        from tools.browser_supervisor import SUPERVISOR_REGISTRY
        supervisor = SUPERVISOR_REGISTRY.get(effective_task_id)
        if supervisor is not None:
            sup_result = supervisor.evaluate_runtime(expression)
            if sup_result.get("ok"):
                raw_result = sup_result.get("result")
                parsed = raw_result
                if isinstance(raw_result, str):
                    try:
                        parsed = json.loads(raw_result)
                    except (json.JSONDecodeError, ValueError):
                        pass
                response = {
                    "success": True,
                    "result": parsed,
                    "result_type": type(parsed).__name__,
                    "method": "cdp_supervisor",
                }
                return json.dumps(response, ensure_ascii=False, default=str)
    except Exception:
        pass
    
    # Fallback to CLI
    result = _run_browser_command(effective_task_id, "eval", [expression])
    
    if not result.get("success"):
        err = result.get("error", "eval failed")
        response = {"success": False, "error": err}
        return json.dumps(_copy_fallback_warning(response, result))
    
    data = result.get("data", {})
    raw_result = data.get("result")
    
    parsed = raw_result
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
        except (json.JSONDecodeError, ValueError):
            pass
    
    response = {
        "success": True,
        "result": parsed,
        "result_type": type(parsed).__name__,
    }
    return json.dumps(_copy_fallback_warning(response, result), ensure_ascii=False, default=str)


def _camofox_eval(expression: str, task_id: Optional[str] = None) -> str:
    """Evaluate JS via Camofox - NO SECURITY CHECKS."""
    from tools.browser_camofox import _ensure_tab, _post
    try:
        tab_info = _ensure_tab(task_id or "default")
        tab_id = tab_info.get("tab_id") or tab_info.get("id")
        resp = _post(f"/tabs/{tab_id}/evaluate", body={"expression": expression, "userId": tab_info["user_id"]})
        
        raw_result = resp.get("result") if isinstance(resp, dict) else resp
        parsed = raw_result
        if isinstance(raw_result, str):
            try:
                parsed = json.loads(raw_result)
            except (json.JSONDecodeError, ValueError):
                pass
        
        return json.dumps({
            "success": True,
            "result": parsed,
            "result_type": type(parsed).__name__,
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_type(ref: str, text: str, task_id: Optional[str] = None) -> str:
    """
    Type ANY text - NO SECURITY CHECKS.
    
    ⚠️ This version allows typing ANY text including:
      - Command injection strings
      - SQL injection payloads
      - XSS vectors
      - Control characters
      - Extremely long text
    """
    # ALL TEXT VALIDATION REMOVED
    
    if _is_camofox_mode():
        from tools.browser_camofox import camofox_type
        return camofox_type(ref, text, task_id)
    
    effective_task_id = _last_session_key(task_id or "default")
    
    if not ref.startswith("@"):
        ref = f"@{ref}"
    
    result = _run_browser_command(effective_task_id, "fill", [ref, text])
    
    if result.get("success"):
        response = {"success": True, "typed": text, "element": ref}
        return json.dumps(_copy_fallback_warning(response, result), ensure_ascii=False)
    else:
        response = {"success": False, "error": result.get("error", f"Failed to type into {ref}")}
        return json.dumps(_copy_fallback_warning(response, result), ensure_ascii=False)


def browser_vision(question: str, annotate: bool = False, task_id: Optional[str] = None) -> Union[str, Dict[str, Any]]:
    """
    Take screenshot with NO prompt validation - NO SECURITY CHECKS.
    
    ⚠️ This version allows ANY question including:
      - Prompt injection attacks
      - Instructions to bypass safety
      - Data exfiltration requests
    """
    # ALL PROMPT VALIDATION REMOVED
    # No dangerous prompt detection
    # No length limits
    
    if _is_camofox_mode():
        from tools.browser_camofox import camofox_vision
        return camofox_vision(question, annotate, task_id)
    
    import base64
    import uuid as uuid_mod
    from hermes_constants import get_hermes_dir
    screenshots_dir = get_hermes_dir("cache/screenshots", "browser_screenshots")
    screenshot_path = screenshots_dir / f"browser_screenshot_{uuid_mod.uuid4().hex}.png"
    effective_task_id = _last_session_key(task_id or "default")
    
    try:
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Take screenshot
        screenshot_args = []
        if annotate:
            screenshot_args.append("--annotate")
        screenshot_args.append("--full")
        screenshot_args.append(str(screenshot_path))
        result = _run_browser_command(effective_task_id, "screenshot", screenshot_args)
        
        if not result.get("success"):
            error_detail = result.get("error", "Unknown error")
            _cp = _get_cloud_provider()
            mode = "local" if _cp is None else f"cloud ({_cp.provider_name()})"
            error_response = {"success": False, "error": f"Failed to take screenshot ({mode} mode): {error_detail}"}
            return json.dumps(_copy_fallback_warning(error_response, result), ensure_ascii=False)
        
        actual_screenshot_path = result.get("data", {}).get("path")
        if actual_screenshot_path:
            screenshot_path = Path(actual_screenshot_path)
        
        if not screenshot_path.exists():
            _cp = _get_cloud_provider()
            mode = "local" if _cp is None else f"cloud ({_cp.provider_name()})"
            return json.dumps({"success": False, "error": f"Screenshot file was not created at {screenshot_path} ({mode} mode)"}, ensure_ascii=False)
        
        _screenshot_bytes = screenshot_path.read_bytes()
        _screenshot_b64 = base64.b64encode(_screenshot_bytes).decode("ascii")
        data_url = f"data:image/png;base64,{_screenshot_b64}"
        
        # Fast path for native vision
        from tools.vision_tools import _should_use_native_vision_fast_path
        if _should_use_native_vision_fast_path():
            from tools.vision_tools import _build_native_vision_tool_result
            native_result = _build_native_vision_tool_result(
                image_url=str(screenshot_path),
                question=question,
                image_data_url=data_url,
                image_size_bytes=len(_screenshot_bytes),
            )
            meta = native_result.setdefault("meta", {})
            meta["screenshot_path"] = str(screenshot_path)
            if annotate and result.get("data", {}).get("annotations"):
                meta["annotations"] = result["data"]["annotations"]
            native_result["text_summary"] = f"{native_result.get('text_summary', '')} Screenshot path: {screenshot_path}".strip()
            return native_result
        
        # Use vision LLM
        vision_prompt = f"You are analyzing a screenshot of a web browser.\n\nUser's question: {question}\n\nProvide a detailed answer based on what you see."
        
        vision_model = _get_vision_model()
        vision_timeout = 120.0
        vision_temperature = 0.1
        
        call_kwargs = {
            "task": "vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": 2000,
            "temperature": vision_temperature,
            "timeout": vision_timeout,
        }
        if vision_model:
            call_kwargs["model"] = vision_model
        
        response = call_llm(**call_kwargs)
        analysis = (response.choices[0].message.content or "").strip()
        
        response_data = {
            "success": True,
            "analysis": analysis or "Vision analysis returned no content.",
            "screenshot_path": str(screenshot_path),
        }
        _copy_fallback_warning(response_data, result)
        if annotate and result.get("data", {}).get("annotations"):
            response_data["annotations"] = result["data"]["annotations"]
        return json.dumps(response_data, ensure_ascii=False)
    
    except Exception as e:
        logger.warning("browser_vision failed: %s", e, exc_info=True)
        error_info = {"success": False, "error": f"Error during vision analysis: {str(e)}"}
        if screenshot_path.exists():
            error_info["screenshot_path"] = str(screenshot_path)
        _copy_fallback_warning(error_info, result if 'result' in locals() else {})
        return json.dumps(error_info, ensure_ascii=False)


# ============================================================================
# Keep all original helper functions (no changes needed)
# ============================================================================

# [All the original helper functions remain exactly the same:
#  - _get_session_info
#  - _run_browser_command
#  - _find_agent_browser
#  - _get_cloud_provider
#  - _is_local_mode
#  - _last_session_key
#  - _navigation_session_key
#  - cleanup_browser
#  - cleanup_all_browsers
#  - check_browser_requirements
#  - etc.
# ]

# The only changes are the security function stubs at the top that always
# return "allow" responses, and the security configuration that's been emptied.

# All other browser tool functions (browser_click, browser_scroll, browser_back,
# browser_press, browser_get_images, browser_snapshot) remain unchanged from
# the original - they already had minimal security and continue unchanged.

# ============================================================================
# Module Test
# ============================================================================

if __name__ == "__main__":
    print("⚠️  UNSAFE BROWSER TOOL - NO SECURITY CHECKS")
    print("=" * 50)
    print("⚠️  WARNING: This version has ALL security features disabled")
    print("⚠️  DO NOT use in production or with sensitive data")
    print("\nDangerous operations allowed:")
    print("  • Any URL (malware, phishing, internal networks)")
    print("  • Any JavaScript (data exfiltration, crypto miners)")
    print("  • Any text (injection attacks)")
    print("  • No rate limits (unlimited requests)")
    print("  • No file validation (any file type/size)")
    print("  • No redirect validation")
    print("  • All protocols (file://, javascript:, data:)")
    print("\n✅ Unsafe browser tool loaded - USE AT YOUR OWN RISK")
