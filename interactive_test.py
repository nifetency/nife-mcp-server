#!/usr/bin/env python3
"""
Interactive MCP Client for NIFE
This script connects to the NIFE MCP server and lets you interact with it.
"""
import json
import sys
import os
from typing import Tuple, Optional, List, Any

# Add the src directory to the path
sys.path.insert(0, '/Users/rentsher/nife-mcp-server/src')

# Now we can import the MCP server directly
from nife_mcp_server.main import NifeMCPServer
import asyncio

async def test_mcp_connection() -> Tuple[Optional[Any], List[Any]]:
    """Test MCP server connection and available tools"""
    
    print("=" * 70)
    print("NIFE MCP Server - Interactive Test")
    print("=" * 70)
    
    # Create server instance
    print("\n1. Initializing MCP Server...")
    server = NifeMCPServer()
    
    print(f"   ✓ Server initialized with {len(server.tools)} tools")
    
    # Test initialize
    print("\n2. Testing Initialize Request...")
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "interactive-test",
                "version": "1.0.0"
            }
        }
    }
    
    init_response = await server.handle_request(init_request)
    if not init_response or 'result' not in init_response:
        print("   ✗ Initialize failed")
        return None, []
    
    print(f"   ✓ Initialize successful")
    server_info = init_response.get('result', {}).get('serverInfo', {})
    print(f"   Server: {server_info.get('name', 'Unknown')} v{server_info.get('version', 'Unknown')}")
    
    # Test list tools
    print("\n3. Listing Available Tools...")
    list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    list_response = await server.handle_request(list_request)
    if not list_response or 'result' not in list_response:
        print("   ✗ Failed to list tools")
        return None, []
    
    tools = list_response.get('result', {}).get('tools', [])
    
    print(f"   ✓ Found {len(tools)} tools\n")
    
    # Categorize tools
    query_tools = [t for t in tools if t['name'].startswith('get_')]
    mutation_tools = [t for t in tools if any(t['name'].startswith(p) for p in ['create_', 'update_', 'delete_', 'deploy_', 'scale_', 'restart_', 'set_', 'add_', 'remove_', 'invite_'])]
    legacy_tools = [t for t in tools if t not in query_tools and t not in mutation_tools]
    
    print("   📊 Query Tools (Read Operations):")
    for tool in query_tools[:5]:
        print(f"      • {tool['name']}: {tool['description'][:50]}...")
    if len(query_tools) > 5:
        print(f"      ... and {len(query_tools) - 5} more query tools")
    
    print(f"\n   🔧 Mutation Tools (Write Operations):")
    for tool in mutation_tools[:5]:
        print(f"      • {tool['name']}: {tool['description'][:50]}...")
    if len(mutation_tools) > 5:
        print(f"      ... and {len(mutation_tools) - 5} more mutation tools")
    
    print(f"\n   🔌 Legacy Tools:")
    for tool in legacy_tools:
        print(f"      • {tool['name']}: {tool['description'][:50]}...")
    
    # Test health check
    print("\n4. Testing Health Check...")
    health_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "nife_health_check",
            "arguments": {}
        }
    }
    
    health_response = await server.handle_request(health_request)
    if not health_response or 'result' not in health_response:
        print("   ✗ Health check failed")
        return server, tools
    
    content = health_response.get('result', {}).get('content', [])
    if not content:
        print("   ✗ No health check content returned")
        return server, tools
    
    health_text = content[0].get('text', '{}')
    health_data = json.loads(health_text)
    
    print(f"   ✓ Health Status: {health_data['status']}")
    print(f"   ✓ Service: {health_data['service']}")
    print(f"   ✓ Version: {health_data['version']}")
    
    if 'test_results' in health_data:
        print("\n   API Connection Tests:")
        for test_name, result in health_data['test_results'].items():
            status_icon = "✓" if result['status'] == 'healthy' else "✗"
            print(f"      {status_icon} {test_name}: {result['status']}")
    
    # Show example usage
    print("\n" + "=" * 70)
    print("🎉 MCP Server is working correctly!")
    print("=" * 70)
    
    print("\n📖 Example Usage:")
    print("\nTo use with Claude Desktop, add this to your config:")
    print("""
{
  "mcpServers": {
    "nife": {
      "command": "/Users/rentsher/nife-mcp-server/.venv/bin/python",
      "args": ["-m", "nife_mcp_server"],
      "env": {
        "NIFE_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
""")
    
    print("\nTo get your access token:")
    print("  $ nifectl auth login")
    print("  $ nifectl auth token")
    
    print("\n" + "=" * 70)
    
    # Interactive mode
    print("\n🔍 Would you like to test a specific tool? (y/n): ", end='')
    
    return server, tools

async def interactive_test(server, tools):
    """Interactive tool testing"""
    
    print("\nAvailable tool categories:")
    print("  1. get_organizations - Get all organizations")
    print("  2. get_apps - Get applications")
    print("  3. get_regions - Get available regions")
    print("  4. get_nife_schema - Get GraphQL schema")
    print("  5. execute_nife_query - Execute custom query")
    print("  0. Exit")
    
    choice = input("\nSelect a tool to test (0-5): ").strip()
    
    if choice == "0":
        return
    
    tool_map = {
        "1": ("get_organizations", {}),
        "2": ("get_apps", {"first": 5}),
        "3": ("get_regions", {}),
        "4": ("get_nife_schema", {"simplified": True}),
        "5": ("execute_nife_query", {
            "query": "query { __typename }",
            "access_token": os.getenv("NIFE_ACCESS_TOKEN", "")
        })
    }
    
    if choice in tool_map:
        tool_name, args = tool_map[choice]
        
        # Add access token if available
        if "access_token" not in args and os.getenv("NIFE_ACCESS_TOKEN"):
            args["access_token"] = os.getenv("NIFE_ACCESS_TOKEN")
        
        print(f"\n🔄 Calling {tool_name}...")
        
        request = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args
            }
        }
        
        try:
            response = await server.handle_request(request)
            if not response or 'result' not in response:
                print(f"\n✗ Error: Invalid response")
                return
            
            content = response.get('result', {}).get('content', [])
            if not content:
                print(f"\n✗ Error: No content in response")
                return
            
            result_text = content[0].get('text', '{}')
            result_data = json.loads(result_text)
            
            print("\n✓ Result:")
            print(json.dumps(result_data, indent=2)[:1000])
            if len(json.dumps(result_data)) > 1000:
                print("\n... (truncated, full result is longer)")
                
        except Exception as e:
            print(f"\n✗ Error: {e}")

if __name__ == "__main__":
    async def main():
        server, tools = await test_mcp_connection()
        
        # Check if initialization was successful
        if server is None:
            print("\n⚠️  Server initialization failed")
            return
        
        # Check if we should do interactive testing
        if os.getenv("NIFE_ACCESS_TOKEN"):
            print("\n✓ NIFE_ACCESS_TOKEN found in environment")
            response = input("\nWould you like to test tools interactively? (y/n): ").strip().lower()
            if response == 'y':
                await interactive_test(server, tools)
        else:
            print("\n⚠️  NIFE_ACCESS_TOKEN not set")
            print("Set it to enable interactive tool testing:")
            print("  export NIFE_ACCESS_TOKEN='your_token'")
    
    asyncio.run(main())
