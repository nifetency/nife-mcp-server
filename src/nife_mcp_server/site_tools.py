"""Site-deployment tools for the hosted MCP server.

The deploy chain (resolve archive -> build config -> S3Deployment mutation) lives
here, server-side, so the model only has to express *intent* in one call instead
of orchestrating 2-3 backend calls itself.
"""
import logging
from typing import Annotated, Any, Dict, Literal, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from nife_mcp_server import site_helpers as h
from nife_mcp_server.nife_api import NifeAPI, NifeAPIError

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """\
Nife.io connector. Current capability: deploying and managing static sites.

To deploy a site:
1. Ask the user for a site name and which organization to use (call
   list_organizations; top-level organizations only).
2. Ask how the code is provided: a Git repository (GitHub/GitLab/Bitbucket) or a
   public archive URL (.zip/.tar.gz), and whether it is already built (import_type
   'build') or needs building (import_type 'source'). For 'source', pick a framework
   with list_site_frameworks (or ask for the build command and output directory).
3. For a PRIVATE Git repository, call list_git_secrets and pass the chosen secret's
   NAME as pat_secret_name. Never ask the user to paste a token into the chat.
4. Call deploy_site once. It performs all backend steps itself. Do not try to chain
   lower-level calls.
5. Source builds take time: poll get_site_status until status is not in progress.

Use redeploy_site to push new code to an existing site. Environment variable values
are secrets: do not echo them back.
"""

_RO = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_DEPLOY = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
# A redeploy replaces the live content of an existing site.
_REDEPLOY = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
)


def _api(ctx: Context) -> NifeAPI:
    """Build a per-request client from the caller's Authorization header."""
    request = getattr(ctx.request_context, "request", None)
    auth = request.headers.get("authorization") if request is not None else None
    if not auth:
        raise ToolError("Missing Authorization header on the MCP connection.")
    return NifeAPI(auth)


def _fail(exc: Exception) -> ToolError:
    return ToolError(str(exc))


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
            # Private repo: resolve the PAT server-side (never via the model),
            # have the backend archive the repo into S3, get that S3 URL back.
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


def register_site_tools(mcp: FastMCP) -> None:
    # ------------------------------------------------------------- discovery
    @mcp.tool(annotations=_RO)
    async def list_organizations(ctx: Context) -> Dict[str, Any]:
        """List the organizations the user can deploy sites into.
        Returns top-level organizations (id, name, slug, type). Use the id as
        organization_id in deploy_site."""
        try:
            orgs = await _api(ctx).organizations()
        except NifeAPIError as exc:
            raise _fail(exc)
        return {
            "organizations": [
                {"id": o["id"], "name": o.get("name"), "slug": o.get("slug"), "type": o.get("type")}
                for o in orgs
            ]
        }

    @mcp.tool(annotations=_RO)
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

    @mcp.tool(annotations=_RO)
    async def list_git_secrets(ctx: Context) -> Dict[str, Any]:
        """List stored secrets (names only) that can be used as a Git personal access
        token for private repositories. Pass the name as pat_secret_name.
        Secret values are never returned."""
        try:
            secrets = await _api(ctx).list_secrets()
        except NifeAPIError as exc:
            raise _fail(exc)
        return {
            "secrets": [
                {
                    "name": s.get("name"),
                    "type": s.get("registryType"),
                    "organization_id": s.get("organizationId"),
                }
                for s in secrets
                if s.get("name") and (s.get("registryType") or "").lower() != "env"
            ]
        }

    @mcp.tool(annotations=_RO)
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
            existing = await _api(ctx).site(site_name)
        except NifeAPIError:
            existing = None  # lookup failures mean "not found" for this check
        return {
            "site_name": site_name,
            "valid": True,
            "already_exists": existing is not None,
            "url_if_deployed": h.site_url(site_name),
        }

    # ---------------------------------------------------------------- status
    @mcp.tool(annotations=_RO)
    async def list_sites(ctx: Context) -> Dict[str, Any]:
        """List the user's deployed static sites with status and URL."""
        try:
            sites = await _api(ctx).sites()
        except NifeAPIError as exc:
            raise _fail(exc)
        return {"sites": sites, "count": len(sites)}

    @mcp.tool(annotations=_RO)
    async def get_site_status(
        site_name: Annotated[str, Field(description="Name of the site")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Get the current status, URL and version of a site. Use it to follow a
        deployment started with deploy_site/redeploy_site until it finishes."""
        try:
            h.validate_site_name(site_name)
            site = await _api(ctx).site(site_name)
        except (ValueError, NifeAPIError) as exc:
            raise _fail(exc)
        if not site:
            raise ToolError(f"No site named '{site_name}' was found.")
        return {"site": site}

    # ---------------------------------------------------------------- deploy
    @mcp.tool(annotations=_DEPLOY)
    async def deploy_site(
        site_name: Annotated[
            str,
            Field(description="Lowercase letters, digits, '-' or '_' (max 30). The site is served at <site_name>.on.nifetency.com."),
        ],
        organization_id: Annotated[str, Field(description="Organization id from list_organizations")],
        source_type: Annotated[
            Literal["git", "archive_url"],
            Field(description="'git' for a GitHub/GitLab/Bitbucket repo, 'archive_url' for a public https link to a .zip/.tar/.tar.gz"),
        ],
        ctx: Context,
        repo_url: Annotated[Optional[str], Field(description="Repository URL, e.g. https://github.com/owner/repo (source_type='git')")] = None,
        branch: Annotated[str, Field(description="Branch or tag name (source_type='git')")] = "main",
        ref_type: Annotated[Literal["heads", "tags"], Field(description="GitHub only: 'heads' for a branch, 'tags' for a tag")] = "heads",
        archive_url: Annotated[Optional[str], Field(description="Public https URL of the archive (source_type='archive_url')")] = None,
        import_type: Annotated[
            Literal["build", "source"],
            Field(description="'build' = the code is already built static files; 'source' = build it first (needs a plan that allows source builds)"),
        ] = "build",
        framework: Annotated[Optional[str], Field(description="Framework preset for import_type='source' (see list_site_frameworks)")] = None,
        install_command: Annotated[Optional[str], Field(description="Override the preset install command")] = None,
        build_command: Annotated[Optional[str], Field(description="Override the preset build command")] = None,
        output_directory: Annotated[Optional[str], Field(description="Override the preset build output directory")] = None,
        node_version: Annotated[Optional[str], Field(description="Node major version for the build (default 20)")] = None,
        pat_secret_name: Annotated[Optional[str], Field(description="NAME of a stored secret holding a Git token, for PRIVATE repos (see list_git_secrets). Never pass the token itself.")] = None,
        env: Annotated[Optional[Dict[str, str]], Field(description="Environment variables for the build, as {NAME: value}")] = None,
        cloud_account_id: Annotated[Optional[str], Field(description="Deploy into this AWS cloud account of the organization instead of Nife's account")] = None,
    ) -> Dict[str, Any]:
        """Deploy a NEW static site. Performs every backend step (fetch/archive the code,
        resolve build settings, start the deployment) in a single call. Returns once
        the deployment has been submitted; poll get_site_status for progress."""
        api = _api(ctx)
        try:
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
            logger.info("deploy_site: site=%s source=%s import=%s", site_name, source_type, import_type)
            result = await api.s3_deployment(variables)
        except (ValueError, NifeAPIError) as exc:
            raise _fail(exc)
        return {
            "submitted": True,
            "site_name": site_name,
            "expected_url": h.site_url(site_name),
            "import_type": import_type,
            "backend_response": result,
            "next_step": "Call get_site_status to follow the deployment.",
        }

    @mcp.tool(annotations=_REDEPLOY)
    async def redeploy_site(
        site_name: Annotated[str, Field(description="Name of the EXISTING site to update")],
        source_type: Annotated[Literal["git", "archive_url"], Field(description="'git' or 'archive_url' (same meaning as deploy_site)")],
        ctx: Context,
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
        pat_secret_name: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Push new code to an existing site. This REPLACES the live content of the site,
        so confirm with the user first. Parameters match deploy_site."""
        api = _api(ctx)
        try:
            variables = await _resolve_deploy_vars(
                api,
                site_name=site_name, source_type=source_type, repo_url=repo_url,
                branch=branch, ref_type=ref_type, archive_url=archive_url,
                import_type=import_type, framework=framework,
                install_command=install_command, build_command=build_command,
                output_directory=output_directory, node_version=node_version,
                pat_secret_name=pat_secret_name, env=env,
            )
            if not await api.site(site_name):
                raise ValueError(f"No existing site named '{site_name}'. Use deploy_site to create it.")
            logger.info("redeploy_site: site=%s source=%s import=%s", site_name, source_type, import_type)
            result = await api.redeploy_s3(variables)
        except (ValueError, NifeAPIError) as exc:
            raise _fail(exc)
        return {
            "submitted": True,
            "site_name": site_name,
            "expected_url": h.site_url(site_name),
            "backend_response": result,
            "next_step": "Call get_site_status to follow the deployment.",
        }

    # ---------------------------------------------------------------- prompt
    @mcp.prompt(title="Deploy a static site")
    def deploy_site_guide(source: str = "") -> str:
        """Guided flow for deploying a static site on Nife."""
        hint = f" The code is at: {source}." if source else ""
        return (
            "Help me deploy a static site on Nife." + hint + " Ask me for anything missing "
            "(site name, organization, whether it needs building), then deploy it with "
            "deploy_site and report the URL once get_site_status shows it is live."
        )
