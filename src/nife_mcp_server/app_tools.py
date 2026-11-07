"""Container app and deployment tools for the hosted MCP server.

Curated (not auto-generated) tools over the nife.io GraphQL operations in
``api/apps.graphqls`` and ``api/deploy.graphqls``. Every tool first loads the app with the
caller's own token, which doubles as the ownership check before any mutation.
"""
import asyncio
import json
import logging
import re
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server import site_helpers as h
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.tool_utils import DESTRUCTIVE, READ_ONLY, WRITE, fail, get_api

logger = logging.getLogger(__name__)

APP_INSTRUCTIONS = """\

CONTAINER APPS AND DEPLOYMENTS (separate from static sites)
- list_apps / get_app / get_app_status give inventory, configuration and live health. Start with
  get_app_status when the user asks whether an app is running.
- list_app_releases shows release history; version numbers can be passed to revert_app_release.
- get_app_logs returns the most recent log lines of the running instances (not a log search).
- set_app_env, restart_app, pause_app, scale_app, redeploy_app_image, revert_app_release and delete_app change
  a live app: confirm with the user first. delete_app is permanent and needs the app name twice.
- To DEPLOY A NEW APP from a Docker image: list_organizations, then list_app_regions for that
  organization, ask the user which region(s), then call deploy_app once. It performs every backend
  step itself (create, regions, configuration, deploy); do not chain lower-level calls. It creates a
  billable app, so confirm name, image, regions and size first. For a PRIVATE image pass
  registry_secret_name (a stored secret NAME, see list_git_secrets); never ask the user to paste
  credentials. To put a new image on an app that already exists use redeploy_app_image.
- If an app runs in several regions, pass region_code (shown by get_app); otherwise it is inferred.
- Environment variable values are secrets: only names are ever returned.
"""

_APP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_APP_STATUSES = ("new", "active", "inactive", "terminated")

# New-app rule from the dashboard's deploy wizard (lowercase letters, digits, hyphens), plus a
# 63-character cap because the name becomes part of a hostname.
_NEW_APP_NAME = re.compile(r"^[a-z0-9-]{1,63}$")
# Strategies a plain image deploy supports. The dashboard also offers blue-green, canary and
# A/B testing, which need extra setup that deploy_app does not collect.
DEPLOY_STRATEGIES = ("rolling", "rolling-update", "recreate")
# The backend can gate a deployment behind an approval; the dashboard recognises it by message.
_APPROVAL_MARKERS = ("requires approval", "approval id", "deployment gated")
# After updateApp the config definition appears asynchronously; the dashboard polls 10 x 500 ms.
_DEFINITION_RETRIES = 10
_DEFINITION_DELAY = 0.5


def _validate_app_name(name: str) -> None:
    if not _APP_NAME.match(name or ""):
        raise ValueError(
            "Invalid app name. Use letters, digits, '.', '_' or '-' (max 63 characters)."
        )


async def _require_app(api: NifeAPI, name: str) -> Dict[str, Any]:
    """Validate the name and load the app with the caller's own token (ownership check)."""
    _validate_app_name(name)
    try:
        app = await api.app(name)
    except NifeAPIError as exc:
        text = str(exc)
        if "rejected the access token" in text or "timed out" in text or "Could not reach" in text:
            raise
        raise NifeAPIError(f"No app named '{name}' was found. Use list_apps to see your apps.")
    if not app:
        raise NifeAPIError(f"No app named '{name}' was found. Use list_apps to see your apps.")
    return app


def _regions(app: Dict[str, Any]) -> List[str]:
    codes = [r.get("code") for r in (app.get("regions") or []) if r.get("code")]
    if not codes:
        default = (app.get("clusterDetails") or {}).get("region_code")
        if default:
            codes = [default]
    return codes


def _pick_region(app: Dict[str, Any], region_code: Optional[str]) -> str:
    codes = _regions(app)
    if region_code:
        if codes and region_code not in codes:
            raise ValueError(
                f"The app is not deployed in region '{region_code}'. Its regions: {', '.join(codes)}."
            )
        return region_code
    if len(codes) == 1:
        return codes[0]
    if not codes:
        raise ValueError("Could not determine the app's region. Pass region_code (see get_app).")
    raise ValueError(f"The app runs in several regions ({', '.join(codes)}). Pass region_code.")


def _env_map(app: Dict[str, Any]) -> Dict[str, str]:
    """Current env vars as {name: value}, for server-side use only (values never leave this module).

    The dashboard reads ``envArgs``, a JSON object string; ``envMapArgs`` ('NAME=value' entries) is
    the fallback.
    """
    raw = app.get("envArgs")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): "" if v is None else str(v) for k, v in parsed.items()}
        except ValueError:
            pass
    out: Dict[str, str] = {}
    for entry in app.get("envMapArgs") or []:
        if isinstance(entry, str) and "=" in entry:
            k, v = entry.split("=", 1)
            out[k] = v
    return out


def _env_names(app: Dict[str, Any]) -> List[str]:
    """Names only, never values."""
    return list(_env_map(app))


def _summary(app: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": app.get("name"),
        "status": app.get("status"),
        "version": app.get("version"),
        "url": app.get("appUrl") or app.get("hostname"),
        "image": app.get("imageName"),
        "replicas": app.get("replicas"),
        "workload_type": app.get("workloadType"),
        "organization": app.get("organizationName"),
        "created_at": app.get("createdAt"),
    }


# ----------------------------------------------------- new-app deployment helpers
def _validate_new_app_name(name: str) -> None:
    if not isinstance(name, str) or not _NEW_APP_NAME.match(name):
        raise ValueError(
            "Invalid app name. Use 1-63 characters: lowercase letters, digits and '-' only."
        )


def _validate_image(image: str) -> None:
    if not isinstance(image, str) or not image or any(c.isspace() for c in image) or len(image) > 300:
        raise ValueError(
            "image must be a non-empty image reference without spaces, e.g. 'nginx:1.27' or 'myorg/api:1.4.2'."
        )


def _resource_requirements(cpu_cores: float, memory_mb: int) -> Dict[str, Any]:
    """The ``resource`` JSON the dashboard sends to updateApp: limits as given, requests at half."""
    cpu_limit = int(round(cpu_cores * 1000))
    return {
        "requestRequirement": {"cpu": f"{cpu_limit // 2}m", "memory": f"{memory_mb // 2}Mi"},
        "LimitRequirement": {"cpu": f"{cpu_limit}m", "memory": f"{memory_mb}Mi"},
    }


def _encrypted_env_args(env: Optional[Dict[str, str]]) -> List[str]:
    """'NAME=<encrypted value>' entries, like the dashboard's buildEncryptedEnvMapArgs.
    Entries with an empty value are skipped, as the dashboard does."""
    if not env:
        return []
    if len(env) > 100:
        raise ValueError("Too many environment variables (max 100).")
    out: List[str] = []
    for name, value in env.items():
        if not h.ENV_KEY_RE.match(name):
            raise ValueError(f"Invalid variable name '{name}'. Use letters, digits and '_'.")
        if not isinstance(value, str) or len(value) > 8192:
            raise ValueError(f"Value of {name} must be a string under 8192 characters.")
        if value:
            out.append(f"{name}={h.encrypt_env_value(value)}")
    return out


def _filter_org_regions(
    clusters: List[Dict[str, Any]], org_regions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Regions an organization can deploy into. Like the dashboard, an organization that has
    region entries is limited to the ones marked default; one with none sees every cluster."""
    if org_regions:
        defaults = {r.get("regCode") for r in org_regions if r.get("isDefault") is True}
        clusters = [c for c in clusters if c.get("regionCode") in defaults]
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for c in clusters:
        code = c.get("regionCode")
        if code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": c.get("name"), "cluster_type": c.get("clustertype")})
    return out


async def _deployable_regions(api: NifeAPI, organization_id: str) -> List[Dict[str, Any]]:
    clusters = await api.available_clusters()
    org_regions = await api.org_regions(organization_id)
    return _filter_org_regions(clusters, org_regions)


async def _app_or_none(api: NifeAPI, name: str) -> Optional[Dict[str, Any]]:
    """The caller's app, or None. Authentication and network failures are never swallowed."""
    try:
        return await api.app(name)
    except NifeAPIError as exc:
        text = str(exc)
        if "rejected the access token" in text or "timed out" in text or "Could not reach" in text:
            raise
        return None


async def _wait_for_definition(api: NifeAPI, name: str) -> Dict[str, Any]:
    for _ in range(_DEFINITION_RETRIES):
        definition = await api.app_definition(name)
        if isinstance(definition, dict) and definition:
            return definition
        await asyncio.sleep(_DEFINITION_DELAY)
    raise NifeAPIError("The app's configuration was not ready in time.")


def _needs_approval(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _APPROVAL_MARKERS)


def _approval_id(message: str) -> Optional[str]:
    match = re.search(r"Approval ID:\s*([A-Za-z0-9_-]+)", message, re.IGNORECASE)
    return match.group(1) if match else None


def register_app_tools(mcp: FastMCP) -> None:
    # ------------------------------------------------------------- read-only
    @mcp.tool(annotations=READ_ONLY, title="List apps")
    async def list_apps(
        ctx: Context,
        status: Annotated[
            Optional[str],
            Field(description="Filter by status: new, active, inactive or terminated"),
        ] = None,
        organization_slug: Annotated[Optional[str], Field(description="Only apps of this organization (slug from list_organizations)")] = None,
        limit: Annotated[int, Field(description="Maximum number of apps (1-100)", ge=1, le=100)] = 50,
    ) -> Dict[str, Any]:
        """List the user's container apps with status, version, image and URL."""
        api = get_api(ctx)
        try:
            if status and status.lower() not in _APP_STATUSES:
                raise ValueError(f"status must be one of: {', '.join(_APP_STATUSES)}")
            apps = await api.apps(status.lower() if status else None, limit, organization_slug)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {"apps": [_summary(a) for a in apps], "count": len(apps)}

    @mcp.tool(annotations=READ_ONLY, title="Get app")
    async def get_app(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Full configuration of a container app: image, port, replicas, size, regions, autoscaling,
        workload type, build and deployment times. Environment variable NAMES only, never values."""
        try:
            app = await _require_app(get_api(ctx), app_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        vm = app.get("vmSize") or {}
        return {
            **_summary(app),
            "hostname": app.get("hostname"),
            "port": app.get("port"),
            "regions": _regions(app),
            "cluster": app.get("clusterDetails"),
            "size": {"name": vm.get("name"), "cpu_cores": vm.get("cPUCores"), "memory_gb": vm.get("memoryGb")},
            "autoscaling": app.get("autoscaling"),
            "resource_type": app.get("resourceType"),
            "deployment_type": app.get("deploymentType"),
            "cron_schedule": app.get("cronSchedule"),
            "source_url": app.get("sourceUrl"),
            "build_log_url": app.get("buildLogsUrl"),
            "last_deployed_at": app.get("deploymentTime"),
            "build_time": app.get("buildTime"),
            "sub_organization": app.get("subOrganizationName"),
            "business_unit": app.get("businessUnitName"),
            "env_variable_names": _env_names(app),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get app status")
    async def get_app_status(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Live health of an app: status, current deployment progress, desired/healthy/unhealthy
        instance counts and each running instance (region, restarts, failures). Use it to follow a
        deployment started with redeploy_app_image or revert_app_release."""
        api = get_api(ctx)
        try:
            await _require_app(api, app_name)
            st = await api.app_status(app_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        st = st or {}
        dep = st.get("deploymentStatus") or {}
        allocs = st.get("allocations") or []
        attention = []
        if dep.get("unhealthyCount"):
            attention.append(f"{dep['unhealthyCount']} unhealthy instance(s).")
        failed = [a for a in allocs if a.get("failed")]
        if failed:
            attention.append(f"{len(failed)} instance(s) failed.")
        restarting = [a for a in allocs if (a.get("restarts") or 0) >= 3]
        if restarting:
            attention.append(f"{len(restarting)} instance(s) restarted 3+ times (possible crash loop).")
        return {
            "app_name": app_name,
            "status": st.get("status"),
            "deployed": st.get("deployed"),
            "version": st.get("version"),
            "url": st.get("appUrl"),
            "deployment": {
                "status": dep.get("status"),
                "description": dep.get("description"),
                "in_progress": dep.get("inProgress"),
                "successful": dep.get("successful"),
                "version": dep.get("version"),
                "desired": dep.get("desiredCount"),
                "placed": dep.get("placedCount"),
                "healthy": dep.get("healthyCount"),
                "unhealthy": dep.get("unhealthyCount"),
            },
            "instances": [
                {
                    "id": a.get("idShort"), "version": a.get("version"), "region": a.get("region"),
                    "status": a.get("status"), "desired_status": a.get("desiredStatus"),
                    "healthy": a.get("healthy"), "failed": a.get("failed"),
                    "restarts": a.get("restarts"), "started_at": a.get("createdAt"),
                }
                for a in allocs
            ],
            "attention": attention,
        }

    @mcp.tool(annotations=READ_ONLY, title="List app releases")
    async def list_app_releases(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
        limit: Annotated[int, Field(description="Maximum number of releases (1-50)", ge=1, le=50)] = 10,
    ) -> Dict[str, Any]:
        """Release history of an app: version, image, status, deployment strategy and reason.
        Pass a version to revert_app_release to go back to it."""
        api = get_api(ctx)
        try:
            await _require_app(api, app_name)
            releases = await api.app_releases(app_name, limit)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "app_name": app_name,
            "releases": [
                {
                    "version": r.get("version"), "status": r.get("status"), "image": r.get("image"),
                    "stable": r.get("stable"), "in_progress": r.get("inProgress"),
                    "strategy": r.get("deploymentStrategy"), "reason": r.get("reason"),
                    "description": r.get("description"), "port": r.get("port"),
                    "created_at": r.get("createdAt"),
                }
                for r in releases
            ],
            "count": len(releases),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get app logs")
    async def get_app_logs(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
        lines: Annotated[int, Field(description="Maximum log lines to return (1-500)", ge=1, le=500)] = 100,
        level: Annotated[Optional[str], Field(description="Only lines of this level, e.g. error or warn")] = None,
        region_code: Annotated[Optional[str], Field(description="Only instances in this region")] = None,
    ) -> Dict[str, Any]:
        """Most recent log lines from the app's running instances, newest last. This is a recent
        window, not a search. Logs can contain sensitive data: do not repeat secrets back."""
        api = get_api(ctx)
        try:
            await _require_app(api, app_name)
            allocs = await api.app_logs(app_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        entries: List[Dict[str, Any]] = []
        for a in allocs:
            if region_code and a.get("region") != region_code:
                continue
            for e in a.get("recentLogs") or []:
                if level and (e.get("level") or "").lower() != level.lower():
                    continue
                entries.append({
                    "timestamp": e.get("timestamp"), "level": e.get("level"),
                    "instance": e.get("instance") or a.get("idShort"),
                    "region": e.get("region") or a.get("region"), "message": e.get("message"),
                })
        entries.sort(key=lambda e: e.get("timestamp") or "")
        total = len(entries)
        entries = entries[-lines:]
        return {"app_name": app_name, "lines": entries, "returned": len(entries), "available": total}

    # ------------------------------------------------------- new app deployment
    @mcp.tool(annotations=READ_ONLY, title="List app regions")
    async def list_app_regions(
        organization_id: Annotated[str, Field(description="Organization id from list_organizations")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Regions a new container app can be deployed to for an organization. Pass the chosen
        codes as region_codes to deploy_app. cluster_type 'byoh' means a customer-hosted region
        served by a Nife agent."""
        api = get_api(ctx)
        try:
            regions = await _deployable_regions(api, organization_id)
        except NifeAPIError as exc:
            raise fail(exc)
        return {
            "organization_id": organization_id,
            "regions": regions,
            "count": len(regions),
        }

    @mcp.tool(annotations=WRITE, title="Deploy new app from Docker image")
    async def deploy_app(
        app_name: Annotated[str, Field(description="Name for the NEW app: 1-63 characters, lowercase letters, digits and '-'")],
        image: Annotated[str, Field(description="Docker image to deploy, e.g. 'nginx:1.27' or 'myorg/api:1.4.2'")],
        organization_id: Annotated[str, Field(description="Organization id from list_organizations")],
        region_codes: Annotated[List[str], Field(description="Region codes from list_app_regions", min_length=1, max_length=10)],
        ctx: Context,
        port: Annotated[int, Field(description="Port the container listens on", ge=1, le=65535)] = 3000,
        external_port: Annotated[int, Field(description="Port exposed to the outside", ge=1, le=65535)] = 80,
        replicas: Annotated[int, Field(description="Replica count (1-10)", ge=1, le=10)] = 2,
        cpu_cores: Annotated[float, Field(description="CPU limit in cores, e.g. 0.5; the request is set to half", ge=0.1, le=16)] = 0.5,
        memory_mb: Annotated[int, Field(description="Memory limit in MiB, e.g. 1024; the request is set to half", ge=64, le=32768)] = 1024,
        strategy: Annotated[str, Field(description="Rollout strategy: rolling (default), rolling-update or recreate")] = "rolling",
        env: Annotated[Optional[Dict[str, str]], Field(description="Environment variables as {NAME: value}. Values are encrypted server-side and never returned.")] = None,
        registry_secret_name: Annotated[Optional[str], Field(description="NAME of a stored registry secret, for a PRIVATE image (see list_git_secrets). Never ask the user to paste credentials.")] = None,
    ) -> Dict[str, Any]:
        """Create and deploy a NEW container app from a Docker image, following the dashboard's
        deploy sequence: create the app, set its regions, apply ports, replicas, size and
        environment, read back the generated configuration, link the registry secret if any, and
        deploy. This creates a billable app, so confirm the details with the user first. Returns once
        the deploy is submitted; follow it with get_app_status. If a step fails after the app was
        created, the app is left as a draft: call deploy_app again with the same name to resume.
        To deploy to an app that already exists use redeploy_app_image."""
        api = get_api(ctx)
        app_id: Optional[str] = None
        resumed = False
        stage = "validating the request"
        try:
            _validate_new_app_name(app_name)
            _validate_image(image)
            if strategy not in DEPLOY_STRATEGIES:
                raise ValueError(f"strategy must be one of: {', '.join(DEPLOY_STRATEGIES)}")
            env_args = _encrypted_env_args(env)
            codes = list(dict.fromkeys(region_codes))

            orgs = await api.organizations()
            if not any(o.get("id") == organization_id for o in orgs):
                raise ValueError("No such organization. Use list_organizations to see yours.")
            known = {r["code"] for r in await _deployable_regions(api, organization_id)}
            unknown = [c for c in codes if c not in known]
            if unknown:
                raise ValueError(
                    f"Region(s) not available to this organization: {', '.join(unknown)}. "
                    f"Available: {', '.join(sorted(known)) or 'none'}. Use list_app_regions."
                )
            if registry_secret_name:
                secrets = await api.list_secrets()
                if not any(
                    s.get("name") == registry_secret_name and (s.get("registryType") or "").lower() != "env"
                    for s in secrets
                ):
                    raise ValueError(
                        f"No stored registry secret named '{registry_secret_name}'. "
                        "Use list_git_secrets to see the available names."
                    )

            existing = await _app_or_none(api, app_name)
            if existing:
                # A draft left by an earlier attempt that never deployed can be resumed.
                if existing.get("status") != "new" or existing.get("deployed"):
                    raise ValueError(
                        f"An app named '{app_name}' already exists. Use redeploy_app_image to put a "
                        "new image on it, or choose another name."
                    )
                if existing.get("organizationId") and existing["organizationId"] != organization_id:
                    raise ValueError("A draft app with this name exists in a different organization.")
                app_id, resumed = existing["id"], True
            else:
                stage = "creating the app"
                created = await api.create_app({
                    "name": app_name, "runtime": "custom", "organizationId": organization_id,
                    "subOrganizationId": "", "businessUnitId": "", "workloadManagementId": "",
                    "deploymentType": "docker",
                })
                if not created or not created.get("id"):
                    raise NifeAPIError("The backend did not return the new app's id.")
                app_id = created["id"]

            stage = "configuring regions"
            try:
                await api.configure_regions(app_name, codes)
            except NifeAPIError as exc:
                if "internal system error" in str(exc) or "no cluster details" in str(exc):
                    raise NifeAPIError(
                        "The organization's cluster configuration is missing. Ask an administrator to fix it."
                    ) from exc
                raise

            stage = "applying the app configuration"
            update: Dict[str, Any] = {
                "appId": app_id,
                "internalPort": str(port), "externalPort": str(external_port),
                "replicas": replicas,
                "build": json.dumps({"builder": "image", "image": image}),
                "resource": json.dumps(_resource_requirements(cpu_cores, memory_mb)),
                "deploymentType": strategy, "workloadType": "deployment", "resourceType": "CPU",
                "routingPolicy": "latency",
            }
            if env_args:
                update["envMapArgs"] = env_args
            await api.update_app(update)

            stage = "reading the generated configuration"
            definition = await _wait_for_definition(api, app_name)

            if registry_secret_name:
                stage = "linking the registry secret"
                await api.link_registry_secret(app_name, registry_secret_name)

            stage = "deploying the image"
            release = await api.deploy_image({
                "appId": app_name, "image": image, "definition": definition,
                "envMapArgs": env_args, "envArgs": "", "archiveUrl": "",
                "strategy": strategy, "deploymentType": strategy,
                "workloadType": "deployment", "resourceType": "CPU",
            })
            if not release:
                raise NifeAPIError("The backend accepted the deploy but returned no release.")
        except (ValueError, NifeAPIError) as exc:
            message = str(exc)
            if app_id and _needs_approval(message):
                return {
                    "submitted": False, "approval_pending": True, "app_name": app_name,
                    "approval_id": _approval_id(message), "detail": message,
                    "next_step": "An administrator must approve this deployment before it rolls out.",
                }
            if app_id:
                raise fail(ValueError(
                    f"Deploy failed while {stage}: {message} The app '{app_name}' exists as a draft and "
                    "nothing is deployed. Fix the cause and call deploy_app again with the same name to resume."
                ))
            raise fail(exc)

        logger.info("deploy_app: app=%s regions=%s resumed=%s", app_name, codes, resumed)
        return {
            "submitted": True, "app_name": app_name, "resumed_draft": resumed, "image": image,
            "regions": codes, "replicas": replicas, "port": port, "external_port": external_port,
            "env_variable_names": sorted(k for k, v in (env or {}).items() if v),
            "release": {"id": release.get("id"), "version": release.get("version"), "status": release.get("status")},
            "reason": release.get("reason"),
            "next_step": "Call get_app_status to follow the deployment; the URL shows there once it is up.",
        }

    # ----------------------------------------------------------- lifecycle
    @mcp.tool(annotations=DESTRUCTIVE, title="Restart app")
    async def restart_app(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Restart all instances of an app. Causes a brief interruption, so confirm with the user
        first. Follow progress with get_app_status."""
        api = get_api(ctx)
        try:
            app = await _require_app(api, app_name)
            result = await api.restart_app(app["id"])
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("restart_app: app=%s", app_name)
        return {"restarted": True, "app_name": app_name, "backend_response": result,
                "next_step": "Call get_app_status to follow the restart."}

    @mcp.tool(annotations=DESTRUCTIVE, title="Pause app")
    async def pause_app(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
        region_code: Annotated[Optional[str], Field(description="Region to pause (required if the app runs in several)")] = None,
    ) -> Dict[str, Any]:
        """Pause (suspend) an app in a region. The app stops serving traffic until resumed, so
        confirm with the user first."""
        api = get_api(ctx)
        try:
            app = await _require_app(api, app_name)
            region = _pick_region(app, region_code)
            result = await api.pause_app(app["id"], region)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("pause_app: app=%s region=%s", app_name, region)
        return {"paused": True, "app_name": app_name, "region": region, "backend_response": result}

    @mcp.tool(annotations=WRITE, title="Resume app")
    async def resume_app(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
        region_code: Annotated[Optional[str], Field(description="Region to resume (required if the app runs in several)")] = None,
    ) -> Dict[str, Any]:
        """Resume a paused app in a region."""
        api = get_api(ctx)
        try:
            app = await _require_app(api, app_name)
            region = _pick_region(app, region_code)
            result = await api.resume_app(app["id"], region)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("resume_app: app=%s region=%s", app_name, region)
        return {"resumed": True, "app_name": app_name, "region": region, "backend_response": result,
                "next_step": "Call get_app_status to follow the startup."}

    @mcp.tool(annotations=DESTRUCTIVE, title="Scale app")
    async def scale_app(
        app_name: Annotated[str, Field(description="Name of the app")],
        ctx: Context,
        replicas: Annotated[Optional[int], Field(description="New replica count (0-50)", ge=0, le=50)] = None,
        cpu_limit: Annotated[Optional[str], Field(description="CPU limit, e.g. '500m' or '1'")] = None,
        memory_limit: Annotated[Optional[str], Field(description="Memory limit, e.g. '512Mi' or '1Gi'")] = None,
        cpu_request: Annotated[Optional[str], Field(description="CPU request, e.g. '250m'")] = None,
        memory_request: Annotated[Optional[str], Field(description="Memory request, e.g. '256Mi'")] = None,
        region_code: Annotated[Optional[str], Field(description="Region to change (required if the app runs in several)")] = None,
        strategy: Annotated[Optional[str], Field(description="Rollout strategy, e.g. 'rolling'")] = None,
    ) -> Dict[str, Any]:
        """Change an app's replica count and/or CPU and memory. May restart instances, so confirm with
        the user first. Pass only the values to change."""
        api = get_api(ctx)
        try:
            if all(v is None for v in (replicas, cpu_limit, memory_limit, cpu_request, memory_request)):
                raise ValueError("Pass at least one of replicas, cpu_limit, memory_limit, cpu_request, memory_request.")
            app = await _require_app(api, app_name)
            region = _pick_region(app, region_code)
            variables: Dict[str, Any] = {
                "appId": app["id"], "organizationId": app.get("organizationId"), "regionCode": region,
            }
            for key, val in (("replicas", replicas), ("cpuLimit", cpu_limit), ("memoryLimit", memory_limit),
                             ("cpuRequest", cpu_request), ("memoryRequest", memory_request),
                             ("strategy", strategy)):
                if val is not None:
                    variables[key] = val
            result = await api.patch_resources(variables)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("scale_app: app=%s region=%s", app_name, region)
        return {"submitted": True, "app_name": app_name, "region": region, "backend_response": result,
                "next_step": "Call get_app_status to follow the rollout."}

    # ---------------------------------------------------------- deployments
    @mcp.tool(annotations=DESTRUCTIVE, title="Redeploy app image")
    async def redeploy_app_image(
        app_name: Annotated[str, Field(description="Name of the EXISTING app to update")],
        image: Annotated[str, Field(description="Container image to deploy, e.g. 'myorg/api:1.4.2'")],
        ctx: Context,
        region_code: Annotated[Optional[str], Field(description="Region to deploy to (required if the app runs in several)")] = None,
        strategy: Annotated[Optional[str], Field(description="Rollout strategy, e.g. 'rolling'")] = None,
        replicas: Annotated[Optional[int], Field(description="Replica count to deploy with", ge=0, le=50)] = None,
    ) -> Dict[str, Any]:
        """Deploy a new image to an existing container app. This REPLACES the running version, so
        confirm the image with the user first. Environment variables are kept as they are. Returns
        once submitted; poll get_app_status."""
        api = get_api(ctx)
        try:
            if not image or any(c.isspace() for c in image) or len(image) > 300:
                raise ValueError("image must be a non-empty image reference without spaces.")
            app = await _require_app(api, app_name)
            region = _pick_region(app, region_code)
            variables: Dict[str, Any] = {
                "appId": app["id"], "image": image.strip(),
                "organizationId": app.get("organizationId"), "regionCode": region,
            }
            if strategy:
                variables["strategy"] = strategy
            if replicas is not None:
                variables["replicas"] = replicas
            result = await api.redeploy_image(variables)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("redeploy_app_image: app=%s region=%s", app_name, region)
        return {"submitted": True, "app_name": app_name, "region": region, "backend_response": result,
                "next_step": "Call get_app_status to follow the deployment."}

    @mcp.tool(annotations=DESTRUCTIVE, title="Set app environment variables")
    async def set_app_env(
        app_name: Annotated[str, Field(description="Name of the EXISTING app")],
        ctx: Context,
        set: Annotated[Optional[Dict[str, str]], Field(description="Variables to add or change, as {NAME: value}")] = None,
        unset: Annotated[Optional[List[str]], Field(description="Names of variables to remove")] = None,
        region_code: Annotated[Optional[str], Field(description="Region to roll out to (required if the app runs in several)")] = None,
        allow_replace_all: Annotated[bool, Field(description="Only if get_app shows no env_variable_names but the app is known to have none to keep. Otherwise leave false.")] = False,
    ) -> Dict[str, Any]:
        """Add, change or remove environment variables on an existing app and roll it out. The backend
        REPLACES the whole variable set on every update, so this tool reads the current values
        server-side, merges your changes and sends the full set; values are never returned. It
        redeploys the app's current image, so confirm with the user first. Never ask the user to
        paste secrets into chat if a stored secret can be used instead."""
        api = get_api(ctx)
        try:
            if not set and not unset:
                raise ValueError("Pass set and/or unset.")
            app = await _require_app(api, app_name)
            if not app.get("imageName"):
                raise ValueError("This app has no image recorded, so env vars cannot be rolled out here.")
            region = _pick_region(app, region_code)
            current = _env_map(app)
            if not current and not allow_replace_all:
                raise ValueError(
                    "Could not read the app's existing variables, and sending a new set would replace "
                    "them. Nothing was changed. If the app really has none, retry with allow_replace_all=true."
                )
            for name, value in (set or {}).items():
                if not h.ENV_KEY_RE.match(name):
                    raise ValueError(f"Invalid variable name '{name}'. Use letters, digits and '_'.")
                if not isinstance(value, str) or len(value) > 8192:
                    raise ValueError(f"Value of {name} must be a string under 8192 characters.")
            missing = [n for n in (unset or []) if n not in current]
            # Existing values are already stored the way the dashboard wrote them (encrypted),
            # so they pass through untouched; only the new values are encrypted here.
            merged = {**current, **{k: h.encrypt_env_value(v) for k, v in (set or {}).items()}}
            for n in (unset or []):
                merged.pop(n, None)
            result = await api.redeploy_image({
                "appId": app["id"], "image": app["imageName"],
                "organizationId": app.get("organizationId"), "regionCode": region,
                "envMapArgs": [f"{k}={v}" for k, v in merged.items()],
            })
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("set_app_env: app=%s region=%s set=%d unset=%d", app_name, region,
                    len(set or {}), len(unset or []))
        return {"submitted": True, "app_name": app_name, "region": region,
                "added_or_changed": sorted(set or {}), "removed": sorted(n for n in (unset or []) if n not in missing),
                "not_found_to_remove": missing, "variable_count": len(merged),
                "backend_response": result, "next_step": "Call get_app_status to follow the rollout."}

    @mcp.tool(annotations=DESTRUCTIVE, title="Revert app release")
    async def revert_app_release(
        app_name: Annotated[str, Field(description="Name of the app")],
        version: Annotated[str, Field(description="Release version to go back to, from list_app_releases")],
        ctx: Context,
        region_code: Annotated[Optional[str], Field(description="Region to revert (required if the app runs in several)")] = None,
    ) -> Dict[str, Any]:
        """Roll an app back to an earlier release from its history. This REPLACES the running version,
        so confirm with the user first."""
        api = get_api(ctx)
        try:
            app = await _require_app(api, app_name)
            region = _pick_region(app, region_code)
            history = await api.app_releases(app_name, 50)
            match = next((r for r in history if str(r.get("version")) == str(version)), None)
            if not match:
                known = ", ".join(str(r.get("version")) for r in history[:15]) or "none"
                raise ValueError(f"Version '{version}' is not in this app's history. Known versions: {known}")
            if str(app.get("version")) == str(version):
                raise ValueError(f"Version '{version}' is already the running version.")
            result = await api.revert_deployment({
                "appId": app["id"], "organizationId": app.get("organizationId"),
                "regionCode": region, "version": str(version),
            })
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("revert_app_release: app=%s region=%s to=%s", app_name, region, version)
        return {"submitted": True, "app_name": app_name, "region": region, "to_version": version,
                "backend_response": result, "next_step": "Call get_app_status to follow the rollback."}

    @mcp.tool(annotations=DESTRUCTIVE, title="Delete app")
    async def delete_app(
        app_name: Annotated[str, Field(description="Name of the app to delete")],
        confirm_app_name: Annotated[str, Field(description="Must exactly equal app_name. Only fill this in after the user has explicitly confirmed the deletion.")],
        ctx: Context,
        region_code: Annotated[Optional[str], Field(description="Region to delete from (required if the app runs in several)")] = None,
    ) -> Dict[str, Any]:
        """PERMANENTLY delete a container app in a region. This cannot be undone. Only call after the
        user has explicitly confirmed, by name, that they want it deleted."""
        api = get_api(ctx)
        try:
            if app_name != confirm_app_name:
                raise ValueError("confirm_app_name must exactly match app_name. Nothing was deleted.")
            app = await _require_app(api, app_name)
            region = _pick_region(app, region_code)
            result = await api.delete_app(app["id"], region)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("delete_app: app=%s region=%s", app_name, region)
        return {"deleted": True, "app_name": app_name, "region": region, "backend_response": result}
