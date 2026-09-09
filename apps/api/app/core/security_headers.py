"""Baseline security response headers. Conservative defaults that do not
assume anything about the frontend's own CSP needs beyond "this API serves
JSON, never HTML" -- if a future endpoint serves HTML this policy should be
revisited. HSTS is only added in production: this process cannot itself
verify that HTTPS is actually terminated in front of it (that is a reverse
proxy/load balancer concern), so it is opt-in via SAFEOPS_ENV rather than
unconditional, to avoid telling browsers to force HTTPS on a deployment
that does not actually serve it.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in _BASE_HEADERS.items():
            response.headers.setdefault(key, value)
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response
