#!/usr/bin/env python3
"""
Main entry point - runs the Intelligent Schema-Driven MCP Server
"""
import asyncio
from nife_mcp_server.intelligent_main import main

if __name__ == "__main__":
    asyncio.run(main())