"""End-to-end tests for the hosted server (requires the `http` extra)."""
import pytest

pytest.importorskip("mcp")
httpx = pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from nife_mcp_server import nife_api  # noqa: E402
from nife_mcp_server.http_app import app  # noqa: E402

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class FakeHTTP:
    """Stands in for the shared httpx client; records what would hit the backend."""

    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        q = (json or {}).get("query", "")
        if "getUserPermissionsByPlan" in q:
            data = {"getUserPermissionsByPlan": {"sourceBuild": True}}
        elif "mutation S3Deployment" in q:
            data = {"S3Deployment": "Deployment started"}
        elif "mutation RedeployS3" in q:
            data = {"RedeployS3": "Redeploy started"}
        elif "getS3deployments(" in q:
            data = {"getS3deployments": {"s3AppName": "my-site", "status": "BUILDING", "appUrl": None}}
        elif "organizations" in q:
            data = {"organizations": {"nodes": [
                {"id": "o1", "parentId": None, "name": "Acme", "slug": "acme", "type": "personal"},
                {"id": "o2", "parentId": "o1", "name": "Sub", "slug": "sub", "type": "x"},
            ]}}
        else:
            data = {}
        return httpx.Response(200, json={"data": data})


# The MCP session manager can only be started once per process, so share one client.
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fake(monkeypatch):
    f = FakeHTTP()
    monkeypatch.setattr(nife_api, "_http", lambda: f)
    return f


def rpc(client, method, params=None, token="tok-user-A", id_=1):
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


def call_tool(client, name, args, token="tok-user-A"):
    r = rpc(client, "tools/call", {"name": name, "arguments": args}, token=token)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


def test_glama_claim_is_public_and_does_not_redirect(client):
    r = client.get("/mcp/.well-known/glama.json", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    assert "location" not in r.headers
    assert "www-authenticate" not in r.headers
    assert r.json() == {
        "$schema": "https://glama.ai/mcp/schemas/connector.json",
        "claim": "glama_claim_138g5Mc4xxNowLypLtSR9Q8SncEkCkQ9",
    }


@pytest.mark.parametrize("method,path", [
    ("POST", "/mcp/.well-known/glama.json"),
    ("GET", "/mcp/.well-known/other.json"),
    ("GET", "/mcp/.well-known/glama.json/"),
    ("GET", "/mcp"),
])
def test_glama_claim_does_not_bypass_auth_for_other_requests(client, method, path):
    r = client.request(method, path, follow_redirects=False)
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_mcp_requires_bearer(client):
    r = rpc(client, "tools/list", token=None)
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")
    for bad in ("Basic abc", "Bearer", "Bearer   "):
        r = client.post("/mcp", headers={**MCP_HEADERS, "Authorization": bad}, json={})
        assert r.status_code == 401


def test_env_token_is_never_used_as_fallback(client, fake, monkeypatch):
    monkeypatch.setenv("NIFE_ACCESS_TOKEN", "server-secret")
    assert rpc(client, "tools/list", token=None).status_code == 401
    assert fake.calls == []


def test_tools_listed(client):
    r = rpc(client, "tools/list")
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"deploy_site", "redeploy_site", "list_organizations", "get_site_status",
            "list_site_frameworks", "list_git_secrets", "check_site_name", "list_sites"} <= names
    by_name = {t["name"]: t for t in r.json()["result"]["tools"]}
    assert by_name["list_organizations"]["annotations"]["readOnlyHint"] is True
    assert by_name["redeploy_site"]["annotations"]["destructiveHint"] is True
    # tokens must never be tool parameters
    for t in by_name.values():
        assert "token" not in " ".join(t["inputSchema"].get("properties", {})).lower().replace("pat_secret_name", "")


def test_list_organizations_forwards_callers_header_and_hides_suborgs(client, fake):
    res = call_tool(client, "list_organizations", {}, token="tok-user-A")
    assert res.get("isError") in (False, None)
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer tok-user-A"
    text = str(res)
    assert "Acme" in text and "Sub" not in text


def test_tokens_do_not_leak_between_requests(client, fake):
    call_tool(client, "list_organizations", {}, token="tok-user-A")
    call_tool(client, "list_organizations", {}, token="tok-user-B")
    assert [c["headers"]["Authorization"] for c in fake.calls] == ["Bearer tok-user-A", "Bearer tok-user-B"]


def test_deploy_public_git_prebuilt(client, fake):
    res = call_tool(client, "deploy_site", {
        "site_name": "my-site", "organization_id": "o1", "source_type": "git",
        "repo_url": "https://github.com/acme/web", "branch": "main"})
    assert res.get("isError") in (False, None), res
    m = next(c for c in fake.calls if "mutation S3Deployment" in c["json"]["query"])
    v = m["json"]["variables"]
    assert v["s3Url"] == "https://github.com/acme/web/archive/refs/heads/main.zip"
    assert v["deployBuildFile"] is True and v["buildCommandsS3"] == []
    assert v["organizationId"] == "o1"
    assert m["headers"]["Authorization"] == "Bearer tok-user-A"


def test_deploy_from_source_uses_framework_preset(client, fake):
    res = call_tool(client, "deploy_site", {
        "site_name": "my-site", "organization_id": "o1", "source_type": "archive_url",
        "archive_url": "https://example.com/src.zip", "import_type": "source",
        "framework": "Vite", "env": {"API_URL": "https://api"}})
    assert res.get("isError") in (False, None), res
    v = next(c for c in fake.calls if "mutation S3Deployment" in c["json"]["query"])["json"]["variables"]
    assert v["deployBuildFile"] is False and v["buildFileName"] == "dist"
    assert v["buildCommandsS3"] == [{"s3Cmd": "npm install"}, {"s3Cmd": "npm run build"}, {"s3Cmd": "20"}]
    assert v["envVariablesS3"][0]["name"] == "API_URL"


def test_private_repo_resolves_pat_server_side(client, fake, monkeypatch):
    seen = {}

    async def fake_secret(self, name):
        seen["name"] = name
        return "ghp_realtoken"

    async def fake_upload(self, repo_url, branch, pat, provider):
        seen.update(pat=pat, provider=provider)
        return "https://s3.example/private.zip"

    monkeypatch.setattr(nife_api.NifeAPI, "secret_value", fake_secret)
    monkeypatch.setattr(nife_api.NifeAPI, "github_upload_to_s3", fake_upload)
    res = call_tool(client, "deploy_site", {
        "site_name": "my-site", "organization_id": "o1", "source_type": "git",
        "repo_url": "https://github.com/acme/private", "pat_secret_name": "my-pat"})
    assert res.get("isError") in (False, None), res
    assert seen == {"name": "my-pat", "pat": "ghp_realtoken", "provider": "github"}
    assert "ghp_realtoken" not in str(res)  # never echoed to the model


def test_invalid_input_returns_tool_error_not_backend_call(client, fake):
    res = call_tool(client, "deploy_site", {
        "site_name": "Bad Name", "organization_id": "o1", "source_type": "git",
        "repo_url": "https://github.com/acme/web"})
    assert res["isError"] is True
    assert not any("mutation S3Deployment" in c["json"]["query"] for c in fake.calls)


def test_redeploy_requires_existing_site(client, fake, monkeypatch):
    async def none_site(self, name):
        return None
    monkeypatch.setattr(nife_api.NifeAPI, "site", none_site)
    res = call_tool(client, "redeploy_site", {
        "site_name": "ghost", "source_type": "archive_url", "archive_url": "https://example.com/a.zip"})
    assert res["isError"] is True
