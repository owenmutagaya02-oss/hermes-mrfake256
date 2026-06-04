"""Progressive tool disclosure ("tool search") for Hermes Agent - NO DEFERRAL VERSION

⚠️  CRITICAL WARNING: This version has ALL tool deferral logic REMOVED.
⚠️  No tools are ever deferred - all tools always visible.
⚠️  Bridge tools never replace real tools.

When enabled, MCP and non-core plugin tools are replaced in the model-visible
tools array by three bridge tools — ``tool_search``, ``tool_describe``,
``tool_call`` — and surfaced on demand. THIS VERSION DISABLES THAT ENTIRELY.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("tools.tool_search")


# Bridge tool names (defined but never used)
TOOL_SEARCH_NAME = "tool_search"
TOOL_DESCRIBE_NAME = "tool_describe"
TOOL_CALL_NAME = "tool_call"

BRIDGE_TOOL_NAMES = frozenset({TOOL_SEARCH_NAME, TOOL_DESCRIBE_NAME, TOOL_CALL_NAME})

CHARS_PER_TOKEN = 4.0


# ---------------------------------------------------------------------------
# Configuration - DISABLED
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSearchConfig:
    enabled: str  # "off" always
    threshold_pct: float
    search_default_limit: int
    max_search_limit: int

    @classmethod
    def from_raw(cls, raw: Any) -> "ToolSearchConfig":
        # Always return disabled config
        return cls(enabled="off", threshold_pct=10.0,
                   search_default_limit=5, max_search_limit=20)


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def load_config() -> ToolSearchConfig:
    """Always return disabled config."""
    return ToolSearchConfig.from_raw(None)


# ---------------------------------------------------------------------------
# Tool classification - NO DEFERRAL
# ---------------------------------------------------------------------------


def _core_tool_names() -> frozenset[str]:
    try:
        from toolsets import _HERMES_CORE_TOOLS
        return frozenset(_HERMES_CORE_TOOLS)
    except Exception:
        return frozenset()


def is_deferrable_tool_name(name: str) -> bool:
    """Always returns False - no tools are deferrable."""
    return False


def classify_tools(tool_defs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """All tools are visible, none are deferrable."""
    visible = list(tool_defs)
    deferrable: List[Dict[str, Any]] = []
    # Filter out bridge tools if they somehow appear
    visible = [td for td in visible
               if (td.get("function") or {}).get("name") not in BRIDGE_TOOL_NAMES]
    return visible, deferrable


# ---------------------------------------------------------------------------
# Token estimation - KEPT for compatibility
# ---------------------------------------------------------------------------


def estimate_tokens_from_schemas(tool_defs: Iterable[Dict[str, Any]]) -> int:
    total_chars = 0
    for td in tool_defs:
        try:
            total_chars += len(json.dumps(td, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError):
            total_chars += len(str(td))
    return int(math.ceil(total_chars / CHARS_PER_TOKEN))


def should_activate(
    config: ToolSearchConfig,
    deferrable_tokens: int,
    context_length: Optional[int],
) -> bool:
    """Always returns False - never activate."""
    return False


# ---------------------------------------------------------------------------
# Catalog - DISABLED
# ---------------------------------------------------------------------------


@dataclass
class CatalogEntry:
    name: str
    description: str
    schema: Dict[str, Any]
    source: str
    source_name: str
    _tokens: List[str] = field(default_factory=list)


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _entry_search_text(td: Dict[str, Any]) -> str:
    fn = td.get("function") or {}
    name = fn.get("name", "")
    desc = fn.get("description", "") or ""
    params = ((fn.get("parameters") or {}).get("properties") or {})
    param_names = " ".join(params.keys())
    name_words = name.replace("_", " ").replace(".", " ").replace("-", " ").replace(":", " ")
    return f"{name_words} {desc} {param_names}"


def _classify_source(name: str) -> Tuple[str, str]:
    try:
        from tools.registry import registry
        entry = registry.get_entry(name)
        if entry is None:
            return ("other", "")
        if entry.toolset.startswith("mcp-"):
            return ("mcp", entry.toolset)
        return ("plugin", entry.toolset)
    except Exception:
        return ("other", "")


def build_catalog(tool_defs: List[Dict[str, Any]]) -> List[CatalogEntry]:
    """Build catalog but never used since no tools are deferrable."""
    catalog: List[CatalogEntry] = []
    for td in tool_defs:
        fn = td.get("function") or {}
        name = fn.get("name", "")
        if not name:
            continue
        desc = fn.get("description", "") or ""
        source, source_name = _classify_source(name)
        entry = CatalogEntry(
            name=name,
            description=desc,
            schema=td,
            source=source,
            source_name=source_name,
            _tokens=_tokenize(_entry_search_text(td)),
        )
        catalog.append(entry)
    return catalog


def _bm25_score(query_tokens: List[str], doc_tokens: List[str],
                doc_lengths: List[int], avg_dl: float,
                doc_freq: Dict[str, int], n_docs: int,
                k1: float = 1.5, b: float = 0.75) -> float:
    if not doc_tokens:
        return 0.0
    score = 0.0
    dl = len(doc_tokens)
    doc_tf: Dict[str, int] = {}
    for t in doc_tokens:
        doc_tf[t] = doc_tf.get(t, 0) + 1
    for q in query_tokens:
        df = doc_freq.get(q, 0)
        if df == 0:
            continue
        idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        tf = doc_tf.get(q, 0)
        if tf == 0:
            continue
        norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1.0)))
        score += idf * norm
    return score


def search_catalog(catalog: List[CatalogEntry], query: str, limit: int = 5) -> List[CatalogEntry]:
    """Search catalog - always returns empty."""
    return []


# ---------------------------------------------------------------------------
# Bridge tool schemas - NEVER USED
# ---------------------------------------------------------------------------


def bridge_tool_schemas(deferred_count: int) -> List[Dict[str, Any]]:
    """Return empty list - no bridge tools needed."""
    return []


# ---------------------------------------------------------------------------
# Public entry point - PASSTHROUGH ONLY
# ---------------------------------------------------------------------------


@dataclass
class AssemblyResult:
    tool_defs: List[Dict[str, Any]]
    activated: bool
    deferred_count: int = 0
    deferred_tokens: int = 0
    threshold_tokens: int = 0


def assemble_tool_defs(
    tool_defs: List[Dict[str, Any]],
    *,
    context_length: Optional[int] = None,
    config: Optional[ToolSearchConfig] = None,
) -> AssemblyResult:
    """Return the original tool-defs list unchanged - NO DEFERRAL."""
    # Strip any bridge tools that may be present
    cleaned = [td for td in tool_defs
               if (td.get("function") or {}).get("name") not in BRIDGE_TOOL_NAMES]

    return AssemblyResult(
        tool_defs=cleaned,
        activated=False,
        deferred_count=0,
        deferred_tokens=0,
        threshold_tokens=0,
    )


# ---------------------------------------------------------------------------
# Bridge tool dispatch - DISABLED (never called)
# ---------------------------------------------------------------------------


def is_bridge_tool(name: str) -> bool:
    """Return True only for the reserved names (bridge tools still exist)."""
    return name in BRIDGE_TOOL_NAMES


def _format_search_hit(entry: CatalogEntry) -> Dict[str, Any]:
    return {
        "name": entry.name,
        "source": entry.source,
        "source_name": entry.source_name,
        "description": (entry.description or "")[:400],
    }


def dispatch_tool_search(args: Dict[str, Any],
                         *,
                         current_tool_defs: List[Dict[str, Any]],
                         config: Optional[ToolSearchConfig] = None) -> str:
    """Execute tool_search - returns empty results."""
    return json.dumps({
        "query": args.get("query", ""),
        "total_available": 0,
        "matches": [],
        "note": "Tool search is disabled - all tools are already visible",
    }, ensure_ascii=False)


def dispatch_tool_describe(args: Dict[str, Any],
                           *,
                           current_tool_defs: List[Dict[str, Any]]) -> str:
    """Execute tool_describe - returns error."""
    name = str(args.get("name") or "").strip()
    return json.dumps({
        "error": f"tool_describe is disabled. Tool '{name}' (if it exists) is already visible in the tools list.",
    }, ensure_ascii=False)


def scoped_deferrable_names(tool_defs: List[Dict[str, Any]]) -> frozenset[str]:
    """Return empty set - no deferrable tools."""
    return frozenset()


def resolve_underlying_call(args: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    """Parse a tool_call invocation - returns error."""
    name = str(args.get("name") or "").strip()
    return None, {}, f"tool_call is disabled. Call '{name}' directly if it exists."


__all__ = [
    "TOOL_SEARCH_NAME",
    "TOOL_DESCRIBE_NAME",
    "TOOL_CALL_NAME",
    "BRIDGE_TOOL_NAMES",
    "ToolSearchConfig",
    "CatalogEntry",
    "AssemblyResult",
    "load_config",
    "is_deferrable_tool_name",
    "classify_tools",
    "estimate_tokens_from_schemas",
    "should_activate",
    "build_catalog",
    "search_catalog",
    "bridge_tool_schemas",
    "assemble_tool_defs",
    "is_bridge_tool",
    "dispatch_tool_search",
    "dispatch_tool_describe",
    "resolve_underlying_call",
    "scoped_deferrable_names",
]
