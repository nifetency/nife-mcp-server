#!/usr/bin/env python3
"""
OAuth 2.1 facade so Claude can log users in to Nife.

Claude speaks standard MCP-OAuth (discovery, dynamic client registration,
authorization code + PKCE). Nife's login is a "CLI session" flow:

    POST {API}/api/v1/cli_sessions          -> {id}
    user opens {DASHBOARD}/login?id=<id>    -> signs in on Nife's own page
    GET  {API}/api/v1/cli_sessions/<id>     -> {access_token, email} when done

This module bridges the two. The MCP server stores NOTHING per user:
  * client_id        = signed blob (redirect URIs)
  * login transaction= signed blob (Nife session id, PKCE challenge, ...)
  * authorization code = encrypted blob (contains the Nife token, 2 min TTL)
  * access token     = the user's own Nife token (passed through)

Secrets: set MCP_SECRET (same value on every replica / across restarts).
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, jsonify, render_template_string, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger("nife_mcp_oauth")

oauth_bp = Blueprint("oauth", __name__)

NIFE_API_BASE = os.environ.get("NIFE_API_BASE", "https://api.nife.io").rstrip("/")
NIFE_DASHBOARD_URL = os.environ.get("NIFE_DASHBOARD_URL", "https://launch.nife.io").rstrip("/")
ALLOWED_REDIRECT_HOSTS = [
    h.strip().lower()
    for h in os.environ.get("ALLOWED_REDIRECT_HOSTS", "claude.ai,claude.com,localhost,127.0.0.1").split(",")
    if h.strip()
]
LOGIN_TXN_MAX_AGE = 15 * 60   # user has 15 minutes to sign in
AUTH_CODE_TTL = 120           # seconds an authorization code is valid

_secret = os.environ.get("MCP_SECRET")
if not _secret:
    _secret = secrets.token_urlsafe(32)
    logger.warning(
        "MCP_SECRET not set: using a random one. Logins in progress and registered "
        "clients are invalidated on restart. Set MCP_SECRET in production."
    )
_signer = URLSafeTimedSerializer(_secret)
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(_secret.encode()).digest()))


# ----------------------------------------------------------------------
# Helpers (also used by http_server.py)
# ----------------------------------------------------------------------
def public_url() -> str:
    """The externally reachable https URL of this server."""
    env = os.environ.get("PUBLIC_URL")
    if env:
        return env.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{proto}://{host}"


def _jwt_exp(token: str) -> Optional[int]:
    """Read the 'exp' claim if the token is a JWT (signature NOT verified;
    Nife's API is the real authority, this is only an expiry hint)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        return int(exp) if exp else None
    except Exception:
        return None


def token_expired(token: str) -> bool:
    exp = _jwt_exp(token)
    return exp is not None and exp <= time.time()


_AUTH_FAIL_HINTS = ("401", "unauthor", "unauthenticated", "not authenticated",
                    "expired", "invalid token", "jwt", "forbidden")


def nife_rejects_token(token: str) -> bool:
    """True only if Nife clearly says the token is bad (not on network errors)."""
    from nife_mcp_server.client import NifeGraphQLClient
    result = NifeGraphQLClient(token).execute_query("query { currentUser { email } }", timeout=10)
    errors = result.get("errors") if isinstance(result, dict) else None
    if not errors:
        return False
    text = json.dumps(errors).lower()
    return any(hint in text for hint in _AUTH_FAIL_HINTS)


def _redirect_allowed(uri: str) -> bool:
    try:
        parsed = urlparse(uri)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host in ("localhost", "127.0.0.1"):
        return True
    if parsed.scheme != "https":
        return False
    return any(host == h or host.endswith("." + h) for h in ALLOWED_REDIRECT_HOSTS)


def _add_params(uri: str, params: Dict[str, str]) -> str:
    params = {k: v for k, v in params.items() if v is not None}
    return uri + ("&" if "?" in uri else "?") + urlencode(params)


def _oauth_error(error: str, description: str, status: int = 400):
    resp = jsonify({"error": error, "error_description": description})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _error_page(message: str, status: int = 400):
    html = render_template_string(
        "<!doctype html><meta charset=utf-8><title>Nife login</title>"
        "<body style='font-family:system-ui;max-width:480px;margin:80px auto;padding:0 16px'>"
        "<h2>Can't continue</h2><p>{{ m }}</p></body>", m=message)
    return html, status


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------
@oauth_bp.get("/.well-known/oauth-protected-resource")
@oauth_bp.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource():
    base = public_url()
    return jsonify({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
    })


@oauth_bp.get("/.well-known/oauth-authorization-server")
@oauth_bp.get("/.well-known/oauth-authorization-server/mcp")
def authorization_server_metadata():
    base = public_url()
    return jsonify({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    })


# ----------------------------------------------------------------------
# Dynamic client registration (stateless)
# ----------------------------------------------------------------------
@oauth_bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    redirect_uris = body.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        return _oauth_error("invalid_redirect_uri", "redirect_uris is required")
    for uri in redirect_uris:
        if not isinstance(uri, str) or not _redirect_allowed(uri):
            return _oauth_error("invalid_redirect_uri", f"redirect_uri not allowed: {uri}")

    client_id = _signer.dumps({"r": redirect_uris}, salt="client")
    resp = jsonify({
        "client_id": client_id,
        "client_name": body.get("client_name", "MCP client"),
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })
    resp.status_code = 201
    return resp


def _load_client(client_id: str) -> Optional[Dict[str, Any]]:
    try:
        return _signer.loads(client_id, salt="client")
    except (BadSignature, SignatureExpired):
        return None


# ----------------------------------------------------------------------
# Authorization: bridge to Nife's CLI-session login
# ----------------------------------------------------------------------
_AUTHORIZE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect Claude to Nife</title>
<style>
 :root{color-scheme:light dark}
 body{font-family:system-ui,sans-serif;max-width:460px;margin:12vh auto;padding:0 20px;text-align:center}
 .btn{display:inline-block;padding:12px 22px;border-radius:8px;background:#2563eb;color:#fff;text-decoration:none;font-weight:600}
 .muted{opacity:.7;font-size:14px}
</style></head>
<body>
<div id="app" data-txn="{{ txn }}" data-login="{{ login_url }}">
 <h2>Connect Claude to Nife</h2>
 <p>Sign in to your Nife account in the new tab. This page continues automatically afterwards.</p>
 <p><a class="btn" id="open" href="{{ login_url }}" target="_blank" rel="noopener">Sign in to Nife</a></p>
 <p id="status" class="muted">Waiting for you to sign in…</p>
 <p class="muted">Signed in with Google, GitHub or another provider and nothing happened?
  <a href="{{ login_url }}" target="_blank" rel="noopener">Click here once more</a> to finish connecting.</p>
 <p class="muted"><a href="{{ cancel_url }}">Cancel</a></p>
</div>
<script>
 var app = document.getElementById('app');
 var txn = app.dataset.txn, loginUrl = app.dataset.login;
 var statusEl = document.getElementById('status');
 try { window.open(loginUrl, '_blank'); } catch (e) {}
 function poll() {
   fetch('/authorize/poll?txn=' + encodeURIComponent(txn))
     .then(function (r) { return r.json(); })
     .then(function (d) {
       if (d.status === 'done') {
         statusEl.textContent = 'Signed in. Returning to Claude…';
         window.location.href = d.redirect;
       } else if (d.status === 'error') {
         statusEl.textContent = d.message;
       } else { setTimeout(poll, 2000); }
     })
     .catch(function () { setTimeout(poll, 3000); });
 }
 poll();
</script></body></html>"""


@oauth_bp.get("/authorize")
def authorize():
    args = request.args
    client = _load_client(args.get("client_id", ""))
    redirect_uri = args.get("redirect_uri", "")
    if not client:
        return _error_page("Unknown client. Remove and re-add the connector in Claude.")
    if redirect_uri not in client.get("r", []):
        return _error_page("redirect_uri does not match the registered client.")

    state = args.get("state")
    if args.get("response_type") != "code":
        return _bounce(redirect_uri, state, "unsupported_response_type")
    challenge = args.get("code_challenge")
    if not challenge or args.get("code_challenge_method") != "S256":
        return _bounce(redirect_uri, state, "invalid_request", "PKCE (S256) is required")

    # 1. Create a Nife login session
    resp = None
    try:
        resp = requests.post(
            f"{NIFE_API_BASE}/api/v1/cli_sessions",
            json={"name": "Claude (MCP)", "signup": False},
            timeout=15,
        )
        session_id = resp.json().get("id") if resp.status_code == 201 else None
    except Exception as exc:
        logger.error(f"Could not create Nife login session at {NIFE_API_BASE}: {type(exc).__name__}")
        session_id = None
    if not session_id:
        logger.error(f"Nife cli_sessions create failed (status={getattr(resp, 'status_code', 'n/a')}) at {NIFE_API_BASE}")
        return _error_page("Could not start a Nife login session. Please try again later.", 502)

    txn = _signer.dumps({
        "sid": session_id,
        "cid": args.get("client_id"),
        "ru": redirect_uri,
        "st": state,
        "cc": challenge,
    }, salt="txn")

    login_url = f"{NIFE_DASHBOARD_URL}/login?id={session_id}"
    cancel_url = _add_params(redirect_uri, {"error": "access_denied", "state": state})
    return render_template_string(_AUTHORIZE_PAGE, txn=txn, login_url=login_url, cancel_url=cancel_url)


def _bounce(redirect_uri: str, state: Optional[str], error: str, description: str = ""):
    from flask import redirect
    return redirect(_add_params(redirect_uri, {"error": error, "error_description": description or None, "state": state}))


@oauth_bp.get("/authorize/poll")
def authorize_poll():
    try:
        txn = _signer.loads(request.args.get("txn", ""), salt="txn", max_age=LOGIN_TXN_MAX_AGE)
    except SignatureExpired:
        return jsonify({"status": "error", "message": "Login expired. Please start again from Claude."})
    except BadSignature:
        return jsonify({"status": "error", "message": "Invalid login request."}), 400

    try:
        resp = requests.get(f"{NIFE_API_BASE}/api/v1/cli_sessions/{txn['sid']}", timeout=10)
        if resp.status_code == 404:
            return jsonify({"status": "error",
                            "message": "This login session no longer exists. Please start again from Claude."})
        if resp.status_code != 200:
            logger.warning(f"cli_sessions poll returned HTTP {resp.status_code} from {NIFE_API_BASE}")
            data = {}
        else:
            data = resp.json()
    except Exception as exc:
        logger.warning(f"cli_sessions poll failed: {type(exc).__name__}")
        data = {}

    access_token = data.get("access_token")
    if not access_token:
        return jsonify({"status": "pending"})

    code = _fernet.encrypt(json.dumps({
        "at": access_token,
        "cc": txn["cc"],
        "cid": txn["cid"],
        "ru": txn["ru"],
    }).encode()).decode()

    return jsonify({
        "status": "done",
        "redirect": _add_params(txn["ru"], {"code": code, "state": txn.get("st")}),
    })


# ----------------------------------------------------------------------
# Token endpoint
# ----------------------------------------------------------------------
@oauth_bp.post("/token")
def token():
    form = request.form if request.form else (request.get_json(silent=True) or {})

    if form.get("grant_type") != "authorization_code":
        return _oauth_error("unsupported_grant_type", "Only authorization_code is supported")

    try:
        payload = json.loads(_fernet.decrypt(form.get("code", "").encode(), ttl=AUTH_CODE_TTL))
    except (InvalidToken, ValueError):
        return _oauth_error("invalid_grant", "Invalid or expired code")

    if form.get("client_id") != payload["cid"] or form.get("redirect_uri") != payload["ru"]:
        return _oauth_error("invalid_grant", "client_id or redirect_uri mismatch")

    verifier = form.get("code_verifier", "")
    computed = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    if not verifier or not secrets.compare_digest(computed, payload["cc"]):
        return _oauth_error("invalid_grant", "PKCE verification failed")

    access_token = payload["at"]
    body: Dict[str, Any] = {"access_token": access_token, "token_type": "Bearer"}
    exp = _jwt_exp(access_token)
    if exp:
        body["expires_in"] = max(60, int(exp - time.time()))

    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp
