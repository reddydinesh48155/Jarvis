"""Security middleware: secure headers and in-memory rate limiting."""

from __future__ import annotations

import time
import logging
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger("nova.middleware.security")


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every HTTP response."""

    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        response = await call_next(request)
        for key, value in self.HEADERS.items():
            response.headers[key] = value
        if settings.environment != "development":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory token-bucket rate limiter per client IP.

    Uses separate limits for auth endpoints vs general API.
    No Redis dependency — suitable for single-node deployment.
    """

    def __init__(self, app: object, **kwargs: object) -> None:
        super().__init__(app, **kwargs)  # type: ignore[arg-type]
        # {ip: [(timestamp, count)]}
        self._auth_buckets: dict[str, list[float]] = defaultdict(list)
        self._api_buckets: dict[str, list[float]] = defaultdict(list)

    def reset(self) -> None:
        """Clear all rate-limit buckets (used for testing)."""
        self._auth_buckets.clear()
        self._api_buckets.clear()

    def _check_rate(self, bucket: list[float], limit: int, window: float = 60.0) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        now = time.monotonic()
        # Purge entries older than the window
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        if path.startswith("/auth/"):
            if not self._check_rate(self._auth_buckets[client_ip], settings.rate_limit_auth_per_minute):
                logger.warning("rate limit exceeded for %s on auth endpoint", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                )
        else:
            if not self._check_rate(self._api_buckets[client_ip], settings.rate_limit_api_per_minute):
                logger.warning("rate limit exceeded for %s on API endpoint", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                )

        return await call_next(request)

