"""Configuration types for resilient HTTP clients."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import httpx

if TYPE_CHECKING:
    from collections.abc import Mapping

ResponseHook = Callable[[httpx.Response], Awaitable[None] | None]
ShouldCacheHook = Callable[[object], bool]


class RetryablePayloadError(httpx.HTTPError):
    """Raised by response hooks when a payload-level condition should trigger a retry."""

    def __init__(self, message: str, *, response: httpx.Response) -> None:
        super().__init__(message)
        self.response = response


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    total: int = 4
    backoff_factor: float = 0.5
    max_backoff_wait: float = 60.0
    respect_retry_after_header: bool = True
    allowed_methods: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
        )
    )
    status_forcelist: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )
    retry_on_exceptions: tuple[type[httpx.HTTPError], ...] = (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
        RetryablePayloadError,
    )
    backoff_jitter: float = 1.0


@dataclass(slots=True, frozen=True)
class RateLimit:
    max_calls: int
    per_seconds: float


@dataclass(slots=True, frozen=True)
class CacheConfig:
    enabled: bool = True
    backend: Literal["sqlite", "memory"] = "memory"
    sqlite_path: str | None = None
    default_ttl_seconds: float | None = None
    refresh_ttl_on_access: bool = True
    should_cache: ShouldCacheHook | None = None


@dataclass(slots=True, frozen=True)
class ResilienceConfig:
    name: str
    base_url: str | None = None
    timeout_seconds: float = 30.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    ratelimit: RateLimit | None = None
    cache: CacheConfig | None = field(default_factory=CacheConfig)
    response_hooks: tuple[ResponseHook, ...] = field(default_factory=tuple)
    default_headers: Mapping[str, str] | None = None
