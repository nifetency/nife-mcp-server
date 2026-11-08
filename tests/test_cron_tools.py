"""Tests for the cron job tools."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from nife_mcp_server import cron_tools
from nife_mcp_server.nife_api import NifeAPIError


def _tool(name):
    mcp = FastMCP("test")
    cron_tools.register_cron_tools(mcp)
    return mcp._tool_manager.get_tool(name).fn


def test_tools_register_with_the_right_hints():
    mcp = FastMCP("test")
    cron_tools.register_cron_tools(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert set(tools) == {"list_cron_job_runs", "get_cron_job_run_logs", "trigger_cron_job_run"}
    assert tools["list_cron_job_runs"].annotations.readOnlyHint is True
    assert tools["get_cron_job_run_logs"].annotations.readOnlyHint is True
    assert tools["trigger_cron_job_run"].annotations.readOnlyHint is False
    assert tools["trigger_cron_job_run"].annotations.destructiveHint is False


@pytest.mark.parametrize("name, ok", [
    ("nightly-report-29012345", True), ("a", True), ("job.v1-2", True),
    ("Nightly", False), ("-bad", False), ("bad-", False), ("a b", False), ("x;drop", False), ("", False),
])
def test_run_name_shape(name, ok):
    if ok:
        assert cron_tools._run_name(name) == name
    else:
        with pytest.raises((ValueError, NifeAPIError)):
            cron_tools._run_name(name)


def test_cron_app_detection():
    assert cron_tools._is_cron_app({"cronSchedule": "0 2 * * *"})
    assert cron_tools._is_cron_app({"workloadType": "CronJob"})
    assert not cron_tools._is_cron_app({"workloadType": "deployment"})
    assert not cron_tools._is_cron_app({})


class FakeAPI:
    def __init__(self, responses=None, app=None):
        self.calls = []
        self.responses = responses or {}
        self.app_record = app if app is not None else {
            "id": "app-1", "name": "nightly", "cronSchedule": "0 2 * * *", "imageName": "acme/job:1"}

    async def app(self, name):
        return self.app_record if name == "nightly" else None

    async def graphql(self, query, variables=None, timeout=60.0):
        self.calls.append((query, variables))
        for key, data in self.responses.items():
            if key in query:
                return data
        return {}


def _run(monkeypatch, api, name, **kwargs):
    monkeypatch.setattr(cron_tools, "get_api", lambda ctx: api)
    return asyncio.run(_tool(name)(ctx=None, **kwargs))


def test_app_keyed_tools_prove_the_app_first(monkeypatch):
    api = FakeAPI()
    for name, kw in [("list_cron_job_runs", {}), ("get_cron_job_run_logs", {"run_name": "r1"}),
                     ("trigger_cron_job_run", {"confirm": True})]:
        with pytest.raises(ToolError, match="No app named 'ghost'"):
            _run(monkeypatch, api, name, app_name="ghost", **kw)
    assert api.calls == []


def test_list_runs_flags_failures_and_clips_messages(monkeypatch):
    runs = [{"name": "r3", "status": "failed", "message": "m" * 900},
            {"name": "r2", "status": "succeeded"}, None]
    api = FakeAPI({"cronJobRuns(": {"cronJobRuns": runs}})
    out = _run(monkeypatch, api, "list_cron_job_runs", app_name="nightly", limit=500)
    assert out["count"] == 2 and out["runs"][0]["name"] == "r3"
    assert len(out["runs"][0]["message"]) < 900
    assert out["attention"] == ["1 failed run(s), most recent: r3."]
    assert api.calls[0][1]["limit"] == 50


def test_logs_validate_the_run_name_before_any_call(monkeypatch):
    api = FakeAPI()
    with pytest.raises(ToolError, match="run_name"):
        _run(monkeypatch, api, "get_cron_job_run_logs", app_name="nightly", run_name="x; drop")
    assert api.calls == []


def test_logs_are_trimmed_to_the_tail(monkeypatch):
    big = "x" * 30000 + "END"
    api = FakeAPI({"cronJobRunLogs(": {"cronJobRunLogs": {"runName": "r1", "podName": "p", "logs": big}}})
    out = _run(monkeypatch, api, "get_cron_job_run_logs", app_name="nightly", run_name="r1", region="in-blr")
    assert out["logs"].endswith("END") and len(out["logs"]) == cron_tools.MAX_LOG_CHARS
    assert out["truncated_to_last_chars"] == cron_tools.MAX_LOG_CHARS
    assert api.calls[0][1] == {"appName": "nightly", "runName": "r1", "region": "in-blr"}


def test_trigger_previews_unless_confirmed(monkeypatch):
    api = FakeAPI()
    out = _run(monkeypatch, api, "trigger_cron_job_run", app_name="nightly")
    assert out["started"] is False and out["schedule"] == "0 2 * * *" and out["image"] == "acme/job:1"
    assert api.calls == []


def test_trigger_refuses_apps_that_are_not_cron_jobs(monkeypatch):
    api = FakeAPI(app={"id": "app-1", "name": "nightly", "workloadType": "deployment"})
    with pytest.raises(ToolError, match="not a cron job app"):
        _run(monkeypatch, api, "trigger_cron_job_run", app_name="nightly", confirm=True)
    assert api.calls == []


def test_confirmed_trigger_starts_one_run(monkeypatch):
    run = {"name": "nightly-manual-1", "region": "in-blr", "status": "pending", "trigger": "manual"}
    api = FakeAPI({"triggerCronJobRun(": {"triggerCronJobRun": run}})
    out = _run(monkeypatch, api, "trigger_cron_job_run", app_name="nightly", confirm=True, region="in-blr")
    assert out["started"] is True and out["run"]["name"] == "nightly-manual-1"
    assert len(api.calls) == 1 and api.calls[0][1] == {"appName": "nightly", "region": "in-blr"}
    empty = FakeAPI({"triggerCronJobRun(": {}})
    with pytest.raises(ToolError, match="did not return the new run"):
        _run(monkeypatch, empty, "trigger_cron_job_run", app_name="nightly", confirm=True)
