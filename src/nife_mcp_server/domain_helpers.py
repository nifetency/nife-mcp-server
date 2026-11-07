"""Pure helpers for the custom-domain tools (no MCP or network imports, easy to test).

Rules mirror the dashboard's Add Domain dialog and the site/app domain tabs.
"""
import ipaddress
import json
import re
from typing import Any, Dict, Optional

# Sites and apps are served at <name>.on.nifetency.com; a custom domain is a CNAME to it.
PLATFORM_SUFFIX = "on.nifetency.com"
# Domains that belong to the platform itself can never be attached as a custom domain.
RESERVED_SUFFIXES = ("nifetency.com", "nife.io")

# Same expression as the dashboard's AddDomainDialog.
DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$", re.IGNORECASE
)
# The dashboard falls back to this when the app definition has no external_port.
DEFAULT_SERVICE_PORT = 8080


def normalize_domain(domain: Any) -> str:
    """Lower-case, trimmed, without a trailing dot."""
    return str(domain or "").strip().lower().rstrip(".")


def validate_domain(domain: Any) -> str:
    """Return the normalized domain or raise ValueError with a message safe to show the user."""
    value = normalize_domain(domain)
    if not value:
        raise ValueError("Please provide a domain name, e.g. 'example.com' or 'app.example.com'.")
    if "://" in value or "/" in value or ":" in value or " " in value:
        raise ValueError("Pass only the domain name, without 'https://', a path or a port.")
    if len(value) > 253:
        raise ValueError("The domain name is too long (max 253 characters).")
    if value.startswith("*."):
        raise ValueError("Wildcard domains are not supported. Use a specific domain such as 'app.example.com'.")
    if not DOMAIN_RE.match(value):
        raise ValueError(
            "Please enter a valid domain name (e.g. example.com or subdomain.example.com)."
        )
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("An IP address is not a domain name.")
    for suffix in RESERVED_SUFFIXES:
        if value == suffix or value.endswith("." + suffix):
            raise ValueError(
                f"'{value}' belongs to the Nife platform and cannot be used as a custom domain."
            )
    return value


def same_domain(a: Any, b: Any) -> bool:
    return bool(a) and bool(b) and normalize_domain(a) == normalize_domain(b)


def cname_target(resource_name: str) -> str:
    return f"{resource_name}.{PLATFORM_SUFFIX}"


def dns_instructions(resource_type: str, resource_name: str, domain: str) -> Dict[str, Any]:
    """The DNS record the user must create at their DNS provider."""
    target = cname_target(resource_name)
    notes = [
        "DNS changes can take from a few minutes up to 24 hours to propagate.",
        "Create the record at your DNS provider (Cloudflare, GoDaddy, Route 53, ...) before adding the domain.",
    ]
    if domain.count(".") == 1:
        notes.append(
            f"'{domain}' looks like a root (apex) domain. Many DNS providers do not allow a CNAME there; "
            "use CNAME flattening / an ALIAS record if your provider offers it, or use a subdomain such as "
            f"'www.{domain}'."
        )
    return {
        "resource_type": resource_type,
        "resource_name": resource_name,
        "domain": domain,
        "record": {"type": "CNAME", "name": domain, "value": target, "ttl": "Auto"},
        "notes": notes,
    }


def service_port(definition: Any) -> int:
    """External service port from an app definition (dashboard: services[0].external_port || 8080)."""
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except ValueError:
            definition = None
    services = definition.get("services") if isinstance(definition, dict) else None
    if isinstance(services, list) and services and isinstance(services[0], dict):
        external_port = services[0].get("external_port")
        try:
            port = int(external_port) if external_port is not None else 0
        except (TypeError, ValueError):
            port = 0
        if 0 < port < 65536:
            return port
    return DEFAULT_SERVICE_PORT


def namespace_for(org: Optional[Dict[str, Any]]) -> str:
    """Kubernetes namespace the dashboard uses: organization slug, else name, else 'default'."""
    org = org or {}
    return org.get("slug") or org.get("name") or "default"


def app_domain_view(status: Dict[str, Any]) -> Dict[str, Any]:
    """Customer-facing view of the backend's custom-domain status record."""
    exists = bool(status.get("exists") and status.get("domain"))
    if not exists:
        return {"configured": False}
    return {
        "configured": True,
        "domain": status.get("domain"),
        "dns_synced": bool(status.get("synced")),
        "state": "active" if status.get("synced") else "pending",
        "verified": status.get("verified"),
        "ssl": {
            "enabled": status.get("sslEnabled") if status.get("sslEnabled") is not None else status.get("status") == "active",
            "expires_at": status.get("sslExpiresAt"),
            "auto_renew": status.get("sslAutoRenew"),
        },
    }
