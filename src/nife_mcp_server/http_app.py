"""Hosted (remote) MCP server over Streamable HTTP.

Run:   nife-mcp-http            (or: uvicorn nife_mcp_server.http_app:app)
URL:   https://<your-host>/mcp  <- this is what users paste into "Add custom connector"

Stateless by design: every request is self-contained and authenticated by its own
Authorization header, so there is no session state that could leak one caller's
identity into another's, and the service scales horizontally behind any load balancer.
"""
import logging
import os
import sys

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from nife_mcp_server.http_auth import AuthMiddleware
from nife_mcp_server.nife_api import VERSION
from nife_mcp_server.oauth import register_oauth_routes
from nife_mcp_server.site_tools import SERVER_INSTRUCTIONS, register_site_tools

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
# httpx logs full request URLs at INFO; keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)

PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP(
    "nife",
    instructions=SERVER_INSTRUCTIONS,
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,   # no sessions: each request carries its own credentials
    json_response=True,
)
register_site_tools(mcp)
register_oauth_routes(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "nife-mcp-server", "version": VERSION})


_origins = [o.strip() for o in os.environ.get("NIFE_MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]

_authenticated_app = AuthMiddleware(
    mcp.streamable_http_app(),
    protected_prefix="/mcp",
    rate_limit_per_minute=int(os.environ.get("NIFE_MCP_RATE_LIMIT_PER_MIN", "120")),
    allowed_origins=_origins or None,
)


async def app(scope, receive, send):
    # This public ownership proof must run before auth and the MCP handler.
    if (
        scope["type"] == "http"
        and scope["method"] == "GET"
        and scope["path"] == "/mcp/.well-known/glama.json"
    ):
        response = JSONResponse({
            "$schema": "https://glama.ai/mcp/schemas/connector.json",
            "claim": "glama_claim_138g5Mc4xxNowLypLtSR9Q8SncEkCkQ9",
        })
        await response(scope, receive, send)
        return
    await _authenticated_app(scope, receive, send)


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, log_level="info")


if __name__ == "__main__":
    main()
