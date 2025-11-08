#!/bin/bash
# Setup script for connecting NIFE MCP Server to Claude Desktop

set -e

echo "============================================================"
echo "NIFE MCP Server - Claude Desktop Setup"
echo "============================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
VENV_PYTHON="/Users/rentsher/nife-mcp-server/.venv/bin/python"

echo ""
echo "Step 1: Checking Claude Desktop configuration directory..."
if [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
    echo -e "${YELLOW}Creating Claude config directory...${NC}"
    mkdir -p "$CLAUDE_CONFIG_DIR"
    echo -e "${GREEN}✓ Created: $CLAUDE_CONFIG_DIR${NC}"
else
    echo -e "${GREEN}✓ Directory exists: $CLAUDE_CONFIG_DIR${NC}"
fi

echo ""
echo "Step 2: Checking for NIFE access token..."
if [ -z "$NIFE_ACCESS_TOKEN" ]; then
    echo -e "${YELLOW}⚠️  NIFE_ACCESS_TOKEN not set in environment${NC}"
    echo ""
    echo "Please get your access token:"
    echo "  1. Run: nifectl auth login"
    echo "  2. Run: nifectl auth token"
    echo ""
    read -p "Enter your NIFE access token: " USER_TOKEN
    
    if [ -z "$USER_TOKEN" ]; then
        echo -e "${RED}✗ No token provided. Exiting.${NC}"
        exit 1
    fi
    NIFE_ACCESS_TOKEN="$USER_TOKEN"
else
    echo -e "${GREEN}✓ Found NIFE_ACCESS_TOKEN in environment${NC}"
fi

echo ""
echo "Step 3: Backing up existing config (if any)..."
if [ -f "$CLAUDE_CONFIG_FILE" ]; then
    BACKUP_FILE="${CLAUDE_CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CLAUDE_CONFIG_FILE" "$BACKUP_FILE"
    echo -e "${GREEN}✓ Backed up to: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}No existing config found${NC}"
fi

echo ""
echo "Step 4: Creating Claude Desktop configuration..."

# Check if config exists and has content
if [ -f "$CLAUDE_CONFIG_FILE" ] && [ -s "$CLAUDE_CONFIG_FILE" ]; then
    # Config exists, try to merge
    echo -e "${YELLOW}Existing config found, will attempt to merge...${NC}"
    
    # Read existing config
    EXISTING_CONFIG=$(cat "$CLAUDE_CONFIG_FILE")
    
    # Check if it's valid JSON
    if echo "$EXISTING_CONFIG" | python3 -m json.tool > /dev/null 2>&1; then
        # Valid JSON, merge with Python
        python3 << EOF
import json
import sys

try:
    with open("$CLAUDE_CONFIG_FILE", "r") as f:
        config = json.load(f)
    
    # Ensure mcpServers exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    # Add or update nife server
    config["mcpServers"]["nife"] = {
        "command": "$VENV_PYTHON",
        "args": ["-m", "nife_mcp_server"],
        "env": {
            "NIFE_ACCESS_TOKEN": "$NIFE_ACCESS_TOKEN"
        }
    }
    
    # Write back
    with open("$CLAUDE_CONFIG_FILE", "w") as f:
        json.dump(config, f, indent=2)
    
    print("✓ Merged NIFE MCP server into existing config")
    sys.exit(0)
    
except Exception as e:
    print(f"✗ Error merging config: {e}")
    sys.exit(1)
EOF
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Successfully merged configuration${NC}"
        else
            echo -e "${RED}✗ Failed to merge, creating new config...${NC}"
            CREATE_NEW=true
        fi
    else
        echo -e "${RED}✗ Existing config is not valid JSON, creating new...${NC}"
        CREATE_NEW=true
    fi
else
    CREATE_NEW=true
fi

# Create new config if needed
if [ "$CREATE_NEW" = true ]; then
    cat > "$CLAUDE_CONFIG_FILE" << EOF
{
  "mcpServers": {
    "nife": {
      "command": "$VENV_PYTHON",
      "args": [
        "-m",
        "nife_mcp_server"
      ],
      "env": {
        "NIFE_ACCESS_TOKEN": "$NIFE_ACCESS_TOKEN"
      }
    }
  }
}
EOF
    echo -e "${GREEN}✓ Created new configuration${NC}"
fi

echo ""
echo "Step 5: Validating configuration..."
if python3 -m json.tool "$CLAUDE_CONFIG_FILE" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Configuration is valid JSON${NC}"
else
    echo -e "${RED}✗ Configuration has JSON syntax errors${NC}"
    exit 1
fi

echo ""
echo "Step 6: Verifying Python environment..."
if [ -f "$VENV_PYTHON" ]; then
    echo -e "${GREEN}✓ Virtual environment found: $VENV_PYTHON${NC}"
    
    # Check if nife_mcp_server is installed
    if "$VENV_PYTHON" -c "import nife_mcp_server" 2>/dev/null; then
        echo -e "${GREEN}✓ nife_mcp_server module is installed${NC}"
    else
        echo -e "${YELLOW}⚠️  nife_mcp_server not found, installing...${NC}"
        cd /Users/rentsher/nife-mcp-server
        source .venv/bin/activate
        pip install -e . > /dev/null 2>&1
        echo -e "${GREEN}✓ Installed nife_mcp_server${NC}"
    fi
else
    echo -e "${RED}✗ Virtual environment not found: $VENV_PYTHON${NC}"
    exit 1
fi

echo ""
echo "Step 7: Testing MCP server..."
echo "Running quick test..."

TEST_RESULT=$("$VENV_PYTHON" << 'PYTHON_SCRIPT'
import sys
import json
sys.path.insert(0, '/Users/rentsher/nife-mcp-server/src')

try:
    from nife_mcp_server.main import NifeMCPServer
    import asyncio
    
    async def test():
        server = NifeMCPServer()
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }
        response = await server.handle_request(request)
        return response.get('result', {}).get('serverInfo', {}).get('name') == 'nife-mcp-server'
    
    result = asyncio.run(test())
    print("SUCCESS" if result else "FAILED")
    
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
PYTHON_SCRIPT
)

if [[ "$TEST_RESULT" == *"SUCCESS"* ]]; then
    echo -e "${GREEN}✓ MCP server test passed${NC}"
else
    echo -e "${RED}✗ MCP server test failed: $TEST_RESULT${NC}"
    echo "The server may still work, but there might be issues."
fi

echo ""
echo "============================================================"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo "============================================================"
echo ""
echo "📝 Configuration saved to:"
echo "   $CLAUDE_CONFIG_FILE"
echo ""
echo "🔄 Next steps:"
echo "   1. Quit Claude Desktop completely (Cmd+Q)"
echo "   2. Restart Claude Desktop"
echo "   3. Look for the hammer/tool icon (🔨) in the interface"
echo "   4. You should see 50+ NIFE tools available!"
echo ""
echo "🔧 Available tools include:"
echo "   • get_apps - List all applications"
echo "   • get_organizations - List organizations"
echo "   • deploy_app - Deploy applications"
echo "   • scale_app - Scale application instances"
echo "   • set_secret - Manage secrets"
echo "   • And 45+ more tools!"
echo ""
echo "📖 To view your configuration:"
echo "   cat '$CLAUDE_CONFIG_FILE'"
echo ""
echo "🧪 To test the server manually:"
echo "   cd /Users/rentsher/nife-mcp-server"
echo "   source .venv/bin/activate"
echo "   python interactive_test.py"
echo ""
echo "============================================================"
