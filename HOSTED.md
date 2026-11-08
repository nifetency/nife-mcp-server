# Hosted Nife MCP connector

Users connect by **URL**: no download, no local Python or Node. The server is a
stateless proxy: every request carries the user's own Nife token in the
`Authorization` header, and the server forwards it to the Nife backend.

```
https://<your-mcp-host>/mcp
```

## What users do

**Claude (web / desktop / mobile):** Settings → Connectors → Add custom connector

1. URL: `https://<your-mcp-host>/mcp`
2. Open **Request headers**, choose `authorization`, value: `Bearer <your Nife token>`
   (type the word `Bearer`, then a space, then the token).

> Claude's *Request headers* option is currently a beta available to a limited set
> of organizations. If it does not appear for an account, that account needs the
> OAuth flow instead: leave the headers empty and click Connect. Claude sends you to the
> Nife sign-in page (see "OAuth sign-in" below).

**Claude Code / Cursor / VS Code / any client that supports headers:**

```bash
claude mcp add --transport http nife https://<your-mcp-host>/mcp \
  --header "Authorization: Bearer <your Nife token>"
```

## OAuth sign-in (accounts without Request headers)

The server is also a minimal OAuth 2.1 authorization server (discovery, dynamic client
registration, authorization code + PKCE). Sign-in reuses the dashboard login:

1. Claude opens `/authorize`, which shows a "Sign in to Nife" button.
2. The button sends you to the dashboard login page (`NIFE_MCP_LOGIN_URL`, default
   `https://launch.nife.io/login`) with `callback=<mcp-host>/oauth/callback` and
   `state=<sealed transaction>`. You sign in there (password, MFA or SSO).
3. After login the dashboard redirects to `/oauth/callback?token=<nife token>&state=...`, and the
   server redirects back to Claude with a short-lived authorization code.
4. Claude exchanges the code and its PKCE verifier at `/token` and receives your Nife token as the
   OAuth access token.

Every `/mcp` call still carries `Authorization: Bearer <nife token>`; the backend validates it as
before. The dashboard login page must accept the `callback` and `state` parameters and redirect back
with `token` and `state`.

Endpoints: `/.well-known/oauth-protected-resource[/mcp]`, `/.well-known/oauth-authorization-server`,
`/register`, `/authorize`, `/oauth/callback`, `/token`. Nothing is stored server-side: client ids,
pending sign-ins and authorization codes are encrypted blobs keyed by `NIFE_MCP_OAUTH_SECRET`
(set it, identically on every replica, or connectors must be re-added after each restart).

Limits: no refresh tokens (when the Nife token expires, `/mcp` answers 401 and Claude asks you
to sign in again), and authorization codes are short-lived (2 min) and PKCE-bound but not
single-use. The Nife token reaches `/oauth/callback` in the URL query string, so keep that path out
of access logs.

## Tools

The server exposes about 108 curated tools in the groups below. This page summarizes them; each
tool's own description is the authoritative contract. Tools that change live infrastructure are
annotated as destructive, and the riskiest ones preview first and only act with `confirm=true`.

### Container apps and deployments

Curated over `apps.graphqls` / `deploy.graphqls`.

| Tool | Purpose |
|---|---|
| `list_apps` / `get_app` | Inventory and full configuration (env var names only, never values) |
| `get_app_status` | Live health: deployment progress, healthy/unhealthy instances, crash-loop hints |
| `list_app_releases` | Release history; versions feed `revert_app_release` |
| `get_app_logs` | Recent log lines of running instances (not a search) |
| `list_app_regions` | Regions a new app can be deployed to for an organization |
| `deploy_app` | **New app** from a Docker image in one call (see below) |
| `deploy_app_from_git` | **New app** built from a GitHub, GitLab or Bitbucket repository and deployed in one call |
| `resume_app` | Resume a paused app |
| `restart_app`, `pause_app`, `scale_app`, `redeploy_app_image`, `revert_app_release`, `set_app_env` | Change a live app (marked destructive) |
| `delete_app` | Permanent; needs the app name twice |

`deploy_app` follows the dashboard's sequence server-side: create the app, set regions, apply ports,
replicas, size and environment, read back the generated configuration, link a registry secret for a
private image, and deploy. Docker images only, with the `rolling`, `rolling-update` or `recreate`
strategy (defaults: port 3000, external port 80, 2 replicas, 0.5 CPU, 1024 MiB). If a step fails after
the app was created, the app stays a draft; calling `deploy_app` again with the same name resumes it.
If the backend holds the rollout for approval, the tool returns `approval_pending` instead of failing.
For a private image the model passes only the NAME of a stored registry secret.

`deploy_app_from_git` checks the repository first (call `inspect_repository` beforehand), creates the
app, links the Git token for a private repository, builds the image on the platform, and then follows
the same steps as `deploy_app`. The build can take several minutes. The repository needs a Dockerfile,
or pass `dockerfile_path` / `dockerfile`. For a private repository the model passes only the NAME of a
stored token secret (`pat_secret_name`). Built images are pushed to the registry namespace set by
`NIFE_BUILD_IMAGE_NAMESPACE`.

`set_app_env` note: the backend replaces the whole env set on every update, so the tool reads the
current values server-side, merges, and redeploys the current image. It refuses to run if it cannot
read the existing variables (override: `allow_replace_all`). New values are encrypted like the
dashboard's `encryptPassword` (key: `NIFE_ENV_ENCRYPTION_KEY` or `NIFE_ENCRYPTION_KEY`, which must be
the same value as the dashboard's `VITE_ENCRYPTION_KEY`; without a key they are sent as plaintext),
existing values pass through as stored. Approval and billing gates in the backend (`RedeployImage`)
can hold or reject a rollout; the error is passed through.

Environment variable values given to `deploy_app`, `deploy_app_from_git`, `set_app_env` and
`deploy_site` are tool parameters, so they pass through the conversation. Tell users to prefer
stored secrets where the platform supports them.

Not yet for apps: canary, blue-green and A/B rollouts, volume creation, port or region changes on an
existing app, and Kubernetes manifest or Helm deploys.

### Static sites

| Tool | Purpose |
|---|---|
| `list_organizations` | Orgs the user can deploy into |
| `list_site_frameworks` | Build presets (install/build/output) |
| `list_git_secrets` | Names of stored Git tokens (values never returned) |
| `inspect_repository` | Check a repo before deploying: public or private, branch, framework |
| `check_site_name` | Validate a name / see if it exists |
| `deploy_site` | **New site**, in one call: Git (public/private) or archive URL; prebuilt or build-from-source |
| `redeploy_site` | Push new code (or an earlier version) to an existing site (marked destructive) |
| `get_site_status` / `list_sites` | Follow a deployment / list sites |

`deploy_site` runs the whole chain server-side (resolve archive → build config →
`S3Deployment` mutation). For private repos the model passes only the *name* of a
stored secret; the server resolves the token itself.

Not supported through MCP in v1: uploading a local zip (a remote server cannot read
the user's disk). Use a Git repo or a public archive URL.

The site tools also include `get_site_details`, `get_site_overview`, `get_site_traffic`,
`get_site_uptime`, `get_site_bandwidth`, `get_site_analytics`, `list_site_deployments`,
`list_site_releases`, `get_release_details`, `revert_site_version`, `delete_site`,
`enable_site_traffic_monitoring` and `delete_git_secret`.

There is deliberately **no** tool to add a Git token, because it would have to pass through the
conversation. Users add tokens in the Nife dashboard (Secrets) and reference them by name.

### Custom domains

| Tool | Purpose |
|---|---|
| `get_domain_dns_instructions` | The CNAME the user must create first (read-only) |
| `get_app_custom_domain` / `get_site_custom_domain` | Domain state: DNS synced, SSL |
| `add_app_custom_domain` / `add_site_custom_domain` | Attach a domain and sync DNS |
| `remove_app_custom_domain` / `remove_site_custom_domain` | Detach (destructive; the default address keeps working) |

### Operations: incidents, alerts, SLOs

`get_health_insights`, `list_incidents`, `get_incident`, `get_root_cause_analysis`, `list_alerts`,
`list_anomalies`, `predict_failures`, `get_slo_status`, `get_health_report`, `search_knowledge_base`
(all read-only), and `acknowledge_alert` / `resolve_alert` (idempotent writes).

### Billing and FinOps

Read-only: `get_spending_overview`, `get_usage_stats`, `list_billing_cycles`, `get_billing_items`,
`list_invoices`, `get_cloud_billing_summary`, `list_cost_recommendations`, `get_cost_forecast`,
`get_cost_anomalies`, `get_cost_usage_patterns`, `get_finops_resource_stats`,
`search_finops_resources`, `get_cost_breakdown`. `apply_cost_recommendation` can change real
infrastructure and is marked destructive; it previews unless `confirm=true`.

### Platform: delivery, usage, capacity (all read-only)

`get_org_dora_metrics`, `get_deployment_history`, `get_incident_history`, `get_audit_log_summary`,
`get_restore_history`, `get_regulatory_reporting`, `get_incident_regulatory_reports`,
`list_backup_policies`, `get_capacity_thresholds`, `get_usage_report_subscription`,
`get_app_usage_metrics`, `get_usage_summary`, `get_app_cost`, `estimate_deployment_cost`,
`get_credits`, `get_volume_overview`, `get_app_failover`, `list_cloud_hosts`, `list_workloads`,
`list_clusters`, `get_cluster_capacity`.

### Infrastructure and access (read-only)

`list_cloud_accounts` (all clouds, status, no credentials), `list_business_units`, `list_roles`,
`get_plan_limits`, `list_managed_clusters`, `list_vm_node_pools`, `list_agents`, `get_agent_metrics`,
`get_agent_security_findings`, `get_agent_health_checks`, `get_resource_forecast`.

### Servers and VMs

`vm_power_action` (start, stop or restart a registered server; destructive, previews unless
`confirm=true`) and `validate_cloud_account` (re-check a cloud account's credentials; changes only
its status).

### Cron jobs

`list_cron_job_runs`, `get_cron_job_run_logs` (read-only) and `trigger_cron_job_run` (runs the job
for real, so it previews unless `confirm=true`).

### Not covered

Databases, webhooks, API and personal access tokens, code scan, GitHub Actions and workflows,
templates, marketplace, image optimization, email management, vault providers, cloud-account
credentials (only Git secrets exist), ingress controller setup, creating or switching blue-green,
canary and A/B releases for sites (they can be listed and inspected), and creating volumes,
snapshots, backups or VMs. Compliance is covered read-only (audit summary, regulatory reporting,
restore history).

## Deploy the server

Build and run locally:

```bash
docker build -t nife-mcp-server .
docker run --rm -p 8100:8000 \
  -e NIFE_MCP_OAUTH_SECRET=<long-random-string> \
  -e NIFE_GRAPHQL_URL=https://nife.io/graphql \
  -e NIFE_EXPRESS_URL=https://clb2.nifetency.com \
  -e NIFE_MCP_LOGIN_URL=http://localhost:8080/login \
  nife-mcp-server
```

Deploy the image anywhere that gives you HTTPS (Nife's Docker-image deployment works).
Expose container port **8000** and put it behind a TLS domain such as `mcp.nife.io`.
The connector URL is then `https://mcp.nife.io/mcp`.

### Configuration (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8000` | |
| `NIFE_GRAPHQL_URL` | `https://api.nife.io/graphql` | |
| `NIFE_EXPRESS_URL` | `https://getuptime.clb2.nifetency.com` | express-backend: private-repo uploads (`/api/github-upload-to-s3`), nifex traffic, uptime and custom-domain routes |
| `NIFE_UPTIME_KUMA_URL` | `https://testuptimekuma.nifetency.com` | Uptime Kuma service. The default looks like a test host: set it explicitly in production |
| `NIFE_FINOPS_URL` | `https://platus.clb2.nifetency.com` | FinOps ML service (cost recommendations, forecast, cost explorer) |
| `NIFE_LSTM_URL` | `https://lstm.on.nifetency.com` | Nia usage-forecast service |
| `NIFE_SITE_DOMAIN` | `on.nifetency.com` | Used only to show the expected site URL |
| `NIFE_BUILD_IMAGE_NAMESPACE` | `nife123` | Registry namespace the platform build pushes images to (`deploy_app_from_git`) |
| `NIFE_ENV_ENCRYPTION_KEY` | *(unset)* | 16/24/32-byte AES key (alias: `NIFE_ENCRYPTION_KEY`). If set, env var values are encrypted exactly like the dashboard does, and stored Git tokens can be decrypted for repository inspection. If unset, env values are sent as plaintext (see above) |
| `NIFE_MCP_RATE_LIMIT_PER_MIN` | `120` | Per token, per process |
| `NIFE_MCP_ALLOWED_ORIGINS` | *(unset)* | Comma-separated; enforced only when the request has an `Origin` header |
| `LOG_LEVEL` | `INFO` | The Authorization header is never logged |
| `NIFE_MCP_OAUTH_SECRET` | *(random per process)* | Any long random string. Seals OAuth client ids / codes; keep it stable and shared across replicas |
| `NIFE_MCP_LOGIN_URL` | `https://launch.nife.io/login` | Dashboard login page the OAuth flow sends users to (must accept `callback` and `state`) |
| `NIFE_MCP_PUBLIC_URL` | *(from Host / X-Forwarded-*)* | Public base URL, e.g. `https://mcp.nife.io`. Set it if the proxy does not forward the host |
| `NIFE_MCP_OAUTH_REDIRECT_HOSTS` | `claude.ai,claude.com` | Hosts allowed to receive authorization codes (loopback http always allowed) |

There is deliberately **no** `NIFE_ACCESS_TOKEN` fallback in hosted mode.

## Security notes

* Requests without `Authorization: Bearer …` get `401` before reaching any tool.
* The Nife token is never a tool parameter, so it never enters the model's context.
* Environment variable values are tool parameters (see "Container apps"), so they do pass through
  the conversation. Secret values are never returned by any tool.
* Terminate TLS at the ingress; do not expose port 8000 over plain HTTP.
* The server cannot validate tokens itself. The Nife backend does, on every call.
* Give users a dedicated, revocable **MCP token** rather than their dashboard session token.
* `archive_url` blocks non-https and private/loopback IP literals, but cannot stop a
  hostname that *resolves* to a private address. The backend that downloads the
  archive must enforce that.

## Verify after deploying

```bash
curl https://<host>/health                                   # 200
curl -i -X POST https://<host>/mcp                            # 401 without a token
npx @modelcontextprotocol/inspector                           # transport: Streamable HTTP,
                                                              # URL: https://<host>/mcp,
                                                              # header: Authorization: Bearer <token>
```

Then do one real deploy of a small public repo and confirm the site comes up, and
create one site from the dashboard with an env var and one from MCP with the same
env var, to confirm the backend treats them identically.

## Run the tests

```bash
pip install -e ".[http]" pytest
pytest
```

## Roadmap

* Refresh tokens / dedicated revocable MCP tokens for the OAuth flow, and OAuth for
  non-Claude clients that need custom redirect schemes.
* Presigned upload tool for local archives.
* Remaining tool groups from "Not covered" above, each curated rather than auto-generated.
* Canary, blue-green and A/B rollouts for container apps, and creating or switching them for sites.
