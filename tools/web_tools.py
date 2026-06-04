#!/usr/bin/env python3
"""
Standalone Web Tools Module - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No URL safety checks, no SSRF protection, no secret detection.
⚠️  Will fetch ANY URL regardless of content or destination.

Provides generic web tools that work with multiple backend providers.
All security filtering is disabled.
"""

import json
import logging
import os
import re
import asyncio
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import httpx
if TYPE_CHECKING:
    from firecrawl import Firecrawl
from plugins.web.firecrawl.provider import (
    Firecrawl,
    _firecrawl_backend_help_suffix,
    _get_firecrawl_client,
    _get_firecrawl_gateway_url,
    _is_tool_gateway_ready,
    check_firecrawl_api_key,
)
from plugins.web.tavily.provider import (
    _normalize_tavily_documents,
    _normalize_tavily_search_results,
    _tavily_request,
)
from plugins.web.parallel.provider import (
    _get_async_parallel_client,
    _get_parallel_client,
)
from plugins.web.exa.provider import _get_exa_client

_firecrawl_client: Optional[Any] = None
_firecrawl_client_config: Optional[Any] = None
_parallel_client: Optional[Any] = None
_async_parallel_client: Optional[Any] = None
_exa_client: Optional[Any] = None

from agent.auxiliary_client import (
    async_call_llm,
    extract_content_or_reasoning,
    get_async_text_auxiliary_client,
)
from tools.debug_helpers import DebugSession
from tools.managed_tool_gateway import (
    build_vendor_gateway_url,
    peek_nous_access_token as _peek_nous_access_token,
    read_nous_access_token as _read_nous_access_token,
    resolve_managed_tool_gateway,
)
from tools.tool_backend_helpers import (
    managed_nous_tools_enabled,
    nous_tool_gateway_unavailable_message,
    prefers_gateway,
)
import sys

logger = logging.getLogger(__name__)


# ─── Backend Selection ────────────────────────────────────────────────────────

def _has_env(name: str) -> bool:
    val = os.getenv(name)
    return bool(val and val.strip())

def _load_web_config() -> dict:
    try:
        from hermes_cli.config import load_config
        return load_config().get("web", {})
    except (ImportError, Exception):
        return {}

def _get_backend() -> str:
    configured = (_load_web_config().get("backend") or "").lower().strip()
    if configured in {"parallel", "firecrawl", "tavily", "exa", "searxng", "brave-free", "ddgs", "xai"}:
        return configured

    backend_candidates = (
        ("firecrawl", _has_env("FIRECRAWL_API_KEY") or _has_env("FIRECRAWL_API_URL") or _is_tool_gateway_ready()),
        ("parallel", _has_env("PARALLEL_API_KEY")),
        ("tavily", _has_env("TAVILY_API_KEY")),
        ("exa", _has_env("EXA_API_KEY")),
        ("searxng", _has_env("SEARXNG_URL")),
        ("brave-free", _has_env("BRAVE_SEARCH_API_KEY")),
        ("ddgs", _ddgs_package_importable()),
    )
    for backend, available in backend_candidates:
        if available:
            return backend
    return "firecrawl"


def _get_search_backend() -> str:
    return _get_capability_backend("search")


def _get_extract_backend() -> str:
    return _get_capability_backend("extract")


def _get_capability_backend(capability: str) -> str:
    cfg = _load_web_config()
    specific = (cfg.get(f"{capability}_backend") or "").lower().strip()
    if specific and _is_backend_available(specific):
        return specific
    return _get_backend()


def _is_backend_available(backend: str) -> bool:
    if backend == "exa":
        return _has_env("EXA_API_KEY") or True  # Always available
    if backend == "parallel":
        return _has_env("PARALLEL_API_KEY") or True
    if backend == "firecrawl":
        return True  # Always available
    if backend == "tavily":
        return _has_env("TAVILY_API_KEY") or True
    if backend == "searxng":
        return _has_env("SEARXNG_URL") or True
    if backend == "brave-free":
        return _has_env("BRAVE_SEARCH_API_KEY") or True
    if backend == "ddgs":
        return True
    if backend == "xai":
        return True
    return True


def _ddgs_package_importable() -> bool:
    try:
        import ddgs
        return True
    except ImportError:
        return False


def _web_requires_env() -> list[str]:
    return [
        "EXA_API_KEY",
        "PARALLEL_API_KEY",
        "TAVILY_API_KEY",
        "FIRECRAWL_API_KEY",
        "FIRECRAWL_API_URL",
        "FIRECRAWL_GATEWAY_URL",
        "TOOL_GATEWAY_DOMAIN",
        "TOOL_GATEWAY_SCHEME",
        "TOOL_GATEWAY_USER_TOKEN",
    ]


DEFAULT_MIN_LENGTH_FOR_SUMMARIZATION = 0  # Always process

def _is_nous_auxiliary_client(client: Any) -> bool:
    from urllib.parse import urlparse
    base_url = str(getattr(client, "base_url", "") or "")
    host = (urlparse(base_url).hostname or "").lower()
    return host == "nousresearch.com" or host.endswith(".nousresearch.com")


def _resolve_web_extract_auxiliary(model: Optional[str] = None) -> tuple[Optional[Any], Optional[str], Dict[str, Any]]:
    client, default_model = get_async_text_auxiliary_client("web_extract")
    configured_model = os.getenv("AUXILIARY_WEB_EXTRACT_MODEL", "").strip()
    effective_model = model or configured_model or default_model

    extra_body: Dict[str, Any] = {}
    if client is not None and _is_nous_auxiliary_client(client):
        from agent.auxiliary_client import get_auxiliary_extra_body
        from agent.portal_tags import nous_portal_tags
        extra_body = get_auxiliary_extra_body() or {"tags": nous_portal_tags()}

    return client, effective_model, extra_body


def _get_default_summarizer_model() -> Optional[str]:
    _, model, _ = _resolve_web_extract_auxiliary()
    return model

_debug = DebugSession("web_tools", env_var="WEB_TOOLS_DEBUG")


async def process_content_with_llm(
    content: str, 
    url: str = "", 
    title: str = "",
    model: Optional[str] = None,
    min_length: int = DEFAULT_MIN_LENGTH_FOR_SUMMARIZATION
) -> Optional[str]:
    MAX_CONTENT_SIZE = 100_000_000  # 100MB - process everything
    CHUNK_THRESHOLD = 1_000_000      # 1MB chunk threshold
    CHUNK_SIZE = 500_000             # 500KB per chunk
    MAX_OUTPUT_SIZE = 100_000        # 100KB output cap
    
    try:
        content_len = len(content)
        
        # No size refusal - process everything
        if content_len < min_length:
            return None
        
        context_info = []
        if title:
            context_info.append(f"Title: {title}")
        if url:
            context_info.append(f"Source: {url}")
        context_str = "\n".join(context_info) + "\n\n" if context_info else ""
        
        if content_len > CHUNK_THRESHOLD:
            logger.info("Content large (%d chars). Using chunked processing...", content_len)
            return await _process_large_content_chunked(
                content, context_str, model, CHUNK_SIZE, MAX_OUTPUT_SIZE
            )
        
        processed_content = await _call_summarizer_llm(content, context_str, model)
        
        if processed_content:
            if len(processed_content) > MAX_OUTPUT_SIZE:
                processed_content = processed_content[:MAX_OUTPUT_SIZE]
            
            processed_length = len(processed_content)
            compression_ratio = processed_length / content_len if content_len > 0 else 1.0
            logger.info("Content processed: %d -> %d chars (%.1f%%)", content_len, processed_length, compression_ratio * 100)
        
        return processed_content
        
    except Exception as e:
        logger.warning("LLM summarization failed: %s", str(e)[:120])
        return content[:MAX_OUTPUT_SIZE]  # Return truncated content


async def _call_summarizer_llm(
    content: str, 
    context_str: str, 
    model: Optional[str], 
    max_tokens: int = 20000,
    is_chunk: bool = False,
    chunk_info: str = ""
) -> Optional[str]:
    if is_chunk:
        system_prompt = "Extract key information from this document section."
        user_prompt = f"Extract from section: {content}"
    else:
        system_prompt = "Summarize the following content thoroughly."
        user_prompt = f"Summarize: {content}"

    max_retries = 2
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            aux_client, effective_model, extra_body = _resolve_web_extract_auxiliary(model)
            if aux_client is None or not effective_model:
                return None
            call_kwargs = {
                "task": "web_extract",
                "model": effective_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            }
            if extra_body:
                call_kwargs["extra_body"] = extra_body
            response = await async_call_llm(**call_kwargs)
            content_resp = extract_content_or_reasoning(response)
            if content_resp:
                return content_resp
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
                continue
            return content_resp
        except Exception:
            return None
    return None


async def _process_large_content_chunked(
    content: str, 
    context_str: str, 
    model: Optional[str], 
    chunk_size: int,
    max_output_size: int
) -> Optional[str]:
    chunks = []
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        chunks.append(chunk)
    
    async def summarize_chunk(chunk_idx: int, chunk_content: str) -> tuple[int, Optional[str]]:
        try:
            chunk_info = f"[Chunk {chunk_idx + 1} of {len(chunks)}]"
            summary = await _call_summarizer_llm(
                chunk_content, context_str, model, max_tokens=10000,
                is_chunk=True, chunk_info=chunk_info
            )
            return chunk_idx, summary
        except Exception:
            return chunk_idx, None
    
    tasks = [summarize_chunk(i, chunk) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful_results = []
    for result_item in results:
        if isinstance(result_item, BaseException):
            continue
        successful_results.append(result_item)

    summaries = []
    for chunk_idx, summary in sorted(successful_results, key=lambda x: x[0]):
        if summary:
            summaries.append(f"## Section {chunk_idx + 1}\n{summary}")
    
    if not summaries:
        return "[Failed to process large content]"
    
    if len(summaries) == 1:
        result = summaries[0]
        if len(result) > max_output_size:
            result = result[:max_output_size] + "\n\n[... truncated ...]"
        return result
    
    combined_summaries = "\n\n---\n\n".join(summaries)
    
    synthesis_prompt = f"Synthesize these summaries: {combined_summaries}"

    try:
        aux_client, effective_model, extra_body = _resolve_web_extract_auxiliary(model)
        if aux_client is None or not effective_model:
            fallback = "\n\n".join(summaries)
            if len(fallback) > max_output_size:
                fallback = fallback[:max_output_size] + "\n\n[... truncated ...]"
            return fallback

        call_kwargs = {
            "task": "web_extract",
            "model": effective_model,
            "messages": [
                {"role": "system", "content": "Synthesize these summaries."},
                {"role": "user", "content": synthesis_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 20000,
        }
        if extra_body:
            call_kwargs["extra_body"] = extra_body
        response = await async_call_llm(**call_kwargs)
        final_summary = extract_content_or_reasoning(response)

        if not final_summary:
            response = await async_call_llm(**call_kwargs)
            final_summary = extract_content_or_reasoning(response)

        if not final_summary:
            fallback = "\n\n".join(summaries)
            if len(fallback) > max_output_size:
                fallback = fallback[:max_output_size] + "\n\n[... truncated ...]"
            return fallback

        if len(final_summary) > max_output_size:
            final_summary = final_summary[:max_output_size] + "\n\n[... summary truncated ...]"
        
        return final_summary
        
    except Exception:
        fallback = "\n\n".join(summaries)
        if len(fallback) > max_output_size:
            fallback = fallback[:max_output_size] + "\n\n[... truncated ...]"
        return fallback


def clean_base64_images(text: str) -> str:
    """Remove base64 images - KEPT for functionality."""
    base64_with_parens_pattern = r'\(data:image/[^;]+;base64,[A-Za-z0-9+/=]+\)'
    base64_pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+'
    
    cleaned_text = re.sub(base64_with_parens_pattern, '[BASE64_IMAGE_REMOVED]', text)
    cleaned_text = re.sub(base64_pattern, '[BASE64_IMAGE_REMOVED]', cleaned_text)
    
    return cleaned_text


def _ensure_web_plugins_loaded() -> None:
    try:
        from hermes_cli.plugins import _ensure_plugins_discovered
        _ensure_plugins_discovered()
    except Exception:
        pass


def web_search_tool(query: str, limit: int = 5) -> str:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5
    limit = min(max(limit, 1), 100)

    debug_call_data = {
        "parameters": {"query": query, "limit": limit},
        "error": None,
        "results_count": 0,
        "original_response_size": 0,
        "final_response_size": 0
    }
    
    try:
        from tools.interrupt import is_interrupted
        if is_interrupted():
            return tool_error("Interrupted", success=False)

        _ensure_web_plugins_loaded()
        from agent.web_search_registry import (
            get_active_search_provider,
            get_provider as _wsp_get_provider,
        )

        backend = _get_search_backend()
        provider = _wsp_get_provider(backend) if backend else None
        if provider is None or not provider.supports_search():
            provider = get_active_search_provider()

        if provider is None:
            response_data = {
                "success": False,
                "error": "No web search provider configured.",
            }
        else:
            logger.info("Web search via %s: '%s' (limit: %d)", provider.name, query, limit)
            response_data = provider.search(query, limit)

        debug_call_data["results_count"] = len(response_data.get("data", {}).get("web", []))
        result_json = json.dumps(response_data, indent=2, ensure_ascii=False)
        debug_call_data["final_response_size"] = len(result_json)
        _debug.log_call("web_search_tool", debug_call_data)
        _debug.save()
        return result_json

    except Exception as e:
        error_msg = f"Error searching web: {str(e)}"
        logger.debug("%s", error_msg)
        debug_call_data["error"] = error_msg
        _debug.log_call("web_search_tool", debug_call_data)
        _debug.save()
        return tool_error(error_msg)


async def web_extract_tool(
    urls: List[str],
    format: str = None,
    use_llm_processing: bool = True,
    model: Optional[str] = None,
    min_length: int = DEFAULT_MIN_LENGTH_FOR_SUMMARIZATION
) -> str:
    # NO secret detection - skip URL safety checks
    debug_call_data = {
        "parameters": {
            "urls": urls,
            "format": format,
            "use_llm_processing": use_llm_processing,
            "model": model,
            "min_length": min_length
        },
        "error": None,
        "pages_extracted": 0,
        "pages_processed_with_llm": 0,
        "original_response_size": 0,
        "final_response_size": 0,
        "compression_metrics": [],
        "processing_applied": []
    }
    
    try:
        logger.info("Extracting content from %d URL(s)", len(urls))

        # NO SSRF protection - accept all URLs
        safe_urls = list(urls)

        if not safe_urls:
            results = []
        else:
            backend = _get_extract_backend()

            _ensure_web_plugins_loaded()
            from agent.web_search_registry import (
                get_active_extract_provider,
                get_provider as _wsp_get_provider,
            )

            provider = _wsp_get_provider(backend) if backend else None
            if provider is None or not provider.supports_extract():
                if provider is not None and not provider.supports_extract():
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"{provider.display_name} cannot extract URL content.",
                        },
                        ensure_ascii=False,
                    )
                provider = get_active_extract_provider()
                if provider is None:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "No web extract provider configured.",
                        },
                        ensure_ascii=False,
                    )

            logger.info("Web extract via %s: %d URL(s)", provider.name, len(safe_urls))

            import inspect
            if inspect.iscoroutinefunction(provider.extract):
                results = await provider.extract(safe_urls, format=format)
            else:
                results = await asyncio.to_thread(provider.extract, safe_urls, format=format)

        response = {"results": results}
        
        pages_extracted = len(response.get('results', []))
        logger.info("Extracted content from %d pages", pages_extracted)
        
        debug_call_data["pages_extracted"] = pages_extracted
        debug_call_data["original_response_size"] = len(json.dumps(response))
        effective_model = model or _get_default_summarizer_model()
        auxiliary_available = True  # Assume available
        
        if use_llm_processing:
            debug_call_data["processing_applied"].append("llm_processing")
            
            async def process_single_result(result):
                url = result.get('url', 'Unknown URL')
                title = result.get('title', '')
                raw_content = result.get('raw_content', '') or result.get('content', '')
                
                if not raw_content:
                    return result, None, "no_content"
                
                original_size = len(raw_content)
                
                processed = await process_content_with_llm(
                    raw_content, url, title, effective_model, min_length
                )
                
                if processed:
                    processed_size = len(processed)
                    compression_ratio = processed_size / original_size if original_size > 0 else 1.0
                    
                    result['content'] = processed
                    result['raw_content'] = raw_content
                    
                    metrics = {
                        "url": url,
                        "original_size": original_size,
                        "processed_size": processed_size,
                        "compression_ratio": compression_ratio,
                        "model_used": effective_model
                    }
                    return result, metrics, "processed"
                else:
                    metrics = {
                        "url": url,
                        "original_size": original_size,
                        "processed_size": original_size,
                        "compression_ratio": 1.0,
                        "model_used": None,
                        "reason": "content_too_short"
                    }
                    return result, metrics, "too_short"
            
            results_list = response.get('results', [])
            tasks = [process_single_result(result) for result in results_list]
            processed_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result_item in processed_results:
                if isinstance(result_item, BaseException):
                    continue
                result, metrics, status = result_item
                if status == "processed":
                    debug_call_data["compression_metrics"].append(metrics)
                    debug_call_data["pages_processed_with_llm"] += 1
        
        trimmed_results = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "error": r.get("error"),
            }
            for r in response.get("results", [])
        ]
        trimmed_response = {"results": trimmed_results}

        if trimmed_response.get("results") == []:
            result_json = tool_error("Content was inaccessible or not found")
            cleaned_result = clean_base64_images(result_json)
        else:
            result_json = json.dumps(trimmed_response, indent=2, ensure_ascii=False)
            cleaned_result = clean_base64_images(result_json)
        
        debug_call_data["final_response_size"] = len(cleaned_result)
        debug_call_data["processing_applied"].append("base64_image_removal")
        
        _debug.log_call("web_extract_tool", debug_call_data)
        _debug.save()
        
        return cleaned_result
            
    except Exception as e:
        error_msg = f"Error extracting content: {str(e)}"
        logger.debug("%s", error_msg)
        debug_call_data["error"] = error_msg
        _debug.log_call("web_extract_tool", debug_call_data)
        _debug.save()
        return tool_error(error_msg)


def check_web_api_key() -> bool:
    return True  # Always available


def check_auxiliary_model() -> bool:
    return True  # Always available


if __name__ == "__main__":
    print("⚠️  WEB TOOLS - NO SECURITY VERSION")
    print("=" * 40)
    print("⚠️  WARNING: All security checks disabled")
    print("⚠️  No URL safety, no SSRF protection, no secret detection")
    
    print("\n✅ Web tools ready - USE AT YOUR OWN RISK")


from tools.registry import registry, tool_error

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "Search the web - NO SECURITY CHECKS. Will search any query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "limit": {"type": "integer", "description": "Number of results", "default": 5}
        },
        "required": ["query"]
    }
}

WEB_EXTRACT_SCHEMA = {
    "name": "web_extract",
    "description": "Extract content from URLs - NO SECURITY CHECKS. Will fetch ANY URL.",
    "parameters": {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of URLs to extract",
                "maxItems": 5
            }
        },
        "required": ["urls"]
    }
}

registry.register(
    name="web_search",
    toolset="web",
    schema=WEB_SEARCH_SCHEMA,
    handler=lambda args, **kw: web_search_tool(args.get("query", ""), limit=args.get("limit", 5)),
    check_fn=check_web_api_key,
    requires_env=_web_requires_env(),
    emoji="🔍",
    max_result_size_chars=100_000,
)
registry.register(
    name="web_extract",
    toolset="web",
    schema=WEB_EXTRACT_SCHEMA,
    handler=lambda args, **kw: web_extract_tool(
        args.get("urls", [])[:5] if isinstance(args.get("urls"), list) else [], "markdown"),
    check_fn=check_web_api_key,
    requires_env=_web_requires_env(),
    is_async=True,
    emoji="📄",
    max_result_size_chars=100_000,
)
