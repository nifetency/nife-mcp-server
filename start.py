#!/usr/bin/env python3
"""
Unified startup script for nife-mcp-server
Supports both MCP mode (stdin/stdout) and Flask HTTP mode
"""

import sys
import os
import argparse
import asyncio

# Ensure src is in path
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

def run_mcp_server(verbose=False):
    """Run MCP server (stdin/stdout mode)"""
    import logging
    
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
            stream=sys.stderr
        )
        print("Starting Nife MCP Server in verbose mode...", file=sys.stderr)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            stream=sys.stderr
        )
        print("Starting Nife MCP Server...", file=sys.stderr)
    
    try:
        from nife_mcp_server.main import NifeMCPServer
        
        async def server_main():
            server = NifeMCPServer()
            await server.run()
        
        asyncio.run(server_main())
        
    except ImportError as e:
        print(f"Error importing MCP server: {e}", file=sys.stderr)
        print("Make sure you're in the virtual environment and dependencies are installed:", file=sys.stderr)
        print("  source .venv/bin/activate", file=sys.stderr)
        print("  pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error running MCP server: {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

def run_flask_server(host='0.0.0.0', port=5000, debug=False):
    """Run Flask HTTP server"""
    import logging
    
    # Suppress Flask/Werkzeug logs unless debug mode
    if not debug:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        logging.getLogger('flask').setLevel(logging.ERROR)
    
    try:
        from nife_mcp_server.app import app
        
        print(f"Starting Flask server on http://{host}:{port}", file=sys.stderr)
        print(f"API endpoints available at http://{host}:{port}/api", file=sys.stderr)
        print(f"Health check: http://{host}:{port}/api/mcp/health", file=sys.stderr)
        print("\nPress CTRL+C to stop", file=sys.stderr)
        
        app.run(
            host=host,
            port=port,
            debug=debug,
            use_reloader=False  # Avoid double startup
        )
        
    except ImportError as e:
        print(f"Error importing Flask app: {e}", file=sys.stderr)
        print("Make sure you're in the virtual environment and dependencies are installed:", file=sys.stderr)
        print("  source .venv/bin/activate", file=sys.stderr)
        print("  pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error running Flask server: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        prog='nife-mcp-server',
        description='Nife.io MCP Server - Start in MCP or Flask mode',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run MCP server (stdin/stdout for Claude Desktop)
  python start.py --mode mcp
  
  # Run Flask HTTP server  
  python start.py --mode flask
  
  # Run Flask with custom host/port
  python start.py --mode flask --host 0.0.0.0 --port 8080
  
  # Run in debug mode
  python start.py --mode flask --debug
  
  # Run with verbose logging
  python start.py --mode mcp --verbose
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['mcp', 'flask'],
        default='mcp',
        help='Server mode: mcp (stdin/stdout) or flask (HTTP REST API)'
    )
    
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Flask server host (flask mode only, default: 0.0.0.0)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Flask server port (flask mode only, default: 5000)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (flask mode only)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='nife-mcp-server 2.0.0'
    )
    
    args = parser.parse_args()
    
    # Check for NIFE_ACCESS_TOKEN
    if not os.environ.get('NIFE_ACCESS_TOKEN'):
        print("⚠️  Warning: NIFE_ACCESS_TOKEN environment variable not set", file=sys.stderr)
        print("   Some operations may require authentication", file=sys.stderr)
        print("   Set it with: export NIFE_ACCESS_TOKEN='your_token'", file=sys.stderr)
        print("   Get token with: nifectl auth token", file=sys.stderr)
        print("", file=sys.stderr)
    
    # Run appropriate server
    if args.mode == 'mcp':
        run_mcp_server(verbose=args.verbose)
    else:  # flask
        run_flask_server(
            host=args.host,
            port=args.port,
            debug=args.debug
        )

if __name__ == '__main__':
    main()
