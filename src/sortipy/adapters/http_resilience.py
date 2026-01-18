from __future__ import annotations

import json
from typing import (
    TYPE_CHECKING,
    Concatenate,
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

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
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

    from sortipy.config.http_resilience import (
        CacheConfig,
        ResilienceConfig,
        ResponseHook,
        RetryPolicy,
        ShouldCacheHook,
    )


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

        retry_transport = RetryTransport(retry=_build_retry(config.retry))

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
        if config.sqlite_path is None:
            raise ValueError("sqlite cache backend requires sqlite_path")
        database_path = config.sqlite_path
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


def _build_retry(policy: RetryPolicy) -> Retry:
    retry_policy = policy
    return Retry(
        total=retry_policy.total,
        backoff_factor=retry_policy.backoff_factor,
        max_backoff_wait=retry_policy.max_backoff_wait,
        respect_retry_after_header=retry_policy.respect_retry_after_header,
        allowed_methods=tuple(retry_policy.allowed_methods),
        status_forcelist=tuple(retry_policy.status_forcelist),
        retry_on_exceptions=retry_policy.retry_on_exceptions,
        backoff_jitter=retry_policy.backoff_jitter,
    )


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
