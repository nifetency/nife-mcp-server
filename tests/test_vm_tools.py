"""Tests for the VM power and cloud account validation tools."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import vm_tools


def _tool(name):
    mcp = FastMCP("test")
    vm_tools.register_vm_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def test_tools_register_with_the_right_hints():
    mcp = FastMCP("test")
    vm_tools.register_vm_tools(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert set(tools) == {"vm_power_action", "validate_cloud_account"}
    assert tools["vm_power_action"].annotations.destructiveHint is True
    assert tools["validate_cloud_account"].annotations.readOnlyHint is False
    assert tools["validate_cloud_account"].annotations.destructiveHint is False


@pytest.mark.parametrize("host_type, expected", [
    ("AWS", "NodeActionAWS"), (" aws ", "NodeActionAWS"), ("Azure", "NodeActionAzure"),
    ("GCP", "NodeAction"), ("", "NodeAction"), (None, "NodeAction"),
])
def test_mutation_follows_the_dashboard_rule(host_type, expected):
    assert vm_tools._mutation_for(host_type) == expected


class FakeAPI:
    def __init__(self, hosts=None, accounts=None):
        self.calls = []
        self.hosts = hosts if hosts is not None else [
            {"id": 1, "type": "AWS", "status": "running", "zone": "ap-south-1", "instanceName": "vm-1"}]
        self.accounts = accounts if accounts is not None else [{"id": "acc-1"}]

    async def organizations(self):
        return [{"id": "org-1", "name": "Acme", "slug": "acme"}]

    async def graphql(self, query, variables=None, timeout=60.0):
        self.calls.append((query, variables))
        if "query OwnHosts" in query:
            return {"getHost": self.hosts}
        if "query OwnCloudAccounts" in query:
            return {"listCloudAccounts": self.accounts}
        if "mutation VmPower" in query:
            name = "NodeActionAWS" if "NodeActionAWS" in query else "NodeAction"
            return {name: {"id": 1, "message": "queued", "nodeId": "i-1"}}
        if "mutation ValidateCloudAccount" in query:
            return {"validateCloudAccount": {"id": "acc-1", "status": "active"}}
        return {}


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(vm_tools, "get_api", lambda ctx: api)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def _mutations(api):
    return [q for q, _ in api.calls if q.lstrip().startswith("mutation")]


def test_power_action_rejects_bad_input_before_any_call(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="action must be one of"):
        _run(monkeypatch, api, "vm_power_action", organization_id="org-1", instance_name="vm-1", action="delete")
    with pytest.raises(ToolError, match="instance_name is required"):
        _run(monkeypatch, api, "vm_power_action", organization_id="org-1", instance_name=" ", action="stop")
    with pytest.raises(ToolError, match="Unknown organization_id"):
        _run(monkeypatch, api, "vm_power_action", organization_id="org-x", instance_name="vm-1", action="stop")
    assert api.calls == []


def test_power_action_only_acts_on_the_organizations_own_hosts(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="No server with that instance_name"):
        _run(monkeypatch, api, "vm_power_action", organization_id="org-1", instance_name="other-vm",
             action="stop", confirm=True)
    assert _mutations(api) == []


def test_power_action_previews_unless_confirmed(monkeypatch):
    api = FakeAPI()
    out = _run(monkeypatch, api, "vm_power_action", organization_id="org-1", instance_name="vm-1", action="Stop")
    assert out["performed"] is False and out["action"] == "stop" and out["current_status"] == "running"
    assert _mutations(api) == []


def test_confirmed_power_action_uses_the_cloud_specific_mutation(monkeypatch):
    api = FakeAPI()
    out = _run(monkeypatch, api, "vm_power_action", organization_id="org-1", instance_name="vm-1",
               action="restart", confirm=True)
    assert out == {"performed": True, "action": "restart", "instance_name": "vm-1",
                   "message": "queued", "node_id": "i-1"}
    (mutation,) = _mutations(api)
    assert "NodeActionAWS(" in mutation
    assert api.calls[-1][1] == {"input": {"instanceName": "vm-1", "action": "restart"}}

    generic = FakeAPI(hosts=[{"id": 2, "type": "GCP", "instanceName": "vm-2"}])
    _run(monkeypatch, generic, "vm_power_action", organization_id="org-1", instance_name="vm-2",
         action="start", confirm=True)
    assert "NodeAction(" in _mutations(generic)[0] and "NodeActionAWS" not in _mutations(generic)[0]


def test_validate_cloud_account_checks_ownership_first(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="No cloud account with that id"):
        _run(monkeypatch, api, "validate_cloud_account", organization_id="org-1", account_id="acc-foreign")
    assert _mutations(api) == []
    with pytest.raises(ToolError, match="Unknown organization_id"):
        _run(monkeypatch, FakeAPI(), "validate_cloud_account", organization_id="org-x", account_id="acc-1")
    out = _run(monkeypatch, api, "validate_cloud_account", organization_id="org-1", account_id="acc-1")
    assert out == {"id": "acc-1", "status": "active"} and len(_mutations(api)) == 1
