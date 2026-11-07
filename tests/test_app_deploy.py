"""Tests for the new-app deploy tools (list_app_regions, deploy_app) and their pure helpers."""
import asyncio
import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import app_tools
from nife_mcp_server import site_helpers as h
from nife_mcp_server.nife_api import NifeAPIError

ORG = "org-1"


# ------------------------------------------------------------------ pure helpers
def test_new_app_name_validation():
    for ok in ["a", "my-app", "swift-falcon-1234", "x" * 63]:
        app_tools._validate_new_app_name(ok)
    for bad in ["", "My-App", "my_app", "my app", "a.b", "x" * 64, "../x"]:
        with pytest.raises(ValueError):
            app_tools._validate_new_app_name(bad)


def test_image_validation():
    app_tools._validate_image("nginx:1.27")
    app_tools._validate_image("myorg/api:1.4.2")
    for bad in ["", "nginx latest", "x" * 301, "nginx\n"]:
        with pytest.raises(ValueError):
            app_tools._validate_image(bad)


def test_resource_requirements_requests_are_half_of_limits():
    assert app_tools._resource_requirements(0.5, 1024) == {
        "requestRequirement": {"cpu": "250m", "memory": "512Mi"},
        "LimitRequirement": {"cpu": "500m", "memory": "1024Mi"},
    }
    assert app_tools._resource_requirements(2, 2048)["LimitRequirement"]["cpu"] == "2000m"


def test_env_args_skip_empty_values_and_validate(monkeypatch):
    monkeypatch.delenv("NIFE_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("NIFE_ENV_ENCRYPTION_KEY", raising=False)
    assert app_tools._encrypted_env_args(None) == []
    assert app_tools._encrypted_env_args({"A": "1", "EMPTY": ""}) == ["A=1"]
    with pytest.raises(ValueError):
        app_tools._encrypted_env_args({"bad name": "x"})
    with pytest.raises(ValueError):
        app_tools._encrypted_env_args({"A": "x" * 8193})
    with pytest.raises(ValueError):
        app_tools._encrypted_env_args({f"V{i}": "x" for i in range(101)})


def test_env_args_are_encrypted_when_key_is_set(monkeypatch):
    key = "0123456789abcdef"
    monkeypatch.setenv("NIFE_ENCRYPTION_KEY", key)
    (entry,) = app_tools._encrypted_env_args({"TOKEN": "s3cret"})
    name, _, value = entry.partition("=")
    assert name == "TOKEN" and value != "s3cret"
    assert h.decrypt_secret(value, key) == "s3cret"


def test_org_regions_limit_to_defaults_and_dedupe():
    clusters = [
        {"regionCode": "us-east-1", "name": "US East", "clustertype": "shared"},
        {"regionCode": "ap-south-1", "name": "Mumbai", "clustertype": "shared"},
        {"regionCode": "ap-south-1", "name": "Mumbai again", "clustertype": "shared"},
        {"regionCode": "edge-1", "name": "Edge", "clustertype": "byoh"},
    ]
    org = [
        {"regCode": "ap-south-1", "isDefault": True},
        {"regCode": "edge-1", "isDefault": True},
        {"regCode": "us-east-1", "isDefault": False},
    ]
    assert [r["code"] for r in app_tools._filter_org_regions(clusters, org)] == ["ap-south-1", "edge-1"]
    # An organization with no region entries sees every cluster.
    assert [r["code"] for r in app_tools._filter_org_regions(clusters, [])] == [
        "us-east-1", "ap-south-1", "edge-1",
    ]


def test_approval_detection():
    msg = "Deployment gated: requires approval. Approval ID: appr_12-ab"
    assert app_tools._needs_approval(msg)
    assert app_tools._approval_id(msg) == "appr_12-ab"
    assert not app_tools._needs_approval("image not found")
    assert app_tools._approval_id("requires approval") is None


# ------------------------------------------------------------------- tool flow
class FakeAPI:
    """Records every backend call, in order."""

    def __init__(self, *, existing=None, deploy_error=None, secrets=None, org_regions=None):
        self.calls = []
        self.existing = existing
        self.deploy_error = deploy_error
        self.secrets = secrets if secrets is not None else []
        self._org_regions = org_regions if org_regions is not None else []

    async def organizations(self):
        return [{"id": ORG, "name": "Acme", "slug": "acme"}]

    async def available_clusters(self):
        return [
            {"regionCode": "ap-south-1", "name": "Mumbai", "clustertype": "shared"},
            {"regionCode": "us-east-1", "name": "US East", "clustertype": "shared"},
        ]

    async def org_regions(self, org_id):
        return self._org_regions

    async def list_secrets(self):
        return self.secrets

    async def app(self, name):
        self.calls.append(("app", name))
        if self.existing:
            return self.existing
        raise NifeAPIError("Could not find app")

    async def create_app(self, input_):
        self.calls.append(("create_app", input_))
        return {"id": "app-uuid", "name": input_["name"], "status": "new"}

    async def configure_regions(self, app_name, region_codes):
        self.calls.append(("configure_regions", app_name, region_codes))

    async def update_app(self, input_):
        self.calls.append(("update_app", input_))

    async def app_definition(self, name):
        self.calls.append(("app_definition", name))
        return {"app": name, "services": [{"internal_port": 3000}]}

    async def link_registry_secret(self, app_name, secret_name):
        self.calls.append(("link_registry_secret", app_name, secret_name))

    async def deploy_image(self, input_):
        self.calls.append(("deploy_image", input_))
        if self.deploy_error:
            raise NifeAPIError(self.deploy_error)
        return {"id": "rel-1", "version": 1, "status": "pending", "reason": "ok"}


def _tool(name):
    mcp = FastMCP("test")
    app_tools.register_app_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(app_tools, "get_api", lambda ctx: api)
    monkeypatch.delenv("NIFE_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("NIFE_ENV_ENCRYPTION_KEY", raising=False)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def _deploy(monkeypatch, api, **overrides):
    args = dict(app_name="demo", image="nginx:1.27", organization_id=ORG, region_codes=["ap-south-1"])
    args.update(overrides)
    return _run(monkeypatch, api, "deploy_app", **args)


def _names(api):
    return [c[0] for c in api.calls]


def test_list_app_regions(monkeypatch):
    out = _run(monkeypatch, FakeAPI(), "list_app_regions", organization_id=ORG)
    assert out["count"] == 2
    assert [r["code"] for r in out["regions"]] == ["ap-south-1", "us-east-1"]


def test_deploy_app_follows_the_dashboard_sequence(monkeypatch):
    api = FakeAPI(secrets=[{"name": "hub", "registryType": "docker"}])
    out = _deploy(monkeypatch, api, env={"MODE": "prod"}, registry_secret_name="hub", replicas=3)

    assert _names(api) == [
        "app", "create_app", "configure_regions", "update_app",
        "app_definition", "link_registry_secret", "deploy_image",
    ]
    calls = {c[0]: c for c in api.calls}
    create = calls["create_app"][1]
    assert create["name"] == "demo" and create["deploymentType"] == "docker"
    assert create["organizationId"] == ORG
    assert calls["configure_regions"][1:] == ("demo", ["ap-south-1"])

    update = calls["update_app"][1]
    assert update["appId"] == "app-uuid"
    assert update["replicas"] == 3 and update["internalPort"] == "3000" and update["externalPort"] == "80"
    assert json.loads(update["build"]) == {"builder": "image", "image": "nginx:1.27"}
    assert json.loads(update["resource"])["LimitRequirement"] == {"cpu": "500m", "memory": "1024Mi"}
    assert update["envMapArgs"] == ["MODE=prod"]  # no key configured: sent as-is

    deploy = calls["deploy_image"][1]
    assert deploy["appId"] == "demo" and deploy["image"] == "nginx:1.27"
    assert deploy["definition"]["app"] == "demo"
    assert deploy["envMapArgs"] == ["MODE=prod"]

    assert out["submitted"] is True and out["release"]["id"] == "rel-1"
    assert out["env_variable_names"] == ["MODE"]
    assert "MODE=prod" not in json.dumps(out)  # values never come back


def test_deploy_app_validation_failures_create_nothing(monkeypatch):
    cases = [
        dict(app_name="Bad_Name"),
        dict(image="nginx latest"),
        dict(strategy="blue-green"),
        dict(region_codes=["mars-1"]),
        dict(organization_id="someone-else"),
        dict(env={"bad name": "x"}),
        dict(registry_secret_name="missing"),
    ]
    for overrides in cases:
        api = FakeAPI()
        with pytest.raises(ToolError):
            _deploy(monkeypatch, api, **overrides)
        assert "create_app" not in _names(api), overrides


def test_deploy_app_refuses_to_touch_a_live_app(monkeypatch):
    api = FakeAPI(existing={"id": "x", "status": "active", "deployed": True, "organizationId": ORG})
    with pytest.raises(ToolError, match="already exists"):
        _deploy(monkeypatch, api)
    assert _names(api) == ["app"]


def test_deploy_app_resumes_an_undeployed_draft(monkeypatch):
    api = FakeAPI(existing={"id": "draft-uuid", "status": "new", "deployed": False, "organizationId": ORG})
    out = _deploy(monkeypatch, api)
    assert out["resumed_draft"] is True
    assert "create_app" not in _names(api)
    assert dict((c[0], c) for c in api.calls)["update_app"][1]["appId"] == "draft-uuid"


def test_deploy_app_draft_in_another_org_is_rejected(monkeypatch):
    api = FakeAPI(existing={"id": "d", "status": "new", "deployed": False, "organizationId": "other"})
    with pytest.raises(ToolError, match="different organization"):
        _deploy(monkeypatch, api)


def test_failure_after_create_explains_the_draft(monkeypatch):
    api = FakeAPI(deploy_error="image pull failed")
    with pytest.raises(ToolError) as exc:
        _deploy(monkeypatch, api)
    text = str(exc.value)
    assert "deploying the image" in text and "image pull failed" in text
    assert "draft" in text and "same name" in text


def test_approval_gate_is_reported_not_raised(monkeypatch):
    api = FakeAPI(deploy_error="Deployment gated: requires approval. Approval ID: appr_9")
    out = _deploy(monkeypatch, api)
    assert out["approval_pending"] is True and out["submitted"] is False
    assert out["approval_id"] == "appr_9"
