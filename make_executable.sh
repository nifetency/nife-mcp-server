#!/bin/bash
# Quick setup script to make all scripts executable

chmod +x release.sh
chmod +x RELEASE_SUMMARY.sh
chmod +x run_server.sh
chmod +x update_claude_config.sh
chmod +x cleanup.sh
chmod +x bin/nife-mcp-server
chmod +x bin/nife-mcp-server.js

echo "✅ All scripts are now executable"
echo ""
echo "Available commands:"
echo "  ./RELEASE_SUMMARY.sh - Quick release status"
echo "  ./release.sh - Automated release wizard"
echo "  ./run_server.sh - Start the MCP server"
echo "  ./update_claude_config.sh - Update Claude Desktop config"
