"""Every tool module registers into one server, so their tool names must not collide.

FastMCP only logs a warning when a name is registered twice and silently keeps the first
definition, so a clash hides one of the tools without any error.
"""
from collections import Counter

import pytest

pytest.importorskip("mcp")
from mcp.server.fastmcp import FastMCP  # noqa: E402

from nife_mcp_server import (  # noqa: E402
    app_tools, cron_tools, domain_tools, infra_tools, ops_tools, platform_tools, site_tools, vm_tools,
)

REGISTRARS = [
    site_tools.register_site_tools,
    app_tools.register_app_tools,
    domain_tools.register_domain_tools,
    ops_tools.register_ops_tools,
    platform_tools.register_platform_tools,
    infra_tools.register_infra_tools,
    vm_tools.register_vm_tools,
    cron_tools.register_cron_tools,
]


def _registered_names():
    mcp = FastMCP("test")
    seen = []
    original = mcp._tool_manager.add_tool

    def record(fn, *args, **kwargs):
        seen.append(kwargs.get("name") or fn.__name__)
        return original(fn, *args, **kwargs)

    mcp._tool_manager.add_tool = record
    for register in REGISTRARS:
        register(mcp)
    return seen, mcp


def test_no_two_modules_register_the_same_tool_name():
    seen, _ = _registered_names()
    clashes = sorted(name for name, n in Counter(seen).items() if n > 1)
    assert clashes == []


def test_every_registered_tool_is_listed():
    seen, mcp = _registered_names()
    assert len(mcp._tool_manager.list_tools()) == len(set(seen))
