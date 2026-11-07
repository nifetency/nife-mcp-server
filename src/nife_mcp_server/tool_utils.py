"""Small helpers shared by the MCP tool modules."""
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from nife_mcp_server import site_helpers as h
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError

# Explicit hints on all four flags: directory reviewers (and MCP clients) should not
# have to rely on spec defaults.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
WRITE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
# Replaces live content or removes data: clients should ask the user first.
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
)


def get_api(ctx: Context) -> NifeAPI:
    """Build a per-request client from the caller's Authorization header."""
    request = getattr(ctx.request_context, "request", None)
    auth = request.headers.get("authorization") if request is not None else None
    if not auth:
        raise ToolError("Missing Authorization header on the MCP connection.")
    return NifeAPI(auth)


def fail(exc: Exception) -> ToolError:
    return ToolError(str(exc))


async def require_org(api: NifeAPI, organization_id: str) -> Dict[str, Any]:
    """Prove the caller belongs to the organization before an org-keyed query is made.

    Several SRE queries take a bare orgId, so the id is checked against the caller's own
    organization list (a GraphQL call made with the caller's token) first.
    """
    for org in await api.organizations():
        if org.get("id") == organization_id:
            return org
    raise NifeAPIError("Unknown organization_id. Use list_organizations to see your organizations.")


async def site_or_none(api: NifeAPI, name: str) -> Optional[Dict[str, Any]]:
    """Look a site up by name. A 'not found' style backend error means None, but an
    authentication failure is never swallowed."""
    try:
        return await api.site(name)
    except NifeAPIError as exc:
        if "rejected the access token" in str(exc) or "timed out" in str(exc) or "Could not reach" in str(exc):
            raise
        return None


async def require_site(api: NifeAPI, name: str) -> Dict[str, Any]:
    """Validate the name and prove the caller can see the site.

    The lookup is made with the caller's own token, so it doubles as the
    ownership check that must precede any host- or name-keyed endpoint
    (traffic, uptime, domains).
    """
    h.validate_site_name(name)
    site = await site_or_none(api, name)
    if not site:
        raise NifeAPIError(f"No site named '{name}' was found. Use list_sites to see your sites.")
    return site
