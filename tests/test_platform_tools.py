"""Tests for the read-only platform tools (delivery, compliance, usage, infrastructure)."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import (
    app_tools, domain_tools, infra_tools, ops_tools, platform_tools, site_tools, vm_tools,
)
from nife_mcp_server.nife_api import NifeAPIError


# ------------------------------------------------------------------ registration
def _names(register):
    mcp = FastMCP("test")
    register(mcp)
    return [t.name for t in mcp._tool_manager.list_tools()]


def test_all_platform_tools_register_with_distinct_names():
    names = _names(platform_tools.register_platform_tools)
    assert len(names) == len(set(names)) == 21
    assert {"get_org_dora_metrics", "list_backup_policies", "get_cluster_capacity",
            "estimate_deployment_cost", "get_credits"} <= set(names)


def test_platform_tools_are_all_read_only():
    mcp = FastMCP("test")
    platform_tools.register_platform_tools(mcp)
    for tool in mcp._tool_manager.list_tools():
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.destructiveHint is False, tool.name


def test_no_tool_name_is_registered_twice_across_the_hosted_server():
    """FastMCP silently keeps the first tool of a duplicate name, so a clash would hide a tool."""
    registers = [
        site_tools.register_site_tools, app_tools.register_app_tools,
        domain_tools.register_domain_tools, ops_tools.register_ops_tools,
        platform_tools.register_platform_tools, infra_tools.register_infra_tools,
        vm_tools.register_vm_tools,
    ]
    per_module = [_names(r) for r in registers]
    combined = FastMCP("test")
    for r in registers:
        r(combined)
    assert len(combined._tool_manager.list_tools()) == sum(len(n) for n in per_module)


# ------------------------------------------------------------------ pure helpers
def test_stamp_turns_dates_into_day_bounds():
    assert platform_tools._stamp("2026-10-01", "d") == "2026-10-01T00:00:00Z"
    assert platform_tools._stamp("2026-10-01", "d", end=True) == "2026-10-01T23:59:59Z"
    assert platform_tools._stamp(None, "d") is None
    with pytest.raises(ValueError, match="must look like"):
        platform_tools._stamp("1 Oct", "d")


def test_range_rejects_reversed_dates():
    platform_tools._range("2026-10-01", "2026-10-31")
    platform_tools._range(None, "2026-10-31")
    with pytest.raises(ValueError, match="must not be after"):
        platform_tools._range("2026-10-31", "2026-10-01")


def test_caps_keeps_only_known_resources():
    assert platform_tools._caps(None) is None
    assert platform_tools._caps({"cpu": "4", "pods": 110, "gpu": None, "extra": 1}) == {"cpu": "4", "pods": 110}


# --------------------------------------------------------------------- tool flow
class FakeAPI:
    """Answers graphql() by looking for the operation name in the query text."""

    def __init__(self, **responses):
        self.calls = []
        self.responses = responses

    async def organizations(self):
        return [{"id": "org-1", "name": "Acme", "slug": "acme"}]

    async def app(self, name):
        self.calls.append(("app", name))
        return {"id": "app-1", "name": name} if name == "web" else None

    async def graphql(self, query, variables=None, timeout=60.0):
        self.calls.append(("graphql", variables))
        for key, data in self.responses.items():
            if f"query {key}" in query:
                return data
        return {}


def _tool(name):
    mcp = FastMCP("test")
    platform_tools.register_platform_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(platform_tools, "get_api", lambda ctx: api)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def _graphql_calls(api):
    return [c for c in api.calls if c[0] == "graphql"]


def test_org_keyed_tools_reject_a_foreign_organization(monkeypatch):
    api = FakeAPI()
    for name, kw in [("get_org_dora_metrics", {}), ("get_restore_history", {}),
                     ("get_capacity_thresholds", {}), ("list_cloud_hosts", {}),
                     ("get_usage_report_subscription", {})]:
        with pytest.raises(ToolError, match="Unknown organization_id"):
            _run(monkeypatch, api, name, organization_id="org-other", **kw)
    assert _graphql_calls(api) == []


def test_app_keyed_tools_prove_the_app_first(monkeypatch):
    api = FakeAPI()
    for name in ("get_deployment_history", "get_incident_history", "get_app_cost",
                 "get_volume_overview", "get_app_failover", "get_app_usage_metrics"):
        with pytest.raises(ToolError, match="No app named 'ghost'"):
            _run(monkeypatch, api, name, app_name="ghost")
    assert _graphql_calls(api) == []


def test_dora_passes_day_bounds_and_rejects_reversed_dates(monkeypatch):
    api = FakeAPI(Dora={"getFourKeysMetrics": {"deploymentFrequency": 3}, "getOverallDoraMetrics": {"x": 1}})
    out = _run(monkeypatch, api, "get_org_dora_metrics", organization_id="org-1",
               from_date="2026-10-01", to_date="2026-10-31")
    assert out == {"four_keys": {"deploymentFrequency": 3}, "totals": {"x": 1}}
    variables = _graphql_calls(api)[0][1]
    assert variables["from"] == "2026-10-01T00:00:00Z" and variables["to"] == "2026-10-31T23:59:59Z"
    with pytest.raises(ToolError, match="must not be after"):
        _run(monkeypatch, FakeAPI(), "get_org_dora_metrics", organization_id="org-1",
             from_date="2026-10-31", to_date="2026-10-01")


def test_deployment_history_clips_commit_messages_and_clamps_limit(monkeypatch):
    api = FakeAPI(DeploymentHistory={"getDeploymentHistory": [{"id": "d1", "commitMessage": "x" * 1000}]})
    out = _run(monkeypatch, api, "get_deployment_history", app_name="web", limit=500)
    assert out["count"] == 1 and len(out["deployments"][0]["commitMessage"]) < 1000
    assert _graphql_calls(api)[0][1] == {"appId": "app-1", "limit": 50}


def test_regulatory_reporting_validates_regulator_before_any_call(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="regulator must be one of"):
        _run(monkeypatch, api, "get_regulatory_reporting", organization_id="org-1", regulator="FDA")
    assert _graphql_calls(api) == []


def test_regulatory_reporting_uses_the_org_slug_and_canonical_regulator(monkeypatch):
    api = FakeAPI(RegReport={"regulatoryReportingSummary": {"regulator": "CERT-In", "reportedOnTime": 4}})
    out = _run(monkeypatch, api, "get_regulatory_reporting", organization_id="org-1", regulator=" cert-in ")
    assert out["reportedOnTime"] == 4
    assert _graphql_calls(api)[0][1] == {"org": "acme", "reg": "CERT-In", "days": 180}


def test_backup_policies_check_every_app(monkeypatch):
    api = FakeAPI(Backups={"backupPolicies": [{"appName": "web", "lastError": "e" * 900}]})
    with pytest.raises(ToolError, match="No app named 'ghost'"):
        _run(monkeypatch, api, "list_backup_policies", app_names=["web", "ghost"])
    assert _graphql_calls(api) == []
    out = _run(monkeypatch, api, "list_backup_policies", app_names=["web"])
    assert out["count"] == 1 and len(out["policies"][0]["lastError"]) < 900


def test_usage_summary_sorts_apps_by_monthly_cost(monkeypatch):
    summary = {"estimatedMonthlyCost": 30, "appCosts": [
        {"appName": "a", "monthlyCost": 5}, {"appName": "b", "monthlyCost": 25}]}
    out = _run(monkeypatch, FakeAPI(UsageSummary={"getUsageSummary": summary}), "get_usage_summary")
    assert [a["appName"] for a in out["appCosts"]] == ["b", "a"] and out["apps_total"] == 2
    empty = _run(monkeypatch, FakeAPI(), "get_usage_summary")
    assert "message" in empty


def test_app_usage_metrics_only_returns_points_when_asked(monkeypatch):
    data = {"getUsageMetricsSummary": {"avgCpuUsage": 12.5},
            "getUsageMetrics": [{"cpuUsage": 1}, {"cpuUsage": 2}, {"cpuUsage": 3}]}
    api = FakeAPI(AppUsage=data)
    assert "points" not in _run(monkeypatch, api, "get_app_usage_metrics", app_name="web")
    out = _run(monkeypatch, api, "get_app_usage_metrics", app_name="web", points=2)
    assert out["summary"] == {"avgCpuUsage": 12.5} and len(out["points"]) == 2
    with pytest.raises(ToolError, match="must not be after"):
        _run(monkeypatch, api, "get_app_usage_metrics", app_name="web",
             start_date="2026-10-31", end_date="2026-10-01")


def test_credits_includes_transactions_only_when_asked(monkeypatch):
    data = {"getMyCredits": {"balance": 10}, "getAutoRechargeSettings": {"enabled": False},
            "getCreditTransactions": [{"amount": 5, "description": "d" * 500}]}
    api = FakeAPI(Credits=data)
    assert "transactions" not in _run(monkeypatch, api, "get_credits", transactions=0)
    out = _run(monkeypatch, api, "get_credits", transactions=5)
    assert out["credits"] == {"balance": 10} and len(out["transactions"][0]["description"]) < 500


def test_volume_overview_returns_newest_snapshots_first(monkeypatch):
    data = {"getVolumeByAppId": [{"name": "data"}], "getVolumeHealth": {"errorMessage": "x" * 900},
            "getVolumeUsageStats": {"usagePercentage": 40},
            "getVolumeSnapshots": [{"id": "old", "createdAt": "2026-01-01"},
                                   {"id": "new", "createdAt": "2026-10-01"}]}
    out = _run(monkeypatch, FakeAPI(Volumes=data), "get_volume_overview", app_name="web", snapshots=1)
    assert [s["id"] for s in out["snapshots"]] == ["new"] and out["snapshot_count"] == 2
    assert len(out["health"]["errorMessage"]) < 900


def test_cloud_hosts_trim_activity_messages(monkeypatch):
    hosts = [{"id": "h1", "InstanceActivity": [{"Type": "start", "Message": "m" * 900}]}, None]
    out = _run(monkeypatch, FakeAPI(Hosts={"getHost": hosts}), "list_cloud_hosts", organization_id="org-1")
    assert out["count"] == 2 and len(out["hosts"]) == 1
    assert len(out["hosts"][0]["InstanceActivity"][0]["Message"]) < 900


def test_workloads_and_clusters_choose_the_org_or_user_query(monkeypatch):
    api = FakeAPI(Workloads={"getWorkloadMangementByorgnizationId": [{"id": "w1"}]},
                  MyWorkloads={"getWorkloadMangementByUser": [{"id": "w2"}]},
                  OrgClusters={"getClusterDetailsByOrgIdMultipleReg": [{"id": "c1"}, None]},
                  MyClusters={"getUserAddedRegions": [{"id": "c2"}]})
    assert _run(monkeypatch, api, "list_workloads", organization_id="org-1")["workloads"] == [{"id": "w1"}]
    assert _run(monkeypatch, api, "list_workloads")["workloads"] == [{"id": "w2"}]
    assert _run(monkeypatch, api, "list_clusters", organization_id="org-1")["count"] == 1
    assert _run(monkeypatch, api, "list_clusters")["clusters"] == [{"id": "c2"}]


def test_cluster_capacity_keeps_known_resources_and_caps_quotas(monkeypatch):
    cluster = {"regionCode": "in-blr", "nodeCount": 3,
               "totalResources": {"cpu": "12", "secret": "x"}, "allocatedResources": None,
               "availableResources": {"cpu": "4", "memory": "8Gi"},
               "resourceQuotas": [{"namespace": f"ns{i}"} for i in range(40)]}
    out = _run(monkeypatch, FakeAPI(Capacity={"getClusterResourceLimits": cluster}),
               "get_cluster_capacity", region_code="in-blr")
    assert out["totalResources"] == {"cpu": "12"} and out["allocatedResources"] is None
    assert len(out["resourceQuotas"]) == 20
    assert "message" in _run(monkeypatch, FakeAPI(), "get_cluster_capacity", region_code="in-blr")


def test_backend_errors_become_tool_errors(monkeypatch):
    class Boom(FakeAPI):
        async def graphql(self, *a, **k):
            raise NifeAPIError("backend down")

    with pytest.raises(ToolError, match="backend down"):
        _run(monkeypatch, Boom(), "get_credits")
