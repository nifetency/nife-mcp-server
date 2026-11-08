# Nife.io MCP Server

<div align="center">

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://pepy.tech/badge/nife-mcp-server)](https://pepy.tech/project/nife-mcp-server)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**A Model Context Protocol (MCP) server that interfaces with the Nife.io GraphQL API**

[Installation](#-installation) •
[Quick Start](#-quick-start) •
[Documentation](#-documentation) •
[Contributing](#-contributing)

</div>

---

##  Overview

Nife MCP Server provides a standardized interface to interact with Nife.io's GraphQL API through the Model Context Protocol, enabling seamless integration with Claude Desktop and other MCP-compatible applications.

###  Key Features

-  **Intelligent Schema Discovery** - Automatically discovers and adapts to the GraphQL schema
-  **Dynamic Tool Generation** - Creates MCP tools on-the-fly from schema
-  **Zero Configuration** - Works out of the box with minimal setup
-  **Secure Authentication** - Bearer token support with flexible configuration
-  **Multiple Install Methods** - PyPI, NPM, or GitHub
-  **Cross-Platform** - Works on macOS, Linux, and Windows
-  **Production Ready** - Comprehensive error handling and logging

##  Installation

### Option 1: PyPI (Recommended for Python users)

```bash
pip install nife-mcp-server
```

### Option 2: NPM (Best for Claude Desktop)

```bash
npx @nifelabs/mcp-server@latest
```

### Option 3: From Source

```bash
git clone https://github.com/nifetency/nife-mcp-server
cd nife-mcp-server
pip install -r requirements.txt
```

##  Quick Start

### 1. Get Your Access Token

```bash
nifectl auth login
nifectl auth token
```

### 2. Configure Claude Desktop

You can use the Nife MCP Server in three ways depending on your setup.

------------------------------------------------------------------------

### 1. Recommended: Using NPX (No Installation Required)

This is the easiest way to get started.

``` json
{
  "mcpServers": {
    "nife": {
      "command": "npx",
      "args": ["--yes", "@nifelabs/mcp-server@latest"],
      "env": {
        "NIFE_ACCESS_TOKEN": "your_token_here",
        "PYTHON": "PYTHON_PATH"

      }
    }
  }
}
```

------------------------------------------------------------------------

### 2.  Using Python (Installed via pip)

If you installed the package via pip:

``` bash
pip install nife-mcp-server
```

Use this configuration:

``` json
{
  "mcpServers": {
    "nife": {
      "command": "python",
      "args": ["-m", "nife_mcp_server"],
      "env": {
        "NIFE_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
```

------------------------------------------------------------------------

### 3.  Local Development (Source Code)

If you're running from source:

``` json
{
  "mcpServers": {
    "nife": {
      "command": "python",
      "args": ["-m", "nife_mcp_server.intelligent_main"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\nife-mcp-server\\src",
        "NIFE_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
```

 Replace the `PYTHONPATH` with your local project path.

------------------------------------------------------------------------

##  Environment Variables

  Variable              Description
  --------------------- ---------------------------------
  `NIFE_ACCESS_TOKEN`   Your API access token from Nife

------------------------------------------------------------------------



### 3. Restart Claude Desktop

Your Nife.io integration is now active! 🎉

## 📚 Documentation

- [Quick Start](#-quick-start) - Get started in 5 minutes
- [Hosted connector (URL-based)](HOSTED.md) - Deploy the remote server and connect by URL
- [API Documentation](ENDPOINT_GUIDE.md) - Complete API reference
- [Release Guide](RELEASE_GUIDE.md) - For contributors and maintainers
- [Contributing](CONTRIBUTING.md) - How to contribute

##  Hosted connector tools: reliability, cost and platform

The hosted connector (`nife-mcp-http`) adds curated tools on top of the site, app and custom-domain tools. The stdio server (`intelligent_main.py`) loads the same tools next to its schema-generated ones when the optional dependencies are installed (`pip install "nife-mcp-server[http]"`, or `pip install -r requirements.txt`). It uses `NIFE_ACCESS_TOKEN` as the caller's token. Without those packages it runs with only the schema-generated tools and logs a hint on stderr. Every call is made with the caller's own token. Organization-keyed tools check membership first, and alert, billing cycle and recommendation ids are checked against the caller's own lists before use.

**Reliability (NERO)**

| Tool | What it does |
|------|--------------|
| `get_health_insights` | Overall health, open incidents, anomalies, predictions and actions. Start here |
| `list_incidents`, `get_incident` | Incidents and their post-mortems |
| `get_root_cause_analysis` | AI root cause analysis (slow; `refresh=true` runs a new one) |
| `list_alerts` | Alerts with status and who handled them |
| `acknowledge_alert`, `resolve_alert` | Change alert state (confirm with the user first) |
| `list_anomalies`, `predict_failures` | Detected anomalies and predicted failures |
| `get_slo_status`, `get_health_report` | SLO and error budget; deep per-service health |
| `search_knowledge_base` | Past incidents and fixes by error text |

**Cost (FinOps)**

| Tool | What it does |
|------|--------------|
| `get_spending_overview`, `get_usage_stats` | Spend against limits; resource usage and cost |
| `list_billing_cycles`, `get_billing_items`, `list_invoices`, `get_cloud_billing_summary` | Billing detail |
| `list_cost_recommendations` | Ranked savings opportunities with totals |
| `get_cost_forecast`, `get_cost_anomalies`, `get_cost_usage_patterns` | Outlook, unusual cost, and what the recommendations rest on |
| `get_cost_breakdown` | Cost explorer: total grouped by provider, service or region |
| `search_finops_resources`, `get_finops_resource_stats` | Multi-cloud inventory with monthly cost |
| `apply_cost_recommendation` | Carries out one recommendation. Previews unless `confirm=true` |

**Platform, delivery and compliance (read-only)**

| Tool | What it does |
|------|--------------|
| `get_org_dora_metrics` | Deployment frequency, lead time, change failure rate and time to restore |
| `get_deployment_history`, `get_incident_history` | Deployment and incident events of one app |
| `get_usage_summary`, `get_app_cost`, `get_app_usage_metrics` | Running cost per account and app; CPU, memory and network usage |
| `estimate_deployment_cost`, `get_credits` | Price a deployment before making it; prepaid balance and transactions |
| `get_volume_overview`, `get_app_failover` | Volumes, health and snapshots; failover targets and which one serves |
| `list_clusters`, `get_cluster_capacity` | Regions and clusters; free CPU, memory, storage and pods |
| `list_cloud_hosts`, `list_workloads` | Connected servers and VMs; workload environments |
| `list_backup_policies`, `get_restore_history` | Backup schedules and restore results |
| `get_capacity_thresholds`, `get_usage_report_subscription` | Capacity alert thresholds; emailed usage report schedule |
| `get_audit_log_summary`, `get_regulatory_reporting`, `get_incident_regulatory_reports` | Audit trail size; on-time reporting to CERT-In, DPB, RBI, SEBI or IRDAI |

These tools only read. Cloud credentials and kubeconfig locations are never requested.

**Infrastructure and governance (read-only)**

| Tool | What it does |
|------|--------------|
| `list_cloud_accounts` | Cloud accounts connected to an organization, without credentials |
| `list_managed_clusters`, `list_vm_node_pools` | Provisioned Kubernetes clusters (no kubeconfig) and VM pools |
| `list_business_units`, `list_roles`, `get_plan_limits` | Business units; role permissions; what the plan allows |
| `list_agents`, `get_agent_metrics` | Nife agents in customer clusters; cluster, node and app usage |
| `get_agent_security_findings`, `get_agent_health_checks` | Findings with remediation; health checks per cluster |
| `get_resource_forecast` | Nia CPU and memory forecast for an organization or app (no charts) |

The forecast service address can be changed with `NIFE_LSTM_URL`.

**Virtual machines and cloud accounts (changes)**

| Tool | What it does |
|------|--------------|
| `vm_power_action` | Start, stop or restart a server or VM. Previews unless `confirm=true` |
| `validate_cloud_account` | Re-check a cloud account's credentials and update its status |

**Cron jobs**

| Tool | What it does |
|------|--------------|
| `list_cron_job_runs`, `get_cron_job_run_logs` | Run history with failure reasons; the tail of one run's log |
| `trigger_cron_job_run` | Start a run now. Previews unless `confirm=true` |

##  Usage

### Starting the Server

```bash
# If installed via pip
nife-mcp-server

# If running from source
python -m nife_mcp_server.intelligent_main
```

The server speaks MCP over stdin/stdout, so it is normally launched by your MCP client (e.g. Claude Desktop) rather than run by hand. It does not listen on a network port.

To run the hosted HTTP connector instead, install the `http` extra (`pip install "nife-mcp-server[http]"`) and run `nife-mcp-http`. It listens on `PORT` (default 8000); see [HOSTED.md](HOSTED.md).

### Environment Variables

- `NIFE_ACCESS_TOKEN` - Your Nife.io access token

The GraphQL endpoint is fixed to `https://api.nife.io/graphql`. The hosted connector has its own settings, listed in [HOSTED.md](HOSTED.md).

### Example Usage with Claude

Once configured, you can ask Claude:

```
"List all my applications in Nife.io"
"Show me the status of my deployments"
"Create a new application called 'my-app'"
```

##  Architecture

```
┌─────────────────┐
│  Claude Desktop │
└────────┬────────┘
         │ MCP Protocol
┌────────▼────────┐
│  Nife MCP Server│
└────────┬────────┘
         │ GraphQL
┌────────▼────────┐
│   Nife.io API   │
└─────────────────┘
```

### Core Components

- **Schema Manager** - Intelligent GraphQL schema introspection
- **Tool Generator** - Dynamic MCP tool creation
- **Query Builder** - Smart query construction
- **Authentication** - Secure token management

##  API Endpoints

### MCP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mcp/context` | GET | Retrieve model context |
| `/api/mcp/context` | POST | Update model context |
| `/api/mcp/schema` | GET | Get GraphQL schema |
| `/api/mcp/query` | POST | Execute custom queries |
| `/api/mcp/health` | GET | Health check |

### GraphQL Integration

The server provides full access to Nife.io's GraphQL API:

-  Query all resources (apps, deployments, etc.)
-  Execute mutations (create, update, delete)
-  Custom query execution
-  Schema introspection

##  Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/nifetency/nife-mcp-server
cd nife-mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .  # Install in editable mode



# Run the server
cd src
python -m nife_mcp_server.intelligent_main
```

### Project Structure

```
nife-mcp-server/
├── src/
│   └── nife_mcp_server/
│       ├── intelligent_main.py  # Main server logic
│       ├── schema_manager.py    # GraphQL schema handling
│       ├── http_app.py          # Hosted (Streamable HTTP) connector
│       ├── http_auth.py         # Auth for the hosted connector
│       ├── oauth.py             # OAuth support
│       ├── nife_api.py          # Async client (GraphQL, express-backend, FinOps)
│       ├── tool_utils.py        # Shared tool helpers and ownership checks
│       ├── site_tools.py        # Site deploy, manage and inspect tools
│       ├── app_tools.py         # Container app tools
│       ├── domain_tools.py      # Custom-domain tools
│       ├── ops_tools.py         # NERO and FinOps tools
│       ├── platform_tools.py    # Delivery, compliance, usage and capacity tools
│       ├── infra_tools.py       # Cloud accounts, clusters, agents, governance
│       ├── vm_tools.py          # VM power actions and cloud account checks
│       ├── cron_tools.py        # Cron job runs
│       └── routes/
│           └── mcp.py          # MCP route handlers
├── tests/                      # Test suite
├── Dockerfile                  # Container image for the hosted server
└── bin/                        # Executable scripts
```

### Running Tests

```bash
pytest
pytest --cov=nife_mcp_server  # With coverage
```

##  Contributing

We love contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Ways to Contribute

-  Report bugs
-  Suggest features
-  Improve documentation
-  Submit pull requests

### Development Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

##  Stats

![GitHub stars](https://img.shields.io/github/stars/nifetency/nife-mcp-server?style=social)
![GitHub forks](https://img.shields.io/github/forks/nifetency/nife-mcp-server?style=social)
![GitHub issues](https://img.shields.io/github/issues/nifetency/nife-mcp-server)
![GitHub pull requests](https://img.shields.io/github/issues-pr/nifetency/nife-mcp-server)

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

##  Acknowledgments

- Built for the [Model Context Protocol](https://modelcontextprotocol.io/)
- Powered by [Nife.io](https://nife.io)
- Designed for [Claude Desktop](https://claude.ai/desktop)

##  Support

-  Email: support@nife.io
-  Issues: [GitHub Issues](https://github.com/nifetency/nife-mcp-server/issues)
-  Discussions: [GitHub Discussions](https://github.com/nifetency/nife-mcp-server/discussions)
-  Documentation: [Full Docs](https://github.com/nifetency/nife-mcp-server#readme)

##  Roadmap

- [ ] WebSocket support for real-time updates
- [ ] GraphQL subscriptions
- [ ] Enhanced caching layer
- [ ] Query batching
- [ ] Metrics and monitoring
- [ ] Docker Compose examples
- [ ] Kubernetes manifests

##  Star History

If you find this project useful, please consider giving it a star!

[![Star History Chart](https://api.star-history.com/svg?repos=nifetency/nife-mcp-server&type=Date)](https://star-history.com/#nifetency/nife-mcp-server&Date)

---

<div align="center">

**Made by the Nife.io team**

[Website](https://nife.io) • [Documentation](https://docs.nife.io) • [Blog](https://blog.nife.io) • [MCP Open Source](https://nife.io/mcp_opensource)

</div>
