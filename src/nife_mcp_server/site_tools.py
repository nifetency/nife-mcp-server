"""Site deployment and management tools for the hosted MCP server.

The deploy chain (validate target -> resolve archive -> build config -> mutation) lives
here, server-side, so the model only has to express *intent* in one call instead of
orchestrating several backend calls itself. Mirrors the dashboard's DeploySite.tsx.
"""
import logging
from typing import Annotated, Any, Dict, Literal, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server import git_access
from nife_mcp_server import site_helpers as h
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.tool_utils import (
    DESTRUCTIVE, READ_ONLY, WRITE, fail, get_api, require_site, site_or_none,
)

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """\
Nife.io connector for static sites: deploy, manage, and inspect them.

DEPLOYING A SITE
1. Ask for a site name and an organization (list_organizations, top-level only). If the
   organization has AWS cloud accounts (list_cloud_accounts) the site can be hosted there.
2. Ask how the code is provided: a Git repository (GitHub/GitLab/Bitbucket) or a public
   archive URL (.zip/.tar/.tar.gz); and whether it is already built (import_type 'build')
   or must be built (import_type 'source').
3. For a Git repo, call inspect_repository first. It tells you if the repo is public or
   private, whether the branch exists, and which framework and build settings to use.
4. PRIVATE repositories: call list_git_secrets and pass the chosen secret's NAME as
   pat_secret_name. Never ask the user to paste a token into the chat.
5. Call deploy_site once. It performs every backend step itself. Do not chain lower-level calls.
6. Poll get_site_status until the status is no longer in progress; on failure read the build
   log URL from list_site_deployments.

MANAGING A SITE
- redeploy_site pushes new code (or an earlier version_id) to an existing site.
- revert_site_version switches the live site back to an earlier version from its history.
- delete_site is permanent: only call it after the user explicitly confirms the site name.
Both redeploy_site and revert_site_version replace live content, so confirm first.

INSPECTING A SITE
- get_site_overview gives a one-call health summary (traffic, errors, speed, uptime,
  bandwidth, releases) with an 'attention' list. Start there.
- get_site_details returns full configuration: build config, env var names, org, cloud account.
- get_site_traffic returns live HTTP metrics: request count, status breakdown, latency, error paths.
  Requires traffic monitoring (enable_site_traffic_monitoring if not yet enabled).
- get_site_uptime returns uptime %, avg response time, and recent outages.
- get_site_bandwidth returns billing-period bandwidth: used, free allowance, cost.
- get_site_analytics returns GraphQL analytics: visitors, bounce rate, top pages, geo, referrers,
  performance percentiles.
- list_site_deployments shows deployment history; version numbers can be passed to revert_site_version.
- list_site_releases shows active blue-green deployments and A/B/canary experiments.
- get_release_details drills into a single blue-green deployment or experiment with metrics.
- get_site_custom_domain shows the custom domain and its DNS status.

Environment variable values are secrets: never echo them back. Tool results never contain
tokens or secret values.
"""


async def _resolve_deploy_vars(
    api: NifeAPI,
    *,
    site_name: str,
    source_type: str,
    repo_url: Optional[str],
    branch: str,
    ref_type: str,
    archive_url: Optional[str],
    import_type: str,
    framework: Optional[str],
    install_command: Optional[str],
    build_command: Optional[str],
    output_directory: Optional[str],
    node_version: Optional[str],
    pat_secret_name: Optional[str],
    env: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """Steps shared by deploy_site and redeploy_site. Returns mutation variables."""
    h.validate_site_name(site_name)

    # 1. Where does the code come from? -> an archive URL the backend can fetch
    if source_type == "git":
        if not repo_url:
            raise ValueError("repo_url is required when source_type='git'")
        provider, owner, repo = h.parse_repo_url(repo_url)
        h.validate_branch(branch)
        if pat_secret_name:
            # Private repo (any provider): the stored token is resolved server-side,
            # never via the model; the backend archives the repo into S3 and returns its URL.
            token = await api.secret_value(pat_secret_name)
            s3_url = await api.github_upload_to_s3(repo_url.strip(), branch, token, provider)
        else:
            s3_url = h.build_archive_url(provider, owner, repo, branch, ref_type)
    elif source_type == "archive_url":
        if not archive_url:
            raise ValueError("archive_url is required when source_type='archive_url'")
        s3_url = h.validate_archive_url(archive_url)
    else:
        raise ValueError("source_type must be 'git' or 'archive_url'")

    # 2. Pre-built files vs. build from source
    if import_type == "build":
        deploy_build_file, build_file_name, commands = True, "", []
    elif import_type == "source":
        if not await api.source_build_allowed():
            raise ValueError(
                "The current plan does not include source builds. Upgrade the plan, "
                "or deploy pre-built files with import_type='build'."
            )
        cfg = h.resolve_build_config(
            framework, install_command, build_command, output_directory, node_version
        )
        deploy_build_file, build_file_name, commands = False, cfg["output"], h.build_commands(cfg)
    else:
        raise ValueError("import_type must be 'build' or 'source'")

    return {
        "s3AppName": site_name,
        "s3Url": s3_url,
        "deployBuildFile": deploy_build_file,
        "buildFileName": build_file_name,
        "buildCommandsS3": commands,
        "envVariablesS3": h.encode_env(env),
    }


def _not_suspended(site: Dict[str, Any], action: str) -> None:
    if (site.get("status") or "").lower() == "suspended":
        raise ValueError(f"The site is suspended and cannot be {action}.")


def register_site_tools(mcp: FastMCP) -> None:
    # ------------------------------------------------------------- discovery
    @mcp.tool(annotations=READ_ONLY)
    async def list_organizations(ctx: Context) -> Dict[str, Any]:
        """List the organizations the user can deploy sites into.
        Returns top-level organizations (id, name, slug, type). Use the id as
        organization_id in deploy_site."""
        try:
            orgs = await get_api(ctx).organizations()
        except NifeAPIError as exc:
            raise fail(exc)
        return {
            "organizations": [
                {"id": o["id"], "name": o.get("name"), "slug": o.get("slug"), "type": o.get("type")}
                for o in orgs
            ]
        }

    @mcp.tool(annotations=READ_ONLY)
    async def list_cloud_accounts(
        organization_id: Annotated[str, Field(description="Organization id from list_organizations")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """List the organization's active AWS cloud accounts. A site can be hosted in one of them
        (pass its id as cloud_account_id to deploy_site) instead of Nife's own AWS account.
        An empty list means the site will be hosted on Nife. No credentials are returned."""
        try:
            accounts = await get_api(ctx).cloud_accounts(organization_id)
        except NifeAPIError as exc:
            raise fail(exc)
        return {
            "cloud_accounts": [
                {"id": a["id"], "name": a.get("name"), "aws_region": a.get("awsRegion")} for a in accounts
            ],
            "default": "Nife (when cloud_account_id is omitted)",
        }

    @mcp.tool(annotations=READ_ONLY)
    async def list_site_frameworks() -> Dict[str, Any]:
        """List framework presets (install command, build command, output directory)
        for building a site from source. Pass the framework name to deploy_site."""
        return {
            "frameworks": [
                {
                    "name": name,
                    "install_command": p["install"],
                    "build_command": p["build"],
                    "output_directory": p["output"],
                }
                for name, p in h.FRAMEWORKS.items()
            ],
            "default_node_version": h.DEFAULT_NODE_VERSION,
        }

    @mcp.tool(annotations=READ_ONLY)
    async def list_git_secrets(
        ctx: Context,
        provider: Annotated[
            Optional[Literal["github", "gitlab", "bitbucket"]],
            Field(description="Only show secrets usable for this Git provider"),
        ] = None,
    ) -> Dict[str, Any]:
        """List stored secrets (names only) that can be used as a Git personal access
        token for private repositories. Pass the name as pat_secret_name.
        Secret values are never returned."""
        try:
            secrets = await get_api(ctx).list_secrets()
        except NifeAPIError as exc:
            raise fail(exc)
        out = []
        for s in secrets:
            rtype = s.get("registryType") or ""
            if not s.get("name") or rtype.lower() == "env":
                continue
            if provider and not h.secret_matches_provider(rtype, provider):
                continue
            out.append({"name": s["name"], "type": rtype or "PAT", "organization_id": s.get("organizationId")})
        return {"secrets": out}

    @mcp.tool(annotations=READ_ONLY)
    async def inspect_repository(
        repo_url: Annotated[str, Field(description="https://github.com/<owner>/<repo> (or gitlab.com / bitbucket.org)")],
        ctx: Context,
        branch: Annotated[Optional[str], Field(description="Branch or tag to check (default: the repo's default branch)")] = None,
        ref_type: Annotated[Literal["heads", "tags"], Field(description="'heads' = branches, 'tags' = tags")] = "heads",
        pat_secret_name: Annotated[Optional[str], Field(description="NAME of a stored Git token secret, for PRIVATE repos (see list_git_secrets)")] = None,
    ) -> Dict[str, Any]:
        """Check a Git repository BEFORE deploying: is it reachable, public or private, does the
        branch exist, which framework is it and what build settings fit. Works for GitHub,
        GitLab and Bitbucket. For private repos pass pat_secret_name; the token is used
        server-side only and never returned."""
        api = get_api(ctx)
        try:
            provider, _, _ = h.parse_repo_url(repo_url)
            token, notes = None, []
            if pat_secret_name:
                stored = await api.secret_value(pat_secret_name)
                token = h.decrypt_secret(stored)
                if token is None:
                    notes.append(
                        "The stored token could not be decrypted on this server "
                        "(NIFE_ENCRYPTION_KEY is not configured or does not match), so access was "
                        "checked anonymously. Deploying with this secret still works."
                    )
            report = await git_access.inspect_repository(
                repo_url, branch=branch, ref_type=ref_type, token=token
            )
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        if pat_secret_name:
            report["pat_secret_name"] = pat_secret_name
        report["notes"] = notes + report.get("notes", [])
        report["repo_url"] = repo_url.strip()
        return report

    @mcp.tool(annotations=READ_ONLY)
    async def check_site_name(
        site_name: Annotated[str, Field(description="Proposed site name")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Check that a site name is valid and not already used by one of the user's sites."""
        try:
            h.validate_site_name(site_name)
        except ValueError as exc:
            return {"site_name": site_name, "valid": False, "reason": str(exc)}
        try:
            existing = await site_or_none(get_api(ctx), site_name)
        except NifeAPIError as exc:
            raise fail(exc)
        return {
            "site_name": site_name,
            "valid": True,
            "already_exists": existing is not None,
            "url_if_deployed": h.site_url(site_name),
        }

    # ---------------------------------------------------------------- status
    @mcp.tool(annotations=READ_ONLY)
    async def list_sites(ctx: Context) -> Dict[str, Any]:
        """List the user's deployed static sites with status and URL."""
        try:
            sites = await get_api(ctx).sites()
        except NifeAPIError as exc:
            raise fail(exc)
        return {
            "sites": [
                {"name": s.get("s3AppName"), "status": s.get("status"), "version": s.get("version"),
                 "url": h.site_url(s["s3AppName"]) if s.get("s3AppName") else None,
                 "organization_id": s.get("organizationId"), "created_at": s.get("createdAt")}
                for s in sites
            ],
            "count": len(sites),
        }

    @mcp.tool(annotations=READ_ONLY)
    async def get_site_status(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Lightweight status check (status, version, URL). Use it to follow a deployment started
        with deploy_site/redeploy_site until it finishes. For full details use get_site_details."""
        try:
            site = await require_site(get_api(ctx), site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "site_name": site_name,
            "status": site.get("status"),
            "version": site.get("version"),
            "url": h.site_url(site_name),
            "last_deployed_at": site.get("deploymentTime"),
            "build_time_seconds": h.build_seconds(site.get("buildTime")),
        }

    # ---------------------------------------------------------------- deploy
    @mcp.tool(annotations=WRITE)
    async def deploy_site(
        site_name: Annotated[
            str,
            Field(description="Lowercase letters, digits, '-' or '_' (max 30). The site is served at <site_name>.on.nifetency.com."),
        ],
        organization_id: Annotated[str, Field(description="Organization id from list_organizations")],
        source_type: Annotated[
            Literal["git", "archive_url"],
            Field(description="'git' for a GitHub/GitLab/Bitbucket repo (public or private), 'archive_url' for a public https link to a .zip/.tar/.tar.gz"),
        ],
        ctx: Context,
        repo_url: Annotated[Optional[str], Field(description="Repository URL, e.g. https://github.com/owner/repo (source_type='git')")] = None,
        branch: Annotated[str, Field(description="Branch or tag name (source_type='git')")] = "main",
        ref_type: Annotated[Literal["heads", "tags"], Field(description="Public GitHub only: 'heads' for a branch, 'tags' for a tag")] = "heads",
        archive_url: Annotated[Optional[str], Field(description="Public https URL of the archive (source_type='archive_url')")] = None,
        import_type: Annotated[
            Literal["build", "source"],
            Field(description="'build' = the code is already built static files; 'source' = build it first (needs a plan that allows source builds)"),
        ] = "build",
        framework: Annotated[Optional[str], Field(description="Framework preset for import_type='source' (see list_site_frameworks or inspect_repository)")] = None,
        install_command: Annotated[Optional[str], Field(description="Override the preset install command")] = None,
        build_command: Annotated[Optional[str], Field(description="Override the preset build command")] = None,
        output_directory: Annotated[Optional[str], Field(description="Override the preset build output directory")] = None,
        node_version: Annotated[Optional[str], Field(description="Node major version for the build (default 20)")] = None,
        pat_secret_name: Annotated[Optional[str], Field(description="NAME of a stored secret holding a Git token, REQUIRED for PRIVATE repos (see list_git_secrets). Never pass the token itself.")] = None,
        env: Annotated[Optional[Dict[str, str]], Field(description="Environment variables for the build, as {NAME: value}")] = None,
        cloud_account_id: Annotated[Optional[str], Field(description="Host the site in this AWS cloud account of the organization (from list_cloud_accounts) instead of Nife's account")] = None,
    ) -> Dict[str, Any]:
        """Deploy a NEW static site. Performs every backend step (validate the target, fetch or
        archive the code, resolve build settings, start the deployment) in a single call.
        Supports public and private Git repositories, archive URLs, prebuilt or built-from-source
        sites. Returns once the deployment is submitted; poll get_site_status for progress."""
        api = get_api(ctx)
        try:
            h.validate_site_name(site_name)
            if await site_or_none(api, site_name):
                raise ValueError(
                    f"A site named '{site_name}' already exists. Use redeploy_site to update it, "
                    "or choose another name."
                )
            orgs = await api.organizations()
            if organization_id not in {o["id"] for o in orgs}:
                raise ValueError(
                    "Unknown organization_id. Use list_organizations to see the organizations "
                    "you can deploy into."
                )
            if cloud_account_id:
                accounts = await api.cloud_accounts(organization_id)
                if cloud_account_id not in {a["id"] for a in accounts}:
                    raise ValueError(
                        "That cloud_account_id is not an active AWS account of this organization. "
                        "Use list_cloud_accounts, or omit it to host on Nife."
                    )
            variables = await _resolve_deploy_vars(
                api,
                site_name=site_name, source_type=source_type, repo_url=repo_url,
                branch=branch, ref_type=ref_type, archive_url=archive_url,
                import_type=import_type, framework=framework,
                install_command=install_command, build_command=build_command,
                output_directory=output_directory, node_version=node_version,
                pat_secret_name=pat_secret_name, env=env,
            )
            variables["organizationId"] = organization_id
            if cloud_account_id:
                variables["cloudAccountId"] = cloud_account_id
            logger.info("deploy_site: site=%s source=%s import=%s private=%s",
                        site_name, source_type, import_type, bool(pat_secret_name))
            result = await api.s3_deployment(variables)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "submitted": True,
            "site_name": site_name,
            "expected_url": h.site_url(site_name),
            "import_type": import_type,
            "private_repository": bool(pat_secret_name),
            "hosted_on": "cloud_account" if cloud_account_id else "nife",
            "backend_response": result,
            "next_step": "Call get_site_status to follow the deployment.",
        }

    @mcp.tool(annotations=DESTRUCTIVE)
    async def redeploy_site(
        site_name: Annotated[str, Field(description="Name of the EXISTING site to update")],
        ctx: Context,
        source_type: Annotated[Optional[Literal["git", "archive_url"]], Field(description="New code: 'git' or 'archive_url' (same meaning as deploy_site). Omit when using version_id.")] = None,
        repo_url: Optional[str] = None,
        branch: str = "main",
        ref_type: Literal["heads", "tags"] = "heads",
        archive_url: Optional[str] = None,
        import_type: Literal["build", "source"] = "build",
        framework: Optional[str] = None,
        install_command: Optional[str] = None,
        build_command: Optional[str] = None,
        output_directory: Optional[str] = None,
        node_version: Optional[str] = None,
        pat_secret_name: Annotated[Optional[str], Field(description="NAME of a stored Git token secret, for PRIVATE repos")] = None,
        env: Optional[Dict[str, str]] = None,
        version_id: Annotated[Optional[str], Field(description="Instead of new code, redeploy this earlier version (see list_site_deployments)")] = None,
        reason: Annotated[Optional[str], Field(description="Why (recorded with a version redeploy)")] = None,
    ) -> Dict[str, Any]:
        """Update an existing site, either with NEW code (source_type + repo_url/archive_url, public
        or private) or by redeploying an earlier version_id from its history. This REPLACES the
        live content, so confirm with the user first. The site's organization and hosting account
        do not change."""
        api = get_api(ctx)
        try:
            site = await require_site(api, site_name)
            _not_suspended(site, "redeployed")
            if version_id:
                if source_type:
                    raise ValueError("Pass either version_id or source_type, not both.")
                variables: Dict[str, Any] = {"s3AppName": site_name, "versionID": version_id}
                if reason:
                    variables["reason"] = reason[:500]
            else:
                if not source_type:
                    raise ValueError("Pass source_type (new code) or version_id (an earlier version).")
                variables = await _resolve_deploy_vars(
                    api,
                    site_name=site_name, source_type=source_type, repo_url=repo_url,
                    branch=branch, ref_type=ref_type, archive_url=archive_url,
                    import_type=import_type, framework=framework,
                    install_command=install_command, build_command=build_command,
                    output_directory=output_directory, node_version=node_version,
                    pat_secret_name=pat_secret_name, env=env,
                )
            logger.info("redeploy_site: site=%s mode=%s", site_name, "version" if version_id else "code")
            result = await api.redeploy_s3(variables)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "submitted": True,
            "site_name": site_name,
            "expected_url": h.site_url(site_name),
            "mode": "version" if version_id else "new_code",
            "backend_response": result,
            "next_step": "Call get_site_status to follow the deployment.",
        }

    @mcp.tool(annotations=DESTRUCTIVE)
    async def revert_site_version(
        site_name: Annotated[str, Field(description="Name of the site")],
        version_id: Annotated[str, Field(description="Version to switch back to, from list_site_deployments")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Switch the live site back to an earlier version from its deployment history (the dashboard's
        Revert button). This REPLACES the current live version, so confirm with the user first."""
        api = get_api(ctx)
        try:
            site = await require_site(api, site_name)
            _not_suspended(site, "reverted")
            history = await api.deployments_list(site_name)
            match = next((d for d in history if str(d.get("version")) == str(version_id)), None)
            if not match:
                known = ", ".join(str(d.get("version")) for d in history[:15]) or "none"
                raise ValueError(f"Version '{version_id}' is not in this site's history. Known versions: {known}")
            if (match.get("status") or "") == "Active":
                raise ValueError(f"Version '{version_id}' is already the live version.")
            result = await api.revert_s3(site["id"], site_name, str(version_id))
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {"reverted": True, "site_name": site_name, "to_version": version_id, "backend_response": result}

    @mcp.tool(annotations=DESTRUCTIVE)
    async def delete_site(
        site_name: Annotated[str, Field(description="Name of the site to delete")],
        confirm_site_name: Annotated[str, Field(description="Must exactly equal site_name. Only fill this in after the user has explicitly confirmed the deletion.")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """PERMANENTLY delete a site and all of its deployment history. This cannot be undone.
        Only call after the user has explicitly confirmed, by name, that they want it deleted."""
        api = get_api(ctx)
        try:
            if site_name != confirm_site_name:
                raise ValueError("confirm_site_name must exactly match site_name. Nothing was deleted.")
            await require_site(api, site_name)
            result = await api.delete_site(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        logger.info("delete_site: site=%s", site_name)
        return {"deleted": True, "site_name": site_name, "backend_response": result}

    # ---------------------------------------------------------------- prompt
    # ------------------------------------------------------------ site details
    @mcp.tool(annotations=READ_ONLY)
    async def get_site_details(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Full configuration and metadata for a site: organization, deployed version,
        build commands, environment variable names (values are never returned), custom domain,
        cloud account, and the last deployment times."""
        api = get_api(ctx)
        try:
            site = await require_site(api, site_name)
            extra = await api.site_extra(site_name)
            domain = await api.custom_domain(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        cmds = h.parse_build_commands(site.get("buildCommandsS3"))
        env_names = [e.get("name") for e in (site.get("envVariablesS3") or []) if e.get("name")]
        org = site.get("orgDetails") or {}
        user = site.get("userDetails") or {}
        return {
            "site_name": site_name,
            "status": site.get("status"),
            "version": site.get("version"),
            "url": h.site_url(site_name),
            "custom_domain": domain,
            "app_id": extra.get("appId"),
            "build_log_url": extra.get("build_url"),
            "organization": {"id": site.get("organizationId"), "name": org.get("name"), "type": org.get("type")},
            "deployed_by": f"{user.get('firstName', '')} {user.get('lastName', '')}".strip() or None,
            "created_by": site.get("createdBy"),
            "created_at": site.get("createdAt"),
            "last_deployed_at": site.get("deploymentTime"),
            "build_time_seconds": h.build_seconds(site.get("buildTime")),
            "deployed_on": site.get("deployedOn"),
            "cloud_account_id": site.get("cloudAccountId"),
            "cloud_account_name": site.get("cloudAccountName"),
            "build_config": cmds,
            "env_variable_names": env_names,
        }

    # --------------------------------------------------- analytics & metrics
    @mcp.tool(annotations=READ_ONLY)
    async def get_site_overview(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
        range: Annotated[
            Literal["1h", "6h", "24h", "7d", "30d"],
            Field(description="Time window for traffic metrics (default 24h)"),
        ] = "24h",
    ) -> Dict[str, Any]:
        """One-call health summary for a site: traffic KPIs, error rate, response time,
        bandwidth, uptime, and an 'attention' list of anything that needs action.
        Start here before drilling into specific tools."""
        api = get_api(ctx)
        try:
            site = await require_site(api, site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)

        host = h.site_host(site_name)
        hours = h.RANGE_HOURS[range]
        attention = []

        status = site.get("status", "")
        if status.lower() not in ("active", "live", "deployed", "succeeded"):
            attention.append(f"Site status is '{status}'.")

        # Traffic (nifex) — best effort
        traffic: Dict[str, Any] = {}
        try:
            breakdown = await api.nifex_status_breakdown(host, range)
            metrics = await api.nifex_http_metrics(host, range)
            traffic = {
                "total_requests": breakdown.get("total"),
                "status_breakdown": breakdown.get("breakdown"),
                "avg_response_ms": (metrics.get("latency") or {}).get("avg_ms"),
                "p95_response_ms": (metrics.get("latency") or {}).get("p95_ms"),
                "bandwidth_bytes": (metrics.get("bandwidth") or {}).get("total_bytes"),
                "error_rate_pct": breakdown.get("error_rate_pct"),
            }
            if isinstance(breakdown.get("error_rate_pct"), (int, float)) and breakdown["error_rate_pct"] > 5:
                attention.append(f"Error rate is {breakdown['error_rate_pct']}% over the last {range}.")
        except NifeAPIError as exc:
            traffic = {"note": str(exc)}
            if "not turned on" in str(exc):
                attention.append("Traffic monitoring is not enabled. Call enable_site_traffic_monitoring.")

        # Bandwidth
        bw: Dict[str, Any] = {}
        try:
            bw_raw = await api.bandwidth(site_name)
            if bw_raw:
                used_gb = h.gb(bw_raw.get("usedBytes"))
                free_gb = h.gb(bw_raw.get("freeLimitBytes"))
                bw = {
                    "used_gb": used_gb,
                    "free_limit_gb": free_gb,
                    "billable_gb": h.gb(bw_raw.get("billableBytes")),
                    "estimated_cost_usd": bw_raw.get("estimatedCost"),
                    "billing_enabled": bw_raw.get("billingEnabled"),
                }
                if free_gb and used_gb and free_gb > 0 and used_gb / free_gb > 0.9:
                    attention.append(f"Bandwidth usage is at {round(used_gb / free_gb * 100)}% of the free limit.")
        except NifeAPIError:
            bw = {}

        # Uptime — best effort
        uptime: Dict[str, Any] = {}
        try:
            beats = await api.uptime_beats(site_name, min(hours, 72))
            if beats is not None:
                uptime = h.uptime_stats(beats)
                if isinstance(uptime.get("uptime_percent"), (int, float)) and uptime["uptime_percent"] < 99:
                    attention.append(f"Uptime is {uptime['uptime_percent']}% (last {min(hours, 72)}h).")
        except NifeAPIError:
            uptime = {}

        # Metrics summary (GraphQL)
        summary: Dict[str, Any] = {}
        try:
            raw = await api.metrics_summary(site_name, hours)
            if raw:
                summary = {
                    "total_requests": raw.get("totalRequests"),
                    "unique_visitors": raw.get("uniqueVisitors"),
                    "avg_response_ms": raw.get("averageResponseTime"),
                    "error_rate_pct": raw.get("errorRate"),
                    "availability_pct": raw.get("availability"),
                    "cache_hit_rate": raw.get("cacheHitRate"),
                    "bounce_rate": raw.get("bounceRate"),
                }
        except NifeAPIError:
            summary = {}

        return {
            "site_name": site_name,
            "status": status,
            "version": site.get("version"),
            "url": h.site_url(site_name),
            "range": range,
            "traffic": traffic,
            "bandwidth": bw,
            "uptime": uptime,
            "metrics_summary": summary,
            "attention": attention,
        }

    @mcp.tool(annotations=READ_ONLY)
    async def get_site_traffic(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
        range: Annotated[
            Literal["1h", "6h", "24h", "7d", "30d"],
            Field(description="Time window"),
        ] = "24h",
    ) -> Dict[str, Any]:
        """Live HTTP traffic for a site: request count, status code breakdown (2xx/3xx/4xx/5xx),
        latency (avg, p95), bandwidth, top error URLs, and a time-series chart.
        Requires traffic monitoring to be enabled (enable_site_traffic_monitoring)."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            host = h.site_host(site_name)
            breakdown = await api.nifex_status_breakdown(host, range)
            metrics = await api.nifex_http_metrics(host, range)
            error_paths = await api.nifex_error_paths(host, range, limit=10)
            series_raw = await api.nifex_series(host, range)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)

        series = h.downsample_series(series_raw.get("series") or [], max_points=24)
        return {
            "site_name": site_name,
            "range": range,
            "total_requests": breakdown.get("total"),
            "error_rate_pct": breakdown.get("error_rate_pct"),
            "status_breakdown": breakdown.get("breakdown"),
            "latency": (metrics.get("latency") or {}),
            "bandwidth": (metrics.get("bandwidth") or {}),
            "http_methods": h.top_items(metrics.get("methods"), 5),
            "top_error_paths": (error_paths.get("paths") or [])[:10],
            "time_series": series,
        }

    @mcp.tool(annotations=READ_ONLY)
    async def get_site_uptime(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
        hours: Annotated[int, Field(description="Look-back window in hours (1–72, default 24)", ge=1, le=72)] = 24,
    ) -> Dict[str, Any]:
        """Uptime percentage, average response time, and recent outages for a site,
        from the Uptime Kuma heartbeat monitor."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            beats = await api.uptime_beats(site_name, hours)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        if beats is None:
            return {
                "site_name": site_name,
                "monitored": False,
                "note": "No uptime monitor found for this site.",
            }
        stats = h.uptime_stats(beats)
        return {"site_name": site_name, "monitored": True, "hours": hours, **stats}

    @mcp.tool(annotations=READ_ONLY)
    async def get_site_bandwidth(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Bandwidth usage for the current billing period: bytes used, free allowance,
        billable overage, rate per GB, and estimated cost."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            bw = await api.bandwidth(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        if not bw:
            return {"site_name": site_name, "note": "No bandwidth data available for this site."}
        return {
            "site_name": site_name,
            "period": bw.get("period"),
            "used_bytes": bw.get("usedBytes"),
            "used_gb": h.gb(bw.get("usedBytes")),
            "free_limit_bytes": bw.get("freeLimitBytes"),
            "free_limit_gb": h.gb(bw.get("freeLimitBytes")),
            "billable_bytes": bw.get("billableBytes"),
            "billable_gb": h.gb(bw.get("billableBytes")),
            "rate_per_gb_usd": bw.get("ratePerGB"),
            "estimated_cost_usd": bw.get("estimatedCost"),
            "billing_enabled": bw.get("billingEnabled"),
        }

    @mcp.tool(annotations=READ_ONLY)
    async def get_site_analytics(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
        range: Annotated[
            Literal["1h", "6h", "24h", "7d", "30d"],
            Field(description="Time window (default 24h)"),
        ] = "24h",
    ) -> Dict[str, Any]:
        """Aggregated analytics for a site: request totals, unique visitors, bounce rate,
        top pages, cache hit rate, availability, performance percentiles (avg/p95/p99),
        and traffic breakdown by geography, referrer, and user-agent.
        Uses the GraphQL metrics endpoints (not nifex)."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            hours = h.RANGE_HOURS[range]
            days = max(1, hours // 24)
            summary = await api.metrics_summary(site_name, hours)
            perf = await api.performance_metrics(site_name, hours)
            traffic = await api.traffic_analytics(site_name, days)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)

        # Latest traffic analytics record
        latest_ta = traffic[0] if traffic else {}
        return {
            "site_name": site_name,
            "range": range,
            "summary": {
                "total_requests": (summary or {}).get("totalRequests"),
                "unique_visitors": (summary or {}).get("uniqueVisitors"),
                "failed_requests": (summary or {}).get("failedRequests"),
                "avg_response_ms": (summary or {}).get("averageResponseTime"),
                "error_rate_pct": (summary or {}).get("errorRate"),
                "availability_pct": (summary or {}).get("availability"),
                "cache_hit_rate": (summary or {}).get("cacheHitRate"),
                "bounce_rate": (summary or {}).get("bounceRate"),
                "total_bytes_transferred": (summary or {}).get("totalBytesTransferred"),
                "latest_version": (summary or {}).get("latestDeploymentVersion"),
            },
            "performance": [
                {
                    "version": p.get("deploymentVersion"),
                    "avg_ms": p.get("avgResponseTime"),
                    "p95_ms": p.get("p95ResponseTime"),
                    "p99_ms": p.get("p99ResponseTime"),
                    "error_rate_pct": p.get("errorRate"),
                    "availability_pct": p.get("availabilityPercent"),
                    "cdn_hit_rate": p.get("cdnHitRate"),
                    "total_requests": p.get("totalRequests"),
                }
                for p in (perf or [])[:5]
            ],
            "top_pages": h.top_items(latest_ta.get("topPages"), 10),
            "geographic_distribution": h.top_items(latest_ta.get("geographicData"), 10),
            "referrers": h.top_items(latest_ta.get("referrerData"), 10),
            "user_agents": h.top_items(latest_ta.get("userAgentData"), 5),
        }

    # -------------------------------------------------------- deployments
    @mcp.tool(annotations=READ_ONLY)
    async def list_site_deployments(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Deployment history for a site: version numbers, statuses, build times,
        build log URLs, and who deployed each version. Use version numbers to
        revert with revert_site_version."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            history = await api.deployments_list(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "site_name": site_name,
            "deployments": [
                {
                    "version": d.get("version"),
                    "status": d.get("status"),
                    "url": d.get("appUrl") or h.site_url(site_name),
                    "deployed_at": d.get("deploymentTime"),
                    "build_time_seconds": h.build_seconds(d.get("buildTime")),
                    "created_at": d.get("createdAt"),
                    "deployed_by": d.get("createdBy"),
                    "build_log_url": d.get("build_url"),
                    "app_id": d.get("appId"),
                }
                for d in history
            ],
            "count": len(history),
        }

    # -------------------------------------------------------------- releases
    @mcp.tool(annotations=READ_ONLY)
    async def list_site_releases(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """List blue-green deployments and active experiments (A/B tests, canary releases)
        for a site. Shows the live slot, versions, statuses, and traffic splits."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            summary = await api.strategy_summary(site_name)
            bg_list = await api.blue_green_list(site_name)
            experiments = await api.active_experiments(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)

        return {
            "site_name": site_name,
            "blue_green": {
                "count": (summary or {}).get("blueGreenDeployments", len(bg_list)),
                "active": (summary or {}).get("activeBlueGreen"),
                "deployments": [
                    {
                        "id": d.get("id"),
                        "blue_version": d.get("blueVersion"),
                        "green_version": d.get("greenVersion"),
                        "active_slot": d.get("activeSlot"),
                        "status": d.get("status"),
                        "blue_url": d.get("blueUrl"),
                        "green_url": d.get("greenUrl"),
                        "created_at": d.get("createdAt"),
                    }
                    for d in bg_list
                ],
            },
            "experiments": [
                {
                    "id": e.get("id"),
                    "name": e.get("experimentName"),
                    "type": e.get("experimentType"),
                    "status": e.get("status"),
                    "control_version": e.get("controlVersion"),
                    "treatment_version": e.get("treatmentVersion"),
                    "traffic_split_pct": e.get("trafficSplit"),
                    "auto_promote": e.get("autoPromote"),
                    "started_at": e.get("startTime"),
                }
                for e in experiments
            ],
            "experiment_count": len(experiments),
        }

    @mcp.tool(annotations=READ_ONLY)
    async def get_release_details(
        ctx: Context,
        deployment_id: Annotated[
            Optional[str],
            Field(description="Blue-green deployment id (from list_site_releases)"),
        ] = None,
        experiment_id: Annotated[
            Optional[str],
            Field(description="Experiment id (from list_site_releases)"),
        ] = None,
        hours: Annotated[int, Field(description="Metric window for experiments (default 24)", ge=1, le=168)] = 24,
    ) -> Dict[str, Any]:
        """Detailed view of a single blue-green deployment or experiment.
        Pass deployment_id for blue-green, experiment_id for an experiment."""
        api = get_api(ctx)
        if not deployment_id and not experiment_id:
            raise fail(ValueError("Pass deployment_id (blue-green) or experiment_id (experiment)."))
        try:
            if deployment_id:
                detail = await api.blue_green(deployment_id)
                health = await api.blue_green_health(deployment_id)
                return {
                    "type": "blue_green",
                    "deployment": detail,
                    "health": health,
                }
            else:
                detail = await api.experiment(experiment_id)  # type: ignore[arg-type]
                metrics = await api.experiment_metrics(experiment_id, hours)  # type: ignore[arg-type]
                return {
                    "type": "experiment",
                    "experiment": detail,
                    "metrics": metrics,
                }
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)

    # --------------------------------------------------------- custom domain
    @mcp.tool(annotations=READ_ONLY)
    async def get_site_custom_domain(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Get the custom domain configured for a site (if any) and its DNS status."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            domain = await api.custom_domain(site_name)
            status = await api.custom_domain_status(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "site_name": site_name,
            "default_url": h.site_url(site_name),
            "custom_domain": domain,
            "domain_configured": bool(domain),
            "dns_status": status,
        }

    # ------------------------------------------------ traffic monitoring
    @mcp.tool(annotations=WRITE)
    async def enable_site_traffic_monitoring(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Enable HTTP traffic monitoring for a site (nifex). Once enabled,
        get_site_traffic will return live data. Wait 1–2 minutes after enabling
        before querying traffic."""
        api = get_api(ctx)
        try:
            await require_site(api, site_name)
            host = h.site_host(site_name)
            result = await api.nifex_start_monitoring(host)
        except (ValueError, NifeAPIError) as exc:
            raise fail(exc)
        return {
            "site_name": site_name,
            "host": host,
            "monitoring_enabled": True,
            "backend_response": result,
            "note": "Wait 1–2 minutes before calling get_site_traffic.",
        }

    # ---------------------------------------------------------------- prompt
    @mcp.prompt(title="Deploy a static site")
    def deploy_site_guide(source: str = "") -> str:
        """Guided flow for deploying a static site on Nife."""
        hint = f" The code is at: {source}." if source else ""
        return (
            "Help me deploy a static site on Nife." + hint + " Ask me for anything missing "
            "(site name, organization, whether it needs building). If it is a Git repository, "
            "inspect it first (it may be private), then deploy it with deploy_site and report the "
            "URL once get_site_status shows it is live."
        )
