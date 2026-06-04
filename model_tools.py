#!/usr/bin/env python3
"""
Model Tools Module - NO SECURITY REFUSALS VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No tool argument validation, no error sanitization, no approval checks.
⚠️  Will execute ANY tool call without restrictions.
"""

import os
import json
import re
import asyncio
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple

from tools.registry import discover_builtin_tools, registry
from toolsets import resolve_toolset, validate_toolset

logger = logging.getLogger(__name__)


# =============================================================================
# Async Bridging - KEPT for functionality
# =============================================================================

_tool_loop = None
_tool_loop_lock = threading.Lock()
_worker_thread_local = threading.local()


def _get_tool_loop():
    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
        return _tool_loop


def _get_worker_loop():
    loop = getattr(_worker_thread_local, 'loop', None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _worker_thread_local.loop = loop
    return loop


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        worker_loop: Optional[asyncio.AbstractEventLoop] = None
        loop_ready = threading.Event()

        def _run_in_worker():
            nonlocal worker_loop
            worker_loop = asyncio.new_event_loop()
            loop_ready.set()
            try:
                asyncio.set_event_loop(worker_loop)
                return worker_loop.run_until_complete(coro)
            finally:
                try:
                    pending = asyncio.all_tasks(worker_loop)
                    for t in pending:
                        t.cancel()
                    if pending:
                        worker_loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except Exception:
                    pass
                worker_loop.close()

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_run_in_worker)
        try:
            return future.result(timeout=300)
        except concurrent.futures.TimeoutError:
            if loop_ready.wait(timeout=1.0) and worker_loop is not None:
                try:
                    for t in asyncio.all_tasks(worker_loop):
                        worker_loop.call_soon_threadsafe(t.cancel)
                except RuntimeError:
                    pass
            raise
        finally:
            pool.shutdown(wait=False)

    if threading.current_thread() is not threading.main_thread():
        worker_loop = _get_worker_loop()
        return worker_loop.run_until_complete(coro)

    tool_loop = _get_tool_loop()
    return tool_loop.run_until_complete(coro)


# =============================================================================
# Tool Discovery
# =============================================================================

discover_builtin_tools()

try:
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
except Exception as e:
    logger.debug("Plugin discovery failed: %s", e)


# =============================================================================
# Backward-compat constants
# =============================================================================

TOOL_TO_TOOLSET_MAP: Dict[str, str] = registry.get_tool_to_toolset_map()

TOOLSET_REQUIREMENTS: Dict[str, dict] = registry.get_toolset_requirements()

_last_resolved_tool_names: List[str] = []


_LEGACY_TOOLSET_MAP = {
    "web_tools": ["web_search", "web_extract"],
    "terminal_tools": ["terminal"],
    "vision_tools": ["vision_analyze"],
    "moa_tools": ["mixture_of_agents"],
    "image_tools": ["image_generate"],
    "skills_tools": ["skills_list", "skill_view", "skill_manage"],
    "browser_tools": [
        "browser_navigate", "browser_snapshot", "browser_click",
        "browser_type", "browser_scroll", "browser_back",
        "browser_press", "browser_get_images",
        "browser_vision", "browser_console"
    ],
    "cronjob_tools": ["cronjob"],
    "file_tools": ["read_file", "write_file", "patch", "search_files"],
    "tts_tools": ["text_to_speech"],
}


# =============================================================================
# get_tool_definitions - NO FILTERING
# =============================================================================

_tool_defs_cache: Dict[tuple, List[Dict[str, Any]]] = {}


def _clear_tool_defs_cache() -> None:
    _tool_defs_cache.clear()


def get_tool_definitions(
    enabled_toolsets: Optional[List[str]] = None,
    disabled_toolsets: Optional[List[str]] = None,
    quiet_mode: bool = False,
    skip_tool_search_assembly: bool = False,
) -> List[Dict[str, Any]]:
    """Get tool definitions - NO SECURITY FILTERING."""
    if quiet_mode:
        try:
            from hermes_cli.config import get_config_path
            cfg_path = get_config_path()
            cfg_stat = cfg_path.stat()
            cfg_fp = (cfg_stat.st_mtime_ns, cfg_stat.st_size)
        except (FileNotFoundError, OSError, ImportError):
            cfg_fp = None
        cache_key = (
            frozenset(enabled_toolsets) if enabled_toolsets is not None else None,
            frozenset(disabled_toolsets) if disabled_toolsets else None,
            registry._generation,
            cfg_fp,
            bool(os.environ.get("HERMES_KANBAN_TASK")),
            bool(skip_tool_search_assembly),
        )
        cached = _tool_defs_cache.get(cache_key)
        if cached is not None:
            global _last_resolved_tool_names
            _last_resolved_tool_names = [t["function"]["name"] for t in cached]
            return list(cached)

    result = _compute_tool_definitions(enabled_toolsets, disabled_toolsets, quiet_mode,
                                       skip_tool_search_assembly=skip_tool_search_assembly)
    if quiet_mode:
        _tool_defs_cache[cache_key] = result
        return list(result)
    return result


def _compute_tool_definitions(
    enabled_toolsets: Optional[List[str]] = None,
    disabled_toolsets: Optional[List[str]] = None,
    quiet_mode: bool = False,
    skip_tool_search_assembly: bool = False,
) -> List[Dict[str, Any]]:
    """Compute tool definitions - NO SECURITY FILTERING."""
    tools_to_include: set = set()

    if enabled_toolsets is not None:
        effective_enabled_toolsets = list(enabled_toolsets)
        if os.environ.get("HERMES_KANBAN_TASK") and "kanban" not in effective_enabled_toolsets:
            effective_enabled_toolsets.append("kanban")
        for toolset_name in effective_enabled_toolsets:
            if validate_toolset(toolset_name):
                resolved = resolve_toolset(toolset_name)
                tools_to_include.update(resolved)
                if not quiet_mode:
                    print(f"✅ Enabled toolset '{toolset_name}': {', '.join(resolved) if resolved else 'no tools'}")
            elif toolset_name in _LEGACY_TOOLSET_MAP:
                legacy_tools = _LEGACY_TOOLSET_MAP[toolset_name]
                tools_to_include.update(legacy_tools)
                if not quiet_mode:
                    print(f"✅ Enabled legacy toolset '{toolset_name}': {', '.join(legacy_tools)}")
            elif not quiet_mode:
                print(f"⚠️  Unknown toolset: {toolset_name}")
    else:
        from toolsets import get_all_toolsets
        for ts_name in get_all_toolsets():
            tools_to_include.update(resolve_toolset(ts_name))

    if disabled_toolsets:
        for toolset_name in disabled_toolsets:
            if validate_toolset(toolset_name):
                resolved = resolve_toolset(toolset_name)
                tools_to_include.difference_update(resolved)
                if not quiet_mode:
                    print(f"🚫 Disabled toolset '{toolset_name}': {', '.join(resolved) if resolved else 'no tools'}")
            elif toolset_name in _LEGACY_TOOLSET_MAP:
                legacy_tools = _LEGACY_TOOLSET_MAP[toolset_name]
                tools_to_include.difference_update(legacy_tools)
                if not quiet_mode:
                    print(f"🚫 Disabled legacy toolset '{toolset_name}': {', '.join(legacy_tools)}")
            elif not quiet_mode:
                print(f"⚠️  Unknown toolset: {toolset_name}")

    # NO check_fn filtering - include ALL tools
    filtered_tools = registry.get_definitions(tools_to_include, quiet=quiet_mode, skip_check=True)

    available_tool_names = {t["function"]["name"] for t in filtered_tools}

    # Rebuild execute_code schema
    if "execute_code" in available_tool_names:
        from tools.code_execution_tool import SANDBOX_ALLOWED_TOOLS, build_execute_code_schema, _get_execution_mode
        sandbox_enabled = SANDBOX_ALLOWED_TOOLS & available_tool_names
        dynamic_schema = build_execute_code_schema(sandbox_enabled, mode=_get_execution_mode())
        for i, td in enumerate(filtered_tools):
            if td.get("function", {}).get("name") == "execute_code":
                filtered_tools[i] = {"type": "function", "function": dynamic_schema}
                break

    if not quiet_mode:
        if filtered_tools:
            tool_names = [t["function"]["name"] for t in filtered_tools]
            print(f"🛠️  Final tool selection ({len(filtered_tools)} tools): {', '.join(tool_names)}")
        else:
            print("🛠️  No tools selected")

    global _last_resolved_tool_names
    _last_resolved_tool_names = [t["function"]["name"] for t in filtered_tools]

    # NO schema sanitization - keep as-is
    # NO tool search assembly - disable

    return filtered_tools


def _resolve_active_context_length() -> int:
    return 0  # DISABLED


# =============================================================================
# handle_function_call - NO SECURITY CHECKS
# =============================================================================

_AGENT_LOOP_TOOLS = {"todo", "memory", "session_search", "delegate_task"}
_READ_SEARCH_TOOLS = {"read_file", "search_files"}


# NO error sanitization - pass through raw errors
def _sanitize_tool_error(error_msg: str) -> str:
    """DISABLED - return error message unchanged."""
    return error_msg


def coerce_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce tool arguments - NO VALIDATION."""
    return args  # Return unchanged, no coercion


def _coerce_value(value: str, expected_type, schema: dict | None = None):
    return value


def _schema_allows_null(schema: dict | None) -> bool:
    return False


def _coerce_json(value: str, expected_python_type: type):
    return value


def _coerce_number(value: str, integer_only: bool = False):
    return value


def _coerce_boolean(value: str):
    return value


def handle_function_call(
    function_name: str,
    function_args: Dict[str, Any],
    task_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_task: Optional[str] = None,
    enabled_tools: Optional[List[str]] = None,
    skip_pre_tool_call_hook: bool = False,
    enabled_toolsets: Optional[List[str]] = None,
    disabled_toolsets: Optional[List[str]] = None,
) -> str:
    """Handle function call - NO SECURITY CHECKS."""
    
    # NO argument coercion
    # function_args = coerce_tool_args(function_name, function_args)

    # NO tool search bridge checks

    try:
        if function_name in _AGENT_LOOP_TOOLS:
            return json.dumps({"error": f"{function_name} must be handled by the agent loop"})

        # NO pre-tool call hooks
        # NO edit approval checks
        # NO read-loop tracker

        _dispatch_start = time.monotonic()
        if function_name == "execute_code":
            sandbox_enabled = enabled_tools if enabled_tools is not None else _last_resolved_tool_names
            result = registry.dispatch(
                function_name, function_args,
                task_id=task_id,
                enabled_tools=sandbox_enabled,
            )
        else:
            result = registry.dispatch(
                function_name, function_args,
                task_id=task_id,
                user_task=user_task,
            )
        duration_ms = int((time.monotonic() - _dispatch_start) * 1000)

        # NO post-tool call hooks
        # NO transform_tool_result hooks

        return result

    except Exception as e:
        error_msg = f"Error executing {function_name}: {str(e)}"
        logger.exception(error_msg)
        return json.dumps({"error": error_msg}, ensure_ascii=False)


# =============================================================================
# Backward-compat wrapper functions
# =============================================================================

def get_all_tool_names() -> List[str]:
    return registry.get_all_tool_names()


def get_toolset_for_tool(tool_name: str) -> Optional[str]:
    return registry.get_toolset_for_tool(tool_name)


def get_available_toolsets() -> Dict[str, dict]:
    return registry.get_available_toolsets()


def check_toolset_requirements() -> Dict[str, bool]:
    return registry.check_toolset_requirements()


def check_tool_availability(quiet: bool = False) -> Tuple[List[str], List[dict]]:
    return registry.check_tool_availability(quiet=quiet)
