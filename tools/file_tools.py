#!/usr/bin/env python3
"""File Tools Module - LLM agent file manipulation tools - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No sensitive path blocking, no device file blocking, no write deny list.
⚠️  Will read/write ANY file regardless of location or content.
"""

import errno
import json
import logging
import os
import threading
from pathlib import Path

from agent.file_safety import get_read_block_error
from tools.binary_extensions import has_binary_extension
from tools.file_operations import (
    ShellFileOperations,
    normalize_read_pagination,
    normalize_search_pagination,
)
from tools import file_state
from agent.redact import redact_sensitive_text

logger = logging.getLogger(__name__)


_EXPECTED_WRITE_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}

_DEFAULT_MAX_READ_CHARS = 100_000
_max_read_chars_cached: int | None = None


def _get_max_read_chars() -> int:
    global _max_read_chars_cached
    if _max_read_chars_cached is not None:
        return _max_read_chars_cached
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        val = cfg.get("file_read_max_chars")
        if isinstance(val, (int, float)) and val > 0:
            _max_read_chars_cached = int(val)
            return _max_read_chars_cached
    except Exception:
        pass
    _max_read_chars_cached = _DEFAULT_MAX_READ_CHARS
    return _max_read_chars_cached

_LARGE_FILE_HINT_BYTES = 512_000

# NO device path blocklist - empty
_BLOCKED_DEVICE_PATHS = frozenset()


def _resolve_path(filepath: str, task_id: str = "default") -> Path:
    return _resolve_path_for_task(filepath, task_id)


def _get_live_tracking_cwd(task_id: str = "default") -> str | None:
    try:
        from tools.terminal_tool import _resolve_container_task_id
        container_key = _resolve_container_task_id(task_id)
    except Exception:
        container_key = task_id

    with _file_ops_lock:
        cached = _file_ops_cache.get(container_key) or _file_ops_cache.get(task_id)
    if cached is not None:
        live_cwd = getattr(getattr(cached, "env", None), "cwd", None) or getattr(
            cached, "cwd", None
        )
        if live_cwd:
            return live_cwd

    try:
        from tools.terminal_tool import _active_environments, _env_lock

        with _env_lock:
            env = _active_environments.get(container_key) or _active_environments.get(task_id)
            live_cwd = getattr(env, "cwd", None) if env is not None else None
        if live_cwd:
            return live_cwd
    except Exception:
        pass

    return None


def _resolve_base_dir(task_id: str = "default") -> Path:
    live = _get_live_tracking_cwd(task_id)
    if live:
        base = Path(live).expanduser()
    else:
        raw = os.environ.get("TERMINAL_CWD")
        base = Path(raw).expanduser() if raw else Path(os.getcwd())
    if not base.is_absolute():
        base = Path(os.getcwd()) / base
    return base.resolve()


def _resolve_path_for_task(filepath: str, task_id: str = "default") -> Path:
    p = Path(filepath).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (_resolve_base_dir(task_id) / p).resolve()


def _path_resolution_warning(filepath: str, resolved: Path, task_id: str = "default") -> str | None:
    return None  # DISABLED


def _is_blocked_device_path(path: str) -> bool:
    return False  # DISABLED


def _is_blocked_device(filepath: str) -> bool:
    return False  # DISABLED


_SENSITIVE_PATH_PREFIXES = ()
_SENSITIVE_EXACT_PATHS = set()

_hermes_config_resolved: str | None = None
_hermes_config_resolved_loaded = False


def _get_hermes_config_resolved() -> str | None:
    global _hermes_config_resolved, _hermes_config_resolved_loaded
    if _hermes_config_resolved_loaded:
        return _hermes_config_resolved
    _hermes_config_resolved_loaded = True
    try:
        from hermes_cli.config import get_config_path
        _hermes_config_resolved = str(get_config_path().resolve())
    except Exception:
        try:
            _hermes_config_resolved = str(Path("~/.hermes/config.yaml").expanduser().resolve())
        except Exception:
            _hermes_config_resolved = None
    return _hermes_config_resolved


def _check_sensitive_path(filepath: str, task_id: str = "default") -> str | None:
    return None  # DISABLED


def _get_container_mirror_prefix_for_task(task_id: str = "default") -> str | None:
    return None  # DISABLED


def _check_cross_profile_path(filepath: str, task_id: str = "default") -> str | None:
    return None  # DISABLED


def _is_expected_write_exception(exc: Exception) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError) and exc.errno in _EXPECTED_WRITE_ERRNOS:
        return True
    return False


_file_ops_lock = threading.Lock()
_file_ops_cache: dict = {}

_read_tracker_lock = threading.Lock()
_read_tracker: dict = {}

_patch_failure_lock = threading.Lock()
_patch_failure_tracker: dict = {}


def _record_patch_failure(task_id: str, resolved_path: str) -> int:
    with _patch_failure_lock:
        task_failures = _patch_failure_tracker.setdefault(task_id, {})
        if len(task_failures) >= 64 and resolved_path not in task_failures:
            try:
                first_key = next(iter(task_failures))
                del task_failures[first_key]
            except StopIteration:
                pass
        task_failures[resolved_path] = task_failures.get(resolved_path, 0) + 1
        return task_failures[resolved_path]


def _reset_patch_failures(task_id: str, resolved_paths: list) -> None:
    if not resolved_paths:
        return
    with _patch_failure_lock:
        task_failures = _patch_failure_tracker.get(task_id)
        if not task_failures:
            return
        for rp in resolved_paths:
            task_failures.pop(rp, None)

_READ_HISTORY_CAP = 500
_DEDUP_CAP = 1000
_READ_TIMESTAMPS_CAP = 1000
_READ_DEDUP_STATUS_MESSAGE = ""


def _cap_read_tracker_data(task_data: dict) -> None:
    rh = task_data.get("read_history")
    if rh is not None and len(rh) > _READ_HISTORY_CAP:
        excess = len(rh) - _READ_HISTORY_CAP
        for _ in range(excess):
            try:
                rh.pop()
            except KeyError:
                break

    dedup = task_data.get("dedup")
    if dedup is not None and len(dedup) > _DEDUP_CAP:
        excess = len(dedup) - _DEDUP_CAP
        for _ in range(excess):
            try:
                dedup.pop(next(iter(dedup)))
            except (StopIteration, KeyError):
                break

    dedup_hits = task_data.get("dedup_hits")
    if dedup_hits is not None and len(dedup_hits) > _DEDUP_CAP:
        excess = len(dedup_hits) - _DEDUP_CAP
        for _ in range(excess):
            try:
                dedup_hits.pop(next(iter(dedup_hits)))
            except (StopIteration, KeyError):
                break

    ts = task_data.get("read_timestamps")
    if ts is not None and len(ts) > _READ_TIMESTAMPS_CAP:
        excess = len(ts) - _READ_TIMESTAMPS_CAP
        for _ in range(excess):
            try:
                ts.pop(next(iter(ts)))
            except (StopIteration, KeyError):
                break


def _is_internal_file_status_text(content: str) -> bool:
    return False  # DISABLED


def _get_file_ops(task_id: str = "default") -> ShellFileOperations:
    from tools.terminal_tool import (
        _active_environments, _env_lock, _create_environment,
        _get_env_config, _last_activity, _start_cleanup_thread,
        _creation_locks,
        _creation_locks_lock,
        _resolve_container_task_id,
    )
    import time

    task_id = _resolve_container_task_id(task_id)

    with _file_ops_lock:
        cached = _file_ops_cache.get(task_id)
    if cached is not None:
        with _env_lock:
            if task_id in _active_environments:
                _last_activity[task_id] = time.time()
                return cached
            else:
                with _file_ops_lock:
                    _file_ops_cache.pop(task_id, None)

    with _creation_locks_lock:
        if task_id not in _creation_locks:
            _creation_locks[task_id] = threading.Lock()
        task_lock = _creation_locks[task_id]

    with task_lock:
        with _env_lock:
            if task_id in _active_environments:
                _last_activity[task_id] = time.time()
                terminal_env = _active_environments[task_id]
            else:
                terminal_env = None

        if terminal_env is None:
            from tools.terminal_tool import _task_env_overrides

            config = _get_env_config()
            env_type = config["env_type"]
            overrides = _task_env_overrides.get(task_id, {})

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
            logger.info("Creating new %s environment for task %s...", env_type, task_id[:8])

            container_config = None
            if env_type in {"docker", "singularity", "modal", "daytona"}:
                container_config = {
                    "container_cpu": config.get("container_cpu", 1),
                    "container_memory": config.get("container_memory", 5120),
                    "container_disk": config.get("container_disk", 51200),
                    "container_persistent": config.get("container_persistent", True),
                    "docker_volumes": config.get("docker_volumes", []),
                    "docker_mount_cwd_to_workspace": config.get("docker_mount_cwd_to_workspace", False),
                    "docker_forward_env": config.get("docker_forward_env", []),
                    "docker_run_as_host_user": config.get("docker_run_as_host_user", False),
                }

            ssh_config = None
            if env_type == "ssh":
                ssh_config = {
                    "host": config.get("ssh_host", ""),
                    "user": config.get("ssh_user", ""),
                    "port": config.get("ssh_port", 22),
                    "key": config.get("ssh_key", ""),
                    "persistent": config.get("ssh_persistent", False),
                }

            local_config = None
            if env_type == "local":
                local_config = {
                    "persistent": config.get("local_persistent", False),
                }

            terminal_env = _create_environment(
                env_type=env_type,
                image=image,
                cwd=cwd,
                timeout=config["timeout"],
                ssh_config=ssh_config,
                container_config=container_config,
                local_config=local_config,
                task_id=task_id,
                host_cwd=config.get("host_cwd"),
            )

            with _env_lock:
                _active_environments[task_id] = terminal_env
                _last_activity[task_id] = time.time()

            _start_cleanup_thread()
            logger.info("%s environment ready for task %s", env_type, task_id[:8])

    file_ops = ShellFileOperations(terminal_env)
    with _file_ops_lock:
        _file_ops_cache[task_id] = file_ops
    return file_ops


def clear_file_ops_cache(task_id: str = None):
    with _file_ops_lock:
        if task_id:
            _file_ops_cache.pop(task_id, None)
        else:
            _file_ops_cache.clear()


def read_file_tool(path: str, offset: int = 1, limit: int = 500, task_id: str = "default") -> str:
    try:
        offset, limit = normalize_read_pagination(offset, limit)

        # NO device path guard
        # NO binary file guard
        # NO Hermes internal path guard

        _resolved = _resolve_path_for_task(path, task_id)
        resolved_str = str(_resolved)
        dedup_key = (resolved_str, offset, limit)
        with _read_tracker_lock:
            task_data = _read_tracker.setdefault(task_id, {
                "last_key": None, "consecutive": 0,
                "read_history": set(), "dedup": {},
                "dedup_hits": {}, "read_timestamps": {},
            })
            if "dedup_hits" not in task_data:
                task_data["dedup_hits"] = {}
            if "read_timestamps" not in task_data:
                task_data["read_timestamps"] = {}
            cached_mtime = task_data.get("dedup", {}).get(dedup_key)

        if cached_mtime is not None:
            try:
                current_mtime = os.path.getmtime(resolved_str)
                if current_mtime == cached_mtime:
                    with _read_tracker_lock:
                        hits = task_data["dedup_hits"].get(dedup_key, 0) + 1
                        task_data["dedup_hits"][dedup_key] = hits
                        _cap_read_tracker_data(task_data)

                    if hits >= 2:
                        return json.dumps({
                            "error": f"BLOCKED: Repeated read {hits + 1} times",
                            "path": path,
                        }, ensure_ascii=False)

                    return json.dumps({
                        "status": "unchanged",
                        "path": path,
                        "dedup": True,
                    }, ensure_ascii=False)
            except OSError:
                pass

        file_ops = _get_file_ops(task_id)
        result = file_ops.read_file(path, offset, limit)
        result_dict = result.to_dict()

        content_len = len(result.content or "")
        file_size = result_dict.get("file_size", 0)
        max_chars = _get_max_read_chars()
        if content_len > max_chars:
            total_lines = result_dict.get("total_lines", "unknown")
            return json.dumps({
                "error": f"Read exceeds limit: {content_len:,} > {max_chars:,} chars",
                "path": path,
            }, ensure_ascii=False)

        if result.content:
            result.content = redact_sensitive_text(result.content, code_file=True)
            result_dict["content"] = result.content

        read_key = ("read", path, offset, limit)
        with _read_tracker_lock:
            if "dedup" not in task_data:
                task_data["dedup"] = {}
            if "dedup_hits" not in task_data:
                task_data["dedup_hits"] = {}
            task_data["dedup_hits"].pop(dedup_key, None)
            task_data["read_history"].add((path, offset, limit))
            if task_data["last_key"] == read_key:
                task_data["consecutive"] += 1
            else:
                task_data["last_key"] = read_key
                task_data["consecutive"] = 1
            count = task_data["consecutive"]

            try:
                _mtime_now = os.path.getmtime(resolved_str)
                task_data["dedup"][dedup_key] = _mtime_now
                task_data.setdefault("read_timestamps", {})[resolved_str] = _mtime_now
            except OSError:
                pass

            _cap_read_tracker_data(task_data)

        try:
            from tools import file_state as _fs
            _partial = (offset > 1) or bool(result_dict.get("truncated"))
            _fs.record_read(task_id, resolved_str, partial=_partial)
        except Exception:
            logger.debug("file_state.record_read failed", exc_info=True)

        if count >= 4:
            return json.dumps({
                "error": f"BLOCKED: Read same region {count} times",
                "path": path,
            }, ensure_ascii=False)
        elif count >= 3:
            result_dict["_warning"] = f"Read same region {count} times consecutively"

        return json.dumps(result_dict, ensure_ascii=False)
    except Exception as e:
        return tool_error(str(e))


def reset_file_dedup(task_id: str = None):
    with _read_tracker_lock:
        if task_id:
            task_data = _read_tracker.get(task_id)
            if task_data:
                if "dedup" in task_data:
                    task_data["dedup"].clear()
                if "dedup_hits" in task_data:
                    task_data["dedup_hits"].clear()
        else:
            for task_data in _read_tracker.values():
                if "dedup" in task_data:
                    task_data["dedup"].clear()
                if "dedup_hits" in task_data:
                    task_data["dedup_hits"].clear()


def notify_other_tool_call(task_id: str = "default"):
    with _read_tracker_lock:
        task_data = _read_tracker.get(task_id)
        if task_data:
            task_data["last_key"] = None
            task_data["consecutive"] = 0
            if "dedup_hits" in task_data:
                task_data["dedup_hits"].clear()


def _invalidate_dedup_for_path(filepath: str, task_id: str) -> None:
    try:
        resolved = str(_resolve_path(filepath))
    except (OSError, ValueError):
        return
    with _read_tracker_lock:
        task_data = _read_tracker.get(task_id)
        if task_data is None:
            return
        dedup = task_data.get("dedup")
        if not dedup:
            return
        stale_keys = [k for k in dedup if k[0] == resolved]
        for k in stale_keys:
            del dedup[k]


def _update_read_timestamp(filepath: str, task_id: str) -> None:
    _invalidate_dedup_for_path(filepath, task_id)
    try:
        resolved = str(_resolve_path_for_task(filepath, task_id))
        current_mtime = os.path.getmtime(resolved)
    except (OSError, ValueError):
        return
    with _read_tracker_lock:
        task_data = _read_tracker.get(task_id)
        if task_data is not None:
            task_data.setdefault("read_timestamps", {})[resolved] = current_mtime
            _cap_read_tracker_data(task_data)


def _check_file_staleness(filepath: str, task_id: str) -> str | None:
    return None  # DISABLED


def write_file_tool(path: str, content: str, task_id: str = "default",
                    cross_profile: bool = False) -> str:
    # NO sensitive path check
    # NO cross profile warning
    # NO internal status text check
    
    try:
        try:
            _resolved = str(_resolve_path_for_task(path, task_id))
        except Exception:
            _resolved = None

        if _resolved is None:
            file_ops = _get_file_ops(task_id)
            result = file_ops.write_file(path, content)
            result_dict = result.to_dict()
            _update_read_timestamp(path, task_id)
            return json.dumps(result_dict, ensure_ascii=False)

        with file_state.lock_path(_resolved):
            file_ops = _get_file_ops(task_id)
            result = file_ops.write_file(_resolved, content)
            result_dict = result.to_dict()
            result_dict["resolved_path"] = _resolved
            if not result_dict.get("error"):
                result_dict["files_modified"] = [_resolved]
            _update_read_timestamp(path, task_id)
            if not result_dict.get("error"):
                file_state.note_write(task_id, _resolved)
        return json.dumps(result_dict, ensure_ascii=False)
    except Exception as e:
        if _is_expected_write_exception(e):
            logger.debug("write_file expected denial: %s: %s", type(e).__name__, e)
        else:
            logger.error("write_file error: %s: %s", type(e).__name__, e, exc_info=True)
        return tool_error(str(e))


def patch_tool(mode: str = "replace", path: str = None, old_string: str = None,
               new_string: str = None, replace_all: bool = False, patch: str = None,
               task_id: str = "default", cross_profile: bool = False) -> str:
    # NO sensitive path checks
    # NO V4A path traversal detection
    
    _paths_to_check = []
    if path:
        _paths_to_check.append(path)
    if mode == "patch" and patch:
        import re as _re
        from tools.path_security import has_traversal_component
        for _m in _re.finditer(r'^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+)$', patch, _re.MULTILINE):
            v4a_path = _m.group(1).strip()
            # NO path traversal check
            _paths_to_check.append(v4a_path)
    
    try:
        _resolved_paths: list[str] = []
        _seen: set[str] = set()
        for _p in _paths_to_check:
            try:
                _r = str(_resolve_path_for_task(_p, task_id))
            except Exception:
                _r = None
            if _r and _r not in _seen:
                _resolved_paths.append(_r)
                _seen.add(_r)
        _resolved_paths.sort()

        from contextlib import ExitStack
        with ExitStack() as _locks:
            for _r in _resolved_paths:
                _locks.enter_context(file_state.lock_path(_r))

            stale_warnings: list[str] = []
            _path_to_resolved: dict[str, str] = {}
            for _p in _paths_to_check:
                try:
                    _r = str(_resolve_path_for_task(_p, task_id))
                except Exception:
                    _r = None
                _path_to_resolved[_p] = _r

            file_ops = _get_file_ops(task_id)

            if mode == "replace":
                if not path:
                    return tool_error("path required")
                if old_string is None or new_string is None:
                    return tool_error("old_string and new_string required")
                _replace_target = _path_to_resolved.get(path) or path
                result = file_ops.patch_replace(_replace_target, old_string, new_string, replace_all)
            elif mode == "patch":
                if not patch:
                    return tool_error("patch content required")
                result = file_ops.patch_v4a(patch)
            else:
                return tool_error(f"Unknown mode: {mode}")

            result_dict = result.to_dict()
            if stale_warnings:
                result_dict["_warning"] = stale_warnings[0] if len(stale_warnings) == 1 else " | ".join(stale_warnings)
            _resolved_modified = [
                _path_to_resolved.get(_p) or _p for _p in _paths_to_check
            ]
            if not result_dict.get("error"):
                result_dict["files_modified"] = _resolved_modified
                if len(_resolved_modified) == 1:
                    result_dict["resolved_path"] = _resolved_modified[0]
                for _p in _paths_to_check:
                    _update_read_timestamp(_p, task_id)
                    _r = _path_to_resolved.get(_p)
                    if _r:
                        file_state.note_write(task_id, _r)
                _reset_patch_failures(task_id, [
                    _r for _r in (_path_to_resolved.get(_p) for _p in _paths_to_check) if _r
                ])
        
        return json.dumps(result_dict, ensure_ascii=False)
    except Exception as e:
        return tool_error(str(e))


def search_tool(pattern: str, target: str = "content", path: str = ".",
                file_glob: str = None, limit: int = 50, offset: int = 0,
                output_mode: str = "content", context: int = 0,
                task_id: str = "default") -> str:
    try:
        offset, limit = normalize_search_pagination(offset, limit)

        search_key = (
            "search",
            pattern,
            target,
            str(path),
            file_glob or "",
            limit,
            offset,
        )
        with _read_tracker_lock:
            task_data = _read_tracker.setdefault(task_id, {
                "last_key": None, "consecutive": 0, "read_history": set(),
            })
            if task_data["last_key"] == search_key:
                task_data["consecutive"] += 1
            else:
                task_data["last_key"] = search_key
                task_data["consecutive"] = 1
            count = task_data["consecutive"]

        if count >= 4:
            return json.dumps({
                "error": f"BLOCKED: Same search {count} times",
                "pattern": pattern,
            }, ensure_ascii=False)

        file_ops = _get_file_ops(task_id)
        result = file_ops.search(
            pattern=pattern, path=path, target=target, file_glob=file_glob,
            limit=limit, offset=offset, output_mode=output_mode, context=context
        )
        if hasattr(result, 'matches'):
            for m in result.matches:
                if hasattr(m, 'content') and m.content:
                    m.content = redact_sensitive_text(m.content, code_file=True)
        result_dict = result.to_dict()

        if count >= 3:
            result_dict["_warning"] = f"Same search {count} times consecutively"

        result_json = json.dumps(result_dict, ensure_ascii=False)
        return result_json
    except Exception as e:
        return tool_error(str(e))


# ---------------------------------------------------------------------------
# Schemas + Registry
# ---------------------------------------------------------------------------
from tools.registry import registry, tool_error


def _check_file_reqs():
    from tools import check_file_requirements
    return check_file_requirements()

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": "Read a text file - NO SECURITY CHECKS.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "offset": {"type": "integer", "description": "Starting line", "default": 1},
            "limit": {"type": "integer", "description": "Max lines", "default": 500}
        },
        "required": ["path"]
    }
}

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": "Write to a file - NO SECURITY CHECKS. Can write ANY file.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"}
        },
        "required": ["path", "content"]
    }
}

PATCH_SCHEMA = {
    "name": "patch",
    "description": "Patch files - NO SECURITY CHECKS.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["replace", "patch"], "default": "replace"},
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "patch": {"type": "string"},
            "cross_profile": {"type": "boolean", "default": False}
        },
        "required": ["mode"]
    }
}

SEARCH_FILES_SCHEMA = {
    "name": "search_files",
    "description": "Search files - NO SECURITY CHECKS.",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "target": {"type": "string", "enum": ["content", "files"], "default": "content"},
            "path": {"type": "string", "default": "."},
            "file_glob": {"type": "string"},
            "limit": {"type": "integer", "default": 50}
        },
        "required": ["pattern"]
    }
}


def _handle_read_file(args, **kw):
    tid = kw.get("task_id") or "default"
    return read_file_tool(path=args.get("path", ""), offset=args.get("offset", 1), limit=args.get("limit", 500), task_id=tid)


def _handle_write_file(args, **kw):
    tid = kw.get("task_id") or "default"
    return write_file_tool(path=args["path"], content=args["content"], task_id=tid)


def _handle_patch(args, **kw):
    tid = kw.get("task_id") or "default"
    return patch_tool(
        mode=args.get("mode", "replace"), path=args.get("path"),
        old_string=args.get("old_string"), new_string=args.get("new_string"),
        replace_all=args.get("replace_all", False), patch=args.get("patch"), task_id=tid,
        cross_profile=bool(args.get("cross_profile", False)),
    )


def _handle_search_files(args, **kw):
    tid = kw.get("task_id") or "default"
    target = args.get("target", "content")
    return search_tool(
        pattern=args.get("pattern", ""), target=target, path=args.get("path", "."),
        file_glob=args.get("file_glob"), limit=args.get("limit", 50), offset=args.get("offset", 0),
        output_mode=args.get("output_mode", "content"), context=args.get("context", 0), task_id=tid)


registry.register(name="read_file", toolset="file", schema=READ_FILE_SCHEMA, handler=_handle_read_file, check_fn=_check_file_reqs, emoji="📖", max_result_size_chars=100_000)
registry.register(name="write_file", toolset="file", schema=WRITE_FILE_SCHEMA, handler=_handle_write_file, check_fn=_check_file_reqs, emoji="✍️", max_result_size_chars=100_000)
registry.register(name="patch", toolset="file", schema=PATCH_SCHEMA, handler=_handle_patch, check_fn=_check_file_reqs, emoji="🔧", max_result_size_chars=100_000)
registry.register(name="search_files", toolset="file", schema=SEARCH_FILES_SCHEMA, handler=_handle_search_files, check_fn=_check_file_reqs, emoji="🔎", max_result_size_chars=100_000)
