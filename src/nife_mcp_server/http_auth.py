"""ASGI middleware that guards the hosted MCP endpoint.

* Requires ``Authorization: Bearer <token>`` on every /mcp request (401 otherwise).
  The token is NOT validated here: it is forwarded to the Nife backend, which is
  the single source of truth for who the caller is and what they may do.
* Per-token rate limiting (keyed on a hash, so the raw token is never stored).
* Request size cap and optional Origin allow-list.
* Never logs the Authorization header.

The in-memory rate limiter is per process. With several replicas, either accept
a per-replica limit or enforce limits at the ingress/gateway.
"""
import base64
import hashlib
import json
import os
import time
from collections import deque
from typing import Deque, Dict, Iterable, Optional

from starlette.responses import JSONResponse

MAX_TOKEN_LEN = 4096

# Public base URL of this server (e.g. https://mcp.nife.io). Optional: when unset it is
# derived from the request's Host / X-Forwarded-* headers.
PUBLIC_URL = os.environ.get("NIFE_MCP_PUBLIC_URL", "").rstrip("/")


def public_base(headers, scheme: str = "https") -> str:
    """Externally visible base URL; ``headers`` is any lowercase-keyed mapping with .get()."""
    if PUBLIC_URL:
        return PUBLIC_URL
    proto = (headers.get("x-forwarded-proto") or scheme).split(",")[0].strip()
    host = (headers.get("x-forwarded-host") or headers.get("host") or "localhost").split(",")[0].strip()
    return f"{proto}://{host}"


def jwt_exp(token: str) -> Optional[float]:
    """``exp`` claim of a JWT, read WITHOUT verifying it. None if not a JWT or no exp.
    Only used to turn an already-expired token into a clean 401 so the client re-authorizes."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


def _expired(token: str) -> bool:
    exp = jwt_exp(token)
    return exp is not None and exp <= time.time()


def _extract_bearer(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parts = value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token or len(token) > MAX_TOKEN_LEN:
        return None
    return token


class AuthMiddleware:
    def __init__(
        self,
        app,
        *,
        protected_prefix: str = "/mcp",
        rate_limit_per_minute: int = 120,
        max_body_bytes: int = 2_000_000,
        allowed_origins: Optional[Iterable[str]] = None,
    ):
        self.app = app
        self.prefix = protected_prefix
        self.limit = rate_limit_per_minute
        self.max_body = max_body_bytes
        self.allowed_origins = {o.rstrip("/") for o in allowed_origins} if allowed_origins else None
        self._hits: Dict[str, Deque[float]] = {}

    # ------------------------------------------------------------------ utils
    def _rate_limited(self, token: str) -> bool:
        if self.limit <= 0:
            return False
        key = hashlib.sha256(token.encode()).hexdigest()
        now = time.monotonic()
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            return True
        window.append(now)
        if len(self._hits) > 10_000:  # bound memory
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
                self._hits.pop(k, None)
        return False

    @staticmethod
    def _error(status: int, message: str, headers: Optional[dict] = None) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status, headers=headers)

    @staticmethod
    def _challenge(headers, scope) -> dict:
        meta = f"{public_base(headers, scope.get('scheme', 'http'))}/.well-known/oauth-protected-resource"
        value = f'Bearer realm="nife-mcp", resource_metadata="{meta}"'
        if _extract_bearer(headers.get("authorization")) is not None:
            value += ', error="invalid_token", error_description="The access token expired"'
        return {"WWW-Authenticate": value}

    # ------------------------------------------------------------------- asgi
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        origin = headers.get("origin")
        if origin and self.allowed_origins is not None and origin.rstrip("/") not in self.allowed_origins:
            await self._error(403, "Origin not allowed")(scope, receive, send)
            return

        token = _extract_bearer(headers.get("authorization"))
        if token is None or _expired(token):
            resp = self._error(
                401,
                "Missing or malformed Authorization header. Send 'Authorization: Bearer <token>'.",
                self._challenge(headers, scope),
            )
            await resp(scope, receive, send)
            return

        try:
            if int(headers.get("content-length", "0")) > self.max_body:
                await self._error(413, "Request body too large")(scope, receive, send)
                return
        except ValueError:
            await self._error(400, "Invalid Content-Length")(scope, receive, send)
            return

        if self._rate_limited(token):
            await self._error(429, "Rate limit exceeded", {"Retry-After": "30"})(scope, receive, send)
            return

        await self.app(scope, receive, send)
