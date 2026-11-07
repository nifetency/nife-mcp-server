"""Read-only platform tools: delivery metrics, compliance, backups, capacity, usage, volumes,
hosts, workloads, clusters, credits and cost, failover.

Every tool goes through the GraphQL API with the caller's own token, so the backend resolvers
keep enforcing access. Apps are proven with the caller's own app lookup before any app-keyed
query, and organization ids are checked with require_org. Queries ask only for fields that are
safe to show: cloud host credentials and kubeconfig locations are never requested.
"""
import logging
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server import ops_helpers as o
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.ops_tools import MAX_ITEMS, Limit, OrgId, _cap, _date, _need, _opt, guarded
from nife_mcp_server.tool_utils import READ_ONLY, get_api, require_org

logger = logging.getLogger(__name__)

PLATFORM_INSTRUCTIONS = """\

PLATFORM, DELIVERY AND COMPLIANCE
- get_org_dora_metrics gives the four delivery metrics (frequency, lead time, change failure
  rate, time to restore). get_deployment_history and get_incident_history list the events.
- get_usage_summary and get_app_cost show running cost per app; estimate_deployment_cost prices
  a deployment before it is made. get_credits shows the prepaid balance.
- get_app_usage_metrics, get_volume_overview and get_app_failover inspect one app.
- list_clusters and get_cluster_capacity show regions and free capacity. list_cloud_hosts shows
  connected servers. list_workloads shows environments.
- list_backup_policies, get_restore_history, get_capacity_thresholds, get_audit_log_summary,
  get_regulatory_reporting and get_incident_regulatory_reports cover compliance evidence.
These tools only read. Cloud credentials and kubeconfig locations are never returned.
"""

REGULATORS = {"cert-in": "CERT-In", "dpb": "DPB", "rbi": "RBI", "sebi": "SEBI", "irdai": "IRDAI"}

AppName = Annotated[str, Field(description="Name of the app")]


async def _own_app(api: NifeAPI, app_name: str) -> Dict[str, Any]:
    """Prove the caller can see the app (lookup made with their own token) and return it."""
    name = _need(app_name, "app_name")
    app = await api.app(name)
    if not app or not app.get("id"):
        raise NifeAPIError(f"No app named '{name}' was found. Use list_apps to see your apps.")
    return app


def _stamp(day: Optional[str], name: str, end: bool = False) -> Optional[str]:
    text = _date(day, name)
    if not text:
        return None
    return f"{text}T23:59:59Z" if end else f"{text}T00:00:00Z"


def _range(start: Optional[str], end: Optional[str]) -> None:
    if start and end and start > end:
        raise ValueError("The start date must not be after the end date.")


def _caps(c: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not c:
        return None
    return {k: c.get(k) for k in ("cpu", "memory", "storage", "pods", "gpu") if c.get(k) is not None}


def _cost_breakdown(b: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not b:
        return None
    return {k: o.money(b.get(k)) for k in ("memoryCost", "cpuCost", "regionsCost", "totalCost")
            if b.get(k) is not None}


def register_platform_tools(mcp: FastMCP) -> None:
    # ============================================================ delivery
    @mcp.tool(annotations=READ_ONLY, title="Get organization DORA metrics")
    @guarded
    async def get_org_dora_metrics(
        organization_id: OrgId,
        ctx: Context,
        environment: Annotated[Optional[str], Field(description="Environment name to filter by")] = None,
        from_date: Annotated[Optional[str], Field(description="Start date, for example 2026-10-01")] = None,
        to_date: Annotated[Optional[str], Field(description="End date, for example 2026-10-31")] = None,
    ) -> Dict[str, Any]:
        """The four DORA delivery metrics for an organization: deployment frequency, lead time for
        changes, change failure rate and mean time to restore, with the totals behind them."""
        api = get_api(ctx)
        start, end = _stamp(from_date, "from_date"), _stamp(to_date, "to_date", end=True)
        _range(from_date, to_date)
        await require_org(api, organization_id)
        variables = {"org": organization_id, "env": _opt(environment, "environment"),
                     "from": start, "to": end}
        data = await api.graphql(
            """query Dora($org: String!, $env: String, $from: Time, $to: Time) {
                 getFourKeysMetrics(organizationID: $org, env: $env, from: $from, to: $to) {
                   deploymentFrequency leadTimeForChanges changeFailureRate meanTimeToRestore
                 }
                 getOverallDoraMetrics(organizationID: $org, env: $env, from: $from, to: $to) {
                   DeploymentFrequency { totalDeployments avgDailyDeployments }
                   LeadTimeForChanges { totalLeadTime avgLeadTime }
                   ChangeFailureRate { totalFailures failureRate }
                   MeanTimeToRestore { totalRestoreTime avgRestoreTime }
                 }
               }""",
            variables,
        )
        return {"four_keys": data.get("getFourKeysMetrics"), "totals": data.get("getOverallDoraMetrics")}

    @mcp.tool(annotations=READ_ONLY, title="Get deployment history")
    @guarded
    async def get_deployment_history(app_name: AppName, ctx: Context, limit: Limit = 20) -> Dict[str, Any]:
        """Deployment events of an app with status, commit and lead time."""
        api = get_api(ctx)
        app = await _own_app(api, app_name)
        data = await api.graphql(
            """query DeploymentHistory($appId: String!, $limit: Int) {
                 getDeploymentHistory(appId: $appId, limit: $limit) {
                   id deploymentId releaseId commitSha commitMessage status initiatedAt completedAt
                   commitTimestamp leadTimeSeconds
                 }
               }""",
            {"appId": app["id"], "limit": _cap(limit)},
        )
        events = data.get("getDeploymentHistory") or []
        for e in events:
            e["commitMessage"] = o.clip(e.get("commitMessage"), 300)
        return {"app": app_name, "deployments": events, "count": len(events)}

    @mcp.tool(annotations=READ_ONLY, title="Get incident history")
    @guarded
    async def get_incident_history(app_name: AppName, ctx: Context, limit: Limit = 20) -> Dict[str, Any]:
        """Incident events of an app with severity, recovery time and whether they were a change failure."""
        api = get_api(ctx)
        app = await _own_app(api, app_name)
        data = await api.graphql(
            """query IncidentHistory($appId: String!, $limit: Int) {
                 getIncidentHistory(appId: $appId, limit: $limit) {
                   id incidentId title severity status detectedAt resolvedAt recoveryTimeSeconds
                   isChangeFailure
                 }
               }""",
            {"appId": app["id"], "limit": _cap(limit)},
        )
        events = data.get("getIncidentHistory") or []
        return {"app": app_name, "incidents": events, "count": len(events)}

    # =========================================================== compliance
    @mcp.tool(annotations=READ_ONLY, title="Get audit log summary")
    @guarded
    async def get_audit_log_summary(ctx: Context) -> Dict[str, Any]:
        """Size and age of the company audit trail and whether old entries are deleted
        automatically. Organization admins only; the backend enforces that."""
        data = await get_api(ctx).graphql(
            """query AuditSummary {
                 auditLogSummary {
                   totalEntries entriesLast30Days oldestEntryAt usersWithActivity autoDeletes
                 }
               }"""
        )
        return data.get("auditLogSummary") or {"message": "No audit summary is available."}

    @mcp.tool(annotations=READ_ONLY, title="Get restore history")
    @guarded
    async def get_restore_history(
        organization_id: OrgId,
        ctx: Context,
        days: Annotated[int, Field(description="Look-back window in days (1-365)", ge=1, le=365)] = 90,
    ) -> Dict[str, Any]:
        """Volume snapshot restore attempts for an organization: counts and the latest result."""
        api = get_api(ctx)
        await require_org(api, organization_id)
        data = await api.graphql(
            """query RestoreHistory($org: String!, $days: Int) {
                 restoreHistorySummary(orgId: $org, days: $days) {
                   days attempts successes lastSuccessAt lastAttemptAt lastAttemptSucceeded
                   lastAttemptApp lastAttemptMessage
                 }
               }""",
            {"org": organization_id, "days": days},
        )
        return data.get("restoreHistorySummary") or {"message": "No restore history is available."}

    @mcp.tool(annotations=READ_ONLY, title="Get regulatory reporting summary")
    @guarded
    async def get_regulatory_reporting(
        organization_id: OrgId,
        regulator: Annotated[str, Field(description="One of CERT-In, DPB, RBI, SEBI, IRDAI")],
        ctx: Context,
        days: Annotated[int, Field(description="Look-back window in days (1-730)", ge=1, le=730)] = 180,
    ) -> Dict[str, Any]:
        """How many critical and high incidents were reported to a regulator on time, late, or not
        at all, and how many are open past the deadline."""
        api = get_api(ctx)
        key = (regulator or "").strip().lower()
        if key not in REGULATORS:
            raise ValueError("regulator must be one of: " + ", ".join(REGULATORS.values()))
        org = await require_org(api, organization_id)
        slug = org.get("slug")
        if not slug:
            raise NifeAPIError("The organization has no slug, which this report needs.")
        data = await api.graphql(
            """query RegReport($org: ID!, $reg: String!, $days: Int) {
                 regulatoryReportingSummary(orgId: $org, regulator: $reg, days: $days) {
                   regulator days deadlineHours reportableIncidents reportedOnTime reportedLate
                   notReported openAndOverdue
                 }
               }""",
            {"org": slug, "reg": REGULATORS[key], "days": days},
        )
        return data.get("regulatoryReportingSummary") or {"message": "No reporting data is available."}

    @mcp.tool(annotations=READ_ONLY, title="Get incident regulatory reports")
    @guarded
    async def get_incident_regulatory_reports(
        incident_id: Annotated[str, Field(description="Incident id from list_incidents")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Reports made to regulators for one incident, with timing against each deadline."""
        data = await get_api(ctx).graphql(
            """query IncidentReports($id: ID!) {
                 incidentRegulatoryReports(incidentId: $id) {
                   incidentId regulator reportedAt reference reportedBy hoursAfterDetection
                   deadlineHours onTime
                 }
               }""",
            {"id": _need(incident_id, "incident_id")},
        )
        reports = data.get("incidentRegulatoryReports") or []
        return {"reports": reports, "count": len(reports)}

    @mcp.tool(annotations=READ_ONLY, title="List backup policies")
    @guarded
    async def list_backup_policies(
        app_names: Annotated[List[str], Field(description="Apps to list policies for (up to 20)", min_length=1, max_length=20)],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Scheduled volume backup policies: schedule (UTC cron), retention, last run and status."""
        api = get_api(ctx)
        names = []
        for n in app_names:
            names.append((await _own_app(api, n))["name"])
        data = await api.graphql(
            """query Backups($names: [String!]!) {
                 backupPolicies(appNames: $names) {
                   id appName name schedule retentionDays enabled nextRunAt lastRunAt lastStatus
                   lastError lastSnapshotName
                 }
               }""",
            {"names": names},
        )
        policies = data.get("backupPolicies") or []
        for p in policies:
            p["lastError"] = o.clip(p.get("lastError"), 400)
        return {"policies": policies, "count": len(policies)}

    @mcp.tool(annotations=READ_ONLY, title="Get capacity thresholds")
    @guarded
    async def get_capacity_thresholds(organization_id: OrgId, ctx: Context) -> Dict[str, Any]:
        """Tight and critical thresholds for CPU, memory and disk: platform default, this
        organization's overrides and the effective values in use."""
        api = get_api(ctx)
        await require_org(api, organization_id)
        line = "{ tight critical }"
        over = "{ tight critical }"
        data = await api.graphql(
            f"""query Thresholds($org: String!) {{
                 capacityThresholds(orgId: $org) {{
                   orgId
                   defaults {{ cpu {line} memory {line} disk {line} }}
                   overrides {{ cpu {over} memory {over} disk {over} }}
                   effective {{ cpu {line} memory {line} disk {line} }}
                 }}
               }}""",
            {"org": organization_id},
        )
        return data.get("capacityThresholds") or {"message": "No thresholds are available."}

    @mcp.tool(annotations=READ_ONLY, title="Get usage report schedule")
    @guarded
    async def get_usage_report_subscription(organization_id: OrgId, ctx: Context) -> Dict[str, Any]:
        """Whether the caller gets the emailed usage and configuration report (off, weekly or monthly)."""
        api = get_api(ctx)
        await require_org(api, organization_id)
        data = await api.graphql(
            """query UsageReportSub($org: String!) {
                 usageReportSubscription(orgId: $org) { orgId frequency lastSentAt }
               }""",
            {"org": organization_id},
        )
        return data.get("usageReportSubscription") or {"frequency": "off"}

    # ============================================================== usage
    @mcp.tool(annotations=READ_ONLY, title="Get app usage metrics")
    @guarded
    async def get_app_usage_metrics(
        app_name: AppName,
        ctx: Context,
        start_date: Annotated[Optional[str], Field(description="Start date, for example 2026-10-01")] = None,
        end_date: Annotated[Optional[str], Field(description="End date, for example 2026-10-31")] = None,
        points: Annotated[int, Field(description="Recent data points to include (0-100)", ge=0, le=100)] = 0,
    ) -> Dict[str, Any]:
        """CPU, memory and network usage of an app: averages, peaks and totals for the period,
        plus the most recent raw data points when asked."""
        api = get_api(ctx)
        start, end = _date(start_date, "start_date"), _date(end_date, "end_date")
        _range(start, end)
        app = await _own_app(api, app_name)
        variables = {"appId": app["id"], "start": start, "end": end, "limit": points or 1}
        data = await api.graphql(
            """query AppUsage($appId: String!, $start: String, $end: String, $limit: Int) {
                 getUsageMetricsSummary(appId: $appId, startDate: $start, endDate: $end) {
                   periodStart periodEnd avgCpuUsage maxCpuUsage avgMemoryUsage maxMemoryUsage
                   totalNetworkRxMB totalNetworkTxMB dataPoints
                 }
                 getUsageMetrics(appId: $appId, startDate: $start, endDate: $end, limit: $limit) {
                   timestamp cpuUsage memoryUsage cpuCores memoryMB networkRxMB networkTxMB
                   diskUsageMB podName billedAmount
                 }
               }""",
            variables,
        )
        out: Dict[str, Any] = {"app": app_name, "summary": data.get("getUsageMetricsSummary")}
        if points:
            out["points"] = (data.get("getUsageMetrics") or [])[:points]
        return out

    @mcp.tool(annotations=READ_ONLY, title="Get usage summary")
    @guarded
    async def get_usage_summary(ctx: Context) -> Dict[str, Any]:
        """Running cost of the account: hourly, daily and monthly estimate, days of credit left
        and the cost of each app."""
        data = await get_api(ctx).graphql(
            """query UsageSummary {
                 getUsageSummary {
                   billingMode currentBalance totalHourlyCost estimatedDailyCost estimatedMonthlyCost
                   daysRemaining runningAppsCount suspendedAppsCount currency calculatedAt
                   autoRechargeEnabled autoRechargeThreshold
                   appCosts { appName status hourlyCost dailyCost monthlyCost memory cpu replicas regionCount }
                 }
               }"""
        )
        s = data.get("getUsageSummary")
        if not s:
            return {"message": "No usage summary is available."}
        costs = sorted(s.get("appCosts") or [], key=lambda a: -(a.get("monthlyCost") or 0))
        s["appCosts"] = costs[:30]
        s["apps_total"] = len(costs)
        return s

    @mcp.tool(annotations=READ_ONLY, title="Get app cost")
    @guarded
    async def get_app_cost(app_name: AppName, ctx: Context) -> Dict[str, Any]:
        """Current hourly, daily and monthly cost of one app with the memory, CPU and region split."""
        api = get_api(ctx)
        app = await _own_app(api, app_name)
        data = await api.graphql(
            """query AppCost($appId: String!) {
                 getAppCurrentCost(appId: $appId) {
                   appName status hourlyCost dailyCost monthlyCost currency lastCalculatedAt
                   resources { memory cpu replicas regions regionCount }
                   breakdown { memoryCost cpuCost regionsCost totalCost }
                 }
               }""",
            {"appId": app["id"]},
        )
        return data.get("getAppCurrentCost") or {"message": "No cost data is available for this app."}

    @mcp.tool(annotations=READ_ONLY, title="Estimate deployment cost")
    @guarded
    async def estimate_deployment_cost(
        ctx: Context,
        memory: Annotated[Optional[str], Field(description="Memory size as the platform names it, for example 512Mi")] = None,
        cpu: Annotated[Optional[str], Field(description="CPU size, for example 500m")] = None,
        replicas: Annotated[Optional[int], Field(description="Number of replicas", ge=1, le=100)] = None,
        regions: Annotated[Optional[List[str]], Field(description="Region codes", max_length=20)] = None,
        organization_id: Annotated[Optional[str], Field(description="Organization id from list_organizations")] = None,
    ) -> Dict[str, Any]:
        """Price a deployment before making it. Nothing is created or charged."""
        api = get_api(ctx)
        if organization_id:
            await require_org(api, organization_id)
        inp = {"memory": _opt(memory, "memory", 30), "cpu": _opt(cpu, "cpu", 30), "replicas": replicas,
               "regions": [_need(r, "region", 50) for r in regions] if regions else None,
               "orgId": organization_id}
        data = await api.graphql(
            """query EstimateCost($input: DeploymentCostEstimateInput!) {
                 estimateDeploymentCost(input: $input) {
                   hourlyCost dailyCost monthlyCost currency calculatedAt
                   breakdown { memoryCost cpuCost regionsCost totalCost }
                 }
               }""",
            {"input": inp},
        )
        return data.get("estimateDeploymentCost") or {"message": "No estimate is available."}

    @mcp.tool(annotations=READ_ONLY, title="Get credits")
    @guarded
    async def get_credits(
        ctx: Context,
        transactions: Annotated[int, Field(description="Recent transactions to include (0-50)", ge=0, le=50)] = 10,
    ) -> Dict[str, Any]:
        """Prepaid credit balance, billing mode, auto-recharge settings and recent transactions."""
        api = get_api(ctx)
        data = await api.graphql(
            """query Credits($n: Int) {
                 getMyCredits {
                   balance unbilledUsage billingMode currency lifetimeCreditsUsed
                   lifetimeCreditsPurchased lastRechargedAt
                 }
                 getAutoRechargeSettings { enabled threshold rechargeAmount }
                 getCreditTransactions(limit: $n) {
                   transactionType amount balanceBefore balanceAfter description createdAt
                 }
               }""",
            {"n": max(transactions, 1)},
        )
        out = {"credits": data.get("getMyCredits"), "auto_recharge": data.get("getAutoRechargeSettings")}
        if transactions:
            out["transactions"] = [
                {**t, "description": o.clip(t.get("description"), 200)}
                for t in (data.get("getCreditTransactions") or [])[:transactions]
            ]
        return out

    # ========================================================= per-app infra
    @mcp.tool(annotations=READ_ONLY, title="Get volume overview")
    @guarded
    async def get_volume_overview(app_name: AppName, ctx: Context, snapshots: Limit = 10) -> Dict[str, Any]:
        """Volumes of an app with size and mount path, health, usage, and recent snapshots."""
        api = get_api(ctx)
        app = await _own_app(api, app_name)
        data = await api.graphql(
            """query Volumes($appId: String!) {
                 getVolumeByAppId(appId: $appId) { name path containerPath size accessMode isRead }
                 getVolumeHealth(appId: $appId) { volumeName healthStatus usagePercentage lastChecked errorMessage }
                 getVolumeUsageStats(appId: $appId) { totalSize usedSize availableSize usagePercentage }
                 getVolumeSnapshots(appId: $appId) { id snapshotName description sizeBytes status createdAt completedAt }
               }""",
            {"appId": app["id"]},
        )
        snaps = data.get("getVolumeSnapshots") or []
        snaps = sorted(snaps, key=lambda s: s.get("createdAt") or "", reverse=True)
        health = data.get("getVolumeHealth")
        if health:
            health["errorMessage"] = o.clip(health.get("errorMessage"), 400)
        return {
            "app": app_name, "volumes": data.get("getVolumeByAppId") or [], "health": health,
            "usage": data.get("getVolumeUsageStats"),
            "snapshots": snaps[:_cap(snapshots)], "snapshot_count": len(snaps),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get app failover")
    @guarded
    async def get_app_failover(app_name: AppName, ctx: Context) -> Dict[str, Any]:
        """Failover state of an app: primary and backup backends, their health and which one serves."""
        api = get_api(ctx)
        await _own_app(api, app_name)
        data = await api.graphql(
            """query Failover($name: String!) {
                 appFailover(appName: $name) {
                   appName host enabled lbPolicy healthCheckPath failoverThreshold servingTarget
                   targets { url role healthy failCount latencyMs serving }
                 }
               }""",
            {"name": app_name.strip()},
        )
        return data.get("appFailover") or {"message": "No failover data is available."}

    # =========================================================== org infra
    @mcp.tool(annotations=READ_ONLY, title="List cloud hosts")
    @guarded
    async def list_cloud_hosts(organization_id: OrgId, ctx: Context) -> Dict[str, Any]:
        """Connected servers and VMs of an organization with type, zone, status and recent actions.
        Access keys and secrets are never requested."""
        api = get_api(ctx)
        await require_org(api, organization_id)
        data = await api.graphql(
            """query Hosts($org: String) {
                 getHost(orgId: $org) {
                   id orgName type status zone instanceName instanceId createdBy createdAt
                   InstanceActivity { Type Activities Message createdAt }
                 }
               }""",
            {"org": organization_id},
        )
        hosts = data.get("getHost") or []
        for h in hosts:
            if h:
                h["InstanceActivity"] = [
                    {**a, "Message": o.clip(a.get("Message"), 200)} for a in (h.get("InstanceActivity") or [])[:10] if a
                ]
        return {"hosts": [h for h in hosts if h], "count": len(hosts)}

    @mcp.tool(annotations=READ_ONLY, title="List workloads")
    @guarded
    async def list_workloads(
        ctx: Context,
        organization_id: Annotated[Optional[str], Field(description="Limit to one organization")] = None,
    ) -> Dict[str, Any]:
        """Workload environments with endpoint and owning organization. Without an organization,
        lists the caller's own."""
        api = get_api(ctx)
        fields = "id environmentName environmentEndpoint organizationName createdAt"
        if organization_id:
            await require_org(api, organization_id)
            data = await api.graphql(
                f"""query Workloads($org: String) {{
                     getWorkloadMangementByorgnizationId(orgId: $org) {{ {fields} }}
                   }}""",
                {"org": organization_id},
            )
            items = data.get("getWorkloadMangementByorgnizationId") or []
        else:
            data = await api.graphql(f"query MyWorkloads {{ getWorkloadMangementByUser {{ {fields} }} }}")
            items = data.get("getWorkloadMangementByUser") or []
        return {"workloads": items[:MAX_ITEMS * 4], "count": len(items)}

    @mcp.tool(annotations=READ_ONLY, title="List clusters")
    @guarded
    async def list_clusters(
        ctx: Context,
        organization_id: Annotated[Optional[str], Field(description="Limit to one organization")] = None,
    ) -> Dict[str, Any]:
        """Regions and clusters with provider, type, load balancer and suspension state.
        Kubeconfig paths and addresses are never requested."""
        api = get_api(ctx)
        fields = ("id regionCode regionName providerType clusterType isDefault isSuspended "
                  "suspendedReason suspendedAt loadBalancerURL")
        if organization_id:
            await require_org(api, organization_id)
            data = await api.graphql(
                f"""query OrgClusters($org: String) {{
                     getClusterDetailsByOrgIdMultipleReg(orgId: $org) {{ {fields} }}
                   }}""",
                {"org": organization_id},
            )
            items = data.get("getClusterDetailsByOrgIdMultipleReg") or []
        else:
            data = await api.graphql(f"query MyClusters {{ getUserAddedRegions {{ {fields} }} }}")
            items = data.get("getUserAddedRegions") or []
        items = [c for c in items if c]
        return {"clusters": items, "count": len(items)}

    @mcp.tool(annotations=READ_ONLY, title="Get cluster capacity")
    @guarded
    async def get_cluster_capacity(
        region_code: Annotated[str, Field(description="Region code from list_clusters")],
        ctx: Context,
        organization_id: Annotated[Optional[str], Field(description="Organization id, to include its quotas")] = None,
    ) -> Dict[str, Any]:
        """Total, allocated and available CPU, memory, storage and pods of a cluster, node count,
        recommended sizes and namespace quotas."""
        api = get_api(ctx)
        code = _need(region_code, "region_code", 50)
        if organization_id:
            await require_org(api, organization_id)
        cap = "{ cpu memory storage pods gpu }"
        rec = "{ cpu memory cpuRequest memoryRequest description }"
        quota = "{ cpu memory pods }"
        data = await api.graphql(
            f"""query Capacity($input: GetClusterResourceLimitsInput!) {{
                 getClusterResourceLimits(input: $input) {{
                   regionCode regionName clusterType nodeCount
                   totalResources {cap} allocatedResources {cap} availableResources {cap}
                   recommendedLimits {{ small {rec} medium {rec} large {rec} xlarge {rec} }}
                   resourceQuotas {{ namespace hard {quota} used {quota} }}
                 }}
               }}""",
            {"input": {"regionCode": code, "organizationId": organization_id, "includeNodeDetails": False}},
        )
        c = data.get("getClusterResourceLimits")
        if not c:
            return {"message": "No capacity data is available for this region."}
        for k in ("totalResources", "allocatedResources", "availableResources"):
            c[k] = _caps(c.get(k))
        c["resourceQuotas"] = (c.get("resourceQuotas") or [])[:20]
        return c
