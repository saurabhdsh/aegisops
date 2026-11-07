"""ASGI middleware. Pure ASGI keeps server-sent events streaming."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse

from aegisops.core.identifiers import new_id
from aegisops.observability.tracing import correlation_id

_EXEMPT = {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}


class CorrelationMiddleware:
    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        incoming = headers.get("x-correlation-id") or new_id("cor")
        scope.setdefault("state", {})["correlation_id"] = incoming
        token = correlation_id.set(incoming)

        async def send_with_id(message) -> None:  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-correlation-id", incoming.encode("ascii"))
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            correlation_id.reset(token)


class SecurityHeadersMiddleware:
    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                ]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    def __init__(self, app, limit: int, window_seconds: float = 60.0) -> None:  # type: ignore[no-untyped-def]
        self.app = app
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http" or self.limit <= 0:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in _EXEMPT:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = client[0] if client else "unknown"
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            correlation = scope.get("state", {}).get("correlation_id")
            response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                        "correlation_id": correlation,
                        "details": {},
                    }
                },
            )
            await response(scope, receive, send)
            return
        bucket.append(now)
        await self.app(scope, receive, send)
