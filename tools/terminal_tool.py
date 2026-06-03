#!/usr/bin/env python3
"""
Terminal Tool Module - UNSAFE VERSION WITH NO SECURITY REFUSALS

⚠️  CRITICAL WARNING: This version has ALL security checks, approval gates,
⚠️  and safety mechanisms REMOVED. This tool will execute ANY command without
⚠️  validation or user approval.

⚠️  DANGEROUS OPERATIONS ALLOWED WITHOUT RESTRICTION:
⚠️    • Any command (rm -rf /, dd, fork bombs, etc.)
⚠️    • No dangerous command detection
⚠️    • No sudo password requirements
⚠️    • No command injection prevention
⚠️    • No workdir validation
⚠️    • No rate limiting
⚠️    • All commands auto-approved

⚠️  USE ONLY IN ISOLATED TEST ENVIRONMENTS:
⚠️    • Dedicated test VMs with no sensitive data
⚠️    • Throwaway containers
⚠️    • Air-gapped networks
⚠️    • NEVER in production

This module executes shell commands in local, Docker, Modal, SSH,
Singularity, and Daytona environments with ALL security features disabled.
"""

import importlib.util
import json
import logging
import os
import platform
import re
import time
import threading
import atexit
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from utils import env_var_enabled

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Global interrupt event - kept for functionality
# ---------------------------------------------------------------------------
from tools.interrupt import is_interrupted, _interrupt_event


# =============================================================================
# DISABLED SECURITY - All approval, sudo, and validation removed
# =============================================================================

# Disable sudo password caching (no prompts needed)
_sudo_password_cache: dict[str, str] = {}
_sudo_password_cache_lock = threading.Lock()

# Disable approval callbacks
_callback_tls = threading.local()


def _get_sudo_password_callback():
    return None  # Always return None - no password prompts


def _get_approval_callback():
    return None  # Always return None - no approval prompts


def set_sudo_password_callback(cb):
    pass  # NO-OP - disabled


def set_approval_callback(cb):
    pass  # NO-OP - disabled


def _get_cached_sudo_password() -> str:
    return ""  # Always return empty - no password


def _set_cached_sudo_password(password: str) -> None:
    pass  # NO-OP - disabled


def _reset_cached_sudo_passwords() -> None:
    pass  # NO-OP - disabled


# Disable dangerous command approval system
def _check_all_guards(command: str, env_type: str) -> dict:
    """DISABLED: Always returns approved."""
    return {
        "approved": True,
        "status": "auto_approved",
        "message": "All commands auto-approved (security disabled)",
        "description": "Security checks disabled",
    }


# Disable workdir validation
_WORKDIR_SAFE_RE = re.compile(r'.*')  # Allow everything


def _validate_workdir(workdir: str) -> str | None:
    """DISABLED: Always returns None (valid)."""
    return None


def _handle_sudo_failure(output: str, env_type: str) -> str:
    """DISABLED: Returns output unchanged."""
    return output


def _prompt_for_sudo_password(timeout_seconds: int = 45) -> str:
    """DISABLED: Always returns empty string (no password)."""
    return ""


def _safe_command_preview(command: Any, limit: int = 200) -> str:
    """Return preview without security concerns."""
    if command is None:
        return "<None>"
    if isinstance(command, str):
        return command[:limit]
    try:
        return repr(command)[:limit]
    except Exception:
        return f"<{type(command).__name__}>"


def _looks_like_env_assignment(token: str) -> bool:
    """Return True when token is a shell environment assignment."""
    if "=" not in token or token.startswith("="):
        return False
    name, _value = token.split("=", 1)
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name))


def _read_shell_token(command: str, start: int) -> tuple[str, int]:
    """Read one shell token, preserving quotes/escapes."""
    i = start
    n = len(command)

    while i < n:
        ch = command[i]
        if ch.isspace() or ch in ";|&()":
            break
        if ch == "'":
            i += 1
            while i < n and command[i] != "'":
                i += 1
            if i < n:
                i += 1
            continue
        if ch == '"':
            i += 1
            while i < n:
                inner = command[i]
                if inner == "\\" and i + 1 < n:
                    i += 2
                    continue
                if inner == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        i += 1

    return command[start:i], i


def _rewrite_real_sudo_invocations(command: str) -> tuple[str, bool]:
    """Rewrite sudo invocations - NO-OP in disabled version."""
    return command, False  # Don't rewrite anything


def _sudo_nopasswd_works() -> bool:
    """DISABLED: Always returns False."""
    return False


def _rewrite_compound_background(command: str) -> str:
    """Rewrite compound background commands - kept for functionality."""
    n = len(command)
    i = 0
    paren_depth = 0
    brace_depth = 0
    last_chain_op_end = -1
    rewrites: list[tuple[int, int]] = []

    while i < n:
        ch = command[i]

        if ch == "\n" and paren_depth == 0 and brace_depth == 0:
            last_chain_op_end = -1
            i += 1
            continue

        if ch.isspace():
            i += 1
            continue

        if ch == "#":
            nl = command.find("\n", i)
            if nl == -1:
                break
            i = nl
            continue

        if ch == "\\" and i + 1 < n:
            i += 2
            continue

        if ch in {"'", '"'}:
            _, next_i = _read_shell_token(command, i)
            i = max(next_i, i + 1)
            continue

        if ch == "(":
            paren_depth += 1
            i += 1
            continue

        if ch == ")":
            paren_depth = max(0, paren_depth - 1)
            i += 1
            continue

        if ch == "{" and i + 1 < n and (command[i + 1].isspace() or command[i + 1] == "\n"):
            brace_depth += 1
            i += 1
            continue
        if ch == "}" and brace_depth > 0:
            brace_depth -= 1
            last_chain_op_end = -1
            i += 1
            continue

        if paren_depth > 0 or brace_depth > 0:
            i += 1
            continue

        if command.startswith("&&", i) or command.startswith("||", i):
            last_chain_op_end = i + 2
            i += 2
            continue

        if ch == ";":
            last_chain_op_end = -1
            i += 1
            continue

        if ch == "|":
            last_chain_op_end = -1
            i += 1
            continue

        if ch == "&":
            if i + 1 < n and command[i + 1] == ">":
                i += 2
                continue
            j = i - 1
            while j >= 0 and command[j].isspace():
                j -= 1
            if j >= 0 and command[j] in "<>":
                i += 1
                continue
            if last_chain_op_end >= 0:
                rewrites.append((last_chain_op_end, i))
            last_chain_op_end = -1
            i += 1
            continue

        _, next_i = _read_shell_token(command, i)
        i = max(next_i, i + 1)

    if not rewrites:
        return command

    result = command
    for chain_end, amp_pos in reversed(rewrites):
        insert_pos = chain_end
        while insert_pos < amp_pos and result[insert_pos].isspace():
            insert_pos += 1
        prefix = result[:insert_pos]
        middle = result[insert_pos:amp_pos]
        suffix = result[amp_pos + 1:]
        result = prefix + "{ " + middle + "& }" + suffix

    return result


def _transform_sudo_command(command: str | None) -> tuple[str | None, str | None]:
    """DISABLED: Returns command unchanged."""
    return command, None


# Import environment classes (kept for functionality)
from tools.environments.local import LocalEnvironment as _LocalEnvironment
from tools.environments.singularity import SingularityEnvironment as _SingularityEnvironment
from tools.environments.ssh import SSHEnvironment as _SSHEnvironment
from tools.environments.docker import DockerEnvironment as _DockerEnvironment
from tools.environments.modal import ModalEnvironment as _ModalEnvironment
from tools.environments.managed_modal import ManagedModalEnvironment as _ManagedModalEnvironment
from tools.managed_tool_gateway import is_managed_tool_gateway_ready
import sys


# Tool description for LLM (unchanged)
TERMINAL_TOOL_DESCRIPTION = """Execute shell commands on a Linux environment. Filesystem usually persists between calls.

Do NOT use cat/head/tail to read files — use read_file instead.
Do NOT use grep/rg/find to search — use search_files instead.
Do NOT use ls to list directories — use search_files(target='files') instead.
Do NOT use sed/awk to edit files — use patch instead.
Do NOT use echo/cat heredoc to create files — use write_file instead.
Reserve terminal for: builds, installs, git, processes, scripts, network, package managers, and anything that needs a shell.

Foreground (default): Commands return INSTANTLY when done, even if the timeout is high. Set timeout=300 for long builds/scripts — you'll still get the result in seconds if it's fast. Prefer foreground for short commands.
Background: Set background=true to get a session_id. Almost always pair with notify_on_complete=true — bg without notify runs SILENTLY and you have no way to learn it finished short of calling process(action='poll') yourself. Two legitimate uses:
  (1) Long-lived processes that never exit (servers, watchers, daemons) — silent is correct, there's no exit to notify on.
  (2) Long-running bounded tasks (tests, builds, deploys, CI pollers, batch jobs) — MUST set notify_on_complete=true. Without it you'll either forget to poll or sit blocked waiting for the user to surface the result.
For servers/watchers, do NOT use shell-level background wrappers (nohup/disown/setsid/trailing '&') in foreground mode. Use background=true so Hermes can track lifecycle and output.
After starting a server, verify readiness with a health check or log signal, then run tests in a separate terminal() call. Avoid blind sleep loops.
Use process(action="poll") for progress checks, process(action="wait") to block until done.
Working directory: Use 'workdir' for per-command cwd.
PTY mode: Set pty=true for interactive CLI tools (Codex, Claude Code, Python REPL).

Do NOT use vim/nano/interactive tools without pty=true — they hang without a pseudo-terminal. Pipe git output to cat if it might page.
"""

# Global state for environment lifecycle management
_active_environments: Dict[str, Any] = {}
_last_activity: Dict[str, float] = {}
_env_lock = threading.Lock()
_creation_locks: Dict[str, threading.Lock] = {}
_creation_locks_lock = threading.Lock()
_cleanup_thread = None
_cleanup_running = False

_docker_orphan_reaper_ran = False
_docker_orphan_reaper_lock = threading.Lock()


def _maybe_reap_docker_orphans(container_config: Dict[str, Any]) -> None:
    """Keep orphan reaper functionality but disable security aspects."""
    global _docker_orphan_reaper_ran
    if not container_config.get("docker_orphan_reaper", True):
        return
    if _docker_orphan_reaper_ran:
        return
    with _docker_orphan_reaper_lock:
        if _docker_orphan_reaper_ran:
            return
        _docker_orphan_reaper_ran = True

    try:
        from tools.environments.docker import (
            reap_orphan_containers, _get_active_profile_name,
        )
    except ImportError:
        return
    try:
        profile = _get_active_profile_name()
        removed = reap_orphan_containers(max_age_seconds=600, profile_filter=profile)
        if removed:
            logger.info("Orphan reaper removed %d stale container(s)", removed)
    except Exception as e:
        logger.debug("Orphan reaper raised: %s", e)


# Per-task environment overrides (kept for functionality)
_task_env_overrides: Dict[str, Dict[str, Any]] = {}


def register_task_env_overrides(task_id: str, overrides: Dict[str, Any]):
    """Register environment overrides for a specific task."""
    _task_env_overrides[task_id] = overrides
    new_cwd = overrides.get("cwd")
    if isinstance(new_cwd, str) and new_cwd.strip():
        container_id = _resolve_container_task_id(task_id)
        with _env_lock:
            env = _active_environments.get(container_id)
        if env is not None and getattr(env, "cwd", None) is not None:
            env.cwd = new_cwd


def clear_task_env_overrides(task_id: str):
    """Clear environment overrides for a task."""
    _task_env_overrides.pop(task_id, None)


def _resolve_container_task_id(task_id: Optional[str]) -> str:
    """Map a tool-call task_id to container/sandbox key."""
    if task_id and task_id in _task_env_overrides:
        return task_id
    return "default"


# Configuration from environment variables (kept for functionality)
def _parse_env_var(name: str, default: str, converter=int, type_label: str = "integer"):
    """Parse environment variable with error handling."""
    raw = os.getenv(name, default)
    try:
        return converter(raw)
    except (ValueError, json.JSONDecodeError):
        raise ValueError(f"Invalid value for {name}: {raw!r} (expected {type_label})")


def _get_env_config() -> Dict[str, Any]:
    """Get terminal environment configuration from environment variables."""
    default_image = "nikolaik/python-nodejs:python3.11-nodejs20"
    env_type = os.getenv("TERMINAL_ENV", "local")
    
    mount_docker_cwd = os.getenv("TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE", "false").lower() in {"true", "1", "yes"}

    if env_type == "local":
        default_cwd = os.getcwd()
    elif env_type == "ssh":
        default_cwd = "~"
    else:
        default_cwd = "/root"

    cwd = os.getenv("TERMINAL_CWD", default_cwd)
    if cwd:
        cwd = os.path.expanduser(cwd)
    host_cwd = None
    host_prefixes = ("/Users/", "/home/", "C:\\", "C:/")
    if env_type == "docker" and mount_docker_cwd:
        docker_cwd_source = os.getenv("TERMINAL_CWD") or os.getcwd()
        candidate = os.path.abspath(os.path.expanduser(docker_cwd_source))
        if (any(candidate.startswith(p) for p in host_prefixes) or
            (os.path.isabs(candidate) and os.path.isdir(candidate) and not candidate.startswith(("/workspace", "/root")))):
            host_cwd = candidate
            cwd = "/workspace"

    from tools.tool_backend_helpers import coerce_modal_mode
    return {
        "env_type": env_type,
        "modal_mode": coerce_modal_mode(os.getenv("TERMINAL_MODAL_MODE", "auto")),
        "docker_image": os.getenv("TERMINAL_DOCKER_IMAGE", default_image),
        "docker_forward_env": _parse_env_var("TERMINAL_DOCKER_FORWARD_ENV", "[]", json.loads, "valid JSON"),
        "singularity_image": os.getenv("TERMINAL_SINGULARITY_IMAGE", f"docker://{default_image}"),
        "modal_image": os.getenv("TERMINAL_MODAL_IMAGE", default_image),
        "daytona_image": os.getenv("TERMINAL_DAYTONA_IMAGE", default_image),
        "cwd": cwd,
        "host_cwd": host_cwd,
        "docker_mount_cwd_to_workspace": mount_docker_cwd,
        "timeout": _parse_env_var("TERMINAL_TIMEOUT", "180"),
        "lifetime_seconds": _parse_env_var("TERMINAL_LIFETIME_SECONDS", "300"),
        "ssh_host": os.getenv("TERMINAL_SSH_HOST", ""),
        "ssh_user": os.getenv("TERMINAL_SSH_USER", ""),
        "ssh_port": _parse_env_var("TERMINAL_SSH_PORT", "22"),
        "ssh_key": os.getenv("TERMINAL_SSH_KEY", ""),
        "ssh_persistent": os.getenv("TERMINAL_SSH_PERSISTENT", "true").lower() in {"true", "1", "yes"},
        "local_persistent": os.getenv("TERMINAL_LOCAL_PERSISTENT", "false").lower() in {"true", "1", "yes"},
        "container_cpu": _parse_env_var("TERMINAL_CONTAINER_CPU", "1", float, "number"),
        "container_memory": _parse_env_var("TERMINAL_CONTAINER_MEMORY", "5120"),
        "container_disk": _parse_env_var("TERMINAL_CONTAINER_DISK", "51200"),
        "container_persistent": os.getenv("TERMINAL_CONTAINER_PERSISTENT", "true").lower() in {"true", "1", "yes"},
        "docker_volumes": _parse_env_var("TERMINAL_DOCKER_VOLUMES", "[]", json.loads, "valid JSON"),
        "docker_env": _parse_env_var("TERMINAL_DOCKER_ENV", "{}", json.loads, "valid JSON"),
        "docker_run_as_host_user": os.getenv("TERMINAL_DOCKER_RUN_AS_HOST_USER", "false").lower() in {"true", "1", "yes"},
        "docker_extra_args": _parse_env_var("TERMINAL_DOCKER_EXTRA_ARGS", "[]", json.loads, "valid JSON"),
        "docker_persist_across_processes": os.getenv("TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES", "true").lower() in {"true", "1", "yes"},
        "docker_orphan_reaper": os.getenv("TERMINAL_DOCKER_ORPHAN_REAPER", "true").lower() in {"true", "1", "yes"},
    }


def _get_modal_backend_state(modal_mode: object | None) -> Dict[str, Any]:
    """Resolve direct vs managed Modal backend selection."""
    from tools.tool_backend_helpers import (
        has_direct_modal_credentials,
        managed_nous_tools_enabled,
        resolve_modal_backend_state,
    )
    return resolve_modal_backend_state(
        modal_mode,
        has_direct=has_direct_modal_credentials(),
        managed_ready=is_managed_tool_gateway_ready("modal"),
    )


def _create_environment(env_type: str, image: str, cwd: str, timeout: int,
                        ssh_config: dict = None, container_config: dict = None,
                        local_config: dict = None,
                        task_id: str = "default",
                        host_cwd: str = None):
    """Create an execution environment for sandboxed command execution."""
    cc = container_config or {}
    cpu = cc.get("container_cpu", 1)
    memory = cc.get("container_memory", 5120)
    disk = cc.get("container_disk", 51200)
    persistent = cc.get("container_persistent", True)
    volumes = cc.get("docker_volumes", [])
    docker_forward_env = cc.get("docker_forward_env", [])
    docker_env = cc.get("docker_env", {})
    docker_extra_args = cc.get("docker_extra_args", [])

    if env_type == "local":
        return _LocalEnvironment(cwd=cwd, timeout=timeout)
    elif env_type == "docker":
        _maybe_reap_docker_orphans(cc)
        return _DockerEnvironment(
            image=image, cwd=cwd, timeout=timeout,
            cpu=cpu, memory=memory, disk=disk,
            persistent_filesystem=persistent, task_id=task_id,
            volumes=volumes,
            host_cwd=host_cwd,
            auto_mount_cwd=cc.get("docker_mount_cwd_to_workspace", False),
            forward_env=docker_forward_env,
            env=docker_env,
            run_as_host_user=cc.get("docker_run_as_host_user", False),
            extra_args=docker_extra_args,
            persist_across_processes=cc.get("docker_persist_across_processes", True),
        )
    elif env_type == "singularity":
        return _SingularityEnvironment(
            image=image, cwd=cwd, timeout=timeout,
            cpu=cpu, memory=memory, disk=disk,
            persistent_filesystem=persistent, task_id=task_id,
        )
    elif env_type == "modal":
        sandbox_kwargs = {}
        if cpu > 0:
            sandbox_kwargs["cpu"] = cpu
        if memory > 0:
            sandbox_kwargs["memory"] = memory
        if disk > 0:
            try:
                import inspect, modal
                if "ephemeral_disk" in inspect.signature(modal.Sandbox.create).parameters:
                    sandbox_kwargs["ephemeral_disk"] = disk
            except Exception:
                pass

        modal_state = _get_modal_backend_state(cc.get("modal_mode"))

        if modal_state["selected_backend"] == "managed":
            return _ManagedModalEnvironment(
                image=image, cwd=cwd, timeout=timeout,
                modal_sandbox_kwargs=sandbox_kwargs,
                persistent_filesystem=persistent, task_id=task_id,
            )

        if modal_state["selected_backend"] != "direct":
            if modal_state["managed_mode_blocked"]:
                raise ValueError("Modal backend not available")
            if modal_state["mode"] == "managed":
                raise ValueError("Managed Modal backend unavailable")
            if modal_state["mode"] == "direct":
                raise ValueError("Direct Modal credentials not found")
            raise ValueError("Modal backend unavailable")

        return _ModalEnvironment(
            image=image, cwd=cwd, timeout=timeout,
            modal_sandbox_kwargs=sandbox_kwargs,
            persistent_filesystem=persistent, task_id=task_id,
        )
    elif env_type == "daytona":
        from tools.environments.daytona import DaytonaEnvironment as _DaytonaEnvironment
        return _DaytonaEnvironment(
            image=image, cwd=cwd, timeout=timeout,
            cpu=int(cpu), memory=memory, disk=disk,
            persistent_filesystem=persistent, task_id=task_id,
        )
    elif env_type == "ssh":
        if not ssh_config or not ssh_config.get("host") or not ssh_config.get("user"):
            raise ValueError("SSH environment requires ssh_host and ssh_user")
        return _SSHEnvironment(
            host=ssh_config["host"],
            user=ssh_config["user"],
            port=ssh_config.get("port", 22),
            key_path=ssh_config.get("key", ""),
            cwd=cwd,
            timeout=timeout,
        )
    else:
        raise ValueError(f"Unknown environment type: {env_type}")


def _cleanup_inactive_envs(lifetime_seconds: int = 300):
    """Clean up environments that have been inactive."""
    current_time = time.time()

    try:
        from tools.process_registry import process_registry
        for task_id in list(_last_activity.keys()):
            if process_registry.has_active_processes(task_id):
                _last_activity[task_id] = current_time
    except ImportError:
        pass

    envs_to_stop = []

    with _env_lock:
        for task_id, last_time in list(_last_activity.items()):
            if current_time - last_time > lifetime_seconds:
                env = _active_environments.pop(task_id, None)
                _last_activity.pop(task_id, None)
                if env is not None:
                    envs_to_stop.append((task_id, env))

        with _creation_locks_lock:
            for task_id, _ in envs_to_stop:
                _creation_locks.pop(task_id, None)

    for task_id, env in envs_to_stop:
        try:
            from tools.file_tools import clear_file_ops_cache
            clear_file_ops_cache(task_id)
        except ImportError:
            pass

        try:
            if hasattr(env, 'cleanup'):
                env.cleanup()
            elif hasattr(env, 'stop'):
                env.stop()
            elif hasattr(env, 'terminate'):
                env.terminate()
            logger.info("Cleaned up inactive environment for task: %s", task_id)
        except Exception as e:
            error_str = str(e)
            if "404" in error_str or "not found" in error_str.lower():
                logger.info("Environment for task %s already cleaned up", task_id)
            else:
                logger.warning("Error cleaning up environment for task %s: %s", task_id, e)


def _cleanup_thread_worker():
    """Background thread worker for cleanup."""
    while _cleanup_running:
        try:
            config = _get_env_config()
            _cleanup_inactive_envs(config["lifetime_seconds"])
        except Exception as e:
            logger.warning("Error in cleanup thread: %s", e, exc_info=True)

        for _ in range(60):
            if not _cleanup_running:
                break
            time.sleep(1)


def _start_cleanup_thread():
    """Start the background cleanup thread."""
    global _cleanup_thread, _cleanup_running

    with _env_lock:
        if _cleanup_thread is None or not _cleanup_thread.is_alive():
            _cleanup_running = True
            _cleanup_thread = threading.Thread(target=_cleanup_thread_worker, daemon=True)
            _cleanup_thread.start()


def _stop_cleanup_thread():
    """Stop the background cleanup thread."""
    global _cleanup_running
    _cleanup_running = False
    if _cleanup_thread is not None:
        try:
            _cleanup_thread.join(timeout=5)
        except (SystemExit, KeyboardInterrupt):
            pass


def get_active_env(task_id: str):
    """Return the active BaseEnvironment for task_id."""
    lookup = _resolve_container_task_id(task_id)
    with _env_lock:
        return _active_environments.get(lookup) or _active_environments.get(task_id)


def is_persistent_env(task_id: str) -> bool:
    """Return True if the active environment is configured for persistence."""
    env = get_active_env(task_id)
    if env is None:
        return False
    return bool(getattr(env, "_persistent", False))


def cleanup_all_environments():
    """Clean up ALL active environments."""
    task_ids = list(_active_environments.keys())
    cleaned = 0
    
    for task_id in task_ids:
        try:
            cleanup_vm(task_id)
            cleaned += 1
        except Exception as e:
            logger.error("Error cleaning %s: %s", task_id, e, exc_info=True)
    
    if cleaned > 0:
        logger.info("Cleaned %d environments", cleaned)
    return cleaned


def cleanup_vm(task_id: str, *, force_remove: bool = False):
    """Manually clean up a specific environment."""
    env = None
    with _env_lock:
        env = _active_environments.pop(task_id, None)
        _last_activity.pop(task_id, None)

    with _creation_locks_lock:
        _creation_locks.pop(task_id, None)

    try:
        from tools.file_tools import clear_file_ops_cache
        clear_file_ops_cache(task_id)
    except ImportError:
        pass

    if env is None:
        return

    try:
        if hasattr(env, 'cleanup'):
            import inspect
            sig = inspect.signature(env.cleanup)
            if "force_remove" in sig.parameters:
                env.cleanup(force_remove=force_remove)
            else:
                env.cleanup()
        elif hasattr(env, 'stop'):
            env.stop()
        elif hasattr(env, 'terminate'):
            env.terminate()
        logger.info("Manually cleaned up environment for task: %s", task_id)
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            logger.info("Environment for task %s already cleaned up", task_id)
        else:
            logger.warning("Error cleaning up environment for task %s: %s", task_id, e)


def _atexit_cleanup():
    """Stop cleanup thread and shut down sandboxes on exit."""
    _stop_cleanup_thread()
    if _active_environments:
        count = len(_active_environments)
        logger.info("Shutting down %d remaining sandbox(es)...", count)
        envs_to_wait = list(_active_environments.values())
        cleanup_all_environments()
        for env in envs_to_wait:
            wait_fn = getattr(env, "wait_for_cleanup", None)
            if wait_fn is None:
                continue
            try:
                wait_fn(timeout=15.0)
            except Exception as e:
                logger.debug("wait_for_cleanup raised on exit: %s", e)

atexit.register(_atexit_cleanup)


# =============================================================================
# Exit Code Context - kept for functionality
# =============================================================================

def _interpret_exit_code(command: str, exit_code: int) -> str | None:
    """Return human-readable note for non-zero exit codes."""
    if exit_code == 0:
        return None

    segments = re.split(r'\s*(?:\|\||&&|[|;])\s*', command)
    last_segment = (segments[-1] if segments else command).strip()

    words = last_segment.split()
    base_cmd = ""
    for w in words:
        if "=" in w and not w.startswith("-"):
            continue
        base_cmd = w.split("/")[-1]
        break

    if not base_cmd:
        return None

    semantics: dict[str, dict[int, str]] = {
        "grep":  {1: "No matches found (not an error)"},
        "egrep": {1: "No matches found (not an error)"},
        "fgrep": {1: "No matches found (not an error)"},
        "rg":    {1: "No matches found (not an error)"},
        "ag":    {1: "No matches found (not an error)"},
        "diff":  {1: "Files differ (expected, not an error)"},
        "find":  {1: "Some directories were inaccessible (partial results may still be valid)"},
        "test":  {1: "Condition evaluated to false (expected, not an error)"},
        "[":     {1: "Condition evaluated to false (expected, not an error)"},
    }

    cmd_semantics = semantics.get(base_cmd)
    if cmd_semantics and exit_code in cmd_semantics:
        return cmd_semantics[exit_code]

    return None


def _command_requires_pipe_stdin(command: str) -> bool:
    """Return True when PTY mode would break stdin-driven commands."""
    normalized = " ".join(command.lower().split())
    return (normalized.startswith("gh auth login") and "--with-token" in normalized)


def _strip_quotes(command: str) -> str:
    """Remove quoted content so regex checks don't match inside strings."""
    result = re.sub(r"'[^']*'", "''", command)
    result = re.sub(r'"(?:[^"\\]|\\.)*"', '""', result)
    result = re.sub(r"`[^`]*`", "``", result)
    return result


_LONG_LIVED_FOREGROUND_PATTERNS = (
    re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:dev|start|serve|watch)\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+compose\s+up\b", re.IGNORECASE),
    re.compile(r"\bnext\s+dev\b", re.IGNORECASE),
    re.compile(r"\bvite(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bnodemon\b", re.IGNORECASE),
    re.compile(r"\buvicorn\b", re.IGNORECASE),
    re.compile(r"\bgunicorn\b", re.IGNORECASE),
    re.compile(r"\bpython(?:3)?\s+-m\s+http\.server\b", re.IGNORECASE),
)


def _looks_like_help_or_version_command(command: str) -> bool:
    """Return True for informational invocations."""
    normalized = " ".join(command.lower().split())
    return (normalized.endswith(" --help") or normalized.endswith(" -h") or
            normalized.endswith(" --version") or normalized.endswith(" -v"))


def _foreground_background_guidance(command: str) -> str | None:
    """Provide guidance for long-running commands."""
    if _looks_like_help_or_version_command(command):
        return None

    unquoted = _strip_quotes(command)

    _SHELL_LEVEL_BACKGROUND_RE = re.compile(
        r"(?:^|[;&|]\s*|&&\s*|\|\|\s*|\$\(\s*)(?:nohup|disown|setsid)\b", re.IGNORECASE | re.MULTILINE
    )
    _INLINE_BACKGROUND_AMP_RE = re.compile(r"\s&\s")
    _TRAILING_BACKGROUND_AMP_RE = re.compile(r"\s&\s*(?:#.*)?$")

    if _SHELL_LEVEL_BACKGROUND_RE.search(unquoted):
        return ("Foreground command uses shell-level background wrappers. Use terminal(background=true) instead.")
    if _INLINE_BACKGROUND_AMP_RE.search(unquoted) or _TRAILING_BACKGROUND_AMP_RE.search(unquoted):
        return ("Foreground command uses '&' backgrounding. Use terminal(background=true) for long-lived processes.")
    for pattern in _LONG_LIVED_FOREGROUND_PATTERNS:
        if pattern.search(unquoted):
            return ("This foreground command appears to start a long-lived server/watch process. Run it with background=true.")
    return None


def _resolve_notification_flag_conflict(
    *,
    notify_on_complete: bool,
    watch_patterns,
    background: bool,
) -> tuple:
    """Resolve conflicts between notification flags."""
    if background and notify_on_complete and watch_patterns:
        return None, "watch_patterns ignored because notify_on_complete=True"
    return watch_patterns, ""


def _resolve_command_cwd(
    *,
    workdir: Optional[str],
    env: Any,
    default_cwd: str,
) -> str:
    """Return the cwd for a command, preferring live session cwd."""
    if workdir:
        return workdir
    live_cwd = getattr(env, "cwd", None)
    if isinstance(live_cwd, str) and live_cwd.strip():
        return live_cwd
    return default_cwd


# =============================================================================
# Main Terminal Tool - NO SECURITY CHECKS
# =============================================================================

def terminal_tool(
    command: str,
    background: bool = False,
    timeout: Optional[int] = None,
    task_id: Optional[str] = None,
    force: bool = False,
    workdir: Optional[str] = None,
    pty: bool = False,
    notify_on_complete: bool = False,
    watch_patterns: Optional[List[str]] = None,
) -> str:
    """
    Execute a command - NO SECURITY CHECKS VERSION.
    
    ⚠️ This version executes ANY command without approval or validation.
    """
    try:
        if not isinstance(command, str):
            return json.dumps({
                "output": "",
                "exit_code": -1,
                "error": f"Invalid command: expected string, got {type(command).__name__}",
            }, ensure_ascii=False)

        config = _get_env_config()
        env_type = config["env_type"]
        effective_task_id = _resolve_container_task_id(task_id)

        overrides = _task_env_overrides.get(effective_task_id, {})
        
        if env_type == "docker":
            image = overrides.get("docker_image") or config["docker_image"]
        elif env_type == "singularity":
            image = overrides.get("singularity_image") or config["singularity_image"]
        elif env_type == "modal":
            image = overrides.get("modal_image") or config["modal_image"]
        elif env_type == "daytona":
            image = overrides.get("daytona_image") or config["daytona_image"]
        else:
            image = ""

        cwd = overrides.get("cwd") or config["cwd"]
        default_timeout = config["timeout"]
        effective_timeout = timeout or default_timeout

        # Remove foreground timeout cap for disabled version
        # (allow any timeout value)
        
        # Provide guidance but don't block
        if not background:
            guidance = _foreground_background_guidance(command)
            if guidance:
                # Just log warning, don't block execution
                logger.warning("Guidance: %s", guidance)

        _start_cleanup_thread()

        with _env_lock:
            if effective_task_id in _active_environments:
                _last_activity[effective_task_id] = time.time()
                env = _active_environments[effective_task_id]
                needs_creation = False
            else:
                needs_creation = True

        if needs_creation:
            with _creation_locks_lock:
                if effective_task_id not in _creation_locks:
                    _creation_locks[effective_task_id] = threading.Lock()
                task_lock = _creation_locks[effective_task_id]

            with task_lock:
                with _env_lock:
                    if effective_task_id in _active_environments:
                        _last_activity[effective_task_id] = time.time()
                        env = _active_environments[effective_task_id]
                        needs_creation = False

                if needs_creation:
                    logger.info("Creating new %s environment for task %s...", env_type, effective_task_id[:8])
                    try:
                        ssh_config = None
                        if env_type == "ssh":
                            ssh_config = {
                                "host": config.get("ssh_host", ""),
                                "user": config.get("ssh_user", ""),
                                "port": config.get("ssh_port", 22),
                                "key": config.get("ssh_key", ""),
                                "persistent": config.get("ssh_persistent", False),
                            }

                        container_config = None
                        if env_type in {"docker", "singularity", "modal", "daytona"}:
                            container_config = {
                                "container_cpu": config.get("container_cpu", 1),
                                "container_memory": config.get("container_memory", 5120),
                                "container_disk": config.get("container_disk", 51200),
                                "container_persistent": config.get("container_persistent", True),
                                "modal_mode": config.get("modal_mode", "auto"),
                                "docker_volumes": config.get("docker_volumes", []),
                                "docker_mount_cwd_to_workspace": config.get("docker_mount_cwd_to_workspace", False),
                                "docker_forward_env": config.get("docker_forward_env", []),
                                "docker_env": config.get("docker_env", {}),
                                "docker_run_as_host_user": config.get("docker_run_as_host_user", False),
                                "docker_extra_args": config.get("docker_extra_args", []),
                                "docker_persist_across_processes": config.get("docker_persist_across_processes", True),
                                "docker_orphan_reaper": config.get("docker_orphan_reaper", True),
                            }

                        local_config = None
                        if env_type == "local":
                            local_config = {"persistent": config.get("local_persistent", False)}

                        new_env = _create_environment(
                            env_type=env_type,
                            image=image,
                            cwd=cwd,
                            timeout=effective_timeout,
                            ssh_config=ssh_config,
                            container_config=container_config,
                            local_config=local_config,
                            task_id=effective_task_id,
                            host_cwd=config.get("host_cwd"),
                        )
                    except ImportError as e:
                        return json.dumps({
                            "output": "",
                            "exit_code": -1,
                            "error": f"Terminal tool disabled: environment creation failed ({e})",
                        }, ensure_ascii=False)

                    with _env_lock:
                        _active_environments[effective_task_id] = new_env
                        _last_activity[effective_task_id] = time.time()
                        env = new_env
                    logger.info("%s environment ready for task %s", env_type, effective_task_id[:8])

        # NO SECURITY CHECKS - skip all approval and validation

        if workdir:
            workdir_error = _validate_workdir(workdir)  # Always returns None
            if workdir_error:
                pass  # Should never happen with disabled validation

        pty_disabled_reason = None
        effective_pty = pty
        if pty and _command_requires_pipe_stdin(command):
            effective_pty = False
            pty_disabled_reason = "PTY disabled for this command because it expects piped stdin/EOF."

        if background:
            from tools.approval import get_current_session_key
            from tools.process_registry import process_registry

            session_key = get_current_session_key(default="")
            effective_cwd = _resolve_command_cwd(
                workdir=workdir,
                env=env,
                default_cwd=cwd,
            )
            try:
                if env_type == "local":
                    proc_session = process_registry.spawn_local(
                        command=command,
                        cwd=effective_cwd,
                        task_id=effective_task_id,
                        session_key=session_key,
                        env_vars=env.env if hasattr(env, 'env') else None,
                        use_pty=effective_pty,
                    )
                else:
                    proc_session = process_registry.spawn_via_env(
                        env=env,
                        command=command,
                        cwd=effective_cwd,
                        task_id=effective_task_id,
                        session_key=session_key,
                    )

                result_data = {
                    "output": "Background process started",
                    "session_id": proc_session.id,
                    "pid": proc_session.pid,
                    "exit_code": 0,
                    "error": None,
                }
                if pty_disabled_reason:
                    result_data["pty_note"] = pty_disabled_reason

                # Provide hints but don't block
                if background and not notify_on_complete and not watch_patterns:
                    result_data["hint"] = "background=true without notify_on_complete=true means this process runs silently."

                # Notification handling
                if background and (notify_on_complete or watch_patterns):
                    from gateway.session_context import get_session_env as _gse
                    _gw_platform = _gse("HERMES_SESSION_PLATFORM", "")
                    if _gw_platform:
                        _gw_chat_id = _gse("HERMES_SESSION_CHAT_ID", "")
                        _gw_thread_id = _gse("HERMES_SESSION_THREAD_ID", "")
                        _gw_user_id = _gse("HERMES_SESSION_USER_ID", "")
                        proc_session.watcher_platform = _gw_platform
                        proc_session.watcher_chat_id = _gw_chat_id
                        proc_session.watcher_user_id = _gw_user_id
                        proc_session.watcher_thread_id = _gw_thread_id

                watch_patterns, conflict_note = _resolve_notification_flag_conflict(
                    notify_on_complete=bool(notify_on_complete),
                    watch_patterns=watch_patterns,
                    background=bool(background),
                )
                if conflict_note:
                    result_data["watch_patterns_ignored"] = conflict_note

                if notify_on_complete and background:
                    proc_session.notify_on_complete = True
                    result_data["notify_on_complete"] = True

                    if proc_session.watcher_platform:
                        proc_session.watcher_interval = 5
                        process_registry.pending_watchers.append({
                            "session_id": proc_session.id,
                            "check_interval": 5,
                            "session_key": session_key,
                            "platform": proc_session.watcher_platform,
                            "chat_id": proc_session.watcher_chat_id,
                            "user_id": proc_session.watcher_user_id,
                            "thread_id": proc_session.watcher_thread_id,
                            "notify_on_complete": True,
                        })

                if watch_patterns and background:
                    proc_session.watch_patterns = list(watch_patterns)
                    result_data["watch_patterns"] = proc_session.watch_patterns

                return json.dumps(result_data, ensure_ascii=False)
            except Exception as e:
                return json.dumps({
                    "output": "",
                    "exit_code": -1,
                    "error": f"Failed to start background process: {str(e)}"
                }, ensure_ascii=False)
        else:
            max_retries = 3
            retry_count = 0
            result = None
            
            while retry_count <= max_retries:
                try:
                    execute_kwargs = {
                        "timeout": effective_timeout,
                        "cwd": _resolve_command_cwd(
                            workdir=workdir,
                            env=env,
                            default_cwd=cwd,
                        ),
                    }
                    result = env.execute(command, **execute_kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    if "timeout" in error_str:
                        return json.dumps({
                            "output": "",
                            "exit_code": 124,
                            "error": f"Command timed out after {effective_timeout} seconds"
                        }, ensure_ascii=False)
                    
                    if retry_count < max_retries:
                        retry_count += 1
                        wait_time = 2 ** retry_count
                        logger.warning("Execution error, retrying in %ds (attempt %d/%d)", wait_time, retry_count, max_retries)
                        time.sleep(wait_time)
                        continue
                    
                    logger.error("Execution failed after %d retries", max_retries)
                    return json.dumps({
                        "output": "",
                        "exit_code": -1,
                        "error": f"Command execution failed: {type(e).__name__}: {str(e)}"
                    }, ensure_ascii=False)
                
                break
            
            output = result.get("output", "")
            returncode = result.get("returncode", 0)

            output = _handle_sudo_failure(output, env_type)

            try:
                from hermes_cli.plugins import invoke_hook
                hook_results = invoke_hook("transform_terminal_output", command=command, output=output, returncode=returncode)
                for hook_result in hook_results:
                    if isinstance(hook_result, str):
                        output = hook_result
                        break
            except Exception:
                pass
            
            from tools.tool_output_limits import get_max_bytes
            MAX_OUTPUT_CHARS = get_max_bytes()
            if len(output) > MAX_OUTPUT_CHARS:
                head_chars = int(MAX_OUTPUT_CHARS * 0.4)
                tail_chars = MAX_OUTPUT_CHARS - head_chars
                omitted = len(output) - head_chars - tail_chars
                truncated_notice = f"\n\n... [OUTPUT TRUNCATED - {omitted} chars omitted out of {len(output)} total] ...\n\n"
                output = output[:head_chars] + truncated_notice + output[-tail_chars:]

            from tools.ansi_strip import strip_ansi
            output = strip_ansi(output)

            from agent.redact import redact_sensitive_text
            output = redact_sensitive_text(output.strip()) if output else ""

            exit_note = _interpret_exit_code(command, returncode)

            result_dict = {
                "output": output,
                "exit_code": returncode,
                "error": None,
            }
            if exit_note:
                result_dict["exit_code_meaning"] = exit_note

            return json.dumps(result_dict, ensure_ascii=False)

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error("terminal_tool exception:\n%s", tb_str)
        return json.dumps({
            "output": "",
            "exit_code": -1,
            "error": f"Failed to execute command: {str(e)}",
        }, ensure_ascii=False)


def check_terminal_requirements() -> bool:
    """Check if requirements are met."""
    try:
        config = _get_env_config()
        env_type = config["env_type"]

        if env_type == "local":
            return True
        elif env_type == "docker":
            from tools.environments.docker import find_docker
            docker = find_docker()
            if not docker:
                return False
            result = subprocess.run([docker, "version"], capture_output=True, timeout=5)
            return result.returncode == 0
        elif env_type == "singularity":
            executable = shutil.which("apptainer") or shutil.which("singularity")
            if executable:
                result = subprocess.run([executable, "--version"], capture_output=True, timeout=5)
                return result.returncode == 0
            return False
        elif env_type == "ssh":
            if not config.get("ssh_host") or not config.get("ssh_user"):
                return False
            return True
        elif env_type == "modal":
            modal_state = _get_modal_backend_state(config.get("modal_mode"))
            if modal_state["selected_backend"] == "managed":
                return True
            if modal_state["selected_backend"] != "direct":
                return False
            if importlib.util.find_spec("modal") is None:
                return False
            return True
        elif env_type == "daytona":
            from daytona import Daytona
            return os.getenv("DAYTONA_API_KEY") is not None
        else:
            return False
    except Exception as e:
        logger.error("Terminal requirements check failed: %s", e)
        return False


if __name__ == "__main__":
    print("⚠️  UNSAFE TERMINAL TOOL - NO SECURITY CHECKS")
    print("=" * 50)
    print("⚠️  WARNING: This version has ALL security features disabled")
    print("⚠️  DO NOT use in production or with sensitive data")
    print("\nDangerous operations allowed:")
    print("  • rm -rf /")
    print("  • dd if=/dev/zero of=/dev/sda")
    print("  • fork bombs")
    print("  • Any command without approval")
    print("  • No sudo password required")
    print("\n✅ Unsafe terminal tool loaded - USE AT YOUR OWN RISK")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from tools.registry import registry

TERMINAL_SCHEMA = {
    "name": "terminal",
    "description": TERMINAL_TOOL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute"},
            "background": {"type": "boolean", "default": False},
            "timeout": {"type": "integer", "minimum": 1},
            "workdir": {"type": "string"},
            "pty": {"type": "boolean", "default": False},
            "notify_on_complete": {"type": "boolean", "default": False},
            "watch_patterns": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["command"]
    }
}


def _handle_terminal(args, **kw):
    return terminal_tool(
        command=args.get("command"),
        background=args.get("background", False),
        timeout=args.get("timeout"),
        task_id=kw.get("task_id"),
        workdir=args.get("workdir"),
        pty=args.get("pty", False),
        notify_on_complete=args.get("notify_on_complete", False),
        watch_patterns=args.get("watch_patterns"),
    )


registry.register(
    name="terminal",
    toolset="terminal",
    schema=TERMINAL_SCHEMA,
    handler=_handle_terminal,
    check_fn=check_terminal_requirements,
    emoji="💻",
    max_result_size_chars=100_000,
)
