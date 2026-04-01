"""
Tool interceptors — cross-cutting concerns injected into every MCP tool call.

Interceptors wrap tool execution with:
  - Authentication injection (API keys, tokens)
  - Rate limiting (per-server, per-hour for LinkedIn)
  - Logging (tool name, input, output, latency)
  - Circuit breaker integration
  - Cost tracking for paid APIs

Interceptors are transparent to agents — they don't know they're being wrapped.
"""

import logging
import time
from collections import defaultdict
from typing import Any, Callable

from core.circuit_breaker import CircuitBreakerError, get_breaker, is_available

logger = logging.getLogger(__name__)

# ── Per-server rate limits (requests per hour) ────────────────────────────────
SERVER_RATE_LIMITS: dict[str, int] = {
    "linkedin": 200,         # Browser scraping — ~65 prospects/hour with 2s nav delay
    "browser_scraper": 120,  # 120 website scrapes/hour via Playwright
    "browser_search": 60,    # 60 Google searches/hour (conservative to avoid captcha)
}

# Sliding window counters: server_name → list of timestamps
_rate_window: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(server_name: str) -> bool:
    """Return True if the call is allowed under the server's hourly rate limit."""
    max_per_hour = SERVER_RATE_LIMITS.get(server_name)
    if max_per_hour is None:
        return True

    now = time.monotonic()
    window = _rate_window[server_name]

    # Prune entries older than 1 hour
    cutoff = now - 3600
    _rate_window[server_name] = [t for t in window if t > cutoff]
    window = _rate_window[server_name]

    if len(window) >= max_per_hour:
        return False

    window.append(now)
    return True


async def with_auth(
    tool_fn: Callable,
    tool_input: dict[str, Any],
    server_name: str,
    credentials: dict[str, str],
) -> Any:
    """Inject authentication into tool call."""
    enriched_input = {**tool_input, "_auth": credentials}
    return await tool_fn(enriched_input)


async def with_logging(
    tool_fn: Callable,
    tool_input: dict[str, Any],
    server_name: str,
    tool_name: str,
) -> Any:
    """Log tool call with input, output, and latency."""
    start = time.monotonic()
    try:
        result = await tool_fn(tool_input)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "[Tool] %s.%s completed in %.0fms",
            server_name, tool_name, elapsed_ms,
        )
        return result
    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.error(
            "[Tool] %s.%s failed in %.0fms: %s",
            server_name, tool_name, elapsed_ms, exc,
        )
        raise


async def with_circuit_breaker(
    tool_fn: Callable,
    tool_input: dict[str, Any],
    server_name: str,
) -> Any:
    """Wrap tool call with circuit breaker for the server."""
    if not is_available(server_name):
        raise CircuitBreakerError(
            f"Circuit breaker OPEN for {server_name} — call rejected"
        )

    breaker = get_breaker(server_name)

    @breaker
    async def _call():
        return await tool_fn(tool_input)

    return await _call()


async def with_timeout(
    tool_fn: Callable,
    tool_input: dict[str, Any],
    timeout_seconds: float = 10.0,
) -> Any:
    """Enforce a hard timeout on tool calls (default 10s per MCP Reliability Playbook)."""
    import asyncio
    try:
        return await asyncio.wait_for(tool_fn(tool_input), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"Tool call timed out after {timeout_seconds}s"
        )


async def intercepted_tool_call(
    tool_fn: Callable,
    tool_input: dict[str, Any],
    server_name: str,
    tool_name: str,
    credentials: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    """
    Execute a tool call through the full interceptor chain:
    rate limit → circuit breaker → auth → timeout → logging.

    This is the primary entry point for all MCP tool calls.
    """
    # Server-specific timeouts (browser automation is slow)
    SERVER_TIMEOUTS: dict[str, float] = {"linkedin": 60.0}
    if timeout_seconds is None:
        timeout_seconds = SERVER_TIMEOUTS.get(server_name, 10.0)
    start = time.monotonic()

    # 1. Rate limit check
    if not _check_rate_limit(server_name):
        logger.warning(
            "[Tool] %s.%s rate-limited (%d/hr max)",
            server_name, tool_name, SERVER_RATE_LIMITS.get(server_name, 0),
        )
        return {
            "error": f"{server_name} rate limit exceeded — try again later",
            "rate_limited": True,
            "skipped": True,
        }

    # 2. Circuit breaker check
    if not is_available(server_name):
        logger.warning("[Tool] %s is unavailable (breaker OPEN)", server_name)
        return {"error": f"{server_name} is currently unavailable", "skipped": True}

    # 3. Auth injection
    if credentials:
        tool_input = {**tool_input, "_auth": credentials}

    # 3. Execute with timeout + circuit breaker + logging
    breaker = get_breaker(server_name)

    try:
        @breaker
        async def _execute():
            import asyncio
            return await asyncio.wait_for(
                tool_fn(tool_input), timeout=timeout_seconds,
            )

        result = await _execute()
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info("[Tool] %s.%s → %.0fms", server_name, tool_name, elapsed_ms)
        return result

    except CircuitBreakerError:
        logger.warning("[Tool] %s.%s rejected by circuit breaker", server_name, tool_name)
        return {"error": f"{server_name} circuit breaker open", "skipped": True}
    except TimeoutError:
        logger.error("[Tool] %s.%s timed out after %.0fs", server_name, tool_name, timeout_seconds)
        return {"error": f"Timeout after {timeout_seconds}s", "skipped": True}
    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.error("[Tool] %s.%s failed in %.0fms: %s", server_name, tool_name, elapsed_ms, exc)
        raise
