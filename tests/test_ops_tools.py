"""Tests for the NERO and FinOps tools and their pure helpers."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import ops_helpers as o
from nife_mcp_server import ops_tools
from nife_mcp_server.nife_api import NifeAPIError


# ------------------------------------------------------------------ pure helpers
def test_clip_shortens_only_long_strings():
    assert o.clip("short", 10) == "short"
    out = o.clip("x" * 30, 10)
    assert out.startswith("x" * 10) and "20 more characters" in out
    assert o.clip(None) is None and o.clip(5) == 5


def test_check_choice_normalizes_and_rejects():
    assert o.check_choice(" HIGH ", o.SEVERITIES, "severity") == "high"
    assert o.check_choice(None, o.SEVERITIES, "severity") is None
    assert o.check_choice("", o.SEVERITIES, "severity") is None
    with pytest.raises(ValueError, match="severity must be one of"):
        o.check_choice("urgent", o.SEVERITIES, "severity")


def test_check_period_shape():
    assert o.check_period(None) == "month"
    assert o.check_period("30d") == "30d" and o.check_period("2026-10") == "2026-10"
    for bad in ("a b", "x" * 17, "7d; drop", ""):
        if bad == "":
            assert o.check_period(bad) == "month"
        else:
            with pytest.raises(ValueError):
                o.check_period(bad)


def test_pct_and_money_handle_odd_input():
    assert o.pct(0.857) == 85.7 and o.pct(85.74) == 85.7
    assert o.pct(True) is None and o.pct("x") is None and o.pct(None) is None
    assert o.money(1.005) == 1.0 or o.money(1.005) == 1.01
    assert o.money(True) is None and o.money("5") is None


@pytest.mark.parametrize(
    "rec, expected",
    [
        ({"estimatedSavings": {"monthly": 120.5}}, 120.5),
        ({"estimated_savings": {"Monthly": 10}}, 10.0),
        ({"savings": 42}, 42.0),
        ({"savings": {"amount": 7}}, 7.0),
        ({"monthlySavings": 3}, 3.0),
        ({"potentialSavings": 9}, 9.0),
        ({"estimatedSavings": True}, 0.0),
        ({}, 0.0),
    ],
)
def test_extract_monthly_savings_accepts_every_dashboard_shape(rec, expected):
    assert o.extract_monthly_savings(rec) == expected


def test_normalize_rank_and_summarize_recommendations():
    raw = [
        {"id": "a", "title": "Rightsize", "priority": "medium", "category": "compute",
         "estimatedSavings": {"monthly": 50}, "confidence": 0.9},
        {"id": "b", "priority": "high", "category": "storage_optimization", "savings": 20},
        {"id": "c", "priority": "high", "category": "compute", "savings": 80},
        {"id": "d", "category": "compute"},
    ]
    recs = [o.normalize_recommendation(r) for r in raw]
    assert recs[0]["confidence_pct"] == 90.0 and recs[3]["title"] == "Untitled recommendation"
    ranked = o.rank_recommendations(recs)
    assert [r["id"] for r in ranked] == ["c", "b", "a", "d"]
    summary = o.summarize_recommendations(ranked)
    assert summary["count"] == 4 and summary["total_monthly_savings"] == 150.0
    assert summary["total_annual_savings"] == 1800.0
    assert summary["by_category"]["compute"] == {"count": 3, "monthly_savings": 130.0}


def test_unwrap_list_shapes():
    assert o.unwrap_list([1, 2]) == [1, 2]
    assert o.unwrap_list({"recommendations": [1]}, "recommendations", "data") == [1]
    assert o.unwrap_list({"data": [2]}, "recommendations", "data") == [2]
    assert o.unwrap_list({"x": 1}, "data") == [] and o.unwrap_list(None) == []


def test_budget_attention_flags():
    assert o.budget_attention({"utilizationPercentage": 50}) == []
    assert "80" in o.budget_attention({"utilizationPercentage": 80.4})[0]
    assert "reached" in o.budget_attention({"utilizationPercentage": 100})[0]
    notes = o.budget_attention({"dailySpending": 12, "dailySpendingLimit": 10})
    assert any("daily" in n for n in notes)


def test_month_over_month():
    assert o.month_over_month({"thisMonth": 150, "lastMonth": 100}) == 50.0
    assert o.month_over_month({"thisMonth": 50, "lastMonth": 100}) == -50.0
    assert o.month_over_month({"thisMonth": 5, "lastMonth": 0}) is None
    assert o.month_over_month({"thisMonth": None, "lastMonth": 5}) is None


def test_slo_attention_flags():
    notes = o.slo_attention({"breaching": True, "errorBudgetPct": 10, "burnRate1h": 3.2,
                             "targetIsDefault": True})
    assert len(notes) == 4
    assert o.slo_attention({"breaching": False, "errorBudgetPct": 90, "burnRate1h": 0.5}) == []
    assert any("days" in n for n in o.slo_attention({"daysRemaining": 1.5, "errorBudgetPct": 60}))


# ------------------------------------------------------------------- tool flow
class FakeAPI:
    """Records backend calls so tests can assert nothing was mutated or fetched."""

    def __init__(self, *, recs=None, anomalies=None, forecast=None, finops_error=None):
        self.calls = []
        self._recs = recs
        self._anomalies = anomalies
        self._forecast = forecast
        self._finops_error = finops_error

    async def organizations(self):
        return [{"id": "org-1", "name": "Acme"}]

    async def sre_incidents(self, org_id, status, severity, limit, detail=False):
        self.calls.append(("sre_incidents", org_id, status, severity, limit, detail))
        return [{"id": "inc-1", "severity": "high", "status": "open", "rootCauseConfidence": 0.8,
                 "description": "d", "postmortem": {"outcome": "fixed"} if detail else None}]

    async def sre_alerts(self, org_id, status, severity, limit):
        self.calls.append(("sre_alerts", org_id, status, severity, limit))
        return [{"id": "al-1", "title": "CPU", "severity": "high", "status": "firing"}]

    async def sre_acknowledge_alert(self, alert_id):
        self.calls.append(("sre_acknowledge_alert", alert_id))
        return {"id": alert_id, "title": "CPU", "status": "acknowledged", "acknowledgedBy": "me"}

    async def sre_resolve_alert(self, alert_id):
        self.calls.append(("sre_resolve_alert", alert_id))
        return {"id": alert_id, "title": "CPU", "status": "resolved", "resolvedBy": "me"}

    async def sre_slo(self, org_id, app_name, service_name, window):
        self.calls.append(("sre_slo", org_id, app_name, service_name, window))
        return {"appName": "demo", "breaching": True, "errorBudgetPct": 10, "sloTarget": 99.9}

    async def billing_current_usage(self):
        return {"monthlySpending": 90, "monthlySpendingLimit": 100, "utilizationPercentage": 90}

    async def billing_spending_stats(self):
        return {"thisMonth": 90, "lastMonth": 60, "thisYear": 500, "averageMonthly": 55}

    async def billing_user_limits(self):
        return {"maxReplicas": 5}

    async def billing_cycles(self, limit):
        self.calls.append(("billing_cycles", limit))
        return [{"id": "cyc-1", "totalAmount": 12.5, "status": "paid"}]

    async def billing_items(self, cycle_id):
        self.calls.append(("billing_items", cycle_id))
        return [{"appName": "demo", "totalPrice": 5.0}, {"appName": "demo2", "totalPrice": 7.5}]

    async def billing_cloud_summary(self, start, end):
        self.calls.append(("billing_cloud_summary", start, end))
        return {"totalCloudCost": 10, "lines": []}

    async def finops_get(self, path, params=None):
        self.calls.append(("finops_get", path))
        if self._finops_error:
            raise NifeAPIError(self._finops_error)
        if path == "/ml/cost-forecast":
            return self._forecast
        if path == "/resources/stats":
            return {"totalResources": 3, "totalCost": 981.004, "byProvider": {"aws": 3}}
        if path == "/global/stats":
            return {"totalCost": 981, "totalResources": 3, "totalRegions": 2}
        return {"recommendations": self._recs or [], "anomalies_detected": self._anomalies or [],
                "usage_patterns": getattr(self, "patterns", [])}

    async def finops_post(self, path, body, params=None):
        self.calls.append(("finops_post", path, body, params))
        if path == "/resources/search":
            return getattr(self, "resources", [])
        if path == "/costs/explorer":
            return getattr(self, "explorer", {})
        return getattr(self, "apply_result", {"success": True, "message": "done"})


def _tool(name):
    mcp = FastMCP("test")
    ops_tools.register_ops_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(ops_tools, "get_api", lambda ctx: api)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def _names(api):
    return [c[0] for c in api.calls]


def test_all_ops_tools_register_with_distinct_names():
    mcp = FastMCP("test")
    ops_tools.register_ops_tools(mcp)
    names = [t.name for t in mcp._tool_manager.list_tools()]
    assert len(names) == len(set(names)) == 26
    assert {"get_health_insights", "acknowledge_alert", "list_cost_recommendations",
            "apply_cost_recommendation", "search_finops_resources", "get_cost_breakdown"} <= set(names)


def test_org_keyed_tools_reject_a_foreign_organization(monkeypatch):
    api = FakeAPI()
    for name, kw in [("list_incidents", {}), ("list_alerts", {}), ("get_slo_status", {})]:
        with pytest.raises(ToolError, match="Unknown organization_id"):
            _run(monkeypatch, api, name, organization_id="org-other", **kw)
    assert api.calls == []


def test_bad_filter_values_fail_before_any_backend_call(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="severity must be one of"):
        _run(monkeypatch, api, "list_incidents", organization_id="org-1", severity="urgent")
    with pytest.raises(ToolError, match="status must be one of"):
        _run(monkeypatch, api, "list_alerts", organization_id="org-1", status="done")
    assert api.calls == []


def test_list_incidents_normalizes_filters_and_clamps_limit(monkeypatch):
    api = FakeAPI()
    out = _run(monkeypatch, api, "list_incidents", organization_id="org-1", status="OPEN", limit=500)
    assert out["count"] == 1 and out["incidents"][0]["root_cause_confidence_pct"] == 80.0
    assert api.calls == [("sre_incidents", "org-1", "open", None, 50, False)]


def test_get_incident_returns_detail_or_a_clear_error(monkeypatch):
    out = _run(monkeypatch, FakeAPI(), "get_incident", organization_id="org-1", incident_id="inc-1")
    assert out["postmortem"]["outcome"] == "fixed"
    with pytest.raises(ToolError, match="No incident"):
        _run(monkeypatch, FakeAPI(), "get_incident", organization_id="org-1", incident_id="nope")


def test_acknowledge_and_resolve_check_the_alert_belongs_to_the_caller(monkeypatch):
    api = FakeAPI()
    for name in ("acknowledge_alert", "resolve_alert"):
        with pytest.raises(ToolError, match="No alert"):
            _run(monkeypatch, api, name, alert_id="al-foreign")
    assert "sre_acknowledge_alert" not in _names(api) and "sre_resolve_alert" not in _names(api)

    ack = _run(monkeypatch, api, "acknowledge_alert", alert_id="al-1")
    assert ack["status"] == "acknowledged"
    res = _run(monkeypatch, api, "resolve_alert", alert_id="al-1")
    assert res["status"] == "resolved"


def test_slo_tool_adds_plain_flags(monkeypatch):
    out = _run(monkeypatch, FakeAPI(), "get_slo_status", organization_id="org-1", window="7d")
    assert out["breaching"] is True and any("breached" in n for n in out["attention"])


def test_spending_overview_combines_three_queries(monkeypatch):
    out = _run(monkeypatch, FakeAPI(), "get_spending_overview")
    assert out["history"]["month_over_month_pct"] == 50.0
    assert out["current"]["utilization_pct"] == 90
    assert any("90" in n for n in out["attention"])


def test_billing_items_requires_a_cycle_the_caller_owns(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="No billing cycle"):
        _run(monkeypatch, api, "get_billing_items", cycle_id="cyc-foreign")
    assert "billing_items" not in _names(api)
    out = _run(monkeypatch, api, "get_billing_items", cycle_id="cyc-1")
    assert out["total"] == 12.5 and out["count"] == 2


def test_cloud_summary_validates_dates(monkeypatch):
    api = FakeAPI()
    for bad in ("10/01/2026", "2026-1-1", "yesterday"):
        with pytest.raises(ToolError, match="must look like"):
            _run(monkeypatch, api, "get_cloud_billing_summary", period_start=bad)
    with pytest.raises(ToolError, match="not be after"):
        _run(monkeypatch, api, "get_cloud_billing_summary", period_start="2026-10-31", period_end="2026-10-01")
    assert api.calls == []
    _run(monkeypatch, api, "get_cloud_billing_summary", period_start="2026-10-01", period_end="2026-10-31")
    assert api.calls == [("billing_cloud_summary", "2026-10-01", "2026-10-31")]


def test_cost_recommendations_rank_filter_and_summarize(monkeypatch):
    recs = [
        {"id": "a", "priority": "medium", "category": "compute", "savings": 50},
        {"id": "b", "priority": "high", "category": "storage_optimization", "savings": 20},
        {"id": "c", "priority": "high", "category": "compute", "savings": 80},
        {"id": "d", "priority": "low", "category": "compute", "savings": 1},
    ]
    out = _run(monkeypatch, FakeAPI(recs=recs), "list_cost_recommendations", min_monthly_savings=10, limit=2)
    assert [r["id"] for r in out["recommendations"]] == ["c", "b"]
    assert out["summary"]["count"] == 3 and out["summary"]["total_monthly_savings"] == 150.0
    only = _run(monkeypatch, FakeAPI(recs=recs), "list_cost_recommendations", category="COMPUTE")
    assert {r["id"] for r in only["recommendations"]} == {"a", "c", "d"}


def test_cost_anomalies_read_either_key_and_ignore_junk(monkeypatch):
    out = _run(monkeypatch, FakeAPI(anomalies=[{"id": 1}, "junk"]), "get_cost_anomalies")
    assert out == {"anomalies": [{"id": 1}], "count": 1}


def test_cost_forecast_shapes_and_missing_service(monkeypatch):
    fc = {"currentMonth": 100, "nextMonth": 110.456, "confidence": 0.7, "factors": [{"name": "x", "impact": "positive"}, 5]}
    out = _run(monkeypatch, FakeAPI(forecast=fc), "get_cost_forecast")
    assert out["next_month"] == 110.46 and out["confidence_pct"] == 70.0 and len(out["factors"]) == 1
    with pytest.raises(ToolError, match="HTTP 404"):
        _run(monkeypatch, FakeAPI(finops_error="The FinOps service has no data for this request (HTTP 404)."),
             "get_cost_forecast")
    assert "message" in _run(monkeypatch, FakeAPI(forecast=[]), "get_cost_forecast")


# ------------------------------------------- inventory, cost explorer, apply recommendation
def test_resource_filter_builder_limits_fields_and_checks_tags():
    f = o.build_resource_filters(provider="aws", cluster_id="c1", tag_key="team", tag_value="platform")
    assert f == [
        {"field": "provider", "operator": "=", "value": "aws"},
        {"field": "metadata.clusterId", "operator": "=", "value": "c1"},
        {"field": "tags.team", "operator": "=", "value": "platform"},
    ]
    assert o.build_resource_filters() == []
    with pytest.raises(ValueError, match="given together"):
        o.build_resource_filters(tag_key="team")
    with pytest.raises(ValueError, match="tag_key may only"):
        o.build_resource_filters(tag_key="a.b", tag_value="x")


def test_check_group_by_and_views():
    assert o.check_group_by(None) is None and o.check_group_by([]) is None
    assert o.check_group_by([" provider ", "service"]) == ["provider", "service"]
    with pytest.raises(ValueError, match="at most"):
        o.check_group_by(["a", "b", "c", "d"])
    with pytest.raises(ValueError, match="short names"):
        o.check_group_by(["provider; drop"])
    view = o.breakdown_view({"total": 10.004, "breakdown": [
        {"key": "compute", "value": 10, "children": [{"key": "EC2", "value": 10}, "junk"]}, "junk"]})
    assert view == {"total": 10.0, "breakdown": [
        {"key": "compute", "value": 10.0, "children": [{"key": "EC2", "value": 10.0}]}]}
    r = o.resource_view({"id": "r1", "resourceId": "i-1", "cost": 5, "tags": {"a": "b"},
                         "metadata": {"vcpu": 2, "secret": "x"}})
    assert r["monthly_cost"] == 5.0 and r["metadata"] == {"vcpu": 2}


def test_resource_stats_tolerates_a_missing_global_endpoint(monkeypatch):
    out = _run(monkeypatch, FakeAPI(), "get_finops_resource_stats")
    assert out["total_cost"] == 981.0 and out["global"]["total_regions"] == 2


def test_search_resources_builds_filters_and_clamps_paging(monkeypatch):
    api = FakeAPI()
    api.resources = [{"id": "r1", "cost": 10}, {"id": "r2", "cost": 5.5}, "junk"]
    out = _run(monkeypatch, api, "search_finops_resources", provider="aws", query=" web ", limit=500)
    assert out["count"] == 2 and out["page_monthly_cost"] == 15.5
    _, path, body, params = api.calls[-1]
    assert path == "/resources/search"
    assert body == [{"field": "provider", "operator": "=", "value": "aws"}]
    assert params == {"limit": 50, "skip": 0, "query": "web"}
    before = len(api.calls)
    with pytest.raises(ToolError, match="given together"):
        _run(monkeypatch, api, "search_finops_resources", tag_key="team")
    assert len(api.calls) == before


def test_cost_breakdown_validates_input_and_shapes_the_body(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="must look like"):
        _run(monkeypatch, api, "get_cost_breakdown", start_date="October")
    with pytest.raises(ToolError, match="not be after"):
        _run(monkeypatch, api, "get_cost_breakdown", start_date="2026-10-31", end_date="2026-10-01")
    assert api.calls == []
    assert "message" in _run(monkeypatch, api, "get_cost_breakdown")
    api.explorer = {"total": 7, "breakdown": [{"key": "aws", "value": 7}]}
    out = _run(monkeypatch, api, "get_cost_breakdown", start_date="2026-10-01", group_by=["provider"])
    assert out["total"] == 7.0
    assert api.calls[-1][2] == {"startDate": "2026-10-01", "groupBy": ["provider"]}


def test_usage_patterns_ignore_junk(monkeypatch):
    api = FakeAPI()
    api.patterns = [{"name": "idle nights"}, "junk"]
    assert _run(monkeypatch, api, "get_cost_usage_patterns") == {"patterns": [{"name": "idle nights"}], "count": 1}


def test_apply_recommendation_checks_ownership_and_needs_confirmation(monkeypatch):
    recs = [{"id": "rec-1", "title": "Rightsize", "priority": "high", "savings": 40}]
    api = FakeAPI(recs=recs)
    with pytest.raises(ToolError, match="No cost recommendation"):
        _run(monkeypatch, api, "apply_cost_recommendation", recommendation_id="rec-foreign", confirm=True)
    assert "finops_post" not in _names(api)

    preview = _run(monkeypatch, api, "apply_cost_recommendation", recommendation_id="rec-1")
    assert preview["applied"] is False and preview["recommendation"]["title"] == "Rightsize"
    assert "finops_post" not in _names(api)

    done = _run(monkeypatch, api, "apply_cost_recommendation", recommendation_id="rec-1", confirm=True)
    assert done["applied"] is True and done["monthly_savings"] == 40.0
    assert api.calls[-1] == ("finops_post", "/recommendations/rec-1/action", {"action": "apply"}, None)


def test_apply_recommendation_reports_a_refusal_from_the_service(monkeypatch):
    api = FakeAPI(recs=[{"id": "rec-1", "title": "Rightsize"}])
    api.apply_result = {"success": False, "message": "Resource is in use"}
    with pytest.raises(ToolError, match="Resource is in use"):
        _run(monkeypatch, api, "apply_cost_recommendation", recommendation_id="rec-1", confirm=True)
