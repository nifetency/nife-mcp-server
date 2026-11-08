"""Cron job tools: run history, run logs, and starting a run now.

Operations mirror nife.io/api/cronjob_runs.graphqls. Every tool loads the app with the caller's own
token first, which doubles as the ownership check.
"""
import logging
import re
from typing import Annotated, Any, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server.nife_api import NifeAPIError
from nife_mcp_server.ops_helpers import clip
from nife_mcp_server.ops_tools import Limit, _cap, _need, _opt, guarded
from nife_mcp_server.platform_tools import AppName, _own_app
from nife_mcp_server.tool_utils import READ_ONLY, WRITE, get_api

logger = logging.getLogger(__name__)

CRON_INSTRUCTIONS = """\

CRON JOBS (container apps that run on a schedule)
- list_cron_job_runs shows an app's recent runs, newest first, with status (pending, running,
  succeeded, failed), whether it was scheduled or manual, how long it took, and why a failed run failed.
- get_cron_job_run_logs returns the last lines of one run's log. Logs can contain sensitive data:
  do not repeat secrets back.
- trigger_cron_job_run starts a run now. It previews first and only runs with confirm=true after the
  user agrees. It fails while another run is in progress.
"""

# Kubernetes object names: lowercase letters, digits, '-' and '.', starting and ending alphanumeric.
_RUN_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
MAX_LOG_CHARS = 20000


def _run_name(value: str) -> str:
    name = _need(value, "run_name")
    if not _RUN_NAME.match(name):
        raise ValueError("run_name must be a run name from list_cron_job_runs.")
    return name


def _is_cron_app(app: Dict[str, Any]) -> bool:
    return bool(app.get("cronSchedule")) or "cron" in (app.get("workloadType") or "").lower()


def _run_view(run: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: run.get(k) for k in ("name", "region", "status", "trigger", "startedAt",
                                   "finishedAt", "durationSeconds")}
    if run.get("message"):
        out["message"] = clip(run["message"], 400)
    return out


def register_cron_tools(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ_ONLY, title="List cron job runs")
    @guarded
    async def list_cron_job_runs(
        app_name: AppName, ctx: Context, limit: Limit = 20,
    ) -> Dict[str, Any]:
        """Recent runs of a cron job app across its regions, newest first. Kubernetes keeps only the
        last 10 successful and 10 failed runs."""
        api = get_api(ctx)
        await _own_app(api, app_name)
        data = await api.graphql(
            """query CronRuns($appName: String!, $limit: Int) {
                 cronJobRuns(appName: $appName, limit: $limit) {
                   name region status trigger startedAt finishedAt durationSeconds message
                 }
               }""",
            {"appName": app_name.strip(), "limit": _cap(limit)},
        )
        runs = [_run_view(r) for r in data.get("cronJobRuns") or [] if r]
        failed = [r["name"] for r in runs if r.get("status") == "failed"]
        return {"app_name": app_name.strip(), "runs": runs, "count": len(runs),
                "attention": [f"{len(failed)} failed run(s), most recent: {failed[0]}."] if failed else []}

    @mcp.tool(annotations=READ_ONLY, title="Get cron job run logs")
    @guarded
    async def get_cron_job_run_logs(
        app_name: AppName,
        run_name: Annotated[str, Field(description="Run name from list_cron_job_runs")],
        ctx: Context,
        region: Annotated[Optional[str], Field(description="Region of the run, if the app runs in several")] = None,
    ) -> Dict[str, Any]:
        """The last lines (up to 500) of one run's log. Logs can contain sensitive data."""
        api = get_api(ctx)
        name = _run_name(run_name)
        where = _opt(region, "region", 60)
        await _own_app(api, app_name)
        data = await api.graphql(
            """query CronRunLogs($appName: String!, $runName: String!, $region: String) {
                 cronJobRunLogs(appName: $appName, runName: $runName, region: $region) {
                   runName podName logs
                 }
               }""",
            {"appName": app_name.strip(), "runName": name, "region": where},
            timeout=90.0,
        )
        res = data.get("cronJobRunLogs") or {}
        logs = res.get("logs") or ""
        truncated = len(logs) > MAX_LOG_CHARS
        return {"run_name": res.get("runName") or name, "pod": res.get("podName"),
                "logs": logs[-MAX_LOG_CHARS:], "truncated_to_last_chars": MAX_LOG_CHARS if truncated else None}

    @mcp.tool(annotations=WRITE, title="Run cron job now")
    @guarded
    async def trigger_cron_job_run(
        app_name: AppName,
        ctx: Context,
        region: Annotated[Optional[str], Field(description="Region to run in; the app's first region if omitted")] = None,
        confirm: Annotated[bool, Field(description="Must be true to start the run. Leave false to preview.")] = False,
    ) -> Dict[str, Any]:
        """Start a run of a cron job app right now, outside its schedule. The job's code runs for real
        (it may write data or send messages), so call without confirm first, show the user what would
        run, and set confirm=true only after they agree. Fails with a conflict while another run is in
        progress; follow the run with list_cron_job_runs."""
        api = get_api(ctx)
        where = _opt(region, "region", 60)
        app = await _own_app(api, app_name)
        if not _is_cron_app(app):
            raise NifeAPIError(f"'{app_name.strip()}' is not a cron job app, so it has no runs to start.")
        if not confirm:
            return {"started": False,
                    "message": "Preview only. Nothing was started. Call again with confirm=true to run it now.",
                    "app_name": app_name.strip(), "schedule": app.get("cronSchedule"),
                    "image": app.get("imageName"), "region": where or "the app's first region"}
        data = await api.graphql(
            """mutation TriggerCron($appName: String!, $region: String) {
                 triggerCronJobRun(appName: $appName, region: $region) {
                   name region status trigger startedAt
                 }
               }""",
            {"appName": app_name.strip(), "region": where},
            timeout=90.0,
        )
        run = data.get("triggerCronJobRun")
        if not run:
            raise NifeAPIError("The backend did not return the new run.")
        logger.info("trigger_cron_job_run: app=%s region=%s", app_name.strip(), run.get("region"))
        return {"started": True, "run": _run_view(run),
                "next_step": "Call list_cron_job_runs to follow the run."}
