#!/bin/bash
# Quick setup script for nife-mcp-server

set -e  # Exit on error

echo "=================================================="
echo "NIFE-MCP-SERVER QUICK SETUP"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Navigate to project directory
cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "Project directory: $PROJECT_DIR"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv .venv
    echo "${GREEN}✓ Virtual environment created${NC}"
else
    echo "${GREEN}✓ Virtual environment found${NC}"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt --quiet
echo "${GREEN}✓ Dependencies installed${NC}"

# Install package in development mode
echo ""
echo "Installing nife-mcp-server package..."
pip install -e . --quiet
echo "${GREEN}✓ Package installed${NC}"

# Run diagnostics
echo ""
echo "=================================================="
echo "RUNNING DIAGNOSTICS"
echo "=================================================="
python diagnose.py

# Check for NIFE_ACCESS_TOKEN
echo ""
echo "=================================================="
echo "CHECKING CONFIGURATION"
echo "=================================================="

if [ -z "$NIFE_ACCESS_TOKEN" ]; then
    echo ""
    echo "${YELLOW}⚠️  NIFE_ACCESS_TOKEN not set${NC}"
    echo ""
    echo "To set your Nife.io access token:"
    echo "  1. Login: nifectl auth login"
    echo "  2. Get token: nifectl auth token"
    echo "  3. Set it: export NIFE_ACCESS_TOKEN='your_token'"
    echo ""
    echo "Or add to ~/.bashrc or ~/.zshrc:"
    echo "  echo \"export NIFE_ACCESS_TOKEN='your_token'\" >> ~/.bashrc"
    echo ""
else
    echo "${GREEN}✓ NIFE_ACCESS_TOKEN is set${NC}"
fi

# Summary
echo ""
echo "=================================================="
echo "SETUP COMPLETE!"
echo "=================================================="
echo ""
echo "You can now run the server:"
echo ""
echo "  ${GREEN}# For Claude Desktop (MCP mode)${NC}"
echo "  python start.py --mode mcp"
echo ""
echo "  ${GREEN}# For HTTP REST API (Flask mode)${NC}"
echo "  python start.py --mode flask"
echo ""
echo "  ${GREEN}# With debug/verbose options${NC}"
echo "  python start.py --mode flask --debug"
echo "  python start.py --mode mcp --verbose"
echo ""
echo "Quick test:"
echo "  ${GREEN}# Start Flask server${NC}"
echo "  python start.py --mode flask &"
echo ""
echo "  ${GREEN}# Test health endpoint${NC}"
echo "  curl http://localhost:5000/api/mcp/health"
echo ""
echo "For troubleshooting, see: ${YELLOW}TROUBLESHOOTING.md${NC}"
echo "For detailed fixes, see: ${YELLOW}FIXES.md${NC}"
echo ""
echo "=================================================="
