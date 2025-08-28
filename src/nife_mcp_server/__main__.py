#!/usr/bin/env python3
"""Entry point for python -m nife_mcp_server"""

import asyncio
import sys
import argparse
from nife_mcp_server.main import NifeMCPServer

def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        prog='nife_mcp_server',
        description='Nife.io MCP Server - Model Context Protocol server for Nife.io platform'
    )
    parser.add_argument(
        '--version', 
        action='version', 
        version='nife_mcp_server 1.0.0'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
        print("Starting Nife MCP Server in verbose mode...", file=sys.stderr)
    else:
        print("Starting Nife MCP Server...", file=sys.stderr)
        print("Server is waiting for MCP client connection via stdin/stdout", file=sys.stderr)
    
    async def server_main():
        """Placeholder for the actual server main function."""
        mcp_server = NifeMCPServer()
        await mcp_server.run()

    try:
        asyncio.run(server_main())
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()