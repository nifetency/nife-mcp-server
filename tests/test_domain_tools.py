"""Tests for the custom-domain tools and their pure helpers."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import domain_helpers as d
from nife_mcp_server import domain_tools
from nife_mcp_server.nife_api import NifeAPIError


# ------------------------------------------------------------------ pure helpers
def test_validate_domain_accepts_normal_names_and_normalizes():
    assert d.validate_domain("Example.COM") == "example.com"
    assert d.validate_domain("  www.example.com. ") == "www.example.com"
    assert d.validate_domain("a-b.c1.example.co.uk") == "a-b.c1.example.co.uk"


@pytest.mark.parametrize(
    "bad",
    [
        "", "   ", "localhost", "https://example.com", "example.com/path", "example.com:8080",
        "exa mple.com", "*.example.com", "-bad.example.com", "bad-.example.com", "1.2.3.4",
        "x" * 250 + ".com", "nifetency.com", "app.on.nifetency.com", "nife.io", "x.nife.io",
    ],
)
def test_validate_domain_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        d.validate_domain(bad)


def test_lookalike_of_reserved_domain_is_allowed():
    assert d.validate_domain("notnife.io") == "notnife.io"
    assert d.validate_domain("nifetency.com.evil.org") == "nifetency.com.evil.org"


def test_dns_instructions_and_apex_note():
    sub = d.dns_instructions("site", "demo", "www.example.com")
    assert sub["record"] == {"type": "CNAME", "name": "www.example.com", "value": "demo.on.nifetency.com", "ttl": "Auto"}
    assert not any("apex" in n for n in sub["notes"])
    apex = d.dns_instructions("app", "demo", "example.com")
    assert any("apex" in n for n in apex["notes"])


def test_service_port_follows_the_dashboard_rule():
    assert d.service_port({"services": [{"external_port": 3000}]}) == 3000
    assert d.service_port({"services": [{"external_port": "8081"}]}) == 8081
    assert d.service_port('{"services": [{"external_port": 9000}]}') == 9000
    for bad in (None, {}, {"services": []}, {"services": [{}]}, {"services": [{"external_port": 0}]},
                {"services": [{"external_port": "x"}]}, "not json"):
        assert d.service_port(bad) == d.DEFAULT_SERVICE_PORT


def test_namespace_prefers_slug_then_name_then_default():
    assert d.namespace_for({"slug": "acme", "name": "Acme Inc"}) == "acme"
    assert d.namespace_for({"name": "Acme Inc"}) == "Acme Inc"
    assert d.namespace_for(None) == "default"


def test_app_domain_view():
    assert d.app_domain_view({"exists": False}) == {"configured": False}
    view = d.app_domain_view({"exists": True, "domain": "a.com", "synced": True, "status": "active"})
    assert view["configured"] and view["state"] == "active" and view["ssl"]["enabled"] is True
    assert d.app_domain_view({"exists": True, "domain": "a.com", "synced": False})["state"] == "pending"


# ------------------------------------------------------------------- tool flow
class FakeAPI:
    """Records every backend call, in order."""

    def __init__(self, *, app_domain=None, site_domain=None, site_status="active",
                 ingress_success=True, ingress_error=None, domain_key="app-uuid"):
        self.calls = []
        self._app_domain = app_domain          # domain string stored for the app, or None
        self._domain_key = domain_key          # key the backend knows the domain under
        self._site_domain = site_domain
        self._site_status = site_status
        self._ingress_success = ingress_success
        self._ingress_error = ingress_error

    # -- lookups used by require_site / _require_app
    async def site(self, name):
        return {"id": "site-1", "s3AppName": name, "status": self._site_status}

    async def app(self, name):
        return {"id": "app-uuid", "name": name, "appUrl": f"https://{name}.on.nifetency.com"}

    # -- sites
    async def custom_domain(self, bucket):
        return self._site_domain

    async def sync_dns_site(self, domain, bucket):
        self.calls.append(("sync_dns_site", domain, bucket))
        return {"ok": True}

    async def delete_site_domain(self, bucket):
        self.calls.append(("delete_site_domain", bucket))
        return {}

    # -- apps
    async def app_domain_status(self, key):
        self.calls.append(("app_domain_status", key))
        if self._app_domain and key == self._domain_key:
            return {"exists": True, "domain": self._app_domain, "synced": True, "status": "active"}
        return {"exists": False}

    async def elb_url(self, app_name):
        self.calls.append(("elb_url", app_name))
        return "elb-123.example.amazonaws.com"

    async def sync_dns_app(self, domain, elb_url, app_name):
        self.calls.append(("sync_dns_app", domain, elb_url, app_name))
        return {"ok": True}

    async def app_ingress_info(self, name):
        self.calls.append(("app_ingress_info", name))
        return {"organization": {"slug": "acme", "name": "Acme"},
                "config": {"definition": {"services": [{"external_port": 3000}]}}}

    async def add_ingress_rule(self, **kwargs):
        self.calls.append(("add_ingress_rule", kwargs))
        if self._ingress_error:
            raise NifeAPIError(self._ingress_error)
        return {"success": self._ingress_success, "message": "no" if not self._ingress_success else "ok"}

    async def delete_app_domain(self, key):
        self.calls.append(("delete_app_domain", key))
        return {}


def _tool(name):
    mcp = FastMCP("test")
    domain_tools.register_domain_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(domain_tools, "get_api", lambda ctx: api)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def _names(api):
    return [c[0] for c in api.calls]


def _mutations(api):
    return [c for c in api.calls if c[0] != "app_domain_status"]


def test_all_domain_tools_are_registered():
    mcp = FastMCP("test")
    domain_tools.register_domain_tools(mcp)
    names = {t.name for t in mcp._tool_manager.list_tools()}
    assert names == {
        "get_domain_dns_instructions", "get_app_custom_domain", "add_app_custom_domain",
        "remove_app_custom_domain", "add_site_custom_domain", "remove_site_custom_domain",
    }


# -- instructions
def test_dns_instructions_tool(monkeypatch):
    out = _run(monkeypatch, FakeAPI(), "get_domain_dns_instructions",
               resource_type="site", resource_name="demo-site", domain="WWW.Example.com")
    assert out["record"]["value"] == "demo-site.on.nifetency.com"
    assert out["domain"] == "www.example.com"
    with pytest.raises(ToolError):
        _run(monkeypatch, FakeAPI(), "get_domain_dns_instructions",
             resource_type="app", resource_name="demo", domain="https://x.com")


# -- apps
def test_add_app_domain_follows_the_dashboard_sequence(monkeypatch):
    api = FakeAPI()
    out = _run(monkeypatch, api, "add_app_custom_domain", app_name="demo", domain="App.Example.com")
    assert [c[0] for c in _mutations(api)] == ["elb_url", "sync_dns_app", "app_ingress_info", "add_ingress_rule"]
    calls = {c[0]: c for c in api.calls}
    assert calls["sync_dns_app"][1:] == ("app.example.com", "elb-123.example.amazonaws.com", "demo")
    ingress = calls["add_ingress_rule"][1]
    assert ingress == {"app_name": "demo", "namespace": "acme", "hosts": ["app.example.com"],
                       "service_name": "demo-service", "service_port": 3000}
    assert out["domain_saved"] and out["ingress_configured"] and not out["resumed"]
    assert out["url"] == "https://app.example.com"


def test_add_app_domain_ingress_failure_reports_saved_domain_without_raising(monkeypatch):
    for api in (FakeAPI(ingress_error="cluster unreachable"), FakeAPI(ingress_success=False)):
        out = _run(monkeypatch, api, "add_app_custom_domain", app_name="demo", domain="app.example.com")
        assert out["domain_saved"] is True and out["ingress_configured"] is False
        assert "retry" in out["next_step"]


def test_add_app_domain_retry_skips_dns_and_reruns_ingress(monkeypatch):
    api = FakeAPI(app_domain="app.example.com")
    out = _run(monkeypatch, api, "add_app_custom_domain", app_name="demo", domain="app.example.com")
    assert out["resumed"] is True
    assert "sync_dns_app" not in _names(api) and "elb_url" not in _names(api)
    assert "add_ingress_rule" in _names(api)


def test_add_app_domain_refuses_a_second_domain(monkeypatch):
    api = FakeAPI(app_domain="old.example.com")
    with pytest.raises(ToolError, match="already has"):
        _run(monkeypatch, api, "add_app_custom_domain", app_name="demo", domain="new.example.com")
    assert _mutations(api) == []


def test_add_app_domain_validation_failure_changes_nothing(monkeypatch):
    api = FakeAPI()
    for bad in ("nife.io", "http://x.com", "localhost"):
        with pytest.raises(ToolError):
            _run(monkeypatch, api, "add_app_custom_domain", app_name="demo", domain=bad)
    assert api.calls == []


def test_add_app_domain_backend_failure_names_the_step(monkeypatch):
    class Failing(FakeAPI):
        async def sync_dns_app(self, *a):
            raise NifeAPIError("CNAME not found")

    with pytest.raises(ToolError, match="syncing the DNS record.*CNAME not found"):
        _run(monkeypatch, Failing(), "add_app_custom_domain", app_name="demo", domain="app.example.com")


def test_get_app_domain(monkeypatch):
    out = _run(monkeypatch, FakeAPI(app_domain="app.example.com"), "get_app_custom_domain", app_name="demo")
    assert out["configured"] and out["domain"] == "app.example.com" and out["state"] == "active"
    assert out["cname_target"] == "demo.on.nifetency.com"
    assert _run(monkeypatch, FakeAPI(), "get_app_custom_domain", app_name="demo")["configured"] is False


def test_get_app_domain_found_under_the_app_name_key(monkeypatch):
    api = FakeAPI(app_domain="app.example.com", domain_key="demo")
    out = _run(monkeypatch, api, "get_app_custom_domain", app_name="demo")
    assert out["configured"] is True


def test_remove_app_domain_requires_exact_confirmation(monkeypatch):
    api = FakeAPI(app_domain="app.example.com")
    with pytest.raises(ToolError, match="confirm_domain"):
        _run(monkeypatch, api, "remove_app_custom_domain", app_name="demo", confirm_domain="other.com")
    assert "delete_app_domain" not in _names(api)

    out = _run(monkeypatch, api, "remove_app_custom_domain", app_name="demo", confirm_domain="APP.example.com")
    assert out["removed"] is True
    assert ("delete_app_domain", "app-uuid") in api.calls


def test_remove_app_domain_uses_the_key_that_matched(monkeypatch):
    api = FakeAPI(app_domain="app.example.com", domain_key="demo")
    _run(monkeypatch, api, "remove_app_custom_domain", app_name="demo", confirm_domain="app.example.com")
    assert ("delete_app_domain", "demo") in api.calls


def test_remove_app_domain_when_none_configured(monkeypatch):
    with pytest.raises(ToolError, match="no custom domain"):
        _run(monkeypatch, FakeAPI(), "remove_app_custom_domain", app_name="demo", confirm_domain="a.com")


# -- sites
def test_add_site_domain(monkeypatch):
    api = FakeAPI()
    out = _run(monkeypatch, api, "add_site_custom_domain", site_name="demo-site", domain="WWW.example.com")
    assert api.calls == [("sync_dns_site", "www.example.com", "demo-site")]
    assert out["added"] is True and out["dns"]["value"] == "demo-site.on.nifetency.com"


def test_add_site_domain_is_idempotent_for_the_same_domain(monkeypatch):
    api = FakeAPI(site_domain="www.example.com")
    out = _run(monkeypatch, api, "add_site_custom_domain", site_name="demo-site", domain="www.example.com")
    assert out["already_configured"] is True and api.calls == []


def test_add_site_domain_refuses_a_second_domain_and_suspended_sites(monkeypatch):
    api = FakeAPI(site_domain="old.example.com")
    with pytest.raises(ToolError, match="already has"):
        _run(monkeypatch, api, "add_site_custom_domain", site_name="demo-site", domain="new.example.com")
    with pytest.raises(ToolError, match="suspended"):
        _run(monkeypatch, FakeAPI(site_status="suspended"), "add_site_custom_domain",
             site_name="demo-site", domain="new.example.com")
    assert api.calls == []


def test_remove_site_domain_requires_exact_confirmation(monkeypatch):
    api = FakeAPI(site_domain="www.example.com")
    with pytest.raises(ToolError, match="confirm_domain"):
        _run(monkeypatch, api, "remove_site_custom_domain", site_name="demo-site", confirm_domain="x.com")
    assert api.calls == []
    out = _run(monkeypatch, api, "remove_site_custom_domain", site_name="demo-site", confirm_domain="www.example.com")
    assert out["removed"] is True and api.calls == [("delete_site_domain", "demo-site")]
    with pytest.raises(ToolError, match="no custom domain"):
        _run(monkeypatch, FakeAPI(), "remove_site_custom_domain", site_name="demo-site", confirm_domain="x.com")
