"""OAuth 2.1 authorization-server shim for the hosted MCP endpoint.

Why: Claude custom connectors without the "Request headers" beta cannot send a static
``Authorization`` header, so they use the MCP OAuth flow instead (discovery -> dynamic client
registration -> authorization code + PKCE -> token).

How: the user signs in through the Nife dashboard (launch.nife.io or a self-hosted URL).
After login the dashboard redirects back to /oauth/callback with the token — no CLI sessions,
no polling needed.

    Claude  ->  GET /authorize
                  page shows "Sign in to Nife" button
                  button opens LAUNCH_URL?callback=<mcp-base>/oauth/callback&state=<txn>

    User logs in on the Nife dashboard (email/password, MFA, SSO — all work)

    Dashboard  ->  redirect to /oauth/callback?token=<access_token>&state=<txn>

    /oauth/callback  ->  302 redirect_uri?code=<sealed-code>  (back to Claude)

    Claude  ->  POST /token (code + PKCE verifier)  ->  access_token = the Nife token

The access token IS the user's Nife token, so the rest of the server is unchanged.

Stateless: the client_id, the pending txn and the authorization code are Fernet-sealed blobs
(key derived from NIFE_MCP_OAUTH_SECRET), so nothing is stored server-side.
Set NIFE_MCP_OAUTH_SECRET to the same value on every replica and across restarts; if unset a
random one is generated at startup and clients must be re-added after each restart.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from html import escape
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from nife_mcp_server.http_auth import jwt_exp, public_base

log = logging.getLogger("nife_mcp.oauth")

# Dashboard login page. Must support ?callback=<url>&state=<str> params.
# After login the dashboard redirects to: <callback>?token=<access_token>&state=<state>
# Override with NIFE_MCP_LOGIN_URL to use a self-hosted dashboard or local dev server.
LAUNCH_URL = os.environ.get("NIFE_MCP_LOGIN_URL", "https://launch.nife.io/login").rstrip("/")

# Hosts allowed to receive authorization codes. Loopback http is always allowed.
# NIFE_MCP_OAUTH_REDIRECT_HOSTS="*" disables the check (not recommended).
REDIRECT_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("NIFE_MCP_OAUTH_REDIRECT_HOSTS", "claude.ai,claude.com").split(",")
    if h.strip()
}
LOOPBACK = {"localhost", "127.0.0.1", "::1"}

TXN_TTL  = 600   # seconds the user has to finish signing in
CODE_TTL = 120   # seconds an authorization code is valid
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

_secret = os.environ.get("NIFE_MCP_OAUTH_SECRET", "")
if not _secret:
    _secret = secrets.token_urlsafe(32)
    log.warning(
        "NIFE_MCP_OAUTH_SECRET is not set: using a random per-process secret. "
        "Connectors must be re-added after every restart."
    )
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(_secret.encode()).digest()))


# --------------------------------------------------------------------------- sealing
def _seal(kind: str, data: Dict[str, Any]) -> str:
    return _fernet.encrypt(json.dumps({"k": kind, **data}).encode()).decode()


def _unseal(kind: str, blob: str, ttl: Optional[int]) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(_fernet.decrypt(blob.encode(), ttl=ttl))
    except (InvalidToken, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) and data.get("k") == kind else None


# --------------------------------------------------------------------------- helpers
def _redirect_ok(uri: str) -> bool:
    try:
        u = urlsplit(uri)
    except ValueError:
        return False
    if u.fragment or not u.hostname:
        return False
    host = u.hostname.lower()
    if u.scheme == "http" and host in LOOPBACK:
        return True
    return u.scheme == "https" and ("*" in REDIRECT_HOSTS or host in REDIRECT_HOSTS)


def _with_params(uri: str, params: Dict[str, str]) -> str:
    sp = urlsplit(uri)
    query = parse_qsl(sp.query, keep_blank_values=True) + list(params.items())
    return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(query), ""))


def _base(request: Request) -> str:
    return public_base(request.headers, request.scope.get("scheme", "https"))


def _oauth_error(code: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": code, "error_description": description},
        status_code=status, headers=NO_STORE,
    )


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root{{color-scheme:light dark;--bg:#fff;--fg:#111;--mut:#666;--card:#f6f7f9;--pri:#4f46e5}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1115;--fg:#eee;--mut:#9aa0a6;--card:#181b21}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);
      color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
.card{{max-width:420px;width:100%;margin:24px;padding:32px;background:var(--card);border-radius:12px}}
h1{{font-size:20px;margin:0 0 12px}}
a.btn{{display:block;text-align:center;padding:12px;border-radius:8px;background:var(--pri);
       color:#fff;text-decoration:none;font-weight:600;margin-bottom:16px}}
.mut{{color:var(--mut);font-size:14px;margin:0}}
</style></head><body><main class="card">{body}</main></body></html>"""
    return HTMLResponse(html, status_code=status,
                        headers={**NO_STORE, "Referrer-Policy": "no-referrer"})


def _page_error(message: str, status: int = 400) -> HTMLResponse:
    return _page("Cannot connect",
                 f"<h1>Cannot connect</h1><p>{escape(message)}</p>", status)


# --------------------------------------------------------------------------- endpoints
async def protected_resource(request: Request) -> Response:
    base = _base(request)
    return JSONResponse({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    })


async def server_metadata(request: Request) -> Response:
    base = _base(request)
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    })


async def register(request: Request) -> Response:
    """Dynamic client registration (RFC 7591). Stateless: client_id seals the redirect URIs."""
    try:
        body = await request.json()
    except ValueError:
        return _oauth_error("invalid_client_metadata", "Body must be JSON")
    uris = body.get("redirect_uris") if isinstance(body, dict) else None
    if (
        not isinstance(uris, list) or not uris or len(uris) > 10
        or not all(isinstance(u, str) and _redirect_ok(u) for u in uris)
    ):
        return _oauth_error(
            "invalid_redirect_uri",
            "redirect_uris must be https URLs on an allowed host",
        )
    name = str(body.get("client_name") or "MCP client")[:80]
    return JSONResponse({
        "client_id": _seal("client", {"ru": uris, "n": name}),
        "client_name": name,
        "redirect_uris": uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, status_code=201, headers=NO_STORE)


async def authorize(request: Request) -> Response:
    """Redirect the user to the Nife dashboard login with a callback URL.
    The dashboard calls /oauth/callback after a successful login."""
    q = request.query_params
    client = _unseal("client", q.get("client_id", ""), ttl=None)
    if not client:
        return _page_error("Unknown client. Remove the connector in Claude and add it again.")
    redirect_uri = q.get("redirect_uri", "")
    if redirect_uri not in client["ru"]:
        return _page_error("redirect_uri does not match the registered client.")

    state = q.get("state", "")

    def fail(code: str, description: str) -> Response:
        params = {"error": code, "error_description": description}
        if state:
            params["state"] = state
        return Response(status_code=302,
                        headers={"Location": _with_params(redirect_uri, params)})

    if q.get("response_type") != "code":
        return fail("unsupported_response_type", "response_type must be code")
    challenge = q.get("code_challenge", "")
    if not challenge or q.get("code_challenge_method") != "S256":
        return fail("invalid_request", "PKCE with code_challenge_method=S256 is required")

    # Seal the OAuth context so we can recover it when the callback arrives
    txn = _seal("txn", {
        "cid": q["client_id"],
        "ru":  redirect_uri,
        "cc":  challenge,
        "st":  state,
    })

    # Build the callback URL using the current public base (ngrok URL etc.)
    callback_url = f"{_base(request)}/oauth/callback"

    # Send the user to the dashboard with callback + txn state
    login_url = _with_params(LAUNCH_URL, {
        "callback": callback_url,
        "state":    txn,
    })

    host = urlsplit(redirect_uri).hostname or ""
    body = (
        f"<h1>Connect to Nife</h1>"
        f"<p class=\"mut\"><b>{escape(client['n'])}</b> ({escape(host)}) "
        f"wants access to your Nife account.</p>"
        f"<a class=\"btn\" href=\"{escape(login_url)}\">Sign in to Nife</a>"
        f"<p class=\"mut\">You will be redirected back here automatically after signing in.</p>"
    )
    return _page("Connect to Nife", body)


async def callback(request: Request) -> Response:
    """The Nife dashboard redirects here after a successful login.
    Expects ?token=<nife_access_token>&state=<sealed_txn>."""
    q = request.query_params

    nife_token = (q.get("token") or "").strip()
    if not nife_token:
        return _page_error("No token received from the Nife dashboard. Please try again.")

    txn = _unseal("txn", q.get("state", ""), ttl=TXN_TTL)
    if not txn:
        return _page_error("Sign-in expired or invalid state. Go back to Claude and connect again.")

    redirect_uri = txn["ru"]
    state        = txn["st"]

    code = _seal("code", {
        "tok": nife_token,
        "cid": txn["cid"],
        "ru":  redirect_uri,
        "cc":  txn["cc"],
    })
    params: Dict[str, str] = {"code": code}
    if state:
        params["state"] = state

    return Response(
        status_code=302,
        headers={"Location": _with_params(redirect_uri, params), **NO_STORE},
    )


async def token(request: Request) -> Response:
    form = {
        k: v[0]
        for k, v in parse_qs((await request.body()).decode("utf-8", "replace")).items()
    }
    if form.get("grant_type") != "authorization_code":
        return _oauth_error("unsupported_grant_type", "Only authorization_code is supported")
    code = _unseal("code", form.get("code", ""), ttl=CODE_TTL)
    if (
        not code
        or form.get("client_id")    != code["cid"]
        or form.get("redirect_uri") != code["ru"]
    ):
        return _oauth_error("invalid_grant",
                            "Invalid, expired or mismatched authorization code")
    verifier = form.get("code_verifier", "")
    computed = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=").decode()
    )
    if not 43 <= len(verifier) <= 128 or not hmac.compare_digest(computed, code["cc"]):
        return _oauth_error("invalid_grant", "PKCE verification failed")

    body: Dict[str, Any] = {
        "access_token": code["tok"],
        "token_type":   "Bearer",
        "scope":        "mcp",
    }
    exp = jwt_exp(code["tok"])
    if exp is not None and exp > time.time():
        body["expires_in"] = int(exp - time.time())
    return JSONResponse(body, headers=NO_STORE)


# --------------------------------------------------------------------------- wiring
def register_oauth_routes(mcp) -> None:
    """Mount the OAuth endpoints on the FastMCP app (all outside the protected /mcp prefix)."""
    route = mcp.custom_route
    route("/.well-known/oauth-protected-resource",     methods=["GET"])(protected_resource)
    route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])(protected_resource)
    route("/.well-known/oauth-authorization-server",   methods=["GET"])(server_metadata)
    route("/register",      methods=["POST"])(register)
    route("/authorize",     methods=["GET"])(authorize)
    route("/oauth/callback", methods=["GET"])(callback)
    route("/token",         methods=["POST"])(token)
