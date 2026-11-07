"""NERO (AI SRE) and FinOps tools for the hosted MCP server.

NERO queries live in the GraphQL schema; billing is GraphQL too; cost recommendations and
forecasts come from the FinOps REST service the dashboard calls. Everything is made with the
caller's own token. Org-keyed queries first prove membership (require_org), and ids that are
not org-keyed (alerts, billing cycles) are checked against the caller's own lists before use.
"""
import asyncio
import functools
import logging
import re
from typing import Annotated, Any, Dict, List, Optional
from urllib.parse import quote

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server import ops_helpers as o
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.tool_utils import (
    DESTRUCTIVE, READ_ONLY, WRITE_IDEMPOTENT, fail, get_api, require_org,
)

logger = logging.getLogger(__name__)

OPS_INSTRUCTIONS = """\

RELIABILITY (NERO) AND COST (FINOPS)
Most NERO tools need an organization_id: call list_organizations first.
- get_health_insights is the best starting point: overall health, open incidents, anomalies,
  failure predictions and recommended actions in one call.
- list_incidents / get_incident show incidents and their post-mortems. get_root_cause_analysis
  runs an AI analysis (slow); pass refresh=true only when a new analysis is needed.
- list_alerts shows alerts. acknowledge_alert and resolve_alert change alert state, so confirm
  with the user first.
- list_anomalies, predict_failures, get_slo_status and get_health_report drill into one app.
- search_knowledge_base finds past incidents and their fixes by error text.
Cost: get_spending_overview gives spend against limits. list_cost_recommendations ranks savings
opportunities; get_cost_forecast and get_cost_anomalies cover the outlook. list_billing_cycles,
get_billing_items, list_invoices and get_cloud_billing_summary cover billing detail.
get_cost_breakdown groups cost by provider, service or region. search_finops_resources and
get_finops_resource_stats show the multi-cloud inventory behind the cost; get_cost_usage_patterns
shows what the recommendations are based on.
apply_cost_recommendation carries out one recommendation and may change real infrastructure:
call it first without confirm to show the user what it would do, and only call it with
confirm=true after the user has agreed.
Amounts are reported as the backend returns them and are never estimated.
"""

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_ITEMS = 50

OrgId = Annotated[str, Field(description="Organization id from list_organizations")]
Limit = Annotated[int, Field(description="Maximum number of items (1-50)", ge=1, le=MAX_ITEMS)]


def _cap(n: int, hi: int = MAX_ITEMS) -> int:
    return max(1, min(int(n), hi))


def _need(value: Optional[str], name: str, limit: int = 200) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{name} is required.")
    if len(text) > limit:
        raise ValueError(f"{name} is too long (max {limit} characters).")
    return text


def _opt(value: Optional[str], name: str, limit: int = 200) -> Optional[str]:
    text = (value or "").strip()
    return _need(text, name, limit) if text else None


def _date(value: Optional[str], name: str) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    if not DATE_RE.match(text):
        raise ValueError(f"{name} must look like 2026-10-01.")
    return text


def guarded(fn):
    """Turn validation and backend errors into tool errors the model can read."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
    return wrapper


def _anomaly_view(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": a.get("id"), "app": a.get("appName"), "service": a.get("serviceName"),
        "metric": a.get("metricType"), "type": a.get("type"), "severity": a.get("severity"),
        "description": o.clip(a.get("description"), 600), "score": a.get("anomalyScore"),
        "expected": a.get("expectedValue"), "actual": a.get("actualValue"),
        "deviation": a.get("deviation"), "method": a.get("detectionMethod"),
        "confidence_pct": o.pct(a.get("confidence")), "detected_at": a.get("detectedAt"),
        "acknowledged": a.get("acknowledged"), "incident_id": a.get("incidentId"),
        "region": a.get("clusterRegion"),
    }


def _prediction_view(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": p.get("id"), "app": p.get("appName"), "service": p.get("serviceName"),
        "type": p.get("predictionType"), "predicted_issue": o.clip(p.get("predictedIssue"), 600),
        "probability_pct": o.pct(p.get("probability")),
        "minutes_to_occurrence": p.get("timeToOccurrenceMinutes"), "severity": p.get("severity"),
        "root_cause": o.clip(p.get("rootCause"), 600), "confidence_pct": o.pct(p.get("confidence")),
        "predicted_at": p.get("predictedAt"), "region": p.get("clusterRegion"),
        "recommended_actions": [o.action_view(a) for a in (p.get("recommendedActions") or [])[:8]],
    }


async def _own_alert(api: NifeAPI, alert_id: str) -> Dict[str, Any]:
    """Alert ids are not org-keyed, so prove the alert is one the caller can see."""
    for alert in await api.sre_alerts(None, None, None, 200):
        if alert.get("id") == alert_id:
            return alert
    raise NifeAPIError("No alert with that id was found. Use list_alerts to see your alerts.")


async def _own_cycle(api: NifeAPI, cycle_id: str) -> Dict[str, Any]:
    for cycle in await api.billing_cycles(50):
        if cycle.get("id") == cycle_id:
            return cycle
    raise NifeAPIError("No billing cycle with that id was found. Use list_billing_cycles first.")


async def _recommendation_payload(api: NifeAPI) -> Any:
    return await api.finops_get("/ml/recommendations")


async def _own_recommendation(api: NifeAPI, rec_id: str) -> Dict[str, Any]:
    """Recommendation ids are not org-keyed, so prove the id is in the caller's own list first."""
    data = await _recommendation_payload(api)
    for raw in o.unwrap_list(data, "recommendations", "data"):
        if isinstance(raw, dict):
            rec = o.normalize_recommendation(raw)
            if rec["id"] == rec_id:
                return rec
    raise NifeAPIError(
        "No cost recommendation with that id was found. Use list_cost_recommendations to see yours."
    )


def register_ops_tools(mcp: FastMCP) -> None:
    # ================================================================== NERO
    @mcp.tool(annotations=READ_ONLY, title="Get health insights")
    @guarded
    async def get_health_insights(
        organization_id: OrgId,
        ctx: Context,
        app_name: Annotated[Optional[str], Field(description="Limit to one app")] = None,
        cluster_id: Annotated[Optional[str], Field(description="Limit to one cluster")] = None,
    ) -> Dict[str, Any]:
        """AI health summary for an organization or one app: overall health, score, open incidents,
        active anomalies, critical failure predictions and recommended actions. Start here."""
        api = get_api(ctx)
        await require_org(api, organization_id)
        data = await api.sre_health_insights(
            organization_id, _opt(app_name, "app_name"), _opt(cluster_id, "cluster_id")
        )
        if not data:
            return {"message": "No health insights are available yet for this scope."}
        return {
            "overall_health": data.get("overallHealth"), "health_score": data.get("healthScore"),
            "critical_issues": data.get("criticalIssues"), "warnings": data.get("warnings"),
            "open_incidents": data.get("openIncidents"),
            "insights": [o.clip(i, 600) for i in (data.get("insights") or [])[:10]]
            if isinstance(data.get("insights"), list) else o.clip(data.get("insights")),
            "trend_analysis": o.clip(data.get("trendAnalysis"), 1200),
            "active_anomalies": [
                {k: a.get(k) for k in ("id", "appName", "serviceName", "metricType", "severity",
                                        "description", "detectedAt")}
                for a in (data.get("activeAnomalies") or [])[:10]
            ],
            "critical_predictions": (data.get("criticalPredictions") or [])[:10],
            "recommendations": [o.action_view(a) for a in (data.get("recommendations") or [])[:10]],
            "generated_at": data.get("generatedAt"),
        }

    @mcp.tool(annotations=READ_ONLY, title="List incidents")
    @guarded
    async def list_incidents(
        organization_id: OrgId,
        ctx: Context,
        status: Annotated[Optional[str], Field(description="open, investigating, resolved or closed")] = None,
        severity: Annotated[Optional[str], Field(description="critical, high, medium, low, warning or info")] = None,
        limit: Limit = 20,
    ) -> Dict[str, Any]:
        """List incidents with severity, status and the detected root cause."""
        api = get_api(ctx)
        st = o.check_choice(status, o.INCIDENT_STATUSES, "status")
        sev = o.check_choice(severity, o.SEVERITIES, "severity")
        await require_org(api, organization_id)
        items = await api.sre_incidents(organization_id, st, sev, _cap(limit))
        return {"incidents": [o.incident_view(i) for i in items], "count": len(items)}

    @mcp.tool(annotations=READ_ONLY, title="Get incident")
    @guarded
    async def get_incident(
        organization_id: OrgId,
        incident_id: Annotated[str, Field(description="Incident id from list_incidents")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Full incident record: description, resolution, indicators and post-mortem."""
        api = get_api(ctx)
        wanted = _need(incident_id, "incident_id")
        await require_org(api, organization_id)
        for inc in await api.sre_incidents(organization_id, None, None, 100, detail=True):
            if inc.get("id") == wanted:
                return o.incident_view(inc, detail=True)
        raise NifeAPIError("No incident with that id was found among the latest 100. Use list_incidents.")

    @mcp.tool(annotations=READ_ONLY, title="Get root cause analysis")
    @guarded
    async def get_root_cause_analysis(
        organization_id: OrgId,
        app_name: Annotated[str, Field(description="App the incident belongs to")],
        service_name: Annotated[str, Field(description="Service inside the app")],
        error_type: Annotated[str, Field(description="Error or incident type, for example CrashLoopBackOff")],
        ctx: Context,
        incident_id: Annotated[Optional[str], Field(description="Incident to analyse, if known")] = None,
        refresh: Annotated[bool, Field(description="Run a new analysis instead of reusing the last one")] = False,
    ) -> Dict[str, Any]:
        """AI root cause analysis: primary cause, causal chain, timeline, impacted services and
        recommended fixes. Can take up to two minutes when refresh is true."""
        api = get_api(ctx)
        app = _need(app_name, "app_name")
        svc = _need(service_name, "service_name")
        err = _need(error_type, "error_type")
        await require_org(api, organization_id)
        data = await api.sre_root_cause(
            incident_id=_opt(incident_id, "incident_id"), app_name=app, service_name=svc,
            error_type=err, org_id=organization_id, refresh=refresh,
        )
        if not data:
            return {"message": "No root cause analysis is available for this request."}
        return {
            "incident_id": data.get("incidentId"), "app": data.get("appName"),
            "service": data.get("serviceName"), "error_type": data.get("errorType"),
            "primary_root_cause": o.clip(data.get("primaryRootCause"), 1200),
            "contributing_factors": (data.get("contributingFactors") or [])[:10],
            "causal_chain": (data.get("causalChain") or [])[:15],
            "timeline": (data.get("timeline") or [])[:20],
            "impacted_services": (data.get("impactedServices") or [])[:20],
            "ai_analysis": o.clip(data.get("aiAnalysis")),
            "confidence_pct": o.pct(data.get("confidence")), "analyzed_at": data.get("analyzedAt"),
            "recommended_fixes": [o.action_view(a) for a in (data.get("recommendedFixes") or [])[:10]],
        }

    @mcp.tool(annotations=READ_ONLY, title="List alerts")
    @guarded
    async def list_alerts(
        organization_id: OrgId,
        ctx: Context,
        status: Annotated[Optional[str], Field(description="firing, active, acknowledged or resolved")] = None,
        severity: Annotated[Optional[str], Field(description="critical, high, medium, low, warning or info")] = None,
        limit: Limit = 20,
    ) -> Dict[str, Any]:
        """List alerts with severity, status and who acknowledged or resolved them."""
        api = get_api(ctx)
        st = o.check_choice(status, o.ALERT_STATUSES, "status")
        sev = o.check_choice(severity, o.SEVERITIES, "severity")
        await require_org(api, organization_id)
        items = await api.sre_alerts(organization_id, st, sev, _cap(limit))
        return {"alerts": [o.alert_view(a) for a in items], "count": len(items)}

    @mcp.tool(annotations=WRITE_IDEMPOTENT, title="Acknowledge alert")
    @guarded
    async def acknowledge_alert(
        alert_id: Annotated[str, Field(description="Alert id from list_alerts")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Mark an alert as acknowledged. Confirm with the user before calling."""
        api = get_api(ctx)
        wanted = _need(alert_id, "alert_id")
        await _own_alert(api, wanted)
        res = await api.sre_acknowledge_alert(wanted)
        if not res:
            raise NifeAPIError("The backend did not confirm the acknowledgement.")
        return {"id": res.get("id"), "title": res.get("title"), "status": res.get("status"),
                "acknowledged_by": res.get("acknowledgedBy"), "acknowledged_at": res.get("acknowledgedAt")}

    @mcp.tool(annotations=WRITE_IDEMPOTENT, title="Resolve alert")
    @guarded
    async def resolve_alert(
        alert_id: Annotated[str, Field(description="Alert id from list_alerts")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Mark an alert as resolved. Confirm with the user before calling."""
        api = get_api(ctx)
        wanted = _need(alert_id, "alert_id")
        await _own_alert(api, wanted)
        res = await api.sre_resolve_alert(wanted)
        if not res:
            raise NifeAPIError("The backend did not confirm the resolution.")
        return {"id": res.get("id"), "title": res.get("title"), "status": res.get("status"),
                "resolved_by": res.get("resolvedBy"), "resolved_at": res.get("resolvedAt")}

    @mcp.tool(annotations=READ_ONLY, title="List anomalies")
    @guarded
    async def list_anomalies(
        organization_id: OrgId,
        ctx: Context,
        app_name: Annotated[Optional[str], Field(description="Limit to one app")] = None,
        service_name: Annotated[Optional[str], Field(description="Limit to one service")] = None,
        severity: Annotated[Optional[str], Field(description="critical, high, medium, low, warning or info")] = None,
        time_range: Annotated[Optional[str], Field(description="For example 1h, 24h or 7d")] = None,
        limit: Limit = 20,
    ) -> Dict[str, Any]:
        """Anomalies found by the NERO detection model, with expected versus actual values."""
        api = get_api(ctx)
        sev = o.check_choice(severity, o.SEVERITIES, "severity")
        rng = o.check_period(time_range, "24h") if time_range else None
        await require_org(api, organization_id)
        items = await api.sre_anomalies(
            organization_id, _opt(app_name, "app_name"), _opt(service_name, "service_name"),
            sev, rng, _cap(limit),
        )
        return {"anomalies": [_anomaly_view(a) for a in items], "count": len(items)}

    @mcp.tool(annotations=READ_ONLY, title="Predict failures")
    @guarded
    async def predict_failures(
        organization_id: OrgId,
        app_name: Annotated[str, Field(description="App to analyse")],
        ctx: Context,
        service_name: Annotated[Optional[str], Field(description="Limit to one service")] = None,
        time_horizon: Annotated[Optional[str], Field(description="For example 1h, 6h or 24h")] = None,
    ) -> Dict[str, Any]:
        """Predicted failures for an app with probability, time to occurrence and suggested actions."""
        api = get_api(ctx)
        app = _need(app_name, "app_name")
        horizon = o.check_period(time_horizon, "1h") if time_horizon else None
        await require_org(api, organization_id)
        items = await api.sre_predictions(organization_id, app, _opt(service_name, "service_name"), horizon)
        return {"predictions": [_prediction_view(p) for p in items[:MAX_ITEMS]], "count": len(items)}

    @mcp.tool(annotations=READ_ONLY, title="Get SLO status")
    @guarded
    async def get_slo_status(
        organization_id: OrgId,
        ctx: Context,
        app_name: Annotated[Optional[str], Field(description="Limit to one app")] = None,
        service_name: Annotated[Optional[str], Field(description="Limit to one service")] = None,
        window: Annotated[Optional[str], Field(description="For example 7d or 30d")] = None,
    ) -> Dict[str, Any]:
        """Availability against the SLO target, error budget left and burn rate, with plain flags."""
        api = get_api(ctx)
        win = o.check_period(window, "30d") if window else None
        await require_org(api, organization_id)
        slo = await api.sre_slo(
            organization_id, _opt(app_name, "app_name"), _opt(service_name, "service_name"), win
        )
        if not slo:
            return {"message": "No SLO data is available for this scope."}
        return {
            "app": slo.get("appName"), "service": slo.get("serviceName"), "window": slo.get("window"),
            "availability": slo.get("availability"), "slo_target": slo.get("sloTarget"),
            "error_budget_remaining_pct": slo.get("errorBudgetPct"),
            "burn_rate": slo.get("burnRate"), "burn_rate_1h": slo.get("burnRate1h"),
            "burn_rate_6h": slo.get("burnRate6h"), "breaching": slo.get("breaching"),
            "days_remaining": slo.get("daysRemaining"), "source": slo.get("source"),
            "generated_at": slo.get("generatedAt"), "attention": o.slo_attention(slo),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get health report")
    @guarded
    async def get_health_report(
        organization_id: OrgId,
        app_name: Annotated[str, Field(description="App to inspect")],
        service_name: Annotated[str, Field(description="Service inside the app")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Deep health report for one service: cluster and pod health, log errors and recommendations.
        Can take up to two minutes."""
        api = get_api(ctx)
        app = _need(app_name, "app_name")
        svc = _need(service_name, "service_name")
        await require_org(api, organization_id)
        r = await api.sre_health_report(app, svc, organization_id)
        if not r:
            return {"message": "No health report is available for this service."}
        logs = r.get("logAnalysis") or {}
        return {
            "app": r.get("appName"), "service": r.get("serviceName"), "timestamp": r.get("timestamp"),
            "health_score": r.get("overallHealthScore"), "health_status": r.get("healthStatus"),
            "errors": (r.get("errors") or [])[:10], "monitoring": r.get("monitoringData"),
            "cluster": r.get("clusterHealth"),
            "logs": {
                "total_errors": logs.get("totalErrors"), "total_warnings": logs.get("totalWarnings"),
                "top_errors": (logs.get("topErrors") or [])[:10],
            },
            "recommendations": [o.action_view(a) for a in (r.get("recommendations") or [])[:10]],
        }

    @mcp.tool(annotations=READ_ONLY, title="Search incident knowledge base")
    @guarded
    async def search_knowledge_base(
        query: Annotated[str, Field(description="Error text or symptom to look up")],
        ctx: Context,
        limit: Limit = 10,
    ) -> Dict[str, Any]:
        """Search past incidents and their proven fixes by error pattern."""
        api = get_api(ctx)
        items = await api.sre_knowledge(_need(query, "query", 500), _cap(limit))
        return {
            "results": [
                {"id": k.get("id"), "incident_type": k.get("incidentType"),
                 "error_pattern": o.clip(k.get("errorPattern"), 400),
                 "root_cause": o.clip(k.get("rootCause"), 600), "solution": o.clip(k.get("solution"), 800),
                 "resolution": o.clip(k.get("resolution"), 600), "effectiveness": k.get("effectiveness"),
                 "times_occurred": k.get("timesOccurred"), "last_occurred": k.get("lastOccurred"),
                 "tags": k.get("tags")}
                for k in items
            ],
            "count": len(items),
        }

    # ================================================================ FinOps
    @mcp.tool(annotations=READ_ONLY, title="Get spending overview")
    @guarded
    async def get_spending_overview(ctx: Context) -> Dict[str, Any]:
        """Spend against limits: this month and today, utilization, last month, year to date,
        month-over-month change and plain-language flags."""
        api = get_api(ctx)
        usage, stats, limits = await asyncio.gather(
            api.billing_current_usage(), api.billing_spending_stats(), api.billing_user_limits()
        )
        usage, stats, limits = usage or {}, stats or {}, limits or {}
        return {
            "current": {
                "monthly_spending": o.money(usage.get("monthlySpending")),
                "daily_spending": o.money(usage.get("dailySpending")),
                "monthly_limit": o.money(usage.get("monthlySpendingLimit")),
                "daily_limit": o.money(usage.get("dailySpendingLimit")),
                "utilization_pct": usage.get("utilizationPercentage"),
            },
            "history": {
                "this_month": o.money(stats.get("thisMonth")), "last_month": o.money(stats.get("lastMonth")),
                "this_year": o.money(stats.get("thisYear")), "average_monthly": o.money(stats.get("averageMonthly")),
                "month_over_month_pct": o.month_over_month(stats),
            },
            "plan_limits": {
                "max_replicas": limits.get("maxReplicas"), "max_memory_gb": limits.get("maxMemoryGb"),
                "max_cpu_cores": limits.get("maxCpuCores"),
            },
            "attention": o.budget_attention(usage),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get usage stats")
    @guarded
    async def get_usage_stats(
        ctx: Context,
        app_name: Annotated[Optional[str], Field(description="Limit to one app; omit for all apps")] = None,
        period: Annotated[str, Field(description="For example month, 7d or 30d")] = "month",
    ) -> Dict[str, Any]:
        """Resource usage and cost: CPU hours, memory, network, storage and total cost."""
        api = get_api(ctx)
        per = o.check_period(period)
        app_id = None
        if _opt(app_name, "app_name"):
            app = await api.app(app_name.strip())
            if not app or not app.get("id"):
                raise NifeAPIError("No app with that name was found. Use list_apps to see your apps.")
            app_id = app["id"]
        s = await api.billing_usage_stats(app_id, per)
        if not s:
            return {"message": "No usage data is available for this scope."}
        return {
            "app": app_name or "all apps", "period": per, "cpu_hours": s.get("cpuHours"),
            "memory_gb_hours": s.get("memoryGbHours"), "network_gb": s.get("networkGb"),
            "storage_gb_days": s.get("storageGbDays"), "total_cost": o.money(s.get("totalCost")),
        }

    @mcp.tool(annotations=READ_ONLY, title="List billing cycles")
    @guarded
    async def list_billing_cycles(ctx: Context, limit: Limit = 12) -> Dict[str, Any]:
        """Past billing cycles with amount, status and dates. Use a cycle id with get_billing_items."""
        cycles = await get_api(ctx).billing_cycles(_cap(limit))
        return {
            "cycles": [
                {"id": c.get("id"), "start": c.get("startDate"), "end": c.get("endDate"),
                 "total_amount": o.money(c.get("totalAmount")), "currency": c.get("currency"),
                 "status": c.get("status"), "paid_at": c.get("paidAt")}
                for c in cycles
            ],
            "count": len(cycles),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get billing items")
    @guarded
    async def get_billing_items(
        cycle_id: Annotated[str, Field(description="Cycle id from list_billing_cycles")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Line items of one billing cycle by app and resource type, with the total."""
        api = get_api(ctx)
        wanted = _need(cycle_id, "cycle_id")
        await _own_cycle(api, wanted)
        items = await api.billing_items(wanted)
        rows = [
            {"app": i.get("appName"), "resource_type": i.get("resourceType"), "quantity": i.get("quantity"),
             "unit_price": o.money(i.get("unitPrice")), "total": o.money(i.get("totalPrice")),
             "period_start": i.get("usagePeriodStart"), "period_end": i.get("usagePeriodEnd")}
            for i in items[:200]
        ]
        total = round(sum(r["total"] or 0 for r in rows), 2)
        return {"cycle_id": wanted, "items": rows, "count": len(items), "total": total,
                "truncated": len(items) > 200}

    @mcp.tool(annotations=READ_ONLY, title="List invoices")
    @guarded
    async def list_invoices(ctx: Context, limit: Limit = 12) -> Dict[str, Any]:
        """Invoices with number, amounts, status and due date."""
        items = await get_api(ctx).billing_invoices(_cap(limit))
        return {
            "invoices": [
                {"id": i.get("id"), "number": i.get("invoiceNumber"), "subtotal": o.money(i.get("subTotal")),
                 "tax": o.money(i.get("taxAmount")), "total": o.money(i.get("totalAmount")),
                 "currency": i.get("currency"), "status": i.get("status"), "due_date": i.get("dueDate"),
                 "paid_at": i.get("paidAt")}
                for i in items
            ],
            "count": len(items),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get cloud billing summary")
    @guarded
    async def get_cloud_billing_summary(
        ctx: Context,
        period_start: Annotated[Optional[str], Field(description="Start date, for example 2026-10-01")] = None,
        period_end: Annotated[Optional[str], Field(description="End date, for example 2026-10-31")] = None,
    ) -> Dict[str, Any]:
        """Cloud cost per app and resource type with markup and total for a period."""
        start, end = _date(period_start, "period_start"), _date(period_end, "period_end")
        if start and end and start > end:
            raise ValueError("period_start must not be after period_end.")
        s = await get_api(ctx).billing_cloud_summary(start, end)
        if not s:
            return {"message": "No cloud billing data is available for this period."}
        lines = s.get("lines") or []
        return {
            "period_start": s.get("periodStart"), "period_end": s.get("periodEnd"),
            "cloud_cost": o.money(s.get("totalCloudCost")), "markup_pct": s.get("markupPercent"),
            "markup": o.money(s.get("totalMarkup")), "total": o.money(s.get("totalAmount")),
            "currency": s.get("currency"),
            "lines": [
                {"app": ln.get("appName"), "resource_type": ln.get("resourceType"),
                 "cloud_cost": o.money(ln.get("cloudCost")), "markup": o.money(ln.get("markupAmount")),
                 "total": o.money(ln.get("totalAmount"))}
                for ln in lines[:100]
            ],
            "truncated": len(lines) > 100,
        }

    @mcp.tool(annotations=READ_ONLY, title="List cost recommendations")
    @guarded
    async def list_cost_recommendations(
        ctx: Context,
        category: Annotated[Optional[str], Field(description="Filter by category, for example compute")] = None,
        min_monthly_savings: Annotated[float, Field(description="Hide items saving less than this per month", ge=0)] = 0,
        limit: Limit = 20,
    ) -> Dict[str, Any]:
        """Ranked cost-saving recommendations (high priority first, biggest saving first) with a
        total of monthly and annual savings. Totals cover everything matching, not only the page."""
        data = await _recommendation_payload(get_api(ctx))
        recs = [o.normalize_recommendation(r) for r in o.unwrap_list(data, "recommendations", "data")
                if isinstance(r, dict)]
        if category:
            want = category.strip().lower()
            recs = [r for r in recs if str(r.get("category") or "").lower() == want]
        recs = [r for r in recs if r["monthly_savings"] >= min_monthly_savings]
        ranked = o.rank_recommendations(recs)
        return {"summary": o.summarize_recommendations(ranked),
                "recommendations": ranked[:_cap(limit)], "shown": min(len(ranked), _cap(limit))}

    @mcp.tool(annotations=READ_ONLY, title="Get cost forecast")
    @guarded
    async def get_cost_forecast(ctx: Context) -> Dict[str, Any]:
        """Forecast of this month and next month, annual projection, per-service trend and drivers."""
        data = await get_api(ctx).finops_get("/ml/cost-forecast")
        if not isinstance(data, dict):
            return {"message": "The FinOps service returned no forecast."}
        return {
            "current_month": o.money(data.get("currentMonth")), "next_month": o.money(data.get("nextMonth")),
            "change_pct": data.get("changePercentage"), "annual_projection": o.money(data.get("annualProjection")),
            "confidence_pct": o.pct(data.get("confidence")),
            "by_service": (data.get("byService") or [])[:20],
            "monthly_forecast": (data.get("monthlyForecast") or [])[:24],
            "factors": [
                {"name": f.get("name"), "impact": f.get("impact"), "description": o.clip(f.get("description"), 400)}
                for f in (data.get("factors") or [])[:10] if isinstance(f, dict)
            ],
        }

    @mcp.tool(annotations=READ_ONLY, title="Get cost anomalies")
    @guarded
    async def get_cost_anomalies(ctx: Context) -> Dict[str, Any]:
        """Unusual cost patterns found by the FinOps ML service."""
        data = await _recommendation_payload(get_api(ctx))
        found: List[Any] = []
        if isinstance(data, dict):
            found = data.get("anomalies_detected") or data.get("anomaliesDetected") or []
        found = [a for a in found if isinstance(a, dict)][:20]
        return {"anomalies": found, "count": len(found)}

    @mcp.tool(annotations=READ_ONLY, title="Get cost usage patterns")
    @guarded
    async def get_cost_usage_patterns(ctx: Context) -> Dict[str, Any]:
        """Usage patterns the FinOps ML service found, which the cost recommendations are based on."""
        data = await _recommendation_payload(get_api(ctx))
        found: List[Any] = []
        if isinstance(data, dict):
            found = data.get("usage_patterns") or data.get("usagePatterns") or []
        found = [p for p in found if isinstance(p, dict)][:20]
        return {"patterns": found, "count": len(found)}

    @mcp.tool(annotations=READ_ONLY, title="Get FinOps resource stats")
    @guarded
    async def get_finops_resource_stats(ctx: Context) -> Dict[str, Any]:
        """Inventory totals across clouds: resource count and cost by provider, service and region."""
        api = get_api(ctx)
        stats = await api.finops_get("/resources/stats")
        if not isinstance(stats, dict):
            return {"message": "The FinOps service returned no resource statistics."}
        out: Dict[str, Any] = {
            "total_resources": stats.get("totalResources"), "total_cost": o.money(stats.get("totalCost")),
            "by_provider": o.cap_map(stats.get("byProvider")),
            "by_service": o.cap_map(stats.get("byService")),
            "by_region": o.cap_map(stats.get("byRegion")),
        }
        try:
            glob = await api.finops_get("/global/stats")
        except NifeAPIError as exc:
            if "rejected the access token" in str(exc):
                raise
            glob = None
        if isinstance(glob, dict):
            out["global"] = {
                "total_cost": o.money(glob.get("totalCost")), "total_resources": glob.get("totalResources"),
                "total_regions": glob.get("totalRegions"),
                "top_services": (glob.get("topServices") or [])[:10],
                "cost_by_provider": o.cap_map(glob.get("costByProvider")),
            }
        return out

    @mcp.tool(annotations=READ_ONLY, title="Search FinOps resources")
    @guarded
    async def search_finops_resources(
        ctx: Context,
        provider: Annotated[Optional[str], Field(description="For example aws, azure, gcp or nife")] = None,
        service: Annotated[Optional[str], Field(description="For example EC2, RDS or kubernetes")] = None,
        region: Annotated[Optional[str], Field(description="Cloud region, for example us-east-1")] = None,
        account: Annotated[Optional[str], Field(description="Cloud account name")] = None,
        cluster_id: Annotated[Optional[str], Field(description="Nife cluster id")] = None,
        namespace: Annotated[Optional[str], Field(description="Kubernetes namespace")] = None,
        app_id: Annotated[Optional[str], Field(description="Nife app id")] = None,
        tag_key: Annotated[Optional[str], Field(description="Tag name; needs tag_value")] = None,
        tag_value: Annotated[Optional[str], Field(description="Tag value; needs tag_key")] = None,
        query: Annotated[Optional[str], Field(description="Free-text search on name, id and tags")] = None,
        limit: Limit = 25,
        skip: Annotated[int, Field(description="Results to skip, for paging", ge=0, le=10000)] = 0,
    ) -> Dict[str, Any]:
        """Search the multi-cloud resource inventory with monthly cost per resource. All filters are
        optional and combine with AND."""
        filters = o.build_resource_filters(
            provider=_opt(provider, "provider", 60), service=_opt(service, "service", 60),
            region=_opt(region, "region", 60), account=_opt(account, "account", 120),
            cluster_id=_opt(cluster_id, "cluster_id"), namespace=_opt(namespace, "namespace", 120),
            app_id=_opt(app_id, "app_id"), tag_key=_opt(tag_key, "tag_key", 64),
            tag_value=_opt(tag_value, "tag_value", 200),
        )
        params: Dict[str, Any] = {"limit": _cap(limit), "skip": int(skip)}
        text = _opt(query, "query", 200)
        if text:
            params["query"] = text
        data = await get_api(ctx).finops_post("/resources/search", filters, params=params)
        items = [r for r in o.unwrap_list(data, "resources", "data") if isinstance(r, dict)]
        rows = [o.resource_view(r) for r in items[:MAX_ITEMS]]
        return {
            "resources": rows, "count": len(rows),
            "page_monthly_cost": round(sum(r["monthly_cost"] or 0 for r in rows), 2),
            "has_more": len(items) >= _cap(limit),
        }

    @mcp.tool(annotations=READ_ONLY, title="Get cost breakdown")
    @guarded
    async def get_cost_breakdown(
        ctx: Context,
        start_date: Annotated[Optional[str], Field(description="Start date, for example 2026-10-01")] = None,
        end_date: Annotated[Optional[str], Field(description="End date, for example 2026-10-31")] = None,
        group_by: Annotated[Optional[List[str]], Field(description="Up to 3 fields, for example provider, service, region")] = None,
    ) -> Dict[str, Any]:
        """Cost explorer: total cost for a period, grouped by the fields given, with child rows."""
        start, end = _date(start_date, "start_date"), _date(end_date, "end_date")
        if start and end and start > end:
            raise ValueError("start_date must not be after end_date.")
        groups = o.check_group_by(group_by)
        body: Dict[str, Any] = {}
        if start:
            body["startDate"] = start
        if end:
            body["endDate"] = end
        if groups:
            body["groupBy"] = groups
        data = await get_api(ctx).finops_post("/costs/explorer", body)
        if not isinstance(data, dict) or not data:
            return {"message": "The FinOps service returned no cost data for this request."}
        return o.breakdown_view(data)

    @mcp.tool(annotations=DESTRUCTIVE, title="Apply cost recommendation")
    @guarded
    async def apply_cost_recommendation(
        recommendation_id: Annotated[str, Field(description="Id from list_cost_recommendations")],
        ctx: Context,
        confirm: Annotated[bool, Field(description="Must be true to apply. Leave false to preview.")] = False,
    ) -> Dict[str, Any]:
        """Carry out one cost recommendation through the FinOps service. This can change real
        infrastructure (right-sizing, schedules, storage tiers). Call without confirm first to show
        the user what would happen, then again with confirm=true only after they agree."""
        api = get_api(ctx)
        wanted = _need(recommendation_id, "recommendation_id")
        rec = await _own_recommendation(api, wanted)
        if not confirm:
            return {
                "applied": False,
                "message": "Preview only. Nothing was changed. Call again with confirm=true to apply.",
                "recommendation": rec,
            }
        res = await api.finops_post(f"/recommendations/{quote(wanted, safe='')}/action", {"action": "apply"})
        res = res if isinstance(res, dict) else {}
        if res.get("success") is False:
            raise NifeAPIError(o.clip(res.get("message"), 300) or "The FinOps service did not apply the recommendation.")
        return {
            "applied": True, "id": rec["id"], "title": rec["title"],
            "monthly_savings": rec["monthly_savings"], "message": o.clip(res.get("message"), 300),
        }
