#!/bin/bash

# Nife MCP Server Launcher Script

echo "🚀 Starting Nife MCP Server..."
echo ""

# Check if we're in the right directory
if [ ! -f "test_endpoint.py" ]; then
    echo "❌ Error: Please run this script from the nife-mcp-server directory"
    exit 1
fi

# Get access token
if [ -z "$NIFE_ACCESS_TOKEN" ]; then
    echo "📋 Getting access token from nifectl..."
    export NIFE_ACCESS_TOKEN=$(nifectl auth token 2>/dev/null)
    
    if [ -z "$NIFE_ACCESS_TOKEN" ]; then
        echo "❌ Error: Could not get access token"
        echo "   Please run: nifectl auth login"
        echo "   Or set manually: export NIFE_ACCESS_TOKEN='your_token'"
        exit 1
    fi
    echo "✅ Access token obtained"
else
    echo "✅ Using existing NIFE_ACCESS_TOKEN"
fi

echo ""
echo "🔍 Testing endpoint..."
python test_endpoint.py

echo ""
echo "🎯 Starting MCP server..."
echo "   (Press Ctrl+C to stop)"
echo ""

python -m nife_mcp_server.intelligent_main
