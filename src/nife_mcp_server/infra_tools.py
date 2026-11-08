"""Read-only infrastructure and governance tools: cloud accounts, agents, forecasts, roles, plan.

Every tool goes through the backend with the caller's own token, so the resolvers keep enforcing
access. Organization ids are checked with require_org, and cluster ids (which are not
organization-keyed) are checked against the caller's own agent list before use. Cloud account
secrets, agent addresses and agent metadata are never requested.
"""
import logging
from typing import Annotated, Any, Dict, Optional
from urllib.parse import quote

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server import ops_helpers as o
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.ops_tools import Limit, OrgId, _cap, _need, _opt, guarded
from nife_mcp_server.platform_tools import _own_app
from nife_mcp_server.tool_utils import READ_ONLY, get_api, require_org

logger = logging.getLogger(__name__)

INFRA_INSTRUCTIONS = """\

INFRASTRUCTURE, AGENTS AND GOVERNANCE
- list_cloud_accounts shows the cloud accounts connected to an organization (no credentials).
  list_business_units shows the business units. list_roles shows the platform roles and what
  each can do. get_plan_limits shows what the caller's plan allows.
- list_agents shows the Nife agents running in customer clusters. get_agent_metrics,
  get_agent_security_findings and get_agent_health_checks take a cluster_id from list_agents.
- get_resource_forecast gives the Nia CPU and memory forecast for an organization or one app:
  current usage, predicted peak and recommendations. Charts are not returned.
These tools only read.
"""

FINDING_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
FINDING_STATUSES = ("OPEN", "ACKNOWLEDGED", "RESOLVED", "FALSE_POSITIVE")
MAX_CHECKS = 50


def _upper_choice(value: Optional[str], allowed: tuple, name: str) -> Optional[str]:
    text = (value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(a.lower() for a in allowed)}.")
    return text


async def _own_agent(api: NifeAPI, cluster_id: str) -> Dict[str, Any]:
    """Cluster ids are not org-keyed, so prove the cluster is one of the caller's own agents."""
    wanted = _need(cluster_id, "cluster_id")
    data = await api.graphql("query OwnAgents { listAgents { id clusterID } }")
    for agent in data.get("listAgents") or []:
        if agent and agent.get("clusterID") == wanted:
            return agent
    raise NifeAPIError("No agent for that cluster_id was found. Use list_agents to see your agents.")


def _forecast_view(data: Dict[str, Any]) -> Dict[str, Any]:
    """The forecast without its base64 chart images, which are large and useless in text."""
    keep = ("max_cpu", "max_mem", "forecast_period", "confidence", "model_version", "trained_at",
            "using_lstm", "cpu_rmse", "mem_rmse", "current_usage", "predicted_peak")
    out = {k: data.get(k) for k in keep if data.get(k) is not None}
    recs = data.get("recommendations")
    if isinstance(recs, list):
        out["recommendations"] = [o.clip(r, 400) for r in recs[:10] if r]
    return out


def register_infra_tools(mcp: FastMCP) -> None:
    # ============================================================ accounts
    @mcp.tool(annotations=READ_ONLY, title="List cloud accounts")
    @guarded
    async def list_cloud_accounts(organization_id: OrgId, ctx: Context) -> Dict[str, Any]:
        """Cloud accounts connected to an organization (AWS, GCP, Azure, OpenStack) with status and
        when they were last validated. Credentials are never returned."""
        api = get_api(ctx)
        await require_org(api, organization_id)
        data = await api.graphql(
            """query ListCloudAccounts($orgId: String!) {
                 listCloudAccounts(orgId: $orgId) {
                   id name cloud status awsRegion gcpProjectId azureSubscriptionId azureTenantId
                   osAuthUrl osProjectId osDomainName lastValidatedAt createdAt
                 }
               }""",
            {"orgId": organization_id},
        )
        accounts = [a for a in data.get("listCloudAccounts") or [] if a]
        return {"accounts": accounts, "count": len(accounts)}

    @mcp.tool(annotations=READ_ONLY, title="List business units")
    @guarded
    async def list_business_units(
        ctx: Context,
        organization_id: Annotated[Optional[str], Field(description="Limit to one organization")] = None,
    ) -> Dict[str, Any]:
        """Business units with their organization and sub-organization."""
        api = get_api(ctx)
        if organization_id:
            await require_org(api, organization_id)
        data = await api.graphql(
            """query BusinessUnits {
                 businessUnitList { id orgId orgName subOrgId subOrgName name }
               }"""
        )
        units = [u for u in data.get("businessUnitList") or [] if u]
        if organization_id:
            units = [u for u in units if u.get("orgId") == organization_id]
        return {"business_units": units, "count": len(units)}

    @mcp.tool(annotations=READ_ONLY, title="List roles")
    @guarded
    async def list_roles(ctx: Context) -> Dict[str, Any]:
        """Platform roles (Admin, Viewer and so on) and the actions each can take per module.
        Roles are the same for every organization."""
        data = await get_api(ctx).graphql(
            """query Roles {
                 getRoles {
                   id name description isSystem
                   permissions { module title create view delete update is_active }
                 }
               }"""
        )
        roles = []
        for r in data.get("getRoles") or []:
            if not r:
                continue
            modules = []
            for p in (r.get("permissions") or [])[:100]:
                if not p or p.get("is_active") is False:
                    continue
                actions = [a for a in ("view", "create", "update", "delete") if p.get(a)]
                if actions:
                    modules.append({"module": p.get("module") or p.get("title"), "can": actions})
            roles.append({"id": r.get("id"), "name": r.get("name"),
                          "description": o.clip(r.get("description"), 300),
                          "system_role": r.get("isSystem"), "permissions": modules})
        return {"roles": roles, "count": len(roles)}

    @mcp.tool(annotations=READ_ONLY, title="Get plan limits")
    @guarded
    async def get_plan_limits(ctx: Context) -> Dict[str, Any]:
        """What the caller's plan allows: app, organization and region limits and which features
        (custom domains, secrets, SSO, source builds, monitoring) are included."""
        data = await get_api(ctx).graphql(
            """query PlanLimits {
                 getUserPermissionsByPlan {
                   planName apps workloadManagement organizationManagement inviteUserLimit
                   applicationHealthDashboard byoh storage versionControlPanel singleSignOn
                   organizationCount subOrganizationCount businessunitCount customDomain
                   appNotification secret monitoringPlatform alertsAdvisories auditLogs sslSecurity
                   infrastructureConfiguration replicas k8sRegions sourceBuild sitesCount
                 }
               }"""
        )
        return data.get("getUserPermissionsByPlan") or {"message": "No plan information is available."}

    # =============================================================== agents
    @mcp.tool(annotations=READ_ONLY, title="List agents")
    @guarded
    async def list_agents(
        ctx: Context,
        organization_id: Annotated[Optional[str], Field(description="Limit to one organization")] = None,
    ) -> Dict[str, Any]:
        """Nife agents running in customer clusters: version, connection status, last heartbeat,
        active deployments and open security findings. Addresses are never returned."""
        api = get_api(ctx)
        if organization_id:
            await require_org(api, organization_id)
        data = await api.graphql(
            """query Agents($org: ID) {
                 listAgents(organizationID: $org) {
                   id clusterID agentVersion status lastHeartbeat lastDisconnected capabilities
                   activeDeployments openSecurityFindings createdAt updatedAt
                 }
               }""",
            {"org": organization_id},
        )
        agents = [a for a in data.get("listAgents") or [] if a]
        down = [a["clusterID"] for a in agents if a.get("status") != "CONNECTED"]
        return {"agents": agents, "count": len(agents),
                "attention": [f"Agent for cluster {c} is not connected." for c in down]}

    @mcp.tool(annotations=READ_ONLY, title="Get agent metrics")
    @guarded
    async def get_agent_metrics(
        cluster_id: Annotated[str, Field(description="Cluster id from list_agents")],
        ctx: Context,
        time_range: Annotated[Optional[str], Field(description="For example 1h, 6h or 24h")] = None,
    ) -> Dict[str, Any]:
        """Cluster usage reported by the agent: CPU, memory and disk, pods and nodes, per-node
        usage and per-application replica health."""
        api = get_api(ctx)
        rng = o.check_period(time_range, "1h") if time_range else None
        agent = await _own_agent(api, cluster_id)
        data = await api.graphql(
            """query AgentMetrics($id: ID!, $range: String) {
                 getAgentMetrics(clusterID: $id, timeRange: $range) {
                   timestamp cpuUsage memoryUsage diskUsage podCount nodeCount activeDeployments
                   nodes { name cpuUsage memoryUsage diskUsage status podCount }
                   applications {
                     name namespace health cpuUsage memoryUsage
                     replicas { desired ready updated available }
                   }
                 }
               }""",
            {"id": agent["clusterID"], "range": rng},
        )
        m = data.get("getAgentMetrics")
        if not m:
            return {"message": "The agent has reported no metrics for this cluster yet."}
        apps = m.get("applications") or []
        m["nodes"] = (m.get("nodes") or [])[:50]
        m["applications"] = apps[:100]
        m["applications_total"] = len(apps)
        return m

    @mcp.tool(annotations=READ_ONLY, title="Get agent security findings")
    @guarded
    async def get_agent_security_findings(
        cluster_id: Annotated[str, Field(description="Cluster id from list_agents")],
        ctx: Context,
        severity: Annotated[Optional[str], Field(description="critical, high, medium, low or info")] = None,
        status: Annotated[Optional[str], Field(description="open, acknowledged, resolved or false_positive")] = None,
        limit: Limit = 25,
    ) -> Dict[str, Any]:
        """Security findings the agent raised for a cluster, with the suggested remediation."""
        api = get_api(ctx)
        sev = _upper_choice(severity, FINDING_SEVERITIES, "severity")
        st = _upper_choice(status, FINDING_STATUSES, "status")
        agent = await _own_agent(api, cluster_id)
        data = await api.graphql(
            """query Findings($id: ID!, $severity: SecuritySeverity, $status: FindingStatus) {
                 getSecurityFindings(clusterID: $id, severity: $severity, status: $status) {
                   id findingID severity findingType title description resourceType resourceName
                   resourceNamespace remediation status firstDetected lastSeen resolvedAt
                 }
               }""",
            {"id": agent["clusterID"], "severity": sev, "status": st},
        )
        found = [f for f in data.get("getSecurityFindings") or [] if f]
        shown = []
        for f in found[:_cap(limit)]:
            f["description"] = o.clip(f.get("description"), 500)
            f["remediation"] = o.clip(f.get("remediation"), 500)
            shown.append(f)
        return {"findings": shown, "shown": len(shown), "total": len(found)}

    @mcp.tool(annotations=READ_ONLY, title="Get agent health checks")
    @guarded
    async def get_agent_health_checks(
        cluster_id: Annotated[str, Field(description="Cluster id from list_agents")],
        ctx: Context,
        check_type: Annotated[Optional[str], Field(description="Limit to one kind of check")] = None,
    ) -> Dict[str, Any]:
        """Health checks the agent ran on a cluster, each healthy, warning or critical."""
        api = get_api(ctx)
        kind = _opt(check_type, "check_type", 60)
        agent = await _own_agent(api, cluster_id)
        data = await api.graphql(
            """query HealthChecks($id: ID!, $type: String) {
                 getHealthChecks(clusterID: $id, checkType: $type) {
                   id checkType status message checkedAt
                 }
               }""",
            {"id": agent["clusterID"], "type": kind},
        )
        checks = [c for c in data.get("getHealthChecks") or [] if c]
        for c in checks:
            c["message"] = o.clip(c.get("message"), 400)
        bad = [c for c in checks if c.get("status") in ("WARNING", "CRITICAL")]
        return {"checks": checks[:MAX_CHECKS], "count": len(checks), "needing_attention": len(bad)}

    # ============================================================ forecast
    @mcp.tool(annotations=READ_ONLY, title="Get resource forecast")
    @guarded
    async def get_resource_forecast(
        organization_id: OrgId,
        ctx: Context,
        app_name: Annotated[Optional[str], Field(description="Forecast one app instead of the whole organization")] = None,
    ) -> Dict[str, Any]:
        """Nia's short-term CPU and memory forecast: current usage, predicted peak and when, the
        model's confidence and recommendations. The charts are not returned."""
        api = get_api(ctx)
        org = await require_org(api, organization_id)
        slug = org.get("slug")
        if not slug:
            raise NifeAPIError("The organization has no slug, which the forecast needs.")
        if app_name:
            app = await _own_app(api, app_name)
            if app.get("organizationId") and app["organizationId"] != organization_id:
                raise NifeAPIError("That app belongs to a different organization.")
            path = f"/api/forecast/app/{quote(slug, safe='')}/{quote(app_name.strip(), safe='')}"
        else:
            path = f"/api/forecast/namespace/{quote(slug, safe='')}"
        data = await api.lstm_get(path)
        if not isinstance(data, dict) or not data:
            return {"message": "There are no usage metrics to forecast from yet for this scope."}
        return {"scope": app_name or "organization", **_forecast_view(data)}
