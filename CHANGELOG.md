# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- NERO (AI SRE) tools: health insights, incidents and post-mortems, root cause analysis, alerts (acknowledge and resolve), anomalies, failure predictions, SLO status, health report, knowledge base search
- FinOps tools: spending overview, usage stats, billing cycles and items, invoices, cloud billing summary, ranked cost recommendations, cost forecast, cost anomalies
- FinOps inventory and cost explorer tools: `search_finops_resources`, `get_finops_resource_stats`, `get_cost_breakdown`, `get_cost_usage_patterns`
- `apply_cost_recommendation`: carries out one cost recommendation. Previews unless `confirm=true`, and only accepts ids from the caller's own recommendation list
- Custom-domain tools: `get_domain_dns_instructions`, `add_site_custom_domain`, `remove_site_custom_domain`, `get_app_custom_domain`, `add_app_custom_domain` (load balancer lookup, DNS sync and ingress rule in one call; safe to retry) and `remove_app_custom_domain`. Removals require the domain name as `confirm_domain`
- Platform, infrastructure, VM and cron tools (read-only listings; cron trigger and `vm_power_action` are confirm-gated)
- `finops_post` client helper for the FinOps service
- Tests for custom domains, NERO/FinOps, platform, infra, VM, cron and a version-consistency check

### Changed
- CI now runs the pytest suite on every OS/Python combination and fails when it fails; the install smoke test no longer swallows errors; Bandit fails on high-severity findings
- Ownership checks: org-keyed queries verify organization membership; alert and billing cycle ids are checked against the caller's own lists before any change or lookup

### Fixed
- Package version is read from one place (`nife_mcp_server.__version__`) so `pyproject.toml`, `package.json`, the health endpoint, the MCP `initialize` response and the API client agree
- npm launcher (`npx @nifelabs/mcp-server`) now puts the bundled `src/` on `PYTHONPATH`, checks for Python 3.10+ and the required packages, and prints how to fix a missing one instead of failing with an import error

## [1.0.0] - 2025-11-09

### Added
- Initial release of Nife MCP Server
- Intelligent schema-driven implementation: auto-discovers GraphQL queries and mutations and generates MCP tools from the schema, with no hard-coded queries
- Custom GraphQL query execution and schema introspection tools
- Field selection modes (auto, all, custom) and recursive type resolution
- Flask-based REST API endpoints with CORS support
- Authentication via Bearer token or environment variable
- Health check endpoint and detailed logging
- Deployment options: NPM, PyPI, Docker
- `test_endpoint.py` endpoint connectivity tester, `update_claude_config.sh` and `run_server.sh`

### Documentation
- README.md, RELEASE_GUIDE.md and ENDPOINT_GUIDE.md

### Supported Platforms
- macOS, Linux, Windows
- Python 3.10+ (3.10 to 3.13 in CI)
- Node.js 16+ (npm launcher)

---

[Unreleased]: https://github.com/nifetency/nife-mcp-server/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/nifetency/nife-mcp-server/releases/tag/v1.0.0
