"""The curated tool modules, listed once, for servers that load them in-process.

The hosted connector (http_app.py) registers the same modules. A test keeps the two lists
equal, so a new module must be added in both places.
"""
from mcp.server.fastmcp import FastMCP

from nife_mcp_server.app_tools import APP_INSTRUCTIONS, register_app_tools
from nife_mcp_server.cron_tools import CRON_INSTRUCTIONS, register_cron_tools
from nife_mcp_server.domain_tools import DOMAIN_INSTRUCTIONS, register_domain_tools
from nife_mcp_server.infra_tools import INFRA_INSTRUCTIONS, register_infra_tools
from nife_mcp_server.ops_tools import OPS_INSTRUCTIONS, register_ops_tools
from nife_mcp_server.platform_tools import PLATFORM_INSTRUCTIONS, register_platform_tools
from nife_mcp_server.site_tools import SERVER_INSTRUCTIONS, register_site_tools
from nife_mcp_server.vm_tools import VM_INSTRUCTIONS, register_vm_tools

INSTRUCTIONS = (
    SERVER_INSTRUCTIONS + APP_INSTRUCTIONS + DOMAIN_INSTRUCTIONS + OPS_INSTRUCTIONS
    + PLATFORM_INSTRUCTIONS + INFRA_INSTRUCTIONS + VM_INSTRUCTIONS + CRON_INSTRUCTIONS
)


def register_all_tools(mcp: FastMCP) -> None:
    register_site_tools(mcp)
    register_app_tools(mcp)
    register_domain_tools(mcp)
    register_ops_tools(mcp)
    register_platform_tools(mcp)
    register_infra_tools(mcp)
    register_vm_tools(mcp)
    register_cron_tools(mcp)
