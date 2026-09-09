"""Shared retry policy for transient external HTTP failures."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx


T = TypeVar("T")
logger = logging.getLogger(__name__)
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


async def retry_http_call(
    call: Callable[[], Awaitable[T]],
    *,
    service: str,
    max_retries: int,
    backoff_seconds: float,
) -> T:
    """Retry timeouts, connection failures, 429 and selected 5xx responses."""
    retries = max(0, max_retries)
    for attempt in range(retries + 1):
        try:
            return await call()
        except Exception as exc:
            if attempt >= retries or not _is_retryable(exc):
                raise
            delay = max(0.0, backoff_seconds) * (2 ** attempt)
            logger.warning(
                "External call failed; retrying service=%s attempt=%d/%d "
                "delay_seconds=%.1f error_type=%s",
                service,
                attempt + 1,
                retries,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")
