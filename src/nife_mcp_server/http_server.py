#!/usr/bin/env python3
"""
Multi-user HTTP (Streamable HTTP) transport for the Nife MCP server.

Identity per request:

  1. OAuth / header mode (default, secure):
         Authorization: Bearer <user's Nife token>
     Claude obtains the token by sending the user through Nife's login page
     (see oauth.py) and then sends it on every request. A missing, expired or
     Nife-rejected token gets HTTP 401, which makes Claude start the login.

  2. Chat-token mode (ALLOW_CHAT_TOKEN=true, testing only): the user pastes a
     token in chat and Claude passes it as the `access_token` tool argument.
     Do NOT combine with OAuth: with no header it skips the 401 login.

There is NO shared/fallback identity. The GraphQL schema is shared (same for
everyone) and loaded once.
"""
import asyncio
import copy
import json
import logging
import os
import sys
import threading
from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

# Safety: never let a shared env token act as a fallback identity for users.
os.environ.pop("NIFE_ACCESS_TOKEN", None)

from nife_mcp_server.intelligent_main import IntelligentNifeMCPServer  # noqa: E402
from nife_mcp_server.oauth import (  # noqa: E402
    nife_rejects_token,
    oauth_bp,
    public_url,
    token_expired,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("nife_mcp_http")

SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]
ALLOW_CHAT_TOKEN = os.environ.get("ALLOW_CHAT_TOKEN", "false").lower() == "true"
# Optional token used ONLY to download the schema (never used for user requests)
SCHEMA_TOKEN = os.environ.get("NIFE_SCHEMA_TOKEN")

app = Flask(__name__)
app.register_blueprint(oauth_bp)
CORS(
    app,
    resources={
        r"/.well-known/*": {"origins": "*"},
        r"/register": {"origins": "*"},
        r"/token": {"origins": "*"},
        r"/mcp": {"origins": "*"},
    },
    expose_headers=["WWW-Authenticate"],
)

server = IntelligentNifeMCPServer()
_init_lock = threading.Lock()

if ALLOW_CHAT_TOKEN:
    logger.warning("ALLOW_CHAT_TOKEN=true: users may paste tokens into chat (less secure, disables OAuth 401)")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _bearer_token() -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def _unauthorized(invalid_token: bool = False) -> Response:
    """401 that tells MCP clients where to start the OAuth login."""
    resp = jsonify({"error": "unauthorized",
                    "message": "Login required. Please sign in to Nife."})
    resp.status_code = 401
    parts = ['Bearer realm="nife-mcp"']
    if invalid_token:
        parts.append('error="invalid_token"')
    parts.append(f'resource_metadata="{public_url()}/.well-known/oauth-protected-resource"')
    resp.headers["WWW-Authenticate"] = ", ".join(parts)
    return resp


def _ensure_ready(token: Optional[str]) -> bool:
    """Load the shared schema once. Uses NIFE_SCHEMA_TOKEN, else the first
    caller's token (if any). That token is not kept afterwards."""
    if server.ready:
        return True
    with _init_lock:
        if server.ready:
            return True
        server.schema_manager.access_token = SCHEMA_TOKEN or token
        try:
            asyncio.run(server.initialize())
        finally:
            server.schema_manager.access_token = None
        return server.ready


def _public_tools(tools: list, header_mode: bool) -> list:
    """Header mode: hide access_token (identity comes from the header).
    Chat mode: keep it and make it required so Claude asks the user for it."""
    cleaned = []
    for tool in tools:
        tool = copy.deepcopy(tool)
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})
        if "access_token" in props:
            if header_mode:
                props.pop("access_token", None)
                schema["required"] = [r for r in schema.get("required", []) if r != "access_token"]
            else:
                props["access_token"]["description"] = (
                    "The user's own Nife access token (from `nifectl auth token`). "
                    "Ask the user for it once, then reuse it for every call in this conversation."
                )
                required = schema.setdefault("required", [])
                if "access_token" not in required:
                    required.append("access_token")
        cleaned.append(tool)
    return cleaned


def _tool_error(msg_id, text: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id,
            "result": {"isError": True,
                       "content": [{"type": "text", "text": json.dumps({"error": text})}]}}


def _handle_message(msg: Dict[str, Any], header_token: Optional[str]) -> Optional[Dict[str, Any]]:
    method = msg.get("method")
    params = msg.get("params") or {}
    msg_id = msg.get("id")

    if method and method.startswith("notifications/"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/call":
        arguments = dict(params.get("arguments") or {})
        if header_token:
            # Header identity always wins over anything the model sent.
            arguments["access_token"] = header_token
        else:
            chat_token = arguments.get("access_token")
            if not (ALLOW_CHAT_TOKEN and chat_token):
                return _tool_error(msg_id, "Access token required. Please sign in to Nife.")
        msg = {**msg, "params": {**params, "arguments": arguments}}

    response = asyncio.run(server.handle_request(msg))
    if response is None:
        return None

    if method == "initialize" and "result" in response:
        requested = params.get("protocolVersion")
        response["result"]["protocolVersion"] = (
            requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[1]
        )
    elif method == "tools/list" and "result" in response:
        response["result"]["tools"] = _public_tools(
            response["result"]["tools"], header_mode=bool(header_token)
        )
    return response


# ----------------------------------------------------------------------
# Routes (OAuth discovery/login routes live in oauth.py)
# ----------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok", "schema_loaded": server.ready,
                    "chat_token_mode": ALLOW_CHAT_TOKEN})


@app.post("/mcp")
def mcp_post():
    header_token = _bearer_token()
    if not header_token and not ALLOW_CHAT_TOKEN:
        return _unauthorized()
    if header_token and token_expired(header_token):
        return _unauthorized(invalid_token=True)

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "Parse error"}}), 400

    # On connect, ask Nife once whether the token is still good; if not,
    # 401 makes Claude send the user through login again.
    if header_token and isinstance(body, dict) and body.get("method") == "initialize":
        if nife_rejects_token(header_token):
            return _unauthorized(invalid_token=True)

    if not _ensure_ready(header_token):
        msg_id = body.get("id") if isinstance(body, dict) else None
        return jsonify({"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32603,
                                  "message": "Could not load Nife schema. Set NIFE_SCHEMA_TOKEN or check api.nife.io access."}}), 503

    try:
        if isinstance(body, list):
            responses = [r for r in (_handle_message(m, header_token) for m in body) if r is not None]
            return (jsonify(responses), 200) if responses else ("", 202)

        response = _handle_message(body, header_token)
        if response is None:
            return "", 202
        return jsonify(response)
    except Exception as exc:  # never leak stack traces or tokens
        logger.error(f"Unhandled error: {type(exc).__name__}: {exc}")
        return jsonify({"jsonrpc": "2.0",
                        "id": body.get("id") if isinstance(body, dict) else None,
                        "error": {"code": -32603, "message": "Internal error"}}), 500


@app.route("/mcp", methods=["GET", "DELETE"])
def mcp_unsupported():
    resp = Response("", status=405)
    resp.headers["Allow"] = "POST"
    return resp


def run():
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    run()
