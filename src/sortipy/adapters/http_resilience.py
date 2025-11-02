from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Concatenate,
    Literal,
    TypedDict,
    Unpack,
)

import httpx
from aiolimiter import AsyncLimiter
from hishel import AsyncSqliteStorage, FilterPolicy
from hishel import Response as HishelCacheResponse
from hishel._policies import BaseFilter
from hishel.httpx import AsyncCacheClient
from httpx_retries import Retry, RetryTransport

from sortipy.common.storage import get_http_cache_path

if TYPE_CHECKING:
    from types import TracebackType

    from httpx._client import UseClientDefault
    from httpx._types import (
        AuthTypes,
        CookieTypes,
        HeaderTypes,
        QueryParamTypes,
        RequestContent,
        RequestData,
        RequestExtensions,
        RequestFiles,
        TimeoutTypes,
        URLTypes,
    )

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

    def build(self) -> Retry:
        return Retry(
            total=self.total,
            backoff_factor=self.backoff_factor,
            max_backoff_wait=self.max_backoff_wait,
            respect_retry_after_header=self.respect_retry_after_header,
            allowed_methods=tuple(self.allowed_methods),
            status_forcelist=tuple(self.status_forcelist),
            retry_on_exceptions=self.retry_on_exceptions,
            backoff_jitter=self.backoff_jitter,
        )


@dataclass(slots=True, frozen=True)
class RateLimit:
    max_calls: int
    per_seconds: float


@dataclass(slots=True, frozen=True)
class CacheConfig:
    enabled: bool = True
    backend: Literal["sqlite", "memory"] = "sqlite"
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


class RequestOptions(TypedDict, total=False):
    content: RequestContent | None
    data: RequestData | None
    files: RequestFiles | None
    json: object
    params: QueryParamTypes | None
    headers: HeaderTypes | None
    cookies: CookieTypes | None
    auth: AuthTypes | UseClientDefault | None
    follow_redirects: bool | UseClientDefault
    timeout: TimeoutTypes | UseClientDefault
    extensions: RequestExtensions | None


class AsyncClientOptions(TypedDict, total=False):
    base_url: str
    timeout: TimeoutTypes
    headers: HeaderTypes
    event_hooks: dict[str, list[ResponseHook]]
    transport: httpx.AsyncBaseTransport


class ResilientClient:
    def __init__(self, config: ResilienceConfig) -> None:
        self.config = config
        self._limiter: AsyncLimiter | None = (
            AsyncLimiter(config.ratelimit.max_calls, config.ratelimit.per_seconds)
            if config.ratelimit
            else None
        )

        retry_transport = RetryTransport(retry=config.retry.build())

        storage, policy = _build_cache_components(config.cache)

        headers = dict(config.default_headers) if config.default_headers else None
        event_hooks = {"response": list(config.response_hooks)} if config.response_hooks else None

        client_kwargs: AsyncClientOptions = {
            "timeout": config.timeout_seconds,
            "transport": retry_transport,
        }
        if config.base_url is not None:
            client_kwargs["base_url"] = config.base_url
        if headers is not None:
            client_kwargs["headers"] = headers
        if event_hooks is not None:
            client_kwargs["event_hooks"] = event_hooks

        if storage is not None:
            self._client = AsyncCacheClient(**client_kwargs, storage=storage, policy=policy)
        else:
            self._client = httpx.AsyncClient(**client_kwargs)

    async def __aenter__(self) -> ResilientClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url: URLTypes,
        **kwargs: Unpack[RequestOptions],
    ) -> httpx.Response:
        async def do_request() -> httpx.Response:
            return await self._client.request(method, url, **kwargs)

        return await self._send(do_request)

    async def get(
        self,
        url: URLTypes,
        **kwargs: Unpack[RequestOptions],
    ) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(
        self,
        url: URLTypes,
        **kwargs: Unpack[RequestOptions],
    ) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def _send(self, func: Callable[[], Awaitable[httpx.Response]]) -> httpx.Response:
        if self._limiter is None:
            return await func()
        async with self._limiter:
            return await func()


class _ShouldCacheResponseFilter(BaseFilter[HishelCacheResponse]):
    """Hishel response filter that delegates to a simple JSON predicate."""

    def __init__(self, predicate: ShouldCacheHook) -> None:
        self._predicate = predicate

    def needs_body(self) -> bool:
        return True

    def apply(self, item: HishelCacheResponse, body: bytes | None) -> bool:  # noqa: ARG002
        if body is None:
            return True
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return True
        return bool(self._predicate(payload))


def _build_cache_components(
    config: CacheConfig | None,
) -> tuple[AsyncSqliteStorage | None, FilterPolicy | None]:
    if config is None or not config.enabled:
        return None, None

    if config.backend not in {"sqlite", "memory"}:
        msg = f"Unsupported cache backend: {config.backend}"
        raise ValueError(msg)

    if config.backend == "sqlite":
        database_path = config.sqlite_path or str(get_http_cache_path())
    else:
        database_path = ":memory:"
    storage = AsyncSqliteStorage(
        database_path=database_path,
        default_ttl=config.default_ttl_seconds,
        refresh_ttl_on_access=config.refresh_ttl_on_access,
    )

    policy: FilterPolicy | None = None
    if config.should_cache is not None:
        policy = FilterPolicy(response_filters=[_ShouldCacheResponseFilter(config.should_cache)])

    return storage, policy


async def http_get_resilient(
    config: ResilienceConfig,
    url: URLTypes,
    **kwargs: Unpack[RequestOptions],
) -> httpx.Response:
    client = ResilientClient(config)
    try:
        return await client.get(url, **kwargs)
    finally:
        await client.aclose()


def with_resilience[**P, T](
    config: ResilienceConfig,
) -> Callable[
    [Callable[Concatenate[ResilientClient, P], Awaitable[T]]],
    Callable[P, Awaitable[T]],
]:
    def decorator(
        func: Callable[Concatenate[ResilientClient, P], Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            client = ResilientClient(config)
            try:
                return await func(client, *args, **kwargs)
            finally:
                await client.aclose()

        return wrapper

    return decorator
