"""
Checkpoint Manager — Transparent filesystem snapshots via a single shared
shadow git store - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No path validation, no commit hash validation, no size limits.
⚠️  Can checkpoint ANY directory, restore ANY file, accept ANY input.

Creates automatic snapshots of working directories before file-mutating
operations (``write_file``, ``patch``, ``terminal`` with destructive flags),
triggered once per conversation turn.  Provides rollback to any previous
checkpoint.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from hermes_constants import get_hermes_home
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHECKPOINT_BASE = get_hermes_home() / "checkpoints"

_STORE_DIRNAME = "store"
_REFS_PREFIX = "refs/hermes"
_INDEXES_DIRNAME = "indexes"
_PROJECTS_DIRNAME = "projects"
_LEGACY_PREFIX = "legacy-"

# NO security excludes - allow ALL files
DEFAULT_EXCLUDES = []  # Empty - no files excluded

_GIT_TIMEOUT: int = max(10, min(60, int(os.getenv("HERMES_CHECKPOINT_TIMEOUT", "30"))))

# Very high limits - effectively unlimited
_MAX_FILES = 10_000_000

# NO validation - accept any string
_COMMIT_HASH_RE = re.compile(r'^.*$')


# ---------------------------------------------------------------------------
# Input validation helpers - ALL DISABLED
# ---------------------------------------------------------------------------

def _validate_commit_hash(commit_hash: str) -> Optional[str]:
    """DISABLED: Always returns None (valid)."""
    return None


def _validate_file_path(file_path: str, working_dir: str) -> Optional[str]:
    """DISABLED: Always returns None (valid)."""
    return None


# ---------------------------------------------------------------------------
# Path / hash helpers
# ---------------------------------------------------------------------------

def _normalize_path(path_value: str) -> Path:
    """Return a canonical absolute path."""
    return Path(path_value).expanduser().resolve()


def _project_hash(working_dir: str) -> str:
    """Deterministic per-project hash: sha256(abs_path)[:16]."""
    abs_path = str(_normalize_path(working_dir))
    return hashlib.sha256(abs_path.encode()).hexdigest()[:16]


def _store_path(base: Optional[Path] = None) -> Path:
    """Return the single shared shadow store path."""
    return (base or CHECKPOINT_BASE) / _STORE_DIRNAME


def _shadow_repo_path(working_dir: str) -> Path:
    """Return the shared store path."""
    return _store_path()


def _index_path(store: Path, dir_hash: str) -> Path:
    return store / _INDEXES_DIRNAME / dir_hash


def _ref_name(dir_hash: str) -> str:
    return f"{_REFS_PREFIX}/{dir_hash}"


def _project_meta_path(store: Path, dir_hash: str) -> Path:
    return store / _PROJECTS_DIRNAME / f"{dir_hash}.json"


# ---------------------------------------------------------------------------
# Git env
# ---------------------------------------------------------------------------

def _git_env(
    store: Path,
    working_dir: str,
    index_file: Optional[Path] = None,
) -> dict:
    """Build env dict that redirects git to the shared store."""
    normalized_working_dir = _normalize_path(working_dir)
    env = os.environ.copy()
    env["GIT_DIR"] = str(store)
    env["GIT_WORK_TREE"] = str(normalized_working_dir)
    env.pop("GIT_NAMESPACE", None)
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    if index_file is not None:
        env["GIT_INDEX_FILE"] = str(index_file)
    else:
        env.pop("GIT_INDEX_FILE", None)
    # Keep user git config - NO isolation
    # env.pop("GIT_CONFIG_GLOBAL", None)
    # env.pop("GIT_CONFIG_SYSTEM", None)
    # env.pop("GIT_CONFIG_NOSYSTEM", None)
    return env


def _run_git(
    args: List[str],
    store: Path,
    working_dir: str,
    timeout: int = _GIT_TIMEOUT,
    allowed_returncodes: Optional[Set[int]] = None,
    index_file: Optional[Path] = None,
) -> Tuple[bool, str, str]:
    """Run a git command - NO security restrictions."""
    normalized_working_dir = _normalize_path(working_dir)
    if not normalized_working_dir.exists():
        msg = f"working directory not found: {normalized_working_dir}"
        logger.error("Git command skipped: %s (%s)", " ".join(["git"] + list(args)), msg)
        return False, "", msg
    if not normalized_working_dir.is_dir():
        msg = f"working directory is not a directory: {normalized_working_dir}"
        logger.error("Git command skipped: %s (%s)", " ".join(["git"] + list(args)), msg)
        return False, "", msg

    env = _git_env(store, str(normalized_working_dir), index_file=index_file)
    cmd = ["git"] + list(args)
    allowed_returncodes = allowed_returncodes or set()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(normalized_working_dir),
        )
        ok = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if not ok and result.returncode not in allowed_returncodes:
            logger.error(
                "Git command failed: %s (rc=%d) stderr=%s",
                " ".join(cmd), result.returncode, stderr,
            )
        return ok, stdout, stderr
    except subprocess.TimeoutExpired:
        msg = f"git timed out after {timeout}s: {' '.join(cmd)}"
        logger.error(msg, exc_info=True)
        return False, "", msg
    except FileNotFoundError as exc:
        missing_target = getattr(exc, "filename", None)
        if missing_target == "git":
            logger.error("Git executable not found: %s", " ".join(cmd), exc_info=True)
            return False, "", "git not found"
        msg = f"working directory not found: {normalized_working_dir}"
        logger.error("Git command failed before execution: %s (%s)", " ".join(cmd), msg, exc_info=True)
        return False, "", msg
    except Exception as exc:
        logger.error("Unexpected git error running %s: %s", " ".join(cmd), exc, exc_info=True)
        return False, "", str(exc)


# ---------------------------------------------------------------------------
# Store initialisation + legacy migration
# ---------------------------------------------------------------------------

def _init_store(store: Path, working_dir: str) -> Optional[str]:
    """Initialise the shared shadow store - NO security restrictions."""
    base = store.parent
    if not store.exists():
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Could not create checkpoint base: {exc}"

    if (store / "HEAD").exists():
        return None

    store.mkdir(parents=True, exist_ok=True)
    (store / _INDEXES_DIRNAME).mkdir(exist_ok=True)
    (store / _PROJECTS_DIRNAME).mkdir(exist_ok=True)

    # Use raw subprocess with minimal restrictions
    init_env = os.environ.copy()
    # Keep user config - NO isolation
    try:
        result = subprocess.run(
            ["git", "init", "--bare", str(store)],
            capture_output=True, text=True,
            env=init_env, timeout=_GIT_TIMEOUT,
        )
        if result.returncode != 0:
            return f"Shadow store init failed: {result.stderr.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return f"Shadow store init failed: {exc}"

    cfg_wd = str(base)
    _run_git(["config", "user.email", "hermes@local"], store, cfg_wd)
    _run_git(["config", "user.name", "Hermes Checkpoint"], store, cfg_wd)
    _run_git(["config", "commit.gpgsign", "false"], store, cfg_wd)
    _run_git(["config", "tag.gpgSign", "false"], store, cfg_wd)
    _run_git(["config", "gc.auto", "0"], store, cfg_wd)

    info_dir = store / "info"
    info_dir.mkdir(exist_ok=True)
    (info_dir / "exclude").write_text("\n".join(DEFAULT_EXCLUDES) + "\n", encoding="utf-8")

    logger.debug("Initialised checkpoint store at %s", store)
    return None


def _register_project(store: Path, working_dir: str) -> None:
    """Create or update project metadata."""
    dir_hash = _project_hash(working_dir)
    meta_path = _project_meta_path(store, dir_hash)
    now = time.time()
    meta: Dict = {"workdir": str(_normalize_path(working_dir)),
                  "created_at": now, "last_touch": now}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                meta["created_at"] = existing.get("created_at", now)
        except (OSError, ValueError):
            pass
    try:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write project metadata %s: %s", meta_path, exc)


def _touch_project(store: Path, working_dir: str) -> None:
    """Update last_touch for a project."""
    dir_hash = _project_hash(working_dir)
    meta_path = _project_meta_path(store, dir_hash)
    if not meta_path.exists():
        _register_project(store, working_dir)
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["workdir"] = str(_normalize_path(working_dir))
    meta["last_touch"] = time.time()
    meta.setdefault("created_at", meta["last_touch"])
    try:
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not update project metadata %s: %s", meta_path, exc)


def _list_projects(store: Path) -> List[Dict]:
    """Return all registered projects."""
    projects_dir = store / _PROJECTS_DIRNAME
    if not projects_dir.exists():
        return []
    out: List[Dict] = []
    for meta_path in projects_dir.glob("*.json"):
        dir_hash = meta_path.stem
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        meta["_hash"] = dir_hash
        out.append(meta)
    return out


def _dir_file_count(path: str) -> int:
    """Quick file count estimate - NO LIMIT."""
    count = 0
    try:
        for _ in Path(path).rglob("*"):
            count += 1
    except (PermissionError, OSError):
        pass
    return count


def _dir_size_bytes(path: Path) -> int:
    """Best-effort recursive size in bytes."""
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


# ---------------------------------------------------------------------------
# CheckpointManager - NO SECURITY
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Manages automatic filesystem checkpoints - NO SECURITY VERSION."""

    def __init__(
        self,
        enabled: bool = False,
        max_snapshots: int = 20,
        max_total_size_mb: int = 500,
        max_file_size_mb: int = 10,
    ):
        self.enabled = enabled
        self.max_snapshots = max(1, int(max_snapshots))
        self.max_total_size_mb = max(0, int(max_total_size_mb))
        self.max_file_size_mb = max(0, int(max_file_size_mb))
        self._checkpointed_dirs: Set[str] = set()
        self._git_available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Turn lifecycle
    # ------------------------------------------------------------------

    def new_turn(self) -> None:
        """Reset per-turn dedup."""
        self._checkpointed_dirs.clear()

    # ------------------------------------------------------------------
    # Public API - NO SECURITY RESTRICTIONS
    # ------------------------------------------------------------------

    def ensure_checkpoint(self, working_dir: str, reason: str = "auto") -> bool:
        """Take a checkpoint - NO path restrictions."""
        if not self.enabled:
            return False

        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
            if not self._git_available:
                logger.debug("Checkpoints disabled: git not found")
        if not self._git_available:
            return False

        abs_dir = str(_normalize_path(working_dir))

        # NO root/home restrictions - allow ANY directory

        if abs_dir in self._checkpointed_dirs:
            return False

        self._checkpointed_dirs.add(abs_dir)

        try:
            return self._take(abs_dir, reason)
        except Exception as e:
            logger.debug("Checkpoint failed (non-fatal): %s", e)
            return False

    def list_checkpoints(self, working_dir: str) -> List[Dict]:
        """List available checkpoints - NO validation."""
        abs_dir = str(_normalize_path(working_dir))
        store = _store_path(CHECKPOINT_BASE)

        if not (store / "HEAD").exists():
            return []

        ref = _ref_name(_project_hash(abs_dir))
        ok, stdout, _ = _run_git(
            ["log", ref, f"--format=%H|%h|%aI|%s", "-n", str(self.max_snapshots)],
            store, abs_dir,
            allowed_returncodes={128, 129},
        )

        if not ok or not stdout:
            return []

        results: List[Dict] = []
        for line in stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                entry = {
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "timestamp": parts[2],
                    "reason": parts[3],
                    "files_changed": 0,
                    "insertions": 0,
                    "deletions": 0,
                }
                stat_ok, stat_out, _ = _run_git(
                    ["diff", "--shortstat", f"{parts[0]}~1", parts[0]],
                    store, abs_dir,
                    allowed_returncodes={128, 129},
                )
                if stat_ok and stat_out:
                    self._parse_shortstat(stat_out, entry)
                results.append(entry)
        return results

    @staticmethod
    def _parse_shortstat(stat_line: str, entry: Dict) -> None:
        """Parse git --shortstat output."""
        m = re.search(r'(\d+) file', stat_line)
        if m:
            entry["files_changed"] = int(m.group(1))
        m = re.search(r'(\d+) insertion', stat_line)
        if m:
            entry["insertions"] = int(m.group(1))
        m = re.search(r'(\d+) deletion', stat_line)
        if m:
            entry["deletions"] = int(m.group(1))

    def diff(self, working_dir: str, commit_hash: str) -> Dict:
        """Show diff - NO validation."""
        # NO commit hash validation
        abs_dir = str(_normalize_path(working_dir))
        store = _store_path(CHECKPOINT_BASE)

        if not (store / "HEAD").exists():
            return {"success": False, "error": "No checkpoints exist for this directory"}

        ok, _, err = _run_git(
            ["cat-file", "-t", commit_hash], store, abs_dir,
        )
        if not ok:
            return {"success": False, "error": f"Checkpoint '{commit_hash}' not found"}

        dir_hash = _project_hash(abs_dir)
        index_file = _index_path(store, dir_hash)

        _run_git(["add", "-A"], store, abs_dir,
                 timeout=_GIT_TIMEOUT * 2, index_file=index_file)

        ok_stat, stat_out, _ = _run_git(
            ["diff", "--stat", commit_hash, "--cached"],
            store, abs_dir, index_file=index_file,
        )
        ok_diff, diff_out, _ = _run_git(
            ["diff", commit_hash, "--cached", "--no-color"],
            store, abs_dir, index_file=index_file,
        )

        ref = _ref_name(dir_hash)
        _run_git(["read-tree", ref], store, abs_dir,
                 index_file=index_file,
                 allowed_returncodes={128})

        if not ok_stat and not ok_diff:
            return {"success": False, "error": "Could not generate diff"}

        return {
            "success": True,
            "stat": stat_out if ok_stat else "",
            "diff": diff_out if ok_diff else "",
        }

    def restore(self, working_dir: str, commit_hash: str, file_path: str = None) -> Dict:
        """Restore files - NO validation, NO path restrictions."""
        # NO commit hash validation
        # NO file path validation - allow absolute paths, path traversal

        abs_dir = str(_normalize_path(working_dir))
        store = _store_path(CHECKPOINT_BASE)

        if not (store / "HEAD").exists():
            return {"success": False, "error": "No checkpoints exist for this directory"}

        ok, _, err = _run_git(
            ["cat-file", "-t", commit_hash], store, abs_dir,
        )
        if not ok:
            return {"success": False, "error": f"Checkpoint '{commit_hash}' not found",
                    "debug": err or None}

        # Take a pre-rollback snapshot
        self._take(abs_dir, f"pre-rollback snapshot (restoring to {commit_hash[:8]})")

        dir_hash = _project_hash(abs_dir)
        index_file = _index_path(store, dir_hash)

        restore_target = file_path if file_path else "."
        ok, stdout, err = _run_git(
            ["checkout", commit_hash, "--", restore_target],
            store, abs_dir, timeout=_GIT_TIMEOUT * 2,
            index_file=index_file,
        )

        if not ok:
            return {"success": False, "error": f"Restore failed: {err}",
                    "debug": err or None}

        ok2, reason_out, _ = _run_git(
            ["log", "--format=%s", "-1", commit_hash], store, abs_dir,
        )
        reason = reason_out if ok2 else "unknown"

        result = {
            "success": True,
            "restored_to": commit_hash[:8],
            "reason": reason,
            "directory": abs_dir,
        }
        if file_path:
            result["file"] = file_path
        return result

    def get_working_dir_for_path(self, file_path: str) -> str:
        """Resolve a file path to its working directory."""
        path = _normalize_path(file_path)
        if path.is_dir():
            candidate = path
        else:
            candidate = path.parent

        markers = {".git", "pyproject.toml", "package.json", "Cargo.toml",
                    "go.mod", "Makefile", "pom.xml", ".hg", "Gemfile"}
        check = candidate
        while check != check.parent:
            if any((check / m).exists() for m in markers):
                return str(check)
            check = check.parent

        return str(candidate)

    # ------------------------------------------------------------------
    # Internal - NO size limits, NO file filtering
    # ------------------------------------------------------------------

    def _take(self, working_dir: str, reason: str) -> bool:
        """Take a snapshot - NO size limits, NO file filtering."""
        store = _store_path(CHECKPOINT_BASE)

        err = _init_store(store, working_dir)
        if err:
            logger.debug("Checkpoint store init failed: %s", err)
            return False

        _touch_project(store, working_dir)

        # NO file count limit
        # if _dir_file_count(working_dir) > _MAX_FILES:
        #     logger.debug("Checkpoint skipped: >%d files in %s", _MAX_FILES, working_dir)
        #     return False

        dir_hash = _project_hash(working_dir)
        index_file = _index_path(store, dir_hash)
        ref = _ref_name(dir_hash)

        if index_file.exists():
            ok_ref, ref_commit, _ = _run_git(
                ["rev-parse", "--verify", ref + "^{commit}"],
                store, working_dir,
                allowed_returncodes={128},
            )
            if ok_ref and ref_commit:
                _run_git(
                    ["read-tree", ref_commit],
                    store, working_dir,
                    index_file=index_file,
                    allowed_returncodes={128},
                )
            else:
                try:
                    index_file.unlink()
                except OSError:
                    pass
        else:
            index_file.parent.mkdir(parents=True, exist_ok=True)

        # Stage all files - NO size filtering
        ok, _, err = _run_git(
            ["add", "-A"], store, working_dir,
            timeout=_GIT_TIMEOUT * 2, index_file=index_file,
        )
        if not ok:
            logger.debug("Checkpoint git-add failed: %s", err)
            return False

        # NO oversize file dropping
        # if self.max_file_size_mb > 0:
        #     self._drop_oversize_from_index(store, working_dir, index_file)

        ok_ref, ref_commit, _ = _run_git(
            ["rev-parse", "--verify", ref + "^{commit}"],
            store, working_dir,
            allowed_returncodes={128},
        )
        has_ref = ok_ref and bool(ref_commit)

        if has_ref:
            ok_diff, _, _ = _run_git(
                ["diff-index", "--cached", "--quiet", ref_commit],
                store, working_dir,
                allowed_returncodes={1},
                index_file=index_file,
            )
            if ok_diff:
                logger.debug("Checkpoint skipped: no changes in %s", working_dir)
                return False
        else:
            ok_ls, ls_out, _ = _run_git(
                ["ls-files", "--cached"],
                store, working_dir,
                index_file=index_file,
            )
            if ok_ls and not ls_out.strip():
                logger.debug("Checkpoint skipped: empty tree in %s", working_dir)
                return False

        ok_tree, tree_sha, err = _run_git(
            ["write-tree"], store, working_dir,
            index_file=index_file,
        )
        if not ok_tree or not tree_sha:
            logger.debug("Checkpoint write-tree failed: %s", err)
            return False

        commit_args = ["commit-tree", tree_sha, "-m", reason, "--no-gpg-sign"]
        if has_ref:
            commit_args = ["commit-tree", tree_sha, "-p", ref_commit, "-m", reason, "--no-gpg-sign"]
        ok_commit, new_sha, err = _run_git(
            commit_args, store, working_dir,
            index_file=index_file,
        )
        if not ok_commit or not new_sha:
            logger.debug("Checkpoint commit-tree failed: %s", err)
            return False

        update_args = ["update-ref", ref, new_sha]
        if has_ref:
            update_args = ["update-ref", ref, new_sha, ref_commit]
        ok_update, _, err = _run_git(
            update_args, store, working_dir,
        )
        if not ok_update:
            logger.debug("Checkpoint update-ref failed: %s", err)
            return False

        logger.debug("Checkpoint taken in %s: %s (%s)", working_dir, reason, new_sha[:8])

        self._prune(store, working_dir, ref)
        self._enforce_size_cap(store)

        return True

    def _drop_oversize_from_index(
        self, store: Path, working_dir: str, index_file: Path,
    ) -> None:
        """DISABLED - No file size filtering."""
        pass

    def _prune(self, store: Path, working_dir: str, ref: str) -> None:
        """Prune old commits."""
        ok, stdout, _ = _run_git(
            ["rev-list", "--count", ref], store, working_dir,
            allowed_returncodes={128},
        )
        if not ok:
            return
        try:
            count = int(stdout)
        except ValueError:
            return
        if count <= self.max_snapshots:
            return

        ok_list, list_out, _ = _run_git(
            ["rev-list", "--reverse", ref], store, working_dir,
        )
        if not ok_list or not list_out:
            return
        commits = list_out.splitlines()
        keep = commits[-self.max_snapshots:]

        new_parent: Optional[str] = None
        for sha in keep:
            ok_tree, tree_sha, _ = _run_git(
                ["rev-parse", f"{sha}^{{tree}}"], store, working_dir,
            )
            if not ok_tree or not tree_sha:
                return
            ok_msg, msg, _ = _run_git(
                ["log", "--format=%s", "-1", sha], store, working_dir,
            )
            commit_msg = msg if ok_msg and msg else "checkpoint"
            args = ["commit-tree", tree_sha, "-m", commit_msg, "--no-gpg-sign"]
            if new_parent is not None:
                args = ["commit-tree", tree_sha, "-p", new_parent,
                        "-m", commit_msg, "--no-gpg-sign"]
            ok_commit, new_sha, _ = _run_git(args, store, working_dir)
            if not ok_commit or not new_sha:
                return
            new_parent = new_sha

        if new_parent is None:
            return
        _run_git(["update-ref", ref, new_parent], store, working_dir)

        _run_git(
            ["reflog", "expire", "--expire=now", "--all"],
            store, working_dir,
        )
        _run_git(
            ["gc", "--prune=now", "--quiet"],
            store, working_dir, timeout=_GIT_TIMEOUT * 3,
        )

    def _enforce_size_cap(self, store: Path) -> None:
        """Enforce size cap - SKIPPED."""
        # NO size cap enforcement
        pass


# ---------------------------------------------------------------------------
# Public helpers for CLI - KEPT FOR FUNCTIONALITY
# ---------------------------------------------------------------------------

def format_checkpoint_list(checkpoints: List[Dict], directory: str) -> str:
    """Format checkpoint list for display."""
    if not checkpoints:
        return f"No checkpoints found for {directory}"

    lines = [f"📸 Checkpoints for {directory}:\n"]
    for i, cp in enumerate(checkpoints, 1):
        ts = cp["timestamp"]
        if "T" in ts:
            ts = ts.split("T")[1].split("+")[0].split("-")[0][:5]
            date = cp["timestamp"].split("T")[0]
            ts = f"{date} {ts}"

        files = cp.get("files_changed", 0)
        ins = cp.get("insertions", 0)
        dele = cp.get("deletions", 0)
        if files:
            stat = f"  ({files} file{'s' if files != 1 else ''}, +{ins}/-{dele})"
        else:
            stat = ""

        lines.append(f"  {i}. {cp['short_hash']}  {ts}  {cp['reason']}{stat}")

    lines.append("\n  /rollback <N>             restore to checkpoint N")
    lines.append("  /rollback diff <N>        preview changes since checkpoint N")
    lines.append("  /rollback <N> <file>      restore a single file from checkpoint N")
    return "\n".join(lines)


_PRUNE_MARKER_NAME = ".last_prune"


def prune_checkpoints(
    retention_days: int = 7,
    delete_orphans: bool = True,
    checkpoint_base: Optional[Path] = None,
    max_total_size_mb: int = 0,
) -> Dict[str, int]:
    """Prune checkpoints - NO safety checks."""
    base = checkpoint_base or CHECKPOINT_BASE
    result = {
        "scanned": 0,
        "deleted_orphan": 0,
        "deleted_stale": 0,
        "errors": 0,
        "bytes_freed": 0,
    }
    if not base.exists():
        return result

    size_before = _dir_size_bytes(base)

    cutoff = 0.0
    if retention_days > 0:
        cutoff = time.time() - retention_days * 86400

    # Legacy cleanup
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if child.name == _STORE_DIRNAME:
            continue
        if child.name.startswith(_LEGACY_PREFIX):
            if retention_days <= 0:
                continue
            try:
                m = child.stat().st_mtime
            except OSError:
                continue
            if m >= cutoff:
                continue
            try:
                size = _dir_size_bytes(child)
                shutil.rmtree(child)
                result["bytes_freed"] += size
                result["deleted_stale"] += 1
            except OSError as exc:
                result["errors"] += 1
                logger.warning("Failed to delete legacy archive %s: %s", child, exc)
            continue
        if not (child / "HEAD").exists():
            continue
        result["scanned"] += 1
        reason: Optional[str] = None
        if delete_orphans:
            workdir: Optional[str] = None
            wd_marker = child / "HERMES_WORKDIR"
            if wd_marker.exists():
                try:
                    workdir = wd_marker.read_text(encoding="utf-8").strip()
                except (OSError, UnicodeDecodeError):
                    workdir = None
            if workdir is None or not Path(workdir).exists():
                reason = "orphan"
        if reason is None and retention_days > 0:
            newest = 0.0
            try:
                for p in child.rglob("*"):
                    try:
                        mt = p.stat().st_mtime
                        newest = max(newest, mt)
                    except OSError:
                        continue
            except OSError:
                pass
            if newest > 0 and newest < cutoff:
                reason = "stale"
        if reason is None:
            continue
        try:
            size = _dir_size_bytes(child)
            shutil.rmtree(child)
            result["bytes_freed"] += size
            if reason == "orphan":
                result["deleted_orphan"] += 1
            else:
                result["deleted_stale"] += 1
        except OSError as exc:
            result["errors"] += 1
            logger.warning("Failed to prune checkpoint repo %s: %s", child.name, exc)

    # v2 store cleanup
    store = _store_path(base)
    if (store / "HEAD").exists():
        for meta in _list_projects(store):
            dir_hash = meta.get("_hash") or ""
            workdir = meta.get("workdir") or ""
            if not dir_hash:
                continue
            result["scanned"] += 1
            reason = None
            if delete_orphans and (not workdir or not Path(workdir).exists()):
                reason = "orphan"
            elif retention_days > 0:
                last_touch = float(meta.get("last_touch", 0) or 0)
                if last_touch > 0 and last_touch < cutoff:
                    reason = "stale"
            if reason is None:
                continue
            ref = _ref_name(dir_hash)
            _run_git(["update-ref", "-d", ref], store, str(base), allowed_returncodes={128})
            try:
                idx = _index_path(store, dir_hash)
                if idx.exists():
                    idx.unlink()
            except OSError:
                pass
            try:
                mp = _project_meta_path(store, dir_hash)
                if mp.exists():
                    mp.unlink()
            except OSError:
                pass
            if reason == "orphan":
                result["deleted_orphan"] += 1
            else:
                result["deleted_stale"] += 1

        _run_git(["reflog", "expire", "--expire=now", "--all"], store, str(base))
        _run_git(["gc", "--prune=now", "--quiet"], store, str(base), timeout=_GIT_TIMEOUT * 3)

    size_after = _dir_size_bytes(base)
    delta = size_before - size_after
    result["bytes_freed"] = max(result["bytes_freed"], delta)

    return result


def store_status(checkpoint_base: Optional[Path] = None) -> Dict:
    """Return store status."""
    base = checkpoint_base or CHECKPOINT_BASE
    out: Dict = {
        "base": str(base),
        "store_size_bytes": 0,
        "legacy_size_bytes": 0,
        "total_size_bytes": 0,
        "project_count": 0,
        "projects": [],
        "legacy_archives": [],
    }
    if not base.exists():
        return out

    store = _store_path(base)
    if store.exists():
        out["store_size_bytes"] = _dir_size_bytes(store)
        if (store / "HEAD").exists():
            for meta in _list_projects(store):
                dir_hash = meta.get("_hash") or ""
                workdir = meta.get("workdir") or ""
                ref = _ref_name(dir_hash)
                ok, count_out, _ = _run_git(
                    ["rev-list", "--count", ref], store, str(base),
                    allowed_returncodes={128},
                )
                try:
                    commits = int(count_out) if ok else 0
                except ValueError:
                    commits = 0
                out["projects"].append({
                    "hash": dir_hash,
                    "workdir": workdir,
                    "exists": bool(workdir) and Path(workdir).exists(),
                    "created_at": meta.get("created_at"),
                    "last_touch": meta.get("last_touch"),
                    "commits": commits,
                })
    out["project_count"] = len(out["projects"])

    for child in base.iterdir():
        if child.is_dir() and child.name.startswith(_LEGACY_PREFIX):
            try:
                size = _dir_size_bytes(child)
            except OSError:
                size = 0
            out["legacy_size_bytes"] += size
            try:
                mt = child.stat().st_mtime
            except OSError:
                mt = 0
            out["legacy_archives"].append({
                "name": child.name,
                "size_bytes": size,
                "mtime": mt,
            })

    out["total_size_bytes"] = _dir_size_bytes(base)
    return out


def clear_all(checkpoint_base: Optional[Path] = None) -> Dict[str, int]:
    """Clear all checkpoints."""
    base = checkpoint_base or CHECKPOINT_BASE
    out = {"bytes_freed": 0, "deleted": False}
    if not base.exists():
        return out
    size = _dir_size_bytes(base)
    try:
        shutil.rmtree(base)
        out["bytes_freed"] = size
        out["deleted"] = True
    except OSError as exc:
        logger.warning("Could not clear checkpoint base %s: %s", base, exc)
    return out


def clear_legacy(checkpoint_base: Optional[Path] = None) -> Dict[str, int]:
    """Clear legacy archives."""
    base = checkpoint_base or CHECKPOINT_BASE
    out = {"bytes_freed": 0, "deleted": 0}
    if not base.exists():
        return out
    for child in list(base.iterdir()):
        if not child.is_dir() or not child.name.startswith(_LEGACY_PREFIX):
            continue
        try:
            size = _dir_size_bytes(child)
            shutil.rmtree(child)
            out["bytes_freed"] += size
            out["deleted"] += 1
        except OSError as exc:
            logger.warning("Could not delete legacy archive %s: %s", child, exc)
    return out
