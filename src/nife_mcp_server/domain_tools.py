"""Custom-domain tools for static sites and container apps (hosted MCP server).

Curated tools over the same backend calls the dashboard's Domains tabs make. Every tool first
loads the site or app with the caller's own token, which doubles as the ownership check before
any host- or name-keyed endpoint is used.
"""
import logging
from typing import Annotated, Any, Dict, Literal, Optional, Tuple

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server import domain_helpers as d
from nife_mcp_server import site_helpers as h
from nife_mcp_server.app_tools import _require_app
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.site_tools import _not_suspended
from nife_mcp_server.tool_utils import DESTRUCTIVE, READ_ONLY, WRITE, fail, get_api, require_site

logger = logging.getLogger(__name__)

DOMAIN_INSTRUCTIONS = """\

CUSTOM DOMAINS (sites and container apps)
- Each site or app can have ONE custom domain. get_site_custom_domain / get_app_custom_domain show
  the current one and its DNS/SSL state.
- ORDER MATTERS: the user must create the CNAME record at their DNS provider FIRST. Call
  get_domain_dns_instructions to give them the exact record, wait until they confirm it is
  created, then call add_site_custom_domain or add_app_custom_domain.
- add_app_custom_domain performs every step itself (load balancer lookup, DNS sync, ingress rule).
  If the ingress step fails the domain is saved but not serving: call it again with the same domain
  to retry. Do not chain lower-level calls.
- remove_site_custom_domain and remove_app_custom_domain stop the domain serving traffic: confirm
  with the user and pass the domain name as confirm_domain.
- DNS can take up to 24 hours to propagate; a domain that is saved but not yet reachable is normal.
"""


async def _app_domain(api: NifeAPI, app: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    """The app's custom-domain record and the key it was found under.

    The backend has used both the app id and the app name as the key, so both are tried;
    deletion then uses whichever key actually matched.
    """
    for key in dict.fromkeys(k for k in (app.get("id"), app.get("name")) if k):
        status = await api.app_domain_status(key)
        if status.get("exists") and status.get("domain"):
            return key, status
    return None, {"exists": False}


def register_domain_tools(mcp: FastMCP) -> None:
    # ----------------------------------------------------------------- guidance
    @mcp.tool(annotations=READ_ONLY, title="Get domain DNS instructions")
    async def get_domain_dns_instructions(
        resource_type: Annotated[Literal["site", "app"], Field(description="'site' for a static site, 'app' for a container app")],
        resource_name: Annotated[str, Field(description="Name of the site or app")],
        domain: Annotated[str, Field(description="The custom domain, e.g. 'www.example.com'")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """The DNS record the user must create at their DNS provider BEFORE adding a custom domain:
        a CNAME from the domain to <name>.on.nifetency.com. Makes no changes."""
        api = get_api(ctx)
        try:
            clean = d.validate_domain(domain)
            if resource_type == "site":
                await require_site(api, resource_name)
            else:
                await _require_app(api, resource_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return d.dns_instructions(resource_type, resource_name, clean)

    # --------------------------------------------------------------------- apps
    @mcp.tool(annotations=READ_ONLY, title="Get app custom domain")
    async def get_app_custom_domain(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Custom domain configured for a container app (if any): whether DNS is synced and the
        SSL state. For static sites use get_site_custom_domain."""
        api = get_api(ctx)
        try:
            app = await _require_app(api, app_name)
            _, status = await _app_domain(api, app)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "app_name": app_name,
            "default_url": app.get("appUrl") or app.get("hostname"),
            "cname_target": d.cname_target(app_name),
            **d.app_domain_view(status),
        }

    @mcp.tool(annotations=WRITE, title="Add app custom domain")
    async def add_app_custom_domain(
        app_name: Annotated[str, Field(description="Name of the EXISTING app")],
        domain: Annotated[str, Field(description="Custom domain to attach, e.g. 'app.example.com'")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Attach a custom domain to a container app: look up the load balancer, sync the DNS record
        and add the ingress rule, in one call. The user must already have created the CNAME record
        (see get_domain_dns_instructions). An app has one custom domain; remove the old one first
        to change it. If the ingress step fails, the domain is saved but not serving: call this tool
        again with the same domain to retry. Follow with get_app_custom_domain."""
        api = get_api(ctx)
        stage = "validating the request"
        try:
            clean = d.validate_domain(domain)
            app = await _require_app(api, app_name)
            _, existing = await _app_domain(api, app)
            current = existing.get("domain") if existing.get("exists") else None
            if current and not d.same_domain(current, clean):
                raise ValueError(
                    f"'{app_name}' already has the custom domain '{current}'. "
                    "Remove it with remove_app_custom_domain before adding another."
                )
            resumed = bool(current)

            if not resumed:
                stage = "looking up the app's load balancer"
                elb = await api.elb_url(app_name)
                stage = "syncing the DNS record"
                await api.sync_dns_app(clean, elb, app_name)

            stage = "adding the ingress rule"
            try:
                info = await api.app_ingress_info(app_name)
                rule = await api.add_ingress_rule(
                    app_name=app_name,
                    namespace=d.namespace_for(info.get("organization")),
                    hosts=[clean],
                    service_name=f"{app_name}-service",
                    service_port=d.service_port((info.get("config") or {}).get("definition")),
                )
                if not rule.get("success"):
                    raise NifeAPIError(rule.get("message") or "The backend did not confirm the ingress rule.")
            except NifeAPIError as exc:
                logger.info("add_app_custom_domain: ingress failed app=%s", app_name)
                return {
                    "app_name": app_name, "domain": clean,
                    "domain_saved": True, "ingress_configured": False, "error": str(exc),
                    "next_step": "The domain is saved but not serving yet. Call add_app_custom_domain again "
                                 "with the same domain to retry the ingress step.",
                }
        except (ValueError, NifeAPIError) as exc:
            if stage != "validating the request" and isinstance(exc, NifeAPIError):
                raise fail(NifeAPIError(f"Failed while {stage}: {exc}"))
            raise fail(exc)
        logger.info("add_app_custom_domain: app=%s resumed=%s", app_name, resumed)
        return {
            "app_name": app_name, "domain": clean, "domain_saved": True, "ingress_configured": True,
            "resumed": resumed, "url": f"https://{clean}",
            "dns": d.dns_instructions("app", app_name, clean)["record"],
            "next_step": "Call get_app_custom_domain to check DNS and SSL status. "
                         "DNS propagation can take up to 24 hours.",
        }

    @mcp.tool(annotations=DESTRUCTIVE, title="Remove app custom domain")
    async def remove_app_custom_domain(
        app_name: Annotated[str, Field(description="Name of the app")],
        confirm_domain: Annotated[str, Field(description="Must equal the app's current custom domain. Only fill this in after the user has explicitly confirmed the removal.")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Remove an app's custom domain. The domain stops serving the app; the default
        <app>.on.nifetency.com address keeps working. Confirm with the user first."""
        api = get_api(ctx)
        try:
            app = await _require_app(api, app_name)
            key, status = await _app_domain(api, app)
            if not key:
                raise ValueError(f"'{app_name}' has no custom domain configured.")
            if not d.same_domain(status.get("domain"), confirm_domain):
                raise ValueError(
                    "confirm_domain must exactly match the app's current custom domain. Nothing was removed."
                )
            await api.delete_app_domain(key)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("remove_app_custom_domain: app=%s", app_name)
        return {"removed": True, "app_name": app_name, "domain": status.get("domain")}

    # -------------------------------------------------------------------- sites
    @mcp.tool(annotations=WRITE, title="Add site custom domain")
    async def add_site_custom_domain(
        site_name: Annotated[str, Field(description="Name of the EXISTING site")],
        domain: Annotated[str, Field(description="Custom domain to attach, e.g. 'www.example.com'")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Attach a custom domain to a static site and sync its DNS record. The user must already
        have created the CNAME record (see get_domain_dns_instructions). A site has one custom domain;
        remove the old one first to change it. Follow with get_site_custom_domain."""
        api = get_api(ctx)
        try:
            clean = d.validate_domain(domain)
            site = await require_site(api, site_name)
            _not_suspended(site, "given a custom domain")
            current = await api.custom_domain(site_name)
            if current:
                if d.same_domain(current, clean):
                    return {
                        "site_name": site_name, "domain": clean, "already_configured": True,
                        "next_step": "Call get_site_custom_domain to check its DNS status.",
                    }
                raise ValueError(
                    f"'{site_name}' already has the custom domain '{current}'. "
                    "Remove it with remove_site_custom_domain before adding another."
                )
            await api.sync_dns_site(clean, site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("add_site_custom_domain: site=%s", site_name)
        return {
            "site_name": site_name, "domain": clean, "added": True, "url": f"https://{clean}",
            "dns": d.dns_instructions("site", site_name, clean)["record"],
            "next_step": "Call get_site_custom_domain to check DNS status. "
                         "DNS propagation can take up to 24 hours.",
        }

    @mcp.tool(annotations=DESTRUCTIVE, title="Remove site custom domain")
    async def remove_site_custom_domain(
        site_name: Annotated[str, Field(description="Name of the site")],
        confirm_domain: Annotated[str, Field(description="Must equal the site's current custom domain. Only fill this in after the user has explicitly confirmed the removal.")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Remove a site's custom domain (clears its route and saved domain). The default
        <site>.on.nifetency.com address keeps working. Confirm with the user first."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            current = await api.custom_domain(site_name)
            if not current:
                raise ValueError(f"'{site_name}' has no custom domain configured.")
            if not d.same_domain(current, confirm_domain):
                raise ValueError(
                    "confirm_domain must exactly match the site's current custom domain. Nothing was removed."
                )
            await api.delete_site_domain(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("remove_site_custom_domain: site=%s", site_name)
        return {"removed": True, "site_name": site_name, "domain": current,
                "default_url": h.site_url(site_name)}
