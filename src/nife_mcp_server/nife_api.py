"""Async client for the Nife backend, used by the hosted (HTTP) MCP server.

Security model
--------------
* The caller's ``Authorization`` header is forwarded verbatim on every request to
  Nife services. Nothing here reads a token from the environment: a request without
  a header never gets here (see ``http_auth.AuthMiddleware``).
* Requests to third parties (GitHub/GitLab/Bitbucket) never carry the Nife header.
* Error messages raised from here are safe to show to the model/user: they never
  contain credentials.
* Every non-GraphQL endpoint (nifex traffic, uptime, domains) is keyed by a host or
  site name. Tools must first prove the caller owns the site with ``site()`` (a
  GraphQL call made with the caller's own token) before using those endpoints.
"""
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

VERSION = "1.2.0"

GRAPHQL_URL = os.environ.get("NIFE_GRAPHQL_URL", "https://api.nife.io/graphql")
# express-backend: /api/github-upload-to-s3, /api/nifex/*, /api/uptime/*, custom-domain routes
EXPRESS_URL = os.environ.get(
    "NIFE_EXPRESS_URL", "https://getuptime.clb2.nifetency.com"
).rstrip("/")
UPTIME_KUMA_URL = os.environ.get(
    "NIFE_UPTIME_KUMA_URL", "https://testuptimekuma.nifetency.com"
).rstrip("/")


class NifeAPIError(Exception):
    """An error that is safe to surface to the MCP client."""


class NotMonitoredError(NifeAPIError):
    """The host exists but traffic tracking has not been turned on for it."""


_client: Optional[httpx.AsyncClient] = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"User-Agent": f"nife-mcp-server/{VERSION}"},
        )
    return _client


async def send(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> httpx.Response:
    """Low-level request with network errors mapped to NifeAPIError."""
    try:
        return await _http().request(
            method, url, params=params, json=json, headers=headers, timeout=timeout
        )
    except httpx.TimeoutException:
        raise NifeAPIError("The request timed out")
    except httpx.HTTPError as exc:
        raise NifeAPIError(f"Could not reach the service ({type(exc).__name__})")


def _detail(resp: httpx.Response) -> str:
    """Best-effort error text from an express-backend / nifex response."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            return str(body.get("detail") or body.get("error") or body.get("message") or "")[:300]
    except ValueError:
        pass
    return ""


def _check_status(resp: httpx.Response) -> None:
    if resp.status_code in (401, 403):
        raise NifeAPIError(
            "Nife rejected the access token (HTTP %d). Check that the token in "
            "the connector's Authorization header is valid and has not expired."
            % resp.status_code
        )
    if resp.status_code >= 400:
        detail = _detail(resp)
        raise NifeAPIError(
            f"Nife API returned HTTP {resp.status_code}" + (f": {detail}" if detail else "")
        )


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        raise NifeAPIError("The service returned a non-JSON response")


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
        resp = await send(
            "POST",
            GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers=self._headers,
            timeout=timeout,
        )
        _check_status(resp)
        body = _json(resp)
        if body.get("errors"):
            msgs = "; ".join(
                str(e.get("message", e)) if isinstance(e, dict) else str(e)
                for e in body["errors"]
            )
            raise NifeAPIError(msgs[:500])
        return body.get("data") or {}

    async def express(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        timeout: float = 30.0,
    ) -> Any:
        """Call express-backend with the caller's token; returns parsed JSON."""
        resp = await send(
            method, f"{EXPRESS_URL}{path}", params=params, json=json,
            headers=self._headers, timeout=timeout,
        )
        _check_status(resp)
        return _json(resp)

    # --------------------------------------------------------- organizations
    async def organizations(self) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetOrganizations {
                 organizations { nodes { id parentId name slug type isActive } }
               }"""
        )
        nodes = (data.get("organizations") or {}).get("nodes") or []
        return [n for n in nodes if not n.get("parentId")]

    async def cloud_accounts(self, org_id: str) -> List[Dict[str, Any]]:
        """Active AWS cloud accounts of an organization (what a site can deploy into).
        Credentials are not part of this query."""
        data = await self.graphql(
            """query ListCloudAccounts($orgId: String!) {
                 listCloudAccounts(orgId: $orgId) { id orgId name cloud status awsRegion }
               }""",
            {"orgId": org_id},
        )
        return [
            a for a in data.get("listCloudAccounts") or []
            if a.get("cloud") == "aws" and a.get("status") == "active"
        ]

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
        """The stored (AES-encrypted) token of a secret. Never returned to the model."""
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
        """Site record, or None. Also the ownership check: it is made with the
        caller's own token."""
        data = await self.graphql(
            """query GetS3Deployments($s3AppName: String!) {
                 getS3deployments(s3AppName: $s3AppName) {
                   id s3AppName status appUrl version
                   buildCommandsS3 { s3Cmd }
                   envVariablesS3 { name }
                   organizationId
                   orgDetails { id name type }
                   userDetails { firstName lastName }
                   deploymentTime buildTime createdBy createdAt
                   deployedOn cloudAccountId cloudAccountName
                 }
               }""",
            {"s3AppName": name},
        )
        found = data.get("getS3deployments")
        if isinstance(found, list):
            found = found[0] if found else None
        return found or None

    async def site_extra(self, name: str) -> Dict[str, Any]:
        """Optional fields (appId, build log URL). Callers must tolerate failure."""
        data = await self.graphql(
            """query GetS3DeploymentsExtra($s3AppName: String!) {
                 getS3deployments(s3AppName: $s3AppName) { appId build_url }
               }""",
            {"s3AppName": name},
        )
        found = data.get("getS3deployments")
        if isinstance(found, list):
            found = found[0] if found else None
        return found or {}

    async def deployments_list(self, name: str) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3DeploymentsList($s3AppName: String) {
                 getS3deploymentsList(s3AppName: $s3AppName) {
                   id appId s3AppName status appUrl deploymentTime buildTime
                   createdBy createdAt version build_url
                 }
               }""",
            {"s3AppName": name},
        )
        return data.get("getS3deploymentsList") or []

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
        """RedeployS3 supports new code (s3Url...) or a version from history (versionID)."""
        data = await self.graphql(
            """mutation RedeployS3(
                 $s3AppName: String! $versionID: String $reason: String
                 $s3Url: String $deployBuildFile: Boolean $buildFileName: String
                 $buildCommandsS3: [S3BuildCommands] $envVariablesS3: [S3EnvVariables]
               ) {
                 RedeployS3(input: {
                   s3AppName: $s3AppName versionID: $versionID reason: $reason
                   s3Url: $s3Url deployBuildFile: $deployBuildFile
                   buildFileName: $buildFileName buildCommandsS3: $buildCommandsS3
                   envVariablesS3: $envVariablesS3
                 })
               }""",
            variables,
            timeout=300.0,
        )
        return data.get("RedeployS3")

    async def revert_s3(self, site_id: str, name: str, version_id: str) -> Any:
        data = await self.graphql(
            """mutation RevertS3Deployment($id: String! $s3AppName: String! $VersionID: String!) {
                 RevertS3Deployment(input: { id: $id, s3AppName: $s3AppName, VersionID: $VersionID })
               }""",
            {"id": site_id, "s3AppName": name, "VersionID": version_id},
            timeout=120.0,
        )
        return data.get("RevertS3Deployment")

    async def delete_site(self, name: str) -> Any:
        data = await self.graphql(
            """mutation DeleteS3Deployment($s3AppName: String!) {
                 deleteS3Deployment(s3AppName: $s3AppName)
               }""",
            {"s3AppName": name},
            timeout=120.0,
        )
        return data.get("deleteS3Deployment")

    async def source_build_allowed(self) -> bool:
        """Best-effort plan check. Returns False only when the plan explicitly
        forbids source builds; the backend enforces the rule authoritatively."""
        try:
            data = await self.graphql(
                "query { getUserPermissionsByPlan { sourceBuild } }", timeout=15.0
            )
            perms = data.get("getUserPermissionsByPlan") or {}
            return perms.get("sourceBuild") is not False
        except NifeAPIError:
            return True

    # ------------------------------------------------------------- bandwidth
    async def bandwidth(self, name: str) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetSiteBandwidthUsage($appName: String!) {
                 getSiteBandwidthUsage(appName: $appName) {
                   appName period usedBytes freeLimitBytes billableBytes
                   ratePerGB estimatedCost billingEnabled
                 }
               }""",
            {"appName": name},
        )
        return data.get("getSiteBandwidthUsage")

    # ------------------------------------------------- S3 metrics / analytics
    async def metrics_summary(self, name: str, hours: int) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3MetricsSummary($appName: String!, $hours: Int) {
                 getS3MetricsSummary(appName: $appName, hours: $hours) {
                   appName totalRequests totalBytesTransferred averageResponseTime
                   errorRate availability failedRequests uniqueVisitors bounceRate
                   topPages cacheHitRate totalCost latestDeploymentVersion
                   lastUpdated customMetricsCount generatedAt
                 }
               }""",
            {"appName": name, "hours": hours},
        )
        return data.get("getS3MetricsSummary")

    async def performance_metrics(self, name: str, hours: int) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3PerformanceMetrics($appName: String!, $hours: Int) {
                 getS3PerformanceMetrics(appName: $appName, hours: $hours) {
                   deploymentVersion avgResponseTime p95ResponseTime p99ResponseTime
                   errorRate availabilityPercent cdnHitRate totalRequests failedRequests
                   cacheHitCount cacheMissCount recordedAt measurementPeriodMinutes
                 }
               }""",
            {"appName": name, "hours": hours},
        )
        return data.get("getS3PerformanceMetrics") or []

    async def traffic_analytics(self, name: str, days: int) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3TrafficAnalytics($appName: String!, $days: Int) {
                 getS3TrafficAnalytics(appName: $appName, days: $days) {
                   deploymentVersion requestCount bytesTransferred uniqueVisitors
                   bounceRate avgSessionDuration topPages referrerData userAgentData
                   geographicData periodStart periodEnd
                 }
               }""",
            {"appName": name, "days": days},
        )
        return data.get("getS3TrafficAnalytics") or []

    async def raw_metrics(self, name: str, metric_type: str, hours: int) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3Metrics($appName: String!, $metricType: String!, $hours: Int) {
                 getS3Metrics(appName: $appName, metricType: $metricType, hours: $hours) {
                   deploymentVersion metricType metricName metricValue metricUnit timestamp
                 }
               }""",
            {"appName": name, "metricType": metric_type, "hours": hours},
        )
        return data.get("getS3Metrics") or []

    # ------------------------------------------- releases (blue-green / A-B)
    async def strategy_summary(self, name: str) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3DeploymentStrategySummary($appName: String!) {
                 getS3DeploymentStrategySummary(appName: $appName) {
                   appName blueGreenDeployments activeExperiments generatedAt
                   activeBlueGreen {
                     id blueVersion greenVersion activeSlot switchStrategy status switchedAt
                   }
                   experiments {
                     id experimentName experimentType status controlVersion
                     treatmentVersion trafficSplit autoPromote startTime
                   }
                   metrics { totalRequests averageResponseTime errorRate availability }
                 }
               }""",
            {"appName": name},
        )
        return data.get("getS3DeploymentStrategySummary")

    async def blue_green_list(self, name: str) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3BlueGreenDeployments($appName: String!) {
                 getS3BlueGreenDeployments(appName: $appName) {
                   id appName blueVersion greenVersion activeSlot blueUrl greenUrl
                   status createdBy createdAt updatedAt
                 }
               }""",
            {"appName": name},
        )
        return data.get("getS3BlueGreenDeployments") or []

    async def blue_green(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3BlueGreenDeployment($deploymentId: String!) {
                 getS3BlueGreenDeployment(deploymentId: $deploymentId) {
                   id appName blueVersion greenVersion activeSlot blueUrl greenUrl
                   switchStrategy healthCheckUrl healthCheckIntervalSeconds
                   rollbackThresholdErrorRate status createdBy createdAt updatedAt switchedAt
                 }
               }""",
            {"deploymentId": deployment_id},
        )
        return data.get("getS3BlueGreenDeployment")

    async def blue_green_health(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query CheckS3BlueGreenHealth($deploymentId: String!) {
                 checkS3BlueGreenHealth(deploymentId: $deploymentId) {
                   deploymentId appName activeSlot blueHealth greenHealth
                   overallHealthy checkedAt
                 }
               }""",
            {"deploymentId": deployment_id},
        )
        return data.get("checkS3BlueGreenHealth")

    async def active_experiments(self, name: str) -> List[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3ActiveExperiments($appName: String!) {
                 getS3ActiveExperiments(appName: $appName) {
                   id appName experimentName experimentType status controlVersion
                   treatmentVersion trafficSplit startTime autoPromote createdAt
                 }
               }""",
            {"appName": name},
        )
        return data.get("getS3ActiveExperiments") or []

    async def experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3Experiment($experimentId: String!) {
                 getS3Experiment(experimentId: $experimentId) {
                   id appName experimentName experimentType status controlVersion
                   treatmentVersion trafficSplit successMetrics currentMetrics startTime
                   endTime autoPromote promoteThreshold createdBy createdAt updatedAt
                 }
               }""",
            {"experimentId": experiment_id},
        )
        return data.get("getS3Experiment")

    async def experiment_metrics(self, experiment_id: str, hours: int) -> Optional[Dict[str, Any]]:
        data = await self.graphql(
            """query GetS3ExperimentMetrics($experimentId: String!, $hours: Int) {
                 getS3ExperimentMetrics(experimentId: $experimentId, hours: $hours) {
                   experimentId experimentName controlVersion treatmentVersion status
                   trafficSplit currentMetrics generatedAt
                   controlMetrics { metricName metricValue metricUnit timestamp }
                   treatmentMetrics { metricName metricValue metricUnit timestamp }
                 }
               }""",
            {"experimentId": experiment_id, "hours": hours},
        )
        return data.get("getS3ExperimentMetrics")

    # --------------------------------------- nifex traffic (via express-backend)
    @staticmethod
    def _monitor_path(host: str, leaf: str) -> str:
        return f"/api/nifex/monitors/{quote(host, safe='')}/{leaf}"

    async def _nifex(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = await send(
            "GET", f"{EXPRESS_URL}{path}", params=params, headers=self._headers, timeout=25.0
        )
        if resp.status_code == 404:
            raise NotMonitoredError(
                "Traffic tracking is not turned on for this site yet. "
                "Use enable_site_traffic_monitoring, then check again in a minute or two."
            )
        if resp.status_code == 503:
            raise NifeAPIError(_detail(resp) or "The metrics database is unavailable right now.")
        _check_status(resp)
        return _json(resp)

    async def nifex_status_breakdown(self, host: str, rng: str) -> Dict[str, Any]:
        return await self._nifex(self._monitor_path(host, "status-breakdown"), {"range": rng})

    async def nifex_http_metrics(self, host: str, rng: str) -> Dict[str, Any]:
        return await self._nifex(self._monitor_path(host, "metrics"), {"range": rng})

    async def nifex_error_paths(self, host: str, rng: str, limit: int = 10) -> Dict[str, Any]:
        return await self._nifex(self._monitor_path(host, "error-paths"), {"range": rng, "limit": limit})

    async def nifex_series(self, host: str, rng: str) -> Dict[str, Any]:
        return await self._nifex(self._monitor_path(host, "series"), {"range": rng})

    async def nifex_live(self, host: str) -> Dict[str, Any]:
        return await self._nifex("/api/nifex/live", {"host": host})

    async def nifex_start_monitoring(self, host: str) -> Dict[str, Any]:
        resp = await send(
            "POST", f"{EXPRESS_URL}/api/nifex/monitors", json={"url": host},
            headers=self._headers, timeout=25.0,
        )
        _check_status(resp)
        return _json(resp)

    # ------------------------------------------------ uptime (Uptime Kuma)
    async def uptime_beats(self, name: str, hours: int) -> Optional[List[Dict[str, Any]]]:
        """Heartbeats for the site's monitor, or None when no monitor exists.

        Never creates a monitor. The Uptime Kuma token is a service credential
        fetched server-side and never leaves this process.
        """
        found = await self.express("GET", "/check-uptime", params={"id": name}, timeout=15.0)
        if not (isinstance(found, dict) and found.get("exists") and found.get("uptimeId")):
            return None
        monitor_id = found["uptimeId"]

        async def kuma_token(refresh: bool) -> str:
            data = await self.express(
                "POST", "/api/uptime/access-token", json={"refresh": refresh}, timeout=15.0
            )
            token = data.get("access_token") if isinstance(data, dict) else None
            if not token:
                raise NifeAPIError("Login to the uptime service failed")
            return token

        for attempt, refresh in enumerate((False, True)):
            token = await kuma_token(refresh)
            resp = await send(
                "GET", f"{UPTIME_KUMA_URL}/monitors/{int(monitor_id)}/beats",
                params={"hours": hours}, headers={"Authorization": f"Bearer {token}"},
                timeout=25.0,
            )
            if resp.status_code == 401 and attempt == 0:
                continue
            if resp.status_code >= 400:
                raise NifeAPIError("Could not fetch uptime data")
            data = _json(resp)
            beats = data.get("monitor_beats") if isinstance(data, dict) else None
            return beats if isinstance(beats, list) else []
        return []

    # ----------------------------------------------------------- domains
    async def custom_domain(self, bucket: str) -> Optional[str]:
        try:
            data = await self.express(
                "GET", "/get-site-custom-domain", params={"bucket_name": bucket}, timeout=15.0
            )
        except NifeAPIError:
            return None
        return (data or {}).get("custom_domain") or None

    async def custom_domain_status(self, bucket: str) -> Dict[str, Any]:
        try:
            data = await self.express("GET", f"/check-custom-domain-site/{quote(bucket, safe='')}", timeout=15.0)
        except NifeAPIError:
            return {"exists": False}
        return data if isinstance(data, dict) else {"exists": False}

    # --------------------------------------------------------------- PAT secrets
    async def list_pats(self) -> List[Dict[str, Any]]:
        """List the user's stored PATs (type + id only, never the token value)."""
        data = await self.graphql(
            """query GetUserPAT {
                 getUserPAT { id type userId createdAt updatedAt }
               }"""
        )
        return data.get("getUserPAT") or []

    async def add_pat(self, pat_type: str, pat_token: str) -> Any:
        data = await self.graphql(
            """mutation AddPAT($type: String!, $patToken: String!) {
                 addPAT(input: { type: $type, patToken: $patToken })
               }""",
            {"type": pat_type, "patToken": pat_token},
        )
        return data.get("addPAT")

    async def delete_pat(self, pat_id: str) -> Any:
        data = await self.graphql(
            """mutation DeletePAT($id: String!) {
                 deletePAT(id: $id)
               }""",
            {"id": pat_id},
        )
        return data.get("deletePAT")

    async def add_secret(
        self,
        name: str,
        registry_type: str,
        password: str,
        organization_id: str,
    ) -> Any:
        """Create a named Git PAT secret.
        Tries the GraphQL mutation first (matches what the dashboard uses),
        falls back to the vault REST endpoint if the mutation doesn't exist."""
        try:
            data = await self.graphql(
                """mutation AddSecret(
                     $name: String! $registryType: String! $passWord: String! $organizationId: String!
                   ) {
                     addSecret(input: {
                       name: $name registryType: $registryType passWord: $passWord
                       organizationId: $organizationId
                     }) { id name registryType organizationId isActive }
                   }""",
                {
                    "name": name,
                    "registryType": registry_type,
                    "passWord": password,
                    "organizationId": organization_id,
                },
            )
            return data.get("addSecret")
        except NifeAPIError:
            # Fallback: vault REST endpoint
            payload = {
                "name": name,
                "organization_id": organization_id,
                "registry_type": registry_type,
                "vault_type": "internal",
                "vault_path": "secrets",
                "secret_data": {"key": name, "value": password},
            }
            resp = await send(
                "POST",
                f"{GRAPHQL_URL.rsplit('/graphql', 1)[0]}/api/v1/vault/secrets",
                json=payload,
                headers=self._headers,
                timeout=20.0,
            )
            _check_status(resp)
            return _json(resp)

    async def delete_secret_by_id(self, secret_id: str) -> Any:
        data = await self.graphql(
            """mutation DeleteSecret($id: String!) {
                 deleteSecret(id: $id)
               }""",
            {"id": secret_id},
        )
        return data.get("deleteSecret")

    # ------------------------------------------- express-backend (REST) upload
    async def github_upload_to_s3(
        self, repo_url: str, branch: str, git_pat: str, provider: str
    ) -> str:
        """Private repo -> archive in S3. Returns the s3Url.

        ``git_pat`` is the stored (encrypted) secret value, exactly as the dashboard
        sends it; the backend decrypts it.
        """
        resp = await send(
            "POST",
            f"{EXPRESS_URL}/api/github-upload-to-s3",
            json={"repoUrl": repo_url, "branch": branch, "gitPat": git_pat, "provider": provider},
            headers=self._headers,
            timeout=300.0,
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
