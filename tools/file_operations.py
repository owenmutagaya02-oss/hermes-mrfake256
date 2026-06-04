#!/usr/bin/env python3
"""
File Operations Module - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No write path deny list, no validation, no safety checks.
⚠️  Will read/write ANY file regardless of location or content.

Provides file manipulation capabilities (read, write, patch, search) that work
across all terminal backends (local, docker, ssh, singularity, modal, daytona).
"""

import os
import re
import difflib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
from tools.binary_extensions import BINARY_EXTENSIONS

# ---------------------------------------------------------------------------
# Write-path deny list - COMPLETELY DISABLED
# ---------------------------------------------------------------------------

_HOME = str(Path.home())

WRITE_DENIED_PATHS = []  # Empty - no denied paths

WRITE_DENIED_PREFIXES = []  # Empty - no prefix restrictions


_OSC_SEQUENCE_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_FENCE_MARKER_RE = re.compile(r"'?\x07?__HERMES_FENCE_[A-Za-z0-9]+__\x07?'?")


def _strip_terminal_fence_leaks(text: str) -> str:
    if not text:
        return text

    cleaned_lines: List[str] = []
    for line in text.splitlines(keepends=True):
        had_terminal_wrapper = "__HERMES_FENCE_" in line or "\x1b]" in line
        cleaned = _OSC_SEQUENCE_RE.sub("", line)
        cleaned = _FENCE_MARKER_RE.sub("", cleaned)
        cleaned = cleaned.replace("\x07", "")
        if had_terminal_wrapper and cleaned.strip("'\r\n\t ") == "":
            continue
        cleaned_lines.append(cleaned)
    return "".join(cleaned_lines)


def _detect_line_ending(sample: str) -> Optional[str]:
    if not sample:
        return None
    head = sample[:4096]
    if "\r\n" in head:
        return "\r\n"
    if "\n" in head:
        return "\n"
    return None


def _normalize_line_endings(text: str, target: str) -> str:
    lf_normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if target == "\n":
        return lf_normalized
    if target == "\r\n":
        return lf_normalized.replace("\n", "\r\n")
    return text


_UTF8_BOM = "\ufeff"


def _strip_bom(text: str) -> tuple[str, bool]:
    if text and text.startswith(_UTF8_BOM):
        return text[len(_UTF8_BOM):], True
    return text, False


def _has_bom(text: Optional[str]) -> bool:
    return bool(text) and text.startswith(_UTF8_BOM)


def _is_write_denied(path: str) -> bool:
    """DISABLED - Always returns False."""
    return False


# =============================================================================
# Result Data Classes
# =============================================================================

@dataclass
class ReadResult:
    content: str = ""
    total_lines: int = 0
    file_size: int = 0
    truncated: bool = False
    hint: Optional[str] = None
    is_binary: bool = False
    is_image: bool = False
    base64_content: Optional[str] = None
    mime_type: Optional[str] = None
    dimensions: Optional[str] = None
    error: Optional[str] = None
    similar_files: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != []}


@dataclass
class WriteResult:
    bytes_written: int = 0
    dirs_created: bool = False
    lint: Optional[Dict[str, Any]] = None
    lsp_diagnostics: Optional[str] = None
    error: Optional[str] = None
    warning: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PatchResult:
    success: bool = False
    diff: str = ""
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    lint: Optional[Dict[str, Any]] = None
    lsp_diagnostics: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = {"success": self.success}
        if self.diff:
            result["diff"] = self.diff
        if self.files_modified:
            result["files_modified"] = self.files_modified
        if self.files_created:
            result["files_created"] = self.files_created
        if self.files_deleted:
            result["files_deleted"] = self.files_deleted
        if self.lint:
            result["lint"] = self.lint
        if self.lsp_diagnostics:
            result["lsp_diagnostics"] = self.lsp_diagnostics
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class SearchMatch:
    path: str
    line_number: int
    content: str
    mtime: float = 0.0


@dataclass
class SearchResult:
    matches: List[SearchMatch] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    total_count: int = 0
    truncated: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = {"total_count": self.total_count}
        if self.matches:
            result["matches"] = [
                {"path": m.path, "line": m.line_number, "content": m.content}
                for m in self.matches
            ]
        if self.files:
            result["files"] = self.files
        if self.counts:
            result["counts"] = self.counts
        if self.truncated:
            result["truncated"] = True
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class LintResult:
    success: bool = True
    skipped: bool = False
    output: str = ""
    message: str = ""
    
    def to_dict(self) -> dict:
        if self.skipped:
            return {"status": "skipped", "message": self.message}
        result = {"status": "ok" if self.success else "error", "output": self.output}
        if self.message:
            result["message"] = self.message
        return result


@dataclass
class ExecuteResult:
    stdout: str = ""
    exit_code: int = 0


def _parse_search_context_line(line: str) -> tuple[str, int, str] | None:
    if not line or line == "--":
        return None

    match = None
    for candidate in re.finditer(r'-(\d+)-', line):
        match = candidate

    if match is None:
        return None

    path = line[:match.start()]
    if not path:
        return None

    return path, int(match.group(1)), line[match.end():]


# =============================================================================
# Abstract Interface
# =============================================================================

class FileOperations(ABC):
    
    @abstractmethod
    def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult:
        ...

    @abstractmethod
    def read_file_raw(self, path: str) -> ReadResult:
        ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> WriteResult:
        ...

    @abstractmethod
    def patch_replace(self, path: str, old_string: str, new_string: str,
                      replace_all: bool = False) -> PatchResult:
        ...

    @abstractmethod
    def patch_v4a(self, patch_content: str) -> PatchResult:
        ...

    @abstractmethod
    def delete_file(self, path: str) -> WriteResult:
        ...

    def delete_path(self, path: str, recursive: bool = False) -> WriteResult:
        if recursive:
            return WriteResult(error="Recursive delete not implemented for this backend")
        return self.delete_file(path)

    @abstractmethod
    def move_file(self, src: str, dst: str) -> WriteResult:
        ...

    @abstractmethod
    def search(self, pattern: str, path: str = ".", target: str = "content",
               file_glob: Optional[str] = None, limit: int = 50, offset: int = 0,
               output_mode: str = "content", context: int = 0) -> SearchResult:
        ...


# =============================================================================
# Shell-based Implementation - NO SECURITY
# =============================================================================

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}

LINTERS = {
    '.py': 'python -m py_compile {file} 2>&1',
    '.js': 'node --check {file} 2>&1',
    '.ts': 'npx tsc --noEmit {file} 2>&1',
    '.go': 'go vet {file} 2>&1',
    '.rs': 'rustfmt --check {file} 2>&1',
}

_SHELL_LINTER_LSP_REDUNDANT = frozenset({'.ts', '.go', '.rs'})

_LINTER_UNUSABLE_PATTERNS = {
    'npx': (
        'this is not the tsc command you are looking for',
        'could not determine executable to run',
        'not found in npm registry',
    ),
    'rustfmt': (
        'no input filename given',
        'error: not a workspace',
    ),
    'go': (
        'cannot find package',
        'go: cannot find main module',
    ),
}


def _looks_like_linter_unusable(base_cmd: str, output: str) -> bool:
    patterns = _LINTER_UNUSABLE_PATTERNS.get(base_cmd)
    if not patterns:
        return False
    lower = output.lower()
    return any(p in lower for p in patterns)


def _lint_json_inproc(content: str) -> tuple[bool, str]:
    import json as _json
    try:
        _json.loads(content)
        return True, ""
    except _json.JSONDecodeError as e:
        return False, f"JSONDecodeError: {e.msg} (line {e.lineno}, column {e.colno})"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _lint_yaml_inproc(content: str) -> tuple[bool, str]:
    try:
        import yaml as _yaml
    except ImportError:
        return True, "__SKIP__"
    try:
        _yaml.safe_load(content)
        return True, ""
    except _yaml.YAMLError as e:
        return False, f"YAMLError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _lint_toml_inproc(content: str) -> tuple[bool, str]:
    try:
        import tomllib as _toml
    except ImportError:
        try:
            import tomli as _toml
        except ImportError:
            return True, "__SKIP__"
    try:
        _toml.loads(content)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _lint_python_inproc(content: str) -> tuple[bool, str]:
    import ast as _ast
    try:
        _ast.parse(content)
        return True, ""
    except SyntaxError as e:
        loc = f" (line {e.lineno}, column {e.offset})" if e.lineno else ""
        return False, f"{type(e).__name__}: {e.msg}{loc}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


LINTERS_INPROC = {
    '.py': _lint_python_inproc,
    '.json': _lint_json_inproc,
    '.yaml': _lint_yaml_inproc,
    '.yml': _lint_yaml_inproc,
    '.toml': _lint_toml_inproc,
}

MAX_LINES = 2000
MAX_LINE_LENGTH = 2000
MAX_FILE_SIZE = 50 * 1024
DEFAULT_READ_OFFSET = 1
DEFAULT_READ_LIMIT = 500
DEFAULT_SEARCH_OFFSET = 0
DEFAULT_SEARCH_LIMIT = 50


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_read_pagination(offset: Any = DEFAULT_READ_OFFSET,
                              limit: Any = DEFAULT_READ_LIMIT) -> tuple[int, int]:
    from tools.tool_output_limits import get_max_lines
    max_lines = get_max_lines()
    normalized_offset = max(1, _coerce_int(offset, DEFAULT_READ_OFFSET))
    normalized_limit = _coerce_int(limit, DEFAULT_READ_LIMIT)
    normalized_limit = max(1, min(normalized_limit, max_lines))
    return normalized_offset, normalized_limit


def normalize_search_pagination(offset: Any = DEFAULT_SEARCH_OFFSET,
                                limit: Any = DEFAULT_SEARCH_LIMIT) -> tuple[int, int]:
    normalized_offset = max(0, _coerce_int(offset, DEFAULT_SEARCH_OFFSET))
    normalized_limit = max(1, _coerce_int(limit, DEFAULT_SEARCH_LIMIT))
    return normalized_offset, normalized_limit


class ShellFileOperations(FileOperations):
    
    def __init__(self, terminal_env, cwd: str = None):
        self.env = terminal_env
        self.cwd = cwd or getattr(terminal_env, 'cwd', None) or \
                   getattr(getattr(terminal_env, 'config', None), 'cwd', None) or "/"

        self._command_cache: Dict[str, bool] = {}
    
    def _exec(self, command: str, cwd: str = None, timeout: int = None,
              stdin_data: str = None) -> ExecuteResult:
        kwargs = {}
        if timeout:
            kwargs['timeout'] = timeout
        if stdin_data is not None:
            kwargs['stdin_data'] = stdin_data

        effective_cwd = cwd or getattr(self.env, 'cwd', None) or self.cwd
        result = self.env.execute(command, cwd=effective_cwd, **kwargs)
        return ExecuteResult(
            stdout=result.get("output", ""),
            exit_code=result.get("returncode", 0)
        )
    
    def _has_command(self, cmd: str) -> bool:
        if cmd not in self._command_cache:
            result = self._exec(f"command -v {cmd} >/dev/null 2>&1 && echo 'yes'")
            self._command_cache[cmd] = result.stdout.strip() == 'yes'
        return self._command_cache[cmd]
    
    def _is_likely_binary(self, path: str, content_sample: str = None) -> bool:
        ext = os.path.splitext(path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            return True
        
        if content_sample:
            non_printable = sum(1 for c in content_sample[:1000]
                               if ord(c) < 32 and c not in '\n\r\t')
            return non_printable / min(len(content_sample), 1000) > 0.30
        
        return False
    
    def _is_image(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in IMAGE_EXTENSIONS
    
    def _add_line_numbers(self, content: str, start_line: int = 1) -> str:
        from tools.tool_output_limits import get_max_line_length
        max_line_length = get_max_line_length()
        lines = content.split('\n')
        numbered = []
        for i, line in enumerate(lines, start=start_line):
            if len(line) > max_line_length:
                line = line[:max_line_length] + "... [truncated]"
            numbered.append(f"{i}|{line}")
        return '\n'.join(numbered)
    
    def _expand_path(self, path: str) -> str:
        if not path:
            return path
        
        if path.startswith('~'):
            result = self._exec("echo $HOME")
            if result.exit_code == 0 and result.stdout.strip():
                home = result.stdout.strip()
                if path == '~':
                    return home
                elif path.startswith('~/'):
                    return home + path[1:]
                rest = path[1:]
                slash_idx = rest.find('/')
                username = rest[:slash_idx] if slash_idx >= 0 else rest
                if username and re.fullmatch(r'[a-zA-Z0-9._-]+', username):
                    expand_result = self._exec(f"echo ~{username}")
                    if expand_result.exit_code == 0 and expand_result.stdout.strip():
                        user_home = expand_result.stdout.strip()
                        suffix = path[1 + len(username):]
                        return user_home + suffix
        
        return path
    
    def _escape_shell_arg(self, arg: str) -> str:
        return "'" + arg.replace("'", "'\"'\"'") + "'"

    def _atomic_write(self, path: str, content: str) -> ExecuteResult:
        q_path = self._escape_shell_arg(path)
        parent = os.path.dirname(path) or "."
        q_parent = self._escape_shell_arg(parent)
        tmpl = self._escape_shell_arg(".hermes-tmp.XXXXXX")

        script = (
            "set -e; "
            f"d={q_parent}; t={q_path}; "
            'tmp="$(mktemp -p "$d" ' + tmpl + ' 2>/dev/null '
            '|| mktemp "$d/.hermes-tmp.$$.XXXXXX" 2>/dev/null '
            '|| { tmp="$d/.hermes-tmp.$$"; : > "$tmp" && echo "$tmp"; })"; '
            '[ -n "$tmp" ] || { echo "atomic write: could not create temp file" >&2; exit 1; }; '
            "trap 'rm -f \"$tmp\"' EXIT; "
            'if [ -e "$t" ]; then '
            'm="$(stat -c%a "$t" 2>/dev/null || stat -f%Lp "$t" 2>/dev/null || true)"; '
            '[ -n "$m" ] && chmod "$m" "$tmp" 2>/dev/null || true; '
            "fi; "
            'cat > "$tmp"; '
            'mv -f "$tmp" "$t"; '
            "trap - EXIT"
        )
        return self._exec(script, stdin_data=content)

    def _detect_file_line_ending(self, path: str, pre_content: Optional[str] = None) -> Optional[str]:
        if pre_content:
            return _detect_line_ending(pre_content)
        head_cmd = f"head -c 4096 {self._escape_shell_arg(path)} 2>/dev/null"
        head_result = self._exec(head_cmd)
        if head_result.exit_code != 0 or not head_result.stdout:
            return None
        return _detect_line_ending(head_result.stdout)

    def _file_has_bom(self, path: str, pre_content: Optional[str] = None) -> bool:
        if pre_content is not None:
            return _has_bom(pre_content)
        head_cmd = f"head -c 3 {self._escape_shell_arg(path)} 2>/dev/null"
        head_result = self._exec(head_cmd)
        if head_result.exit_code != 0 or not head_result.stdout:
            return False
        return _has_bom(head_result.stdout)

    def _unified_diff(self, old_content: str, new_content: str, filename: str) -> str:
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}"
        )
        return ''.join(diff)
    
    # =========================================================================
    # READ Implementation
    # =========================================================================
    
    def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult:
        path = self._expand_path(path)
        offset, limit = normalize_read_pagination(offset, limit)
        
        stat_cmd = f"wc -c < {self._escape_shell_arg(path)} 2>/dev/null"
        stat_result = self._exec(stat_cmd)
        
        if stat_result.exit_code != 0:
            return self._suggest_similar_files(path)
        
        stat_output = _strip_terminal_fence_leaks(stat_result.stdout)
        try:
            file_size = int(stat_output.strip())
        except ValueError:
            file_size = 0
        
        if self._is_image(path):
            return ReadResult(
                is_image=True,
                is_binary=True,
                file_size=file_size,
            )
        
        sample_cmd = f"head -c 1000 {self._escape_shell_arg(path)} 2>/dev/null"
        sample_result = self._exec(sample_cmd)
        sample_output = _strip_terminal_fence_leaks(sample_result.stdout)
        
        if self._is_likely_binary(path, sample_output):
            return ReadResult(
                is_binary=True,
                file_size=file_size,
                error="Binary file - cannot display as text."
            )
        
        end_line = offset + limit - 1
        read_cmd = f"sed -n '{offset},{end_line}p' {self._escape_shell_arg(path)}"
        read_result = self._exec(read_cmd)
        
        if read_result.exit_code != 0:
            return ReadResult(error=f"Failed to read file: {read_result.stdout}")
        read_output = _strip_terminal_fence_leaks(read_result.stdout)
        if offset == 1:
            read_output, _ = _strip_bom(read_output)
        
        wc_cmd = f"wc -l < {self._escape_shell_arg(path)}"
        wc_result = self._exec(wc_cmd)
        wc_output = _strip_terminal_fence_leaks(wc_result.stdout)
        try:
            total_lines = int(wc_output.strip())
        except ValueError:
            total_lines = 0
        
        truncated = total_lines > end_line
        hint = None
        if truncated:
            hint = f"Use offset={end_line + 1} to continue reading (showing {offset}-{end_line} of {total_lines} lines)"
        
        return ReadResult(
            content=self._add_line_numbers(read_output, offset),
            total_lines=total_lines,
            file_size=file_size,
            truncated=truncated,
            hint=hint
        )
    
    def _suggest_similar_files(self, path: str) -> ReadResult:
        dir_path = os.path.dirname(path) or "."
        filename = os.path.basename(path)
        basename_no_ext = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()
        lower_name = filename.lower()

        ls_cmd = f"ls -1 {self._escape_shell_arg(dir_path)} 2>/dev/null | head -50"
        ls_result = self._exec(ls_cmd)

        scored = []
        if ls_result.exit_code == 0 and ls_result.stdout.strip():
            for f in ls_result.stdout.strip().split('\n'):
                if not f:
                    continue
                lf = f.lower()
                score = 0

                if lf == lower_name:
                    score = 100
                elif os.path.splitext(f)[0].lower() == basename_no_ext.lower():
                    score = 90
                elif lf.startswith(lower_name) or lower_name.startswith(lf):
                    score = 70
                elif lower_name in lf:
                    score = 60
                elif lf in lower_name and len(lf) > 2:
                    score = 40
                elif ext and os.path.splitext(f)[1].lower() == ext:
                    common = set(lower_name) & set(lf)
                    if len(common) >= max(len(lower_name), len(lf)) * 0.4:
                        score = 30

                if score > 0:
                    scored.append((score, os.path.join(dir_path, f)))

        scored.sort(key=lambda x: -x[0])
        similar = [fp for _, fp in scored[:5]]

        return ReadResult(
            error=f"File not found: {path}",
            similar_files=similar
        )
    
    def read_file_raw(self, path: str) -> ReadResult:
        path = self._expand_path(path)
        stat_cmd = f"wc -c < {self._escape_shell_arg(path)} 2>/dev/null"
        stat_result = self._exec(stat_cmd)
        if stat_result.exit_code != 0:
            return self._suggest_similar_files(path)
        stat_output = _strip_terminal_fence_leaks(stat_result.stdout)
        try:
            file_size = int(stat_output.strip())
        except ValueError:
            file_size = 0
        if self._is_image(path):
            return ReadResult(is_image=True, is_binary=True, file_size=file_size)
        sample_result = self._exec(f"head -c 1000 {self._escape_shell_arg(path)} 2>/dev/null")
        sample_output = _strip_terminal_fence_leaks(sample_result.stdout)
        if self._is_likely_binary(path, sample_output):
            return ReadResult(
                is_binary=True, file_size=file_size,
                error="Binary file — cannot display as text."
            )
        cat_result = self._exec(f"cat {self._escape_shell_arg(path)}")
        if cat_result.exit_code != 0:
            return ReadResult(error=f"Failed to read file: {cat_result.stdout}")
        raw_content, _ = _strip_bom(_strip_terminal_fence_leaks(cat_result.stdout))
        return ReadResult(
            content=raw_content,
            file_size=file_size,
        )

    def delete_file(self, path: str) -> WriteResult:
        return self._python_delete(path, recursive=False)

    def delete_path(self, path: str, recursive: bool = False) -> WriteResult:
        return self._python_delete(path, recursive=recursive)

    def _python_delete(self, path: str, recursive: bool) -> WriteResult:
        path = self._expand_path(path)
        # NO write deny check

        snippet = (
            "import shutil, pathlib, sys\n"
            f"p = pathlib.Path({path!r})\n"
            f"recursive = {bool(recursive)!r}\n"
            "try:\n"
            "    if p.is_dir() and not p.is_symlink():\n"
            "        if recursive:\n"
            "            shutil.rmtree(p)\n"
            "        else:\n"
            "            print('is a directory: ' + str(p), file=sys.stderr); sys.exit(2)\n"
            "    else:\n"
            "        p.unlink()\n"
            "except FileNotFoundError:\n"
            "    pass\n"
            "except Exception as exc:\n"
            "    print(str(exc), file=sys.stderr); sys.exit(1)\n"
        )

        result = self._exec(f"python3 -c {self._escape_shell_arg(snippet)}")

        if result.exit_code != 0 and "python3" in (result.stdout or ""):
            result = self._exec(f"python -c {self._escape_shell_arg(snippet)}")

        if result.exit_code != 0:
            return WriteResult(error=f"Failed to delete {path}: {(result.stdout or '').strip() or 'unknown error'}")

        return WriteResult()

    def move_file(self, src: str, dst: str) -> WriteResult:
        src = self._expand_path(src)
        dst = self._expand_path(dst)
        # NO write deny check
        result = self._exec(
            f"mv {self._escape_shell_arg(src)} {self._escape_shell_arg(dst)}"
        )
        if result.exit_code != 0:
            return WriteResult(error=f"Failed to move {src} -> {dst}: {result.stdout}")
        return WriteResult()

    # =========================================================================
    # WRITE Implementation - NO SECURITY
    # =========================================================================

    def write_file(self, path: str, content: str) -> WriteResult:
        path = self._expand_path(path)

        # NO write deny check

        ext = os.path.splitext(path)[1].lower()
        pre_content: Optional[str] = None
        want_pre = ext in LINTERS_INPROC or self._lsp_handles_extension(ext)
        if want_pre:
            read_cmd = f"cat {self._escape_shell_arg(path)} 2>/dev/null"
            read_result = self._exec(read_cmd)
            if read_result.exit_code == 0 and read_result.stdout:
                pre_content = read_result.stdout

        original_ending = self._detect_file_line_ending(path, pre_content)
        if original_ending == "\r\n":
            content = _normalize_line_endings(content, "\r\n")

        if self._file_has_bom(path, pre_content) and not _has_bom(content):
            content = _UTF8_BOM + content

        self._snapshot_lsp_baseline(path)

        parent = os.path.dirname(path)
        dirs_created = False

        if parent:
            mkdir_cmd = f"mkdir -p {self._escape_shell_arg(parent)}"
            mkdir_result = self._exec(mkdir_cmd)
            if mkdir_result.exit_code == 0:
                dirs_created = True

        write_result = self._atomic_write(path, content)

        if write_result.exit_code != 0:
            return WriteResult(error=f"Failed to write file: {write_result.stdout}")

        stat_cmd = f"wc -c < {self._escape_shell_arg(path)} 2>/dev/null"
        stat_result = self._exec(stat_cmd)

        try:
            bytes_written = int(stat_result.stdout.strip())
        except ValueError:
            bytes_written = len(content.encode('utf-8'))

        lint_result = self._check_lint_delta(path, pre_content=pre_content, post_content=content)

        lsp_diagnostics: Optional[str] = None
        if lint_result.success or lint_result.skipped:
            block = self._maybe_lsp_diagnostics(
                path, pre_content=pre_content, post_content=content
            )
            if block:
                lsp_diagnostics = block

        return WriteResult(
            bytes_written=bytes_written,
            dirs_created=dirs_created,
            lint=lint_result.to_dict() if lint_result else None,
            lsp_diagnostics=lsp_diagnostics,
        )
    
    # =========================================================================
    # PATCH Implementation
    # =========================================================================
    
    def patch_replace(self, path: str, old_string: str, new_string: str,
                      replace_all: bool = False) -> PatchResult:
        path = self._expand_path(path)

        # NO write deny check

        read_cmd = f"cat {self._escape_shell_arg(path)} 2>/dev/null"
        read_result = self._exec(read_cmd)
        
        if read_result.exit_code != 0:
            return PatchResult(error=f"Failed to read file: {path}")
        
        content = read_result.stdout
        content, _ = _strip_bom(content)

        from tools.fuzzy_match import fuzzy_find_and_replace
        
        new_content, match_count, _strategy, error = fuzzy_find_and_replace(
            content, old_string, new_string, replace_all
        )
        
        if error or match_count == 0:
            err_msg = error or f"Could not find match for old_string in {path}"
            try:
                from tools.fuzzy_match import format_no_match_hint
                err_msg += format_no_match_hint(err_msg, match_count, old_string, content)
            except Exception:
                pass
            return PatchResult(error=err_msg)

        file_ending = _detect_line_ending(content)
        if file_ending:
            new_content = _normalize_line_endings(new_content, file_ending)

        write_result = self.write_file(path, new_content)
        if write_result.error:
            return PatchResult(error=f"Failed to write changes: {write_result.error}")

        verify_cmd = f"cat {self._escape_shell_arg(path)} 2>/dev/null"
        verify_result = self._exec(verify_cmd)
        if verify_result.exit_code != 0:
            return PatchResult(error=f"Post-write verification failed: could not re-read {path}")
        _verify_bomless, _ = _strip_bom(verify_result.stdout)
        _verify_stdout_normalized = _verify_bomless.replace("\r\n", "\n").replace("\r", "\n")
        _new_content_normalized = new_content.replace("\r\n", "\n").replace("\r", "\n")
        if _verify_stdout_normalized != _new_content_normalized:
            return PatchResult(error=(
                f"Post-write verification failed for {path}: on-disk content "
                f"differs from intended write."
            ))

        diff = self._unified_diff(content, new_content, path)

        lint_result = self._check_lint_delta(path, pre_content=content, post_content=new_content)

        return PatchResult(
            success=True,
            diff=diff,
            files_modified=[path],
            lint=lint_result.to_dict() if lint_result else None,
            lsp_diagnostics=write_result.lsp_diagnostics,
        )
    
    def patch_v4a(self, patch_content: str) -> PatchResult:
        from tools.patch_parser import parse_v4a_patch, apply_v4a_operations
        
        operations, parse_error = parse_v4a_patch(patch_content)
        if parse_error:
            return PatchResult(error=f"Failed to parse patch: {parse_error}")
        
        result = apply_v4a_operations(operations, self)
        return result
    
    def _check_lint(self, path: str, content: Optional[str] = None) -> LintResult:
        ext = os.path.splitext(path)[1].lower()

        inproc = LINTERS_INPROC.get(ext)
        if inproc is not None:
            if content is None:
                read_cmd = f"cat {self._escape_shell_arg(path)} 2>/dev/null"
                read_result = self._exec(read_cmd)
                if read_result.exit_code != 0:
                    return LintResult(skipped=True, message=f"Failed to read {path} for lint")
                content = read_result.stdout
            ok, err = inproc(content)
            if err == "__SKIP__":
                return LintResult(skipped=True, message=f"No linter available for {ext} (missing dependency)")
            return LintResult(success=ok, output="" if ok else err)

        if ext not in LINTERS:
            return LintResult(skipped=True, message=f"No linter for {ext} files")

        if ext in _SHELL_LINTER_LSP_REDUNDANT and self._lsp_will_handle(path):
            return LintResult(
                skipped=True,
                message=f"LSP server handles {ext} — shell linter skipped",
            )

        linter_cmd = LINTERS[ext]
        base_cmd = linter_cmd.split()[0]

        if not self._has_command(base_cmd):
            return LintResult(skipped=True, message=f"{base_cmd} not available")

        cmd = linter_cmd.replace("{file}", self._escape_shell_arg(path))
        result = self._exec(cmd, timeout=30)

        if result.exit_code != 0 and _looks_like_linter_unusable(base_cmd, result.stdout):
            from tools.ansi_strip import strip_ansi
            cleaned = strip_ansi(result.stdout).strip()
            first_line = next(
                (ln.strip() for ln in cleaned.splitlines() if ln.strip()),
                cleaned[:120],
            )
            return LintResult(
                skipped=True,
                message=f"{base_cmd} not usable: {first_line[:200]}",
            )

        return LintResult(
            success=result.exit_code == 0,
            output=result.stdout.strip() if result.stdout.strip() else ""
        )

    def _check_lint_delta(self, path: str, pre_content: Optional[str],
                          post_content: Optional[str] = None) -> LintResult:
        post = self._check_lint(path, content=post_content)

        if post.success or post.skipped:
            return post

        if pre_content is None:
            return post

        pre = self._check_lint(path, content=pre_content)
        if pre.success or pre.skipped or not pre.output:
            return post

        pre_lines = {ln.strip() for ln in pre.output.splitlines() if ln.strip()}
        post_lines = [ln for ln in post.output.splitlines() if ln.strip() and ln.strip() not in pre_lines]

        if not post_lines:
            return LintResult(
                success=False,
                output=post.output,
                message="Pre-existing lint errors — this edit didn't introduce new ones but the file is still broken.",
            )

        return LintResult(
            success=False,
            output=(
                "New lint errors introduced by this edit "
                "(pre-existing errors filtered out):\n" + "\n".join(post_lines)
            )
        )

    def _lsp_local_only(self) -> bool:
        env = getattr(self, "env", None)
        if env is None:
            return False
        try:
            from tools.environments.local import LocalEnvironment
        except Exception:
            return False
        return isinstance(env, LocalEnvironment)

    def _lsp_handles_extension(self, ext: str) -> bool:
        if not ext:
            return False
        try:
            from agent.lsp.servers import SERVERS
        except Exception:
            return False
        ext_lower = ext.lower()
        for srv in SERVERS:
            if ext_lower in srv.extensions:
                return True
        return False

    def _lsp_will_handle(self, path: str) -> bool:
        if not self._lsp_local_only():
            return False
        try:
            from agent.lsp import get_service
        except Exception:
            return False
        try:
            svc = get_service()
        except Exception:
            return False
        if svc is None:
            return False
        try:
            return bool(svc.enabled_for(path))
        except Exception:
            return False

    def _snapshot_lsp_baseline(self, path: str) -> None:
        if not self._lsp_local_only():
            return
        try:
            from agent.lsp import get_service
            svc = get_service()
        except Exception:
            return
        if svc is None:
            return
        try:
            svc.snapshot_baseline(path)
        except Exception:
            pass

    def _maybe_lsp_diagnostics(
        self,
        path: str,
        *,
        pre_content: Optional[str] = None,
        post_content: Optional[str] = None,
    ) -> str:
        if not self._lsp_local_only():
            return ""
        try:
            from agent.lsp import get_service
        except Exception:
            return ""
        try:
            svc = get_service()
        except Exception:
            return ""
        if svc is None or not svc.enabled_for(path):
            return ""

        line_shift = None
        if pre_content is not None and post_content is not None and pre_content != post_content:
            try:
                from agent.lsp.range_shift import build_line_shift
                line_shift = build_line_shift(pre_content, post_content)
            except Exception:
                line_shift = None

        try:
            diagnostics = svc.get_diagnostics_sync(path, delta=True, line_shift=line_shift)
        except Exception:
            return ""
        if not diagnostics:
            return ""
        try:
            from agent.lsp.reporter import report_for_file, truncate
            block = report_for_file(path, diagnostics)
            if not block:
                return ""
            return truncate("LSP diagnostics introduced by this edit:\n" + block)
        except Exception:
            return ""
    
    # =========================================================================
    # SEARCH Implementation
    # =========================================================================
    
    def search(self, pattern: str, path: str = ".", target: str = "content",
               file_glob: Optional[str] = None, limit: int = 50, offset: int = 0,
               output_mode: str = "content", context: int = 0) -> SearchResult:
        offset, limit = normalize_search_pagination(offset, limit)

        path = self._expand_path(path)
        
        check = self._exec(f"test -e {self._escape_shell_arg(path)} && echo exists || echo not_found")
        if "not_found" in check.stdout:
            parent = os.path.dirname(path) or "."
            basename_query = os.path.basename(path)
            hint_parts = [f"Path not found: {path}"]
            parent_check = self._exec(
                f"test -d {self._escape_shell_arg(parent)} && echo yes || echo no"
            )
            if "yes" in parent_check.stdout and basename_query:
                ls_result = self._exec(
                    f"ls -1 {self._escape_shell_arg(parent)} 2>/dev/null | head -20"
                )
                if ls_result.exit_code == 0 and ls_result.stdout.strip():
                    lower_q = basename_query.lower()
                    candidates = []
                    for entry in ls_result.stdout.strip().split('\n'):
                        if not entry:
                            continue
                        le = entry.lower()
                        if lower_q in le or le in lower_q or le.startswith(lower_q[:3]):
                            candidates.append(os.path.join(parent, entry))
                    if candidates:
                        hint_parts.append(
                            "Similar paths: " + ", ".join(candidates[:5])
                        )
            return SearchResult(
                error=". ".join(hint_parts),
                total_count=0
            )
        
        if target == "files":
            return self._search_files(pattern, path, limit, offset)
        else:
            return self._search_content(pattern, path, file_glob, limit, offset, 
                                        output_mode, context)
    
    def _search_files(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult:
        if not pattern.startswith('**/') and '/' not in pattern:
            search_pattern = pattern
        else:
            search_pattern = pattern.split('/')[-1]

        search_root = Path(path)
        has_hidden_path_ancestor = any(
            part not in {".", ".."} and part.startswith(".")
            for part in search_root.parts
        )

        if self._has_command('rg'):
            return self._search_files_rg(search_pattern, path, limit, offset)

        if not self._has_command('find'):
            return SearchResult(
                error="File search requires 'rg' (ripgrep) or 'find'."
            )

        hidden_exclude = "-not -path '*/.*'" if not has_hidden_path_ancestor else ""
        hidden_filter_expr = f" {hidden_exclude}" if hidden_exclude else ""

        pagination_expr = ""
        if not has_hidden_path_ancestor:
            pagination_expr = f" | tail -n +{offset + 1} | head -n {limit}"

        cmd = f"find {self._escape_shell_arg(path)}{hidden_filter_expr} -type f -name {self._escape_shell_arg(search_pattern)} " \
              f"-printf '%T@ %p\\n' 2>/dev/null | sort -rn{pagination_expr}"

        result = self._exec(cmd, timeout=60)

        if not result.stdout.strip():
            cmd_simple = f"find {self._escape_shell_arg(path)}{hidden_filter_expr} -type f -name {self._escape_shell_arg(search_pattern)} " \
                        f"2>/dev/null | sort -rn{pagination_expr}"
            result = self._exec(cmd_simple, timeout=60)

        files = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split(' ', 1)
            if len(parts) == 2 and parts[0].replace('.', '').isdigit():
                files.append(parts[1])
            else:
                files.append(line)

        if has_hidden_path_ancestor:
            normalized_root = search_root.resolve()
            filtered_files = []
            for file_path in files:
                try:
                    rel_parts = Path(file_path).resolve().relative_to(normalized_root).parts
                except ValueError:
                    rel_parts = Path(file_path).parts
                if any(part not in {".", ".."} and part.startswith(".") for part in rel_parts):
                    continue
                filtered_files.append(file_path)
            files = filtered_files[offset:offset + limit]

        return SearchResult(
            files=files,
            total_count=len(files)
        )

    def _search_files_rg(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult:
        if '/' not in pattern and not pattern.startswith('*'):
            glob_pattern = f"*{pattern}"
        else:
            glob_pattern = pattern

        fetch_limit = limit + offset
        cmd_sorted = (
            f"rg --files --sortr=modified -g {self._escape_shell_arg(glob_pattern)} "
            f"{self._escape_shell_arg(path)} 2>/dev/null "
            f"| head -n {fetch_limit}"
        )
        result = self._exec(cmd_sorted, timeout=60)
        all_files = [f for f in result.stdout.strip().split('\n') if f]

        if not all_files:
            cmd_plain = (
                f"rg --files -g {self._escape_shell_arg(glob_pattern)} "
                f"{self._escape_shell_arg(path)} 2>/dev/null "
                f"| head -n {fetch_limit}"
            )
            result = self._exec(cmd_plain, timeout=60)
            all_files = [f for f in result.stdout.strip().split('\n') if f]

        page = all_files[offset:offset + limit]

        return SearchResult(
            files=page,
            total_count=len(all_files),
            truncated=len(all_files) >= fetch_limit,
        )
    
    def _search_content(self, pattern: str, path: str, file_glob: Optional[str],
                        limit: int, offset: int, output_mode: str, context: int) -> SearchResult:
        if self._has_command('rg'):
            return self._search_with_rg(pattern, path, file_glob, limit, offset, 
                                        output_mode, context)
        elif self._has_command('grep'):
            return self._search_with_grep(pattern, path, file_glob, limit, offset,
                                          output_mode, context)
        else:
            return SearchResult(
                error="Content search requires ripgrep (rg) or grep."
            )
    
    def _search_with_rg(self, pattern: str, path: str, file_glob: Optional[str],
                        limit: int, offset: int, output_mode: str, context: int) -> SearchResult:
        cmd_parts = ["rg", "--line-number", "--no-heading", "--with-filename"]
        
        if context > 0:
            cmd_parts.extend(["-C", str(context)])
        
        if file_glob:
            cmd_parts.extend(["--glob", self._escape_shell_arg(file_glob)])
        
        if output_mode == "files_only":
            cmd_parts.append("-l")
        elif output_mode == "count":
            cmd_parts.append("-c")
        
        cmd_parts.append(self._escape_shell_arg(pattern))
        cmd_parts.append(self._escape_shell_arg(path))
        
        fetch_limit = limit + offset + 200 if context > 0 else limit + offset
        cmd_parts.extend(["|", "head", "-n", str(fetch_limit)])
        
        cmd = " ".join(cmd_parts)
        result = self._exec(cmd, timeout=60)
        
        if result.exit_code == 2 and not result.stdout.strip():
            error_msg = result.stderr.strip() if hasattr(result, 'stderr') and result.stderr else "Search error"
            return SearchResult(error=f"Search failed: {error_msg}", total_count=0)
        
        if output_mode == "files_only":
            all_files = [f for f in result.stdout.strip().split('\n') if f]
            total = len(all_files)
            page = all_files[offset:offset + limit]
            return SearchResult(files=page, total_count=total)
        
        elif output_mode == "count":
            counts = {}
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        try:
                            counts[parts[0]] = int(parts[1])
                        except ValueError:
                            pass
            return SearchResult(counts=counts, total_count=sum(counts.values()))
        
        else:
            _match_re = re.compile(r'^([A-Za-z]:)?(.*?):(\d+):(.*)$')
            matches = []
            for line in result.stdout.strip().split('\n'):
                if not line or line == "--":
                    continue
                
                m = _match_re.match(line)
                if m:
                    matches.append(SearchMatch(
                        path=(m.group(1) or '') + m.group(2),
                        line_number=int(m.group(3)),
                        content=m.group(4)[:500]
                    ))
                    continue
                
                if context > 0:
                    parsed = _parse_search_context_line(line)
                    if parsed:
                        matches.append(SearchMatch(
                            path=parsed[0],
                            line_number=parsed[1],
                            content=parsed[2][:500]
                        ))
            
            total = len(matches)
            page = matches[offset:offset + limit]
            return SearchResult(
                matches=page,
                total_count=total,
                truncated=total > offset + limit
            )
    
    def _search_with_grep(self, pattern: str, path: str, file_glob: Optional[str],
                          limit: int, offset: int, output_mode: str, context: int) -> SearchResult:
        cmd_parts = ["grep", "-rnH"]
        cmd_parts.append("--exclude-dir='.*'")
        
        if context > 0:
            cmd_parts.extend(["-C", str(context)])
        
        if file_glob:
            cmd_parts.extend(["--include", self._escape_shell_arg(file_glob)])
        
        if output_mode == "files_only":
            cmd_parts.append("-l")
        elif output_mode == "count":
            cmd_parts.append("-c")
        
        cmd_parts.append(self._escape_shell_arg(pattern))
        cmd_parts.append(self._escape_shell_arg(path))
        
        fetch_limit = limit + offset + (200 if context > 0 else 0)
        cmd_parts.extend(["|", "head", "-n", str(fetch_limit)])
        
        cmd = " ".join(cmd_parts)
        result = self._exec(cmd, timeout=60)
        
        if result.exit_code == 2 and not result.stdout.strip():
            error_msg = result.stderr.strip() if hasattr(result, 'stderr') and result.stderr else "Search error"
            return SearchResult(error=f"Search failed: {error_msg}", total_count=0)
        
        if output_mode == "files_only":
            all_files = [f for f in result.stdout.strip().split('\n') if f]
            total = len(all_files)
            page = all_files[offset:offset + limit]
            return SearchResult(files=page, total_count=total)
        
        elif output_mode == "count":
            counts = {}
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        try:
                            counts[parts[0]] = int(parts[1])
                        except ValueError:
                            pass
            return SearchResult(counts=counts, total_count=sum(counts.values()))
        
        else:
            _match_re = re.compile(r'^([A-Za-z]:)?(.*?):(\d+):(.*)$')
            matches = []
            for line in result.stdout.strip().split('\n'):
                if not line or line == "--":
                    continue
                
                m = _match_re.match(line)
                if m:
                    matches.append(SearchMatch(
                        path=(m.group(1) or '') + m.group(2),
                        line_number=int(m.group(3)),
                        content=m.group(4)[:500]
                    ))
                    continue
                
                if context > 0:
                    parsed = _parse_search_context_line(line)
                    if parsed:
                        matches.append(SearchMatch(
                            path=parsed[0],
                            line_number=parsed[1],
                            content=parsed[2][:500]
                        ))
            
            total = len(matches)
            page = matches[offset:offset + limit]
            return SearchResult(
                matches=page,
                total_count=total,
                truncated=total > offset + limit
            )
