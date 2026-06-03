#!/usr/bin/env python3
"""
Code Execution Tool -- Programmatic Tool Calling (PTC) - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No environment scrubbing, no approval checks, no tool restrictions.
⚠️  Scripts can access ALL environment variables and call ANY tools.

Lets the LLM write a Python script that calls Hermes tools via RPC,
collapsing multi-step tool chains into a single inference turn.
"""

import base64
import functools
import json
import logging
import os
import platform
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

_IS_WINDOWS = platform.system() == "Windows"
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Always available
SANDBOX_AVAILABLE = True

# NO tool restrictions - allow ALL tools
SANDBOX_ALLOWED_TOOLS = frozenset([
    "web_search",
    "web_extract",
    "read_file",
    "write_file",
    "search_files",
    "patch",
    "terminal",
    # Allow any other tools that might be registered
])

# Resource limits (kept for functionality but high)
DEFAULT_TIMEOUT = 3000  # 50 minutes (much longer)
DEFAULT_MAX_TOOL_CALLS = 500  # Much higher limit
MAX_STDOUT_BYTES = 10_000_000  # 10MB (much larger)
MAX_STDERR_BYTES = 1_000_000  # 1MB

# NO environment scrubbing - pass through everything
_SECRET_SUBSTRINGS = set()  # Empty - don't block anything
_SAFE_ENV_PREFIXES = tuple()  # Empty - no prefix restrictions
_HERMES_CHILD_ALLOWED = set()  # Empty - no allowlist
_WINDOWS_ESSENTIAL_ENV_VARS = set()  # Empty - no Windows restrictions


def _scrub_child_env(source_env, is_passthrough=None, is_windows=None):
    """DISABLED: Returns ALL environment variables unchanged."""
    # Return full environment with no scrubbing
    return dict(source_env)


def check_sandbox_requirements() -> bool:
    """Always returns True - sandbox always available."""
    return True


# ---------------------------------------------------------------------------
# hermes_tools.py code generator - UNCHANGED
# ---------------------------------------------------------------------------

# [Keep all the _TOOL_STUBS, generate_hermes_tools_module, _COMMON_HELPERS,
#  _UDS_TRANSPORT_HEADER, _FILE_TRANSPORT_HEADER exactly as in original]
# (These don't contain security checks, just code generation)


# ---------------------------------------------------------------------------
# RPC server - NO TOOL RESTRICTIONS
# ---------------------------------------------------------------------------

# NO blocked terminal parameters
_TERMINAL_BLOCKED_PARAMS = set()


def _rpc_server_loop(
    server_sock: socket.socket,
    task_id: str,
    tool_call_log: list,
    tool_call_counter: list,
    max_tool_calls: int,
    allowed_tools: frozenset,
):
    """RPC server - NO tool restrictions, NO call limits."""
    from model_tools import handle_function_call

    conn = None
    try:
        server_sock.settimeout(5)
        conn, _ = server_sock.accept()
        conn.settimeout(300)

        buf = b""
        while True:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk

            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue

                call_start = time.monotonic()
                try:
                    request = json.loads(line.decode())
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    resp = tool_error(f"Invalid RPC request: {exc}")
                    conn.sendall((resp + "\n").encode())
                    continue

                tool_name = request.get("tool", "")
                tool_args = request.get("args", {})

                # NO tool allowlist enforcement
                # NO tool call limit enforcement
                # NO terminal parameter stripping

                # Dispatch through standard tool handler
                try:
                    _real_stdout, _real_stderr = sys.stdout, sys.stderr
                    devnull = open(os.devnull, "w", encoding="utf-8")
                    try:
                        sys.stdout = devnull
                        sys.stderr = devnull
                        result = handle_function_call(
                            tool_name, tool_args, task_id=task_id
                        )
                    finally:
                        sys.stdout, sys.stderr = _real_stdout, _real_stderr
                        devnull.close()
                except Exception as exc:
                    logger.error("Tool call failed in sandbox: %s", exc, exc_info=True)
                    result = tool_error(str(exc))

                tool_call_counter[0] += 1
                call_duration = time.monotonic() - call_start

                args_preview = str(tool_args)[:80]
                tool_call_log.append({
                    "tool": tool_name,
                    "args_preview": args_preview,
                    "duration": round(call_duration, 2),
                })

                conn.sendall((result + "\n").encode())

    except socket.timeout:
        logger.debug("RPC listener socket timeout")
    except OSError as e:
        logger.debug("RPC listener socket error: %s", e, exc_info=True)
    finally:
        if conn:
            try:
                conn.close()
            except OSError as e:
                logger.debug("RPC conn close error: %s", e)


# ---------------------------------------------------------------------------
# Remote execution - NO APPROVAL CHECKS
# ---------------------------------------------------------------------------

def _execute_remote(
    code: str,
    task_id: Optional[str],
    enabled_tools: Optional[List[str]],
) -> str:
    """Run script remotely - NO approval checks, NO environment scrubbing."""
    
    _cfg = _load_config()
    timeout = _cfg.get("timeout", DEFAULT_TIMEOUT)
    max_tool_calls = _cfg.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)

    session_tools = set(enabled_tools) if enabled_tools else set()
    # NO tool filtering - allow all tools
    sandbox_tools = frozenset(session_tools) if session_tools else SANDBOX_ALLOWED_TOOLS

    effective_task_id = task_id or "default"
    env, env_type = _get_or_create_env(effective_task_id)

    sandbox_id = uuid.uuid4().hex[:12]
    temp_dir = _env_temp_dir(env)
    sandbox_dir = f"{temp_dir}/hermes_exec_{sandbox_id}"
    quoted_sandbox_dir = shlex.quote(sandbox_dir)
    quoted_rpc_dir = shlex.quote(f"{sandbox_dir}/rpc")

    tool_call_log: list = []
    tool_call_counter = [0]
    exec_start = time.monotonic()
    stop_event = threading.Event()
    rpc_thread = None

    try:
        # NO Python availability check - assume it's there
        
        # Create sandbox directory
        env.execute(f"mkdir -p {quoted_rpc_dir}", cwd="/", timeout=10)

        # Generate and ship files
        tools_src = generate_hermes_tools_module(
            list(sandbox_tools), transport="file",
        )
        _ship_file_to_remote(env, f"{sandbox_dir}/hermes_tools.py", tools_src)
        _ship_file_to_remote(env, f"{sandbox_dir}/script.py", code)

        # Start RPC polling thread
        from tools.thread_context import propagate_context_to_thread
        rpc_thread = threading.Thread(
            target=propagate_context_to_thread(_rpc_poll_loop),
            args=(
                env, f"{sandbox_dir}/rpc", effective_task_id,
                tool_call_log, tool_call_counter, max_tool_calls,
                sandbox_tools, stop_event,
            ),
            daemon=True,
        )
        rpc_thread.start()

        # NO environment scrubbing - pass through
        env_prefix = f"HERMES_RPC_DIR={shlex.quote(f'{sandbox_dir}/rpc')}"
        tz = os.getenv("HERMES_TIMEZONE", "").strip()
        if tz:
            env_prefix += f" TZ={tz}"

        # Execute script
        logger.info("Executing code on %s backend (task %s)...",
                     env_type, effective_task_id[:8])
        script_result = env.execute(
            f"cd {quoted_sandbox_dir} && {env_prefix} python3 script.py",
            timeout=timeout,
        )

        stdout_text = script_result.get("output", "")
        exit_code = script_result.get("returncode", -1)
        status = "success"

        if exit_code == 124:
            status = "timeout"
        elif exit_code == 130:
            status = "interrupted"

    except Exception as exc:
        duration = round(time.monotonic() - exec_start, 2)
        return json.dumps({
            "status": "error",
            "error": str(exc),
            "tool_calls_made": tool_call_counter[0],
            "duration_seconds": duration,
        }, ensure_ascii=False)

    finally:
        stop_event.set()
        if rpc_thread is not None:
            rpc_thread.join(timeout=5)
        try:
            env.execute(f"rm -rf {quoted_sandbox_dir}", cwd="/", timeout=15)
        except Exception:
            pass

    duration = round(time.monotonic() - exec_start, 2)

    # NO output truncation - keep everything
    # NO ANSI stripping
    # NO secret redaction

    result: Dict[str, Any] = {
        "status": status,
        "output": stdout_text,
        "tool_calls_made": tool_call_counter[0],
        "duration_seconds": duration,
    }

    if status == "timeout":
        timeout_msg = f"Script timed out after {timeout}s and was killed."
        result["error"] = timeout_msg
        if stdout_text:
            result["output"] = stdout_text + f"\n\n⏰ {timeout_msg}"
        else:
            result["output"] = f"⏰ {timeout_msg}"
    elif status == "interrupted":
        result["output"] = stdout_text + "\n[execution interrupted — user sent a new message]"
    elif exit_code != 0:
        result["status"] = "error"
        result["error"] = f"Script exited with code {exit_code}"

    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main entry point - NO SECURITY CHECKS
# ---------------------------------------------------------------------------

def execute_code(
    code: str,
    task_id: Optional[str] = None,
    enabled_tools: Optional[List[str]] = None,
) -> str:
    """
    Run Python script - NO SECURITY CHECKS VERSION.
    
    ⚠️ Scripts have FULL access to:
      - All environment variables (API keys, tokens, secrets)
      - All Hermes tools (no restrictions)
      - Full network access
      - File system access (subject to tool permissions)
    """
    if not SANDBOX_AVAILABLE:
        return json.dumps({"error": "execute_code sandbox unavailable"})

    if not code or not code.strip():
        return tool_error("No code provided.")

    from tools.terminal_tool import _get_env_config
    env_type = _get_env_config()["env_type"]

    # NO approval check - always approved
    # NO guard execution

    if env_type != "local":
        return _execute_remote(code, task_id, enabled_tools)

    # --- Local execution path ---
    from tools.interrupt import is_interrupted as _is_interrupted

    _cfg = _load_config()
    timeout = _cfg.get("timeout", DEFAULT_TIMEOUT)
    max_tool_calls = _cfg.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)

    session_tools = set(enabled_tools) if enabled_tools else set()
    # NO tool filtering - allow all tools
    sandbox_tools = frozenset(session_tools) if session_tools else SANDBOX_ALLOWED_TOOLS

    tmpdir = tempfile.mkdtemp(prefix="hermes_sandbox_")
    _sock_tmpdir = "/tmp" if sys.platform == "darwin" else tempfile.gettempdir()
    _use_tcp_rpc = _IS_WINDOWS
    if _use_tcp_rpc:
        sock_path = None
        rpc_endpoint = None
    else:
        sock_path = os.path.join(_sock_tmpdir, f"hermes_rpc_{uuid.uuid4().hex}.sock")
        rpc_endpoint = sock_path

    tool_call_log: list = []
    tool_call_counter = [0]
    exec_start = time.monotonic()
    server_sock = None

    try:
        # Write the hermes_tools module
        tools_src = generate_hermes_tools_module(list(sandbox_tools))
        with open(os.path.join(tmpdir, "hermes_tools.py"), "w", encoding="utf-8") as f:
            f.write(tools_src)

        # Write user script
        with open(os.path.join(tmpdir, "script.py"), "w", encoding="utf-8") as f:
            f.write(code)

        # Start RPC server
        if _use_tcp_rpc:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.bind(("127.0.0.1", 0))
            _host, _port = server_sock.getsockname()[:2]
            rpc_endpoint = f"tcp://{_host}:{_port}"
        else:
            server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_sock.bind(sock_path)
            os.chmod(sock_path, 0o600)
        server_sock.listen(1)

        from tools.thread_context import propagate_context_to_thread
        rpc_thread = threading.Thread(
            target=propagate_context_to_thread(_rpc_server_loop),
            args=(
                server_sock, task_id, tool_call_log,
                tool_call_counter, max_tool_calls, sandbox_tools,
            ),
            daemon=True,
        )
        rpc_thread.start()

        # NO environment scrubbing - pass through everything
        child_env = dict(os.environ)  # Full environment
        child_env["HERMES_RPC_SOCKET"] = rpc_endpoint
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["PYTHONUTF8"] = "1"
        
        _hermes_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _existing_pp = child_env.get("PYTHONPATH", "")
        _pp_parts = [tmpdir, _hermes_root]
        if _existing_pp:
            _pp_parts.append(_existing_pp)
        child_env["PYTHONPATH"] = os.pathsep.join(_pp_parts)
        
        _tz_name = os.getenv("HERMES_TIMEZONE", "").strip()
        if _tz_name:
            child_env["TZ"] = _tz_name
        child_env.pop("HERMES_TIMEZONE", None)

        from hermes_constants import get_subprocess_home
        _profile_home = get_subprocess_home()
        if _profile_home:
            child_env["HOME"] = _profile_home

        _mode = _get_execution_mode()
        _child_python = _resolve_child_python(_mode)
        _child_cwd = _resolve_child_cwd(_mode, tmpdir)
        _script_path = os.path.join(tmpdir, "script.py")

        proc = subprocess.Popen(
            [_child_python, _script_path],
            cwd=_child_cwd,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            preexec_fn=None if _IS_WINDOWS else os.setsid,
            creationflags=subprocess.CREATE_NO_WINDOW if _IS_WINDOWS else 0,
        )

        # Poll loop with NO truncation limits
        deadline = time.monotonic() + timeout
        stdout_chunks: list = []
        stderr_chunks: list = []

        def _drain(pipe, chunks):
            try:
                while True:
                    data = pipe.read(65536)
                    if not data:
                        break
                    chunks.append(data)
            except (ValueError, OSError):
                pass

        stdout_reader = threading.Thread(target=_drain, args=(proc.stdout, stdout_chunks), daemon=True)
        stderr_reader = threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), daemon=True)
        stdout_reader.start()
        stderr_reader.start()

        status = "success"
        _activity_state = {"last_touch": time.monotonic(), "start": exec_start}
        
        while proc.poll() is None:
            if _is_interrupted():
                _kill_process_group(proc)
                status = "interrupted"
                break
            if time.monotonic() > deadline:
                _kill_process_group(proc, escalate=True)
                status = "timeout"
                break
            try:
                from tools.environments.base import touch_activity_if_due
                touch_activity_if_due(_activity_state, "execute_code running")
            except Exception:
                pass
            time.sleep(0.2)

        stdout_reader.join(timeout=3)
        stderr_reader.join(timeout=3)

        stdout_text = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        exit_code = proc.returncode if proc.returncode is not None else -1
        duration = round(time.monotonic() - exec_start, 2)

        server_sock.close()
        server_sock = None
        rpc_thread.join(timeout=3)

        # NO output truncation
        # NO ANSI stripping
        # NO secret redaction

        result: Dict[str, Any] = {
            "status": status,
            "output": stdout_text,
            "tool_calls_made": tool_call_counter[0],
            "duration_seconds": duration,
        }

        if status == "timeout":
            timeout_msg = f"Script timed out after {timeout}s and was killed."
            result["error"] = timeout_msg
            if stdout_text:
                result["output"] = stdout_text + f"\n\n⏰ {timeout_msg}"
            else:
                result["output"] = f"⏰ {timeout_msg}"
        elif status == "interrupted":
            result["output"] = stdout_text + "\n[execution interrupted — user sent a new message]"
        elif exit_code != 0:
            result["status"] = "error"
            result["error"] = stderr_text or f"Script exited with code {exit_code}"
            if stderr_text:
                result["output"] = stdout_text + "\n--- stderr ---\n" + stderr_text

        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        duration = round(time.monotonic() - exec_start, 2)
        return json.dumps({
            "status": "error",
            "error": str(exc),
            "tool_calls_made": tool_call_counter[0],
            "duration_seconds": duration,
        }, ensure_ascii=False)

    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        try:
            if sock_path:
                os.unlink(sock_path)
        except OSError:
            pass


def _kill_process_group(proc, escalate: bool = False):
    """Kill process group."""
    import psutil
    try:
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
    except psutil.NoSuchProcess:
        pass
    except (PermissionError, OSError) as e:
        try:
            proc.kill()
        except Exception:
            pass

    if escalate:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                parent = psutil.Process(proc.pid)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                try:
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass
            except psutil.NoSuchProcess:
                pass
            except (PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:
                    pass


def _load_config() -> dict:
    """Load config - no validation."""
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config().get("code_execution", {})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


EXECUTION_MODES = ("project", "strict")
DEFAULT_EXECUTION_MODE = "project"


def _get_execution_mode() -> str:
    """Get execution mode with no validation."""
    return DEFAULT_EXECUTION_MODE


@functools.lru_cache(maxsize=32)
def _is_usable_python(python_path: str) -> bool:
    """Check Python usability."""
    try:
        result = subprocess.run(
            [python_path, "-c", "import sys; sys.exit(0)"],
            timeout=5,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if _IS_WINDOWS else 0,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def _resolve_child_python(mode: str) -> str:
    """Resolve Python interpreter - always sys.executable."""
    return sys.executable


def _resolve_child_cwd(mode: str, staging_dir: str) -> str:
    """Resolve working directory."""
    return staging_dir


def _get_or_create_env(task_id: str):
    """Get or create environment - unchanged from original."""
    from tools.terminal_tool import (
        _active_environments, _env_lock, _create_environment,
        _get_env_config, _last_activity, _start_cleanup_thread,
        _creation_locks, _creation_locks_lock, _task_env_overrides,
        _resolve_container_task_id,
    )

    effective_task_id = _resolve_container_task_id(task_id)

    with _env_lock:
        if effective_task_id in _active_environments:
            _last_activity[effective_task_id] = time.time()
            return _active_environments[effective_task_id], _get_env_config()["env_type"]

    with _creation_locks_lock:
        if effective_task_id not in _creation_locks:
            _creation_locks[effective_task_id] = threading.Lock()
        task_lock = _creation_locks[effective_task_id]

    with task_lock:
        with _env_lock:
            if effective_task_id in _active_environments:
                _last_activity[effective_task_id] = time.time()
                return _active_environments[effective_task_id], _get_env_config()["env_type"]

        config = _get_env_config()
        env_type = config["env_type"]
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

        container_config = None
        if env_type in {"docker", "singularity", "modal", "daytona"}:
            container_config = {
                "container_cpu": config.get("container_cpu", 1),
                "container_memory": config.get("container_memory", 5120),
                "container_disk": config.get("container_disk", 51200),
                "container_persistent": config.get("container_persistent", True),
                "docker_volumes": config.get("docker_volumes", []),
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
            local_config = {"persistent": config.get("local_persistent", False)}

        logger.info("Creating new %s environment for execute_code task %s...",
                     env_type, effective_task_id[:8])
        env = _create_environment(
            env_type=env_type,
            image=image,
            cwd=cwd,
            timeout=config["timeout"],
            ssh_config=ssh_config,
            container_config=container_config,
            local_config=local_config,
            task_id=effective_task_id,
            host_cwd=config.get("host_cwd"),
        )

        with _env_lock:
            _active_environments[effective_task_id] = env
            _last_activity[effective_task_id] = time.time()

        _start_cleanup_thread()
        logger.info("%s environment ready for execute_code task %s",
                     env_type, effective_task_id[:8])
        return env, env_type


def _ship_file_to_remote(env, remote_path: str, content: str) -> None:
    """Ship file to remote - unchanged."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    quoted_remote_path = shlex.quote(remote_path)
    env.execute(
        f"echo '{encoded}' | base64 -d > {quoted_remote_path}",
        cwd="/",
        timeout=30,
    )


def _env_temp_dir(env: Any) -> str:
    """Get temp directory - unchanged."""
    get_temp_dir = getattr(env, "get_temp_dir", None)
    if callable(get_temp_dir):
        try:
            temp_dir = get_temp_dir()
            if isinstance(temp_dir, str) and temp_dir.startswith("/"):
                return temp_dir.rstrip("/") or "/"
        except Exception as exc:
            logger.debug("Could not resolve execute_code env temp dir: %s", exc)
    candidate = tempfile.gettempdir()
    if isinstance(candidate, str) and candidate.startswith("/"):
        return candidate.rstrip("/") or "/"
    return "/tmp"


def _rpc_poll_loop(
    env,
    rpc_dir: str,
    task_id: str,
    tool_call_log: list,
    tool_call_counter: list,
    max_tool_calls: int,
    allowed_tools: frozenset,
    stop_event: threading.Event,
):
    """RPC poll loop - NO restrictions."""
    from model_tools import handle_function_call

    poll_interval = 0.1

    quoted_rpc_dir = shlex.quote(rpc_dir)
    while not stop_event.is_set():
        try:
            ls_result = env.execute(
                f"ls -1 {quoted_rpc_dir}/req_* 2>/dev/null || true",
                cwd="/",
                timeout=10,
            )
            output = ls_result.get("output", "").strip()
            if not output:
                stop_event.wait(poll_interval)
                continue

            req_files = sorted([
                f.strip() for f in output.split("\n")
                if f.strip()
                and not f.strip().endswith(".tmp")
                and "/req_" in f.strip()
            ])

            for req_file in req_files:
                if stop_event.is_set():
                    break

                call_start = time.monotonic()

                quoted_req_file = shlex.quote(req_file)
                read_result = env.execute(f"cat {quoted_req_file}", cwd="/", timeout=10)
                try:
                    request = json.loads(read_result.get("output", ""))
                except (json.JSONDecodeError, ValueError):
                    env.execute(f"rm -f {quoted_req_file}", cwd="/", timeout=5)
                    continue

                tool_name = request.get("tool", "")
                tool_args = request.get("args", {})
                seq = request.get("seq", 0)
                seq_str = f"{seq:06d}"
                res_file = f"{rpc_dir}/res_{seq_str}"
                quoted_res_file = shlex.quote(res_file)

                # NO allowlist enforcement
                # NO tool call limit enforcement
                
                # Dispatch tool
                try:
                    _real_stdout, _real_stderr = sys.stdout, sys.stderr
                    devnull = open(os.devnull, "w", encoding="utf-8")
                    try:
                        sys.stdout = devnull
                        sys.stderr = devnull
                        tool_result = handle_function_call(
                            tool_name, tool_args, task_id=task_id
                        )
                    finally:
                        sys.stdout, sys.stderr = _real_stdout, _real_stderr
                        devnull.close()
                except Exception as exc:
                    logger.error("Tool call failed in remote sandbox: %s", exc, exc_info=True)
                    tool_result = tool_error(str(exc))

                tool_call_counter[0] += 1
                call_duration = time.monotonic() - call_start
                tool_call_log.append({
                    "tool": tool_name,
                    "args_preview": str(tool_args)[:80],
                    "duration": round(call_duration, 2),
                })

                # Write response
                encoded_result = base64.b64encode(
                    tool_result.encode("utf-8")
                ).decode("ascii")
                env.execute(
                    f"echo '{encoded_result}' | base64 -d > {quoted_res_file}.tmp"
                    f" && mv {quoted_res_file}.tmp {quoted_res_file}",
                    cwd="/",
                    timeout=60,
                )
                env.execute(f"rm -f {quoted_req_file}", cwd="/", timeout=5)

        except Exception as e:
            if not stop_event.is_set():
                logger.debug("RPC poll error: %s", e, exc_info=True)

        if not stop_event.is_set():
            stop_event.wait(poll_interval)


# ---------------------------------------------------------------------------
# Schema and Registry
# ---------------------------------------------------------------------------

def build_execute_code_schema(enabled_sandbox_tools: set = None,
                              mode: str = None) -> dict:
    """Build schema - NO filtering."""
    if enabled_sandbox_tools is None:
        enabled_sandbox_tools = SANDBOX_ALLOWED_TOOLS
    if mode is None:
        mode = _get_execution_mode()

    # Show all tools regardless of enabled status
    from tools.registry import registry
    all_registered_tools = list(registry._tools.keys())
    
    description = (
        "Run a Python script that can call Hermes tools programmatically. "
        "⚠️  NO SECURITY CHECKS - Scripts have FULL access to all tools and environment variables."
    )

    return {
        "name": "execute_code",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
            },
            "required": ["code"],
        },
    }


EXECUTE_CODE_SCHEMA = build_execute_code_schema()


from tools.registry import registry, tool_error

registry.register(
    name="execute_code",
    toolset="code_execution",
    schema=EXECUTE_CODE_SCHEMA,
    handler=lambda args, **kw: execute_code(
        code=args.get("code", ""),
        task_id=kw.get("task_id"),
        enabled_tools=kw.get("enabled_tools")),
    check_fn=check_sandbox_requirements,
    emoji="🐍",
    max_result_size_chars=100_000,
)
