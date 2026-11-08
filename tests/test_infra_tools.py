"""Tests for the read-only infrastructure tools (cloud accounts, agents, forecast, roles, plan)."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import infra_tools
from nife_mcp_server.nife_api import NifeAPIError


def _tool(name):
    mcp = FastMCP("test")
    infra_tools.register_infra_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def test_all_infra_tools_register_and_only_read():
    mcp = FastMCP("test")
    infra_tools.register_infra_tools(mcp)
    tools = mcp._tool_manager.list_tools()
    names = [t.name for t in tools]
    assert len(names) == len(set(names)) == 11
    assert {"list_connected_cloud_accounts", "list_agents", "get_resource_forecast", "list_roles",
            "list_managed_clusters", "list_vm_node_pools"} <= set(names)
    for t in tools:
        assert t.annotations.readOnlyHint is True and t.annotations.destructiveHint is False, t.name


def test_upper_choice_normalizes_and_rejects():
    allowed = infra_tools.FINDING_STATUSES
    assert infra_tools._upper_choice(" false-positive ", allowed, "status") == "FALSE_POSITIVE"
    assert infra_tools._upper_choice(None, allowed, "status") is None
    assert infra_tools._upper_choice("", allowed, "status") is None
    with pytest.raises(ValueError, match="status must be one of"):
        infra_tools._upper_choice("done", allowed, "status")


def test_forecast_view_drops_chart_images_and_clips_advice():
    view = infra_tools._forecast_view({
        "max_cpu": "71%", "actual_plot": "A" * 5000, "forecast_plot": "B" * 5000,
        "actual_plots": ["A"], "forecast_plots": ["B"], "using_lstm": True,
        "predicted_peak": {"cpu": "80%", "time": "soon"},
        "recommendations": ["scale up", "", "x" * 900],
    })
    assert view["max_cpu"] == "71%" and view["using_lstm"] is True
    assert "actual_plot" not in view and "forecast_plots" not in view
    assert len(view["recommendations"]) == 2 and len(view["recommendations"][1]) < 900


class FakeAPI:
    """Answers graphql() by the operation name in the query and records the calls."""

    def __init__(self, responses=None, forecast=None, apps=None):
        self.calls = []
        self.responses = responses or {}
        self.forecast = forecast
        self.apps = apps if apps is not None else {"web": {"id": "app-1", "name": "web", "organizationId": "org-1"}}

    async def organizations(self):
        return [{"id": "org-1", "name": "Acme", "slug": "acme team"}]

    async def app(self, name):
        return self.apps.get(name)

    async def graphql(self, query, variables=None, timeout=60.0):
        self.calls.append(("graphql", variables))
        for key, data in self.responses.items():
            if f"query {key}" in query:
                return data
        return {}

    async def lstm_get(self, path):
        self.calls.append(("lstm_get", path))
        return self.forecast


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(infra_tools, "get_api", lambda ctx: api)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def _backend_calls(api):
    return [c for c in api.calls if c[0] != "app"]


AGENTS = {"OwnAgents": {"listAgents": [{"id": "a1", "clusterID": "c1"}]}}


def test_org_keyed_tools_reject_a_foreign_organization(monkeypatch):
    api = FakeAPI()
    for name in ("list_connected_cloud_accounts", "get_resource_forecast", "list_managed_clusters", "list_vm_node_pools"):
        with pytest.raises(ToolError, match="Unknown organization_id"):
            _run(monkeypatch, api, name, organization_id="org-other")
    for name in ("list_business_units", "list_agents"):
        with pytest.raises(ToolError, match="Unknown organization_id"):
            _run(monkeypatch, api, name, organization_id="org-other")
    assert _backend_calls(api) == []


def test_cluster_keyed_tools_prove_the_agent_first(monkeypatch):
    api = FakeAPI(AGENTS)
    for name in ("get_agent_metrics", "get_agent_security_findings", "get_agent_health_checks"):
        with pytest.raises(ToolError, match="No agent for that cluster_id"):
            _run(monkeypatch, api, name, cluster_id="c-foreign")
    # only the ownership lookups ran; no cluster data was asked for
    assert all(c[1] is None for c in _backend_calls(api))


def test_cloud_accounts_list(monkeypatch):
    api = FakeAPI({"ListCloudAccounts": {"listCloudAccounts": [{"id": "x", "cloud": "aws"}, None]}})
    out = _run(monkeypatch, api, "list_connected_cloud_accounts", organization_id="org-1")
    assert out == {"accounts": [{"id": "x", "cloud": "aws"}], "count": 1}
    assert _backend_calls(api)[0][1] == {"orgId": "org-1"}


def test_business_units_filter_by_organization(monkeypatch):
    units = [{"id": "b1", "orgId": "org-1"}, {"id": "b2", "orgId": "org-2"}, None]
    api = FakeAPI({"BusinessUnits": {"businessUnitList": units}})
    assert _run(monkeypatch, api, "list_business_units")["count"] == 2
    only = _run(monkeypatch, api, "list_business_units", organization_id="org-1")
    assert [u["id"] for u in only["business_units"]] == ["b1"]


def test_roles_are_condensed_to_allowed_actions(monkeypatch):
    roles = [{"id": "1", "name": "Viewer", "description": "d", "isSystem": True, "permissions": [
        {"module": "apps", "view": True, "create": False, "is_active": True},
        {"module": "billing", "view": False, "create": False, "update": False, "delete": False, "is_active": True},
        {"module": "old", "view": True, "is_active": False},
    ]}, None]
    out = _run(monkeypatch, FakeAPI({"Roles": {"getRoles": roles}}), "list_roles")
    assert out["count"] == 1
    assert out["roles"][0]["permissions"] == [{"module": "apps", "can": ["view"]}]


def test_managed_clusters_never_ask_for_kubeconfig_and_flag_failures(monkeypatch):
    clusters = [{"clusterName": "prod", "status": "active"},
                {"clusterName": "dev", "status": "failed", "errorMessage": "e" * 900}, None]
    api = FakeAPI({"ManagedClusters": {"listManagedClusters": clusters}})
    out = _run(monkeypatch, api, "list_managed_clusters", organization_id="org-1")
    assert out["count"] == 2 and out["attention"] == ["Cluster dev failed to provision or update."]
    assert len(out["clusters"][1]["errorMessage"]) < 900
    assert api.calls[0][1] == {"orgId": "org-1"}
    # the query text itself must not select the credentials-bearing fields
    import inspect
    source = inspect.getsource(infra_tools.register_infra_tools)
    query = source.split("query ManagedClusters")[1].split('"""')[0]
    assert "kubeconfig" not in query and "endpoint" not in query and "pulumiStack" not in query


def test_vm_node_pools_flag_degraded_ones(monkeypatch):
    pools = [{"poolName": "a", "status": "ready"}, {"poolName": "b", "status": "degraded"}]
    out = _run(monkeypatch, FakeAPI({"VmNodePools": {"listVMNodePools": pools}}),
               "list_vm_node_pools", organization_id="org-1")
    assert out["count"] == 2 and out["attention"] == ["Node pool b is degraded."]


def test_plan_limits_message_when_empty(monkeypatch):
    out = _run(monkeypatch, FakeAPI({"PlanLimits": {"getUserPermissionsByPlan": {"planName": "Pro"}}}),
               "get_plan_limits")
    assert out == {"planName": "Pro"}
    assert "message" in _run(monkeypatch, FakeAPI(), "get_plan_limits")


def test_list_agents_flags_disconnected_ones(monkeypatch):
    agents = [{"clusterID": "c1", "status": "CONNECTED"}, {"clusterID": "c2", "status": "DISCONNECTED"}]
    out = _run(monkeypatch, FakeAPI({"Agents": {"listAgents": agents}}), "list_agents")
    assert out["count"] == 2 and out["attention"] == ["Agent for cluster c2 is not connected."]


def test_agent_metrics_cap_nodes_and_apps(monkeypatch):
    metrics = {"cpuUsage": 40, "nodes": [{"name": f"n{i}"} for i in range(80)],
               "applications": [{"name": f"a{i}"} for i in range(150)]}
    api = FakeAPI({**AGENTS, "AgentMetrics": {"getAgentMetrics": metrics}})
    out = _run(monkeypatch, api, "get_agent_metrics", cluster_id="c1", time_range="6h")
    assert len(out["nodes"]) == 50 and len(out["applications"]) == 100 and out["applications_total"] == 150
    assert _backend_calls(api)[-1][1] == {"id": "c1", "range": "6h"}
    with pytest.raises(ToolError):
        _run(monkeypatch, api, "get_agent_metrics", cluster_id="c1", time_range="1h; drop")
    empty = _run(monkeypatch, FakeAPI(AGENTS), "get_agent_metrics", cluster_id="c1")
    assert "message" in empty


def test_security_findings_validate_filters_before_any_call(monkeypatch):
    api = FakeAPI(AGENTS)
    with pytest.raises(ToolError, match="severity must be one of"):
        _run(monkeypatch, api, "get_agent_security_findings", cluster_id="c1", severity="urgent")
    assert _backend_calls(api) == []


def test_security_findings_send_enum_values_and_clip_text(monkeypatch):
    findings = [{"id": str(i), "description": "d" * 900, "remediation": "r" * 900} for i in range(5)]
    api = FakeAPI({**AGENTS, "Findings": {"getSecurityFindings": findings}})
    out = _run(monkeypatch, api, "get_agent_security_findings", cluster_id="c1",
               severity="High", status="false-positive", limit=2)
    assert out["shown"] == 2 and out["total"] == 5 and len(out["findings"][0]["description"]) < 900
    assert _backend_calls(api)[-1][1] == {"id": "c1", "severity": "HIGH", "status": "FALSE_POSITIVE"}


def test_health_checks_count_those_needing_attention(monkeypatch):
    checks = [{"status": "HEALTHY", "message": "ok"}, {"status": "CRITICAL", "message": "m" * 900}]
    out = _run(monkeypatch, FakeAPI({**AGENTS, "HealthChecks": {"getHealthChecks": checks}}),
               "get_agent_health_checks", cluster_id="c1")
    assert out["count"] == 2 and out["needing_attention"] == 1 and len(out["checks"][1]["message"]) < 900


def test_forecast_uses_the_org_slug_quoted_and_returns_no_charts(monkeypatch):
    api = FakeAPI(forecast={"max_cpu": "70%", "actual_plot": "IMG", "recommendations": ["scale"]})
    out = _run(monkeypatch, api, "get_resource_forecast", organization_id="org-1")
    assert out["scope"] == "organization" and out["max_cpu"] == "70%" and "actual_plot" not in out
    assert api.calls == [("lstm_get", "/api/forecast/namespace/acme%20team")]


def test_app_forecast_checks_the_app_and_its_organization(monkeypatch):
    api = FakeAPI(forecast={"max_mem": "55%"})
    out = _run(monkeypatch, api, "get_resource_forecast", organization_id="org-1", app_name="web")
    assert out["scope"] == "web"
    assert api.calls == [("lstm_get", "/api/forecast/app/acme%20team/web")]
    with pytest.raises(ToolError, match="No app named 'ghost'"):
        _run(monkeypatch, FakeAPI(), "get_resource_forecast", organization_id="org-1", app_name="ghost")
    other = FakeAPI(apps={"web": {"id": "app-1", "name": "web", "organizationId": "org-2"}})
    with pytest.raises(ToolError, match="different organization"):
        _run(monkeypatch, other, "get_resource_forecast", organization_id="org-1", app_name="web")
    assert other.calls == []


def test_forecast_reports_missing_metrics_instead_of_failing(monkeypatch):
    out = _run(monkeypatch, FakeAPI(forecast=None), "get_resource_forecast", organization_id="org-1")
    assert "message" in out


def test_backend_errors_become_tool_errors(monkeypatch):
    class Boom(FakeAPI):
        async def graphql(self, *a, **k):
            raise NifeAPIError("backend down")

    with pytest.raises(ToolError, match="backend down"):
        _run(monkeypatch, Boom(), "list_roles")
