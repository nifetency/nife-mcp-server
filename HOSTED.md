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
registration, authorization code + PKCE). Sign-in reuses the dashboard login through the same
`cli_session` hand-off as `nifectl auth login`: `/authorize` creates a session on the Nife
backend, you sign in at the dashboard (`/login?id=...`, password, MFA or SSO), and the token the
dashboard stores on that session is returned to Claude as the OAuth access token. Every `/mcp`
call still carries `Authorization: Bearer <nife token>`; the backend validates it as before.

Endpoints: `/.well-known/oauth-protected-resource[/mcp]`, `/.well-known/oauth-authorization-server`,
`/register`, `/authorize`, `/oauth/poll`, `/token`. Nothing is stored server-side: client ids,
pending sign-ins and authorization codes are encrypted blobs keyed by `NIFE_MCP_OAUTH_SECRET`
(set it, identically on every replica, or connectors must be re-added after each restart).
The backend's `WEB_AUTH_URL` must point at the dashboard login page.

Limits: no refresh tokens (when the Nife token expires, `/mcp` answers 401 and Claude asks you
to sign in again), and authorization codes are short-lived (2 min) and PKCE-bound but not
single-use.

## Tools (v1: static sites, v1.1: container apps)

Container apps and deployments (curated over `apps.graphqls` / `deploy.graphqls`):

| Tool | Purpose |
|---|---|
| `list_apps` / `get_app` | Inventory and full configuration (env var names only) |
| `get_app_status` | Live health: deployment progress, healthy/unhealthy instances, crash-loop hints |
| `list_app_releases` | Release history; versions feed `revert_app_release` |
| `get_app_logs` | Recent log lines of running instances (not a search) |
| `resume_app` | Resume a paused app |
| `restart_app`, `pause_app`, `scale_app`, `redeploy_app_image`, `revert_app_release`, `set_app_env` | Change a live app (marked destructive) |
| `delete_app` | Permanent; needs the app name twice |

Not yet: creating a new app (`createApp` + `deployImage` / `upsertAndDeployApp`), canary and blue-green
for apps, volumes, custom domains.

`set_app_env` note: the backend replaces the whole env set on every update, so the tool reads the
current values server-side, merges, and redeploys the current image. It refuses to run if it cannot
read the existing variables (override: `allow_replace_all`). New values are encrypted like the
dashboard does (needs `NIFE_ENV_ENCRYPTION_KEY`; without it they are sent as plaintext), existing
values pass through as stored. Approval and billing gates in the
backend (`RedeployImage`) can hold or reject a rollout; the error is passed through.

Static sites:

| Tool | Purpose |
|---|---|
| `list_organizations` | Orgs the user can deploy into |
| `list_site_frameworks` | Build presets (install/build/output) |
| `list_git_secrets` | Names of stored Git tokens (values never returned) |
| `check_site_name` | Validate a name / see if it exists |
| `deploy_site` | **New site**, in one call: Git (public/private) or archive URL; prebuilt or build-from-source |
| `redeploy_site` | Push new code to an existing site (marked destructive) |
| `get_site_status` / `list_sites` | Follow a deployment / list sites |

`deploy_site` runs the whole chain server-side (resolve archive → build config →
`S3Deployment` mutation). For private repos the model passes only the *name* of a
stored secret; the server resolves the token itself.

Not supported through MCP in v1: uploading a local zip (a remote server cannot read
the user's disk). Use a Git repo or a public archive URL.

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
| `NIFE_EXPRESS_URL` | `https://getuptime.clb2.nifetency.com` | Hosts `/api/github-upload-to-s3` (private repos) |
| `NIFE_SITE_DOMAIN` | `on.nifetency.com` | Used only to show the expected site URL |
| `NIFE_ENV_ENCRYPTION_KEY` | *(unset)* | 16/24/32-byte AES key. If set, env var values are encrypted exactly like the dashboard does. If unset they are sent as plaintext (see below) |
| `NIFE_MCP_RATE_LIMIT_PER_MIN` | `120` | Per token, per process |
| `NIFE_MCP_ALLOWED_ORIGINS` | *(unset)* | Comma-separated; enforced only when the request has an `Origin` header |
| `LOG_LEVEL` | `INFO` | The Authorization header is never logged |
| `NIFE_MCP_OAUTH_SECRET` | *(random per process)* | Any long random string. Seals OAuth client ids / codes; keep it stable and shared across replicas |
| `NIFE_MCP_PUBLIC_URL` | *(from Host / X-Forwarded-*)* | Public base URL, e.g. `https://mcp.nife.io`. Set it if the proxy does not forward the host |
| `NIFE_REST_URL` | *(NIFE_GRAPHQL_URL minus `/graphql`)* | Host serving `/api/v1/cli_sessions` |
| `NIFE_MCP_OAUTH_REDIRECT_HOSTS` | `claude.ai,claude.com` | Hosts allowed to receive authorization codes (loopback http always allowed) |

There is deliberately **no** `NIFE_ACCESS_TOKEN` fallback in hosted mode.

## Security notes

* Requests without `Authorization: Bearer …` get `401` before reaching any tool.
* The token is never a tool parameter, so it never enters the model's context.
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
* More tool groups (logs and metrics search, domains and env vars, volumes, databases, clusters), each curated rather than auto-generated.
* Container app creation (`upsertAndDeployApp`).
