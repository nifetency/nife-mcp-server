"""Tests for running the curated tools inside the local stdio server."""
import asyncio
import json

import pytest

pytest.importorskip("mcp")
httpx = pytest.importorskip("httpx")
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402

from nife_mcp_server import nife_api, stdio_tools, tool_utils  # noqa: E402
from nife_mcp_server.intelligent_main import IntelligentNifeMCPServer  # noqa: E402
from nife_mcp_server.stdio_tools import CuratedTools  # noqa: E402
from nife_mcp_server.tool_registry import register_all_tools  # noqa: E402


class NoRequestCtx:
    """What FastMCP hands a tool when there is no HTTP request: the property raises."""

    @property
    def request_context(self):
        raise ValueError("Context is not available outside of a request")


class HTTPCtx:
    def __init__(self, headers):
        request = type("Request", (), {"headers": headers})()
        self.request_context = type("RequestContext", (), {"request": request})()


@pytest.fixture(autouse=True)
def reset_token():
    tool_utils.set_stdio_token(None)
    yield
    tool_utils.set_stdio_token(None)


def _run(coro):
    return asyncio.run(coro)


def _rpc(server, method, params=None):
    return _run(server.handle_request({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}))


def _native_server():
    srv = IntelligentNifeMCPServer()
    srv.tools = {
        "query_apps": {"name": "query_apps", "description": "native query", "inputSchema": {"type": "object"}},
        "list_sites": {"name": "list_sites", "description": "native", "inputSchema": {"type": "object"}},
    }
    return srv


# ---------------------------------------------------------------- credentials
def test_stdio_token_is_used_when_there_is_no_request():
    tool_utils.set_stdio_token("abc")
    assert tool_utils.get_api(NoRequestCtx())._auth == "Bearer abc"
    tool_utils.set_stdio_token("Bearer xyz")
    assert tool_utils.get_api(NoRequestCtx())._auth == "Bearer xyz"


def test_no_request_and_no_token_is_an_error_that_names_the_fix():
    with pytest.raises(ToolError, match="NIFE_ACCESS_TOKEN"):
        tool_utils.get_api(NoRequestCtx())


def test_http_calls_never_fall_back_to_the_stdio_token():
    tool_utils.set_stdio_token("local")
    with pytest.raises(ToolError, match="Missing Authorization header"):
        tool_utils.get_api(HTTPCtx({}))
    assert tool_utils.get_api(HTTPCtx({"authorization": "Bearer remote"}))._auth == "Bearer remote"


# ------------------------------------------------------------------- registry
def test_registry_matches_the_hosted_server():
    from nife_mcp_server.http_app import mcp as hosted

    fresh = FastMCP("test")
    register_all_tools(fresh)

    def names(m):
        return {t.name for t in m._tool_manager.list_tools()}

    assert names(fresh) == names(hosted)


# ----------------------------------------------------------- CuratedTools
def test_curated_list_has_schemas_and_annotations():
    listing = _run(CuratedTools("tok").list())
    names = {t["name"] for t in listing}
    assert {"list_sites", "get_health_insights", "list_clusters"} <= names
    assert all(t["inputSchema"] for t in listing)
    sites = next(t for t in listing if t["name"] == "list_sites")
    assert sites["annotations"]["readOnlyHint"] is True


def test_curated_call_reports_errors_as_results():
    tools = CuratedTools("tok")
    bad = _run(tools.call("get_site_status", {"site_name": "bad name!"}))
    assert bad["isError"] is True and bad["content"][0]["type"] == "text"
    assert _run(tools.call("no_such_tool", {}))["isError"] is True


def test_curated_call_sends_the_local_token_to_the_backend(monkeypatch):
    class FakeHTTP:
        def __init__(self):
            self.calls = []
            self.is_closed = False

        async def request(self, method, url, params=None, json=None, headers=None, timeout=None):
            self.calls.append(headers or {})
            return httpx.Response(200, json={"data": {"organizations": {"nodes": []}}})

    fake = FakeHTTP()
    monkeypatch.setattr(nife_api, "_http", lambda: fake)
    res = _run(CuratedTools("tok-local").call("list_organizations", {}))
    assert "content" in res
    assert fake.calls and fake.calls[0].get("Authorization") == "Bearer tok-local"


# ------------------------------------------------------ the stdio server itself
def test_tools_list_merges_and_the_schema_generated_tool_wins():
    srv = _native_server()
    srv._load_curated("tok")
    tools = _rpc(srv, "tools/list")["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "query_apps" in names and "get_health_insights" in names
    assert names.count("list_sites") == 1
    assert next(t for t in tools if t["name"] == "list_sites")["description"] == "native"


def test_tools_call_routes_curated_names_and_leaves_native_ones_alone():
    srv = _native_server()
    srv._load_curated("tok")
    res = _rpc(srv, "tools/call", {"name": "get_site_status", "arguments": {"site_name": "bad name!"}})
    assert res["result"]["isError"] is True
    # A native name still takes the original path (the schema is not loaded in this test).
    native = _rpc(srv, "tools/call", {"name": "health_check", "arguments": {}})
    assert "not ready" in json.loads(native["result"]["content"][0]["text"])["error"].lower()


def test_initialize_carries_the_usage_instructions():
    srv = _native_server()
    srv.ready = True  # skip schema loading
    srv._load_curated("tok")
    result = _rpc(srv, "initialize")["result"]
    assert "NERO" in result["instructions"]


def test_server_runs_without_the_optional_dependencies(monkeypatch):
    def missing(token):
        raise ImportError("No module named 'mcp'")

    monkeypatch.setattr(stdio_tools, "CuratedTools", missing)
    srv = _native_server()
    srv._load_curated("tok")
    assert srv.curated is None
    tools = _rpc(srv, "tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == ["query_apps", "list_sites"]
    assert "instructions" not in _rpc(_with_ready(srv), "initialize")["result"]


def _with_ready(srv):
    srv.ready = True
    return srv
