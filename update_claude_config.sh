#!/bin/bash

# One-line Claude Desktop Config Updater for Nife MCP Server

echo "🔧 Updating Claude Desktop config for Nife MCP Server..."

# Get the token
echo "📋 Getting access token..."
TOKEN=$(nifectl auth token 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Error: Could not get access token"
    echo "   Please run: nifectl auth login"
    exit 1
fi

echo "✅ Token obtained"

# Create config directory if it doesn't exist
mkdir -p ~/Library/Application\ Support/Claude

# Write the config
cat > ~/Library/Application\ Support/Claude/claude_desktop_config.json << EOF
{
  "mcpServers": {
    "nife": {
      "command": "python",
      "args": ["-m", "nife_mcp_server.intelligent_main"],
      "cwd": "/Users/rentsher/nife-mcp-server",
      "env": {
        "NIFE_ACCESS_TOKEN": "$TOKEN"
      }
    }
  }
}
EOF

echo "✅ Config updated successfully!"
echo ""
echo "📍 Config location: ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "🔄 Next steps:"
echo "   1. Quit Claude Desktop completely (Cmd+Q)"
echo "   2. Reopen Claude Desktop"
echo "   3. Ask Claude: 'What Nife.io tools are available?'"
echo ""
echo "✨ Done!"
