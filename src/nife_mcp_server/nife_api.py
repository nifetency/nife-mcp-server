"""Async client for the Nife backend, used by the hosted (HTTP) MCP server.

Security model
--------------
* The caller's ``Authorization`` header is forwarded verbatim on every request.
* Nothing in this module reads a token from the environment. A request without
  a header never gets here (see ``http_auth.AuthMiddleware``), so the server can
  never act with its own identity on behalf of an anonymous caller.
* Error messages raised from here are safe to show to the model/user: they never
  contain credentials.
"""
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

VERSION = "1.1.0"

GRAPHQL_URL = os.environ.get("NIFE_GRAPHQL_URL", "https://api.nife.io/graphql")
# express-backend: hosts /api/github-upload-to-s3 (private repo -> S3 archive)
EXPRESS_URL = os.environ.get(
    "NIFE_EXPRESS_URL", "https://getuptime.clb2.nifetency.com"
).rstrip("/")


class NifeAPIError(Exception):
    """An error that is safe to surface to the MCP client."""


_client: Optional[httpx.AsyncClient] = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"User-Agent": f"nife-mcp-server/{VERSION}"},
        )
    return _client


def _check_status(resp: httpx.Response) -> None:
    if resp.status_code in (401, 403):
        raise NifeAPIError(
            "Nife rejected the access token (HTTP %d). Check that the token in "
            "the connector's Authorization header is valid and has not expired."
            % resp.status_code
        )
    if resp.status_code >= 400:
        raise NifeAPIError(f"Nife API returned HTTP {resp.status_code}")


class NifeAPI:
    """One instance per MCP request; holds that caller's Authorization value."""

    def __init__(self, authorization: str):
        self._auth = authorization

    @property
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": self._auth, "Content-Type": "application/json"}

    # ------------------------------------------------------------------ core
    async def graphql(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        try:
            resp = await _http().post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables or {}},
                headers=self._headers,
                timeout=timeout,
            )
        except httpx.TimeoutException:
            raise NifeAPIError("The Nife API timed out")
        except httpx.HTTPError as exc:
            raise NifeAPIError(f"Could not reach the Nife API ({type(exc).__name__})")

        _check_status(resp)
        try:
            body = resp.json()
        except ValueError:
            raise NifeAPIError("The Nife API returned a non-JSON response")

        if body.get("errors"):
            msgs = "; ".join(
                str(e.get("message", e)) if isinstance(e, dict) else str(e)
                for e in body["errors"]
            )
            raise NifeAPIError(msgs[:500])
        return body.get("data") or {}

    # --------------------------------------------------------- organizations
    async def organizations(self) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetOrganizations {
                 organizations { nodes { id parentId name slug type isActive } }
               }"""
        )
        nodes = (data.get("organizations") or {}).get("nodes") or []
        return [n for n in nodes if not n.get("parentId")]

    # --------------------------------------------------------------- secrets
    async def list_secrets(self) -> List[Dict[str, Any]]:
        """Secret metadata only. The secret value is never requested here."""
        data = await self.graphql(
            """query SecretsList($name: String!) {
                 getSecret(name: $name) { id organizationId name registryType isActive }
               }""",
            {"name": ""},
        )
        return data.get("getSecret") or []

    async def secret_value(self, name: str) -> str:
        """Resolve a secret's stored token by name. Never returned to the model."""
        data = await self.graphql(
            """query SecretsList($name: String!) {
                 getSecret(name: $name) { name passWord }
               }""",
            {"name": name},
        )
        for s in data.get("getSecret") or []:
            if s.get("name") == name and s.get("passWord"):
                return s["passWord"]
        raise NifeAPIError(
            f"Secret '{name}' was not found or has no stored token. "
            "Use list_git_secrets to see the available names."
        )

    # ----------------------------------------------------------------- sites
    async def sites(self) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetAllS3Deployments {
                 getAllS3deployments {
                   id s3AppName status appUrl version organizationId createdAt
                 }
               }"""
        )
        return data.get("getAllS3deployments") or []

    async def site(self, name: str) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3Deployments($s3AppName: String!) {
                 getS3deployments(s3AppName: $s3AppName) {
                   id s3AppName status appUrl version organizationId
                   deploymentTime buildTime createdAt deployedOn
                 }
               }""",
            {"s3AppName": name},
        )
        found = data.get("getS3deployments")
        if isinstance(found, list):
            found = found[0] if found else None
        return found or None

    async def s3_deployment(self, variables: Dict[str, Any]) -> Any:
        data = await self.graphql(
            """mutation S3Deployment(
                 $s3AppName: String! $s3Url: String $deployBuildFile: Boolean
                 $buildFileName: String $buildCommandsS3: [S3BuildCommands]
                 $envVariablesS3: [S3EnvVariables] $organizationId: String
                 $cloudAccountId: String
               ) {
                 S3Deployment(input: {
                   s3AppName: $s3AppName deployBuildFile: $deployBuildFile
                   s3Url: $s3Url buildFileName: $buildFileName
                   buildCommandsS3: $buildCommandsS3 envVariablesS3: $envVariablesS3
                   organizationId: $organizationId cloudAccountId: $cloudAccountId
                 })
               }""",
            variables,
            timeout=300.0,
        )
        return data.get("S3Deployment")

    async def redeploy_s3(self, variables: Dict[str, Any]) -> Any:
        data = await self.graphql(
            """mutation RedeployS3(
                 $s3AppName: String! $s3Url: String $deployBuildFile: Boolean
                 $buildFileName: String $buildCommandsS3: [S3BuildCommands]
                 $envVariablesS3: [S3EnvVariables]
               ) {
                 RedeployS3(input: {
                   s3AppName: $s3AppName s3Url: $s3Url
                   deployBuildFile: $deployBuildFile buildFileName: $buildFileName
                   buildCommandsS3: $buildCommandsS3 envVariablesS3: $envVariablesS3
                 })
               }""",
            variables,
            timeout=300.0,
        )
        return data.get("RedeployS3")

    async def source_build_allowed(self) -> bool:
        """Best-effort plan check. Returns False only when the plan explicitly
        forbids source builds; any failure here is ignored because the backend
        enforces the rule authoritatively."""
        try:
            data = await self.graphql(
                "query { getUserPermissionsByPlan { sourceBuild } }", timeout=15.0
            )
            perms = data.get("getUserPermissionsByPlan") or {}
            return perms.get("sourceBuild") is not False
        except NifeAPIError:
            return True

    # ------------------------------------------------- express-backend (REST)
    async def github_upload_to_s3(
        self, repo_url: str, branch: str, git_pat: str, provider: str
    ) -> str:
        """Private repo -> archive in S3. Returns the s3Url."""
        try:
            resp = await _http().post(
                f"{EXPRESS_URL}/api/github-upload-to-s3",
                json={
                    "repoUrl": repo_url,
                    "branch": branch,
                    "gitPat": git_pat,
                    "provider": provider,
                },
                headers=self._headers,
                timeout=300.0,
            )
        except httpx.TimeoutException:
            raise NifeAPIError("Fetching the private repository timed out")
        except httpx.HTTPError as exc:
            raise NifeAPIError(
                f"Could not reach the repository upload service ({type(exc).__name__})"
            )

        if resp.status_code in (401, 403):
            _check_status(resp)
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = str(resp.json().get("error", ""))[:300]
            except ValueError:
                pass
            raise NifeAPIError(
                f"Repository fetch failed (HTTP {resp.status_code}) {detail}".strip()
            )
        try:
            s3_url = resp.json().get("s3Url")
        except ValueError:
            s3_url = None
        if not s3_url:
            raise NifeAPIError("The upload service did not return an archive URL")
        return s3_url
