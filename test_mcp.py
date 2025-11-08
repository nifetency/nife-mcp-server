#!/usr/bin/env python3
"""
Test script to interact with the NIFE MCP server
"""
import json
import subprocess
import sys

def send_mcp_request(request):
    """Send a request to the MCP server and get response"""
    try:
        # Run the MCP server with the request
        process = subprocess.Popen(
            [sys.executable, '-m', 'nife_mcp_server'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='/Users/rentsher/nife-mcp-server'
        )
        
        # Send the request
        stdout, stderr = process.communicate(input=json.dumps(request) + '\n', timeout=10)
        
        # Print stderr (logs)
        if stderr:
            print("=== Server Logs ===", file=sys.stderr)
            print(stderr, file=sys.stderr)
            print("=" * 50, file=sys.stderr)
        
        # Parse and return response
        if stdout.strip():
            return json.loads(stdout.strip())
        return None
        
    except subprocess.TimeoutExpired:
        process.kill()
        return {"error": "Request timeout"}
    except Exception as e:
        return {"error": str(e)}

def test_initialize():
    """Test initialize request"""
    print("1. Testing Initialize...")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }
    
    response = send_mcp_request(request)
    print(json.dumps(response, indent=2))
    return response

def test_list_tools():
    """Test listing available tools"""
    print("\n2. Testing List Tools...")
    
    # First initialize
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        }
    }
    
    list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    # Send both requests
    combined_input = json.dumps(init_request) + '\n' + json.dumps(list_request) + '\n'
    
    try:
        process = subprocess.Popen(
            [sys.executable, '-m', 'nife_mcp_server'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='/Users/rentsher/nife-mcp-server'
        )
        
        stdout, stderr = process.communicate(input=combined_input, timeout=10)
        
        if stderr:
            print("=== Server Logs ===", file=sys.stderr)
            print(stderr, file=sys.stderr)
        
        # Parse responses (should be two JSON objects)
        lines = [line.strip() for line in stdout.split('\n') if line.strip()]
        
        for i, line in enumerate(lines):
            print(f"\nResponse {i+1}:")
            try:
                response = json.loads(line)
                if 'result' in response and 'tools' in response.get('result', {}):
                    tools = response['result']['tools']
                    print(f"Found {len(tools)} tools:")
                    for tool in tools[:10]:  # Show first 10
                        print(f"  - {tool['name']}: {tool['description'][:60]}...")
                    if len(tools) > 10:
                        print(f"  ... and {len(tools) - 10} more tools")
                else:
                    print(json.dumps(response, indent=2))
            except json.JSONDecodeError:
                print(f"Invalid JSON: {line}")
                
    except Exception as e:
        print(f"Error: {e}")

def test_health_check():
    """Test health check tool"""
    print("\n3. Testing Health Check Tool...")
    
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "nife_health_check",
                "arguments": {}
            }
        }
    ]
    
    combined_input = '\n'.join(json.dumps(req) for req in requests) + '\n'
    
    try:
        process = subprocess.Popen(
            [sys.executable, '-m', 'nife_mcp_server'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='/Users/rentsher/nife-mcp-server'
        )
        
        stdout, stderr = process.communicate(input=combined_input, timeout=15)
        
        if stderr:
            print("=== Server Logs ===", file=sys.stderr)
            print(stderr, file=sys.stderr)
        
        lines = [line.strip() for line in stdout.split('\n') if line.strip()]
        
        for line in lines:
            try:
                response = json.loads(line)
                if 'result' in response and 'content' in response.get('result', {}):
                    content = response['result']['content'][0]['text']
                    health_data = json.loads(content)
                    print(json.dumps(health_data, indent=2))
                elif 'result' in response:
                    print(json.dumps(response, indent=2))
            except:
                pass
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("NIFE MCP Server Connection Test")
    print("=" * 60)
    
    test_initialize()
    test_list_tools()
    test_health_check()
    
    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60)
