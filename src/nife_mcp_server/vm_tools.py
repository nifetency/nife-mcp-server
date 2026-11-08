"""Write tools for virtual machines and cloud accounts.

Both prove ownership first: hosts and cloud accounts are looked up through organization-keyed
queries that require_org has already checked, and only then is a mutation made with the caller's
own token. A power action previews unless confirm=true, like apply_cost_recommendation.
"""
import logging
from typing import Annotated, Any, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from nife_mcp_server.nife_api import NifeAPI, NifeAPIError
from nife_mcp_server.ops_tools import OrgId, _need, guarded
from nife_mcp_server.tool_utils import DESTRUCTIVE, WRITE_IDEMPOTENT, get_api, require_org

logger = logging.getLogger(__name__)

VM_INSTRUCTIONS = """\

VIRTUAL MACHINES AND CLOUD ACCOUNTS (changes)
- list_cloud_hosts shows the servers and VMs of an organization. vm_power_action starts, stops or
  restarts one: it previews first, and only acts with confirm=true after the user has agreed.
  Stopping a VM interrupts everything running on it.
- validate_cloud_account re-checks a connected cloud account's credentials and updates its status.
"""

POWER_ACTIONS = ("start", "stop", "restart")

# AWS and Azure hosts have their own mutations; every other cloud uses the generic one
# (nife-dashboard/client/src/lib/vmPower.ts).
_MUTATIONS = {
    "AWS": "NodeActionAWS",
    "AZURE": "NodeActionAzure",
}


def _mutation_for(host_type: Optional[str]) -> str:
    return _MUTATIONS.get((host_type or "").strip().upper(), "NodeAction")


async def _own_host(api: NifeAPI, organization_id: str, instance_name: str) -> Dict[str, Any]:
    """Find the host among the organization's own hosts (a query made with the caller's token)."""
    data = await api.graphql(
        """query OwnHosts($org: String) {
             getHost(orgId: $org) { id type status zone instanceName instanceId }
           }""",
        {"org": organization_id},
    )
    for host in data.get("getHost") or []:
        if host and host.get("instanceName") == instance_name:
            return host
    raise NifeAPIError(
        "No server with that instance_name was found in this organization. Use list_cloud_hosts."
    )


def register_vm_tools(mcp: FastMCP) -> None:
    @mcp.tool(annotations=DESTRUCTIVE, title="Start, stop or restart a VM")
    @guarded
    async def vm_power_action(
        organization_id: OrgId,
        instance_name: Annotated[str, Field(description="instanceName from list_cloud_hosts")],
        action: Annotated[str, Field(description="start, stop or restart")],
        ctx: Context,
        confirm: Annotated[bool, Field(description="Must be true to act. Leave false to preview.")] = False,
    ) -> Dict[str, Any]:
        """Start, stop or restart a registered server or VM. Stopping or restarting interrupts
        everything running on it. Call without confirm first to show the user what would happen,
        then again with confirm=true only after they agree."""
        api = get_api(ctx)
        verb = (action or "").strip().lower()
        if verb not in POWER_ACTIONS:
            raise ValueError("action must be one of: " + ", ".join(POWER_ACTIONS))
        name = _need(instance_name, "instance_name")
        await require_org(api, organization_id)
        host = await _own_host(api, organization_id, name)
        if not confirm:
            return {
                "performed": False,
                "message": "Preview only. Nothing was changed. Call again with confirm=true to act.",
                "action": verb, "instance_name": name, "type": host.get("type"),
                "current_status": host.get("status"), "zone": host.get("zone"),
            }
        mutation = _mutation_for(host.get("type"))
        data = await api.graphql(
            f"""mutation VmPower($input: StartAndStopVM) {{
                 {mutation}(input: $input) {{ id message nodeId }}
               }}""",
            {"input": {"instanceName": name, "action": verb}},
            timeout=120.0,
        )
        res = data.get(mutation) or {}
        logger.info("vm_power_action: action=%s type=%s", verb, host.get("type"))
        return {"performed": True, "action": verb, "instance_name": name,
                "message": res.get("message"), "node_id": res.get("nodeId")}

    @mcp.tool(annotations=WRITE_IDEMPOTENT, title="Validate cloud account")
    @guarded
    async def validate_cloud_account(
        organization_id: OrgId,
        account_id: Annotated[str, Field(description="Account id from list_connected_cloud_accounts")],
        ctx: Context,
    ) -> Dict[str, Any]:
        """Re-check a connected cloud account's credentials with the provider and update its status
        (active or invalid). Changes nothing else and returns no credentials."""
        api = get_api(ctx)
        wanted = _need(account_id, "account_id")
        await require_org(api, organization_id)
        listed = await api.graphql(
            """query OwnCloudAccounts($orgId: String!) { listCloudAccounts(orgId: $orgId) { id } }""",
            {"orgId": organization_id},
        )
        if not any(a and a.get("id") == wanted for a in listed.get("listCloudAccounts") or []):
            raise NifeAPIError("No cloud account with that id was found in this organization. Use list_connected_cloud_accounts.")
        data = await api.graphql(
            """mutation ValidateCloudAccount($id: String!) {
                 validateCloudAccount(id: $id) { id name cloud status lastValidatedAt }
               }""",
            {"id": wanted},
            timeout=90.0,
        )
        account = data.get("validateCloudAccount")
        if not account:
            raise NifeAPIError("The backend did not return the validation result.")
        return account
