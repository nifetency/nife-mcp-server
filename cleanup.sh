#!/bin/bash
# Script to clean up non-required files from nife-mcp-server

echo "🧹 Cleaning up non-required files..."
echo ""

# Legacy implementation files
echo "Removing legacy implementation files..."
rm -f src/nife_mcp_server/main.py
rm -f src/nife_mcp_server/app.py

# Models and unused routes
echo "Removing unused models and routes..."
rm -rf src/nife_mcp_server/models/
rm -f src/nife_mcp_server/routes/user.py

# Database
echo "Removing database files..."
rm -rf src/nife_mcp_server/database/

# Static files
echo "Removing static files..."
rm -rf src/nife_mcp_server/static/

# Test files
echo "Removing test files..."
rm -f test_*.py
rm -f interactive_test.py
rm -f diagnose.py
rm -f check_api_schema.py
rm -f start.py

# Documentation (keeping README.md only)
echo "Removing extra documentation..."
rm -f README_NEW.md
rm -f USAGE_EXAMPLES.md
rm -f SETUP_GUIDE.md
rm -f IMPLEMENTATION_STATUS.md
rm -f Usage_guide.md

# Shell scripts
echo "Removing shell scripts..."
rm -f setup.sh
rm -f setup_claude_desktop.sh
rm -f run_test.sh

# Build artifacts
echo "Removing build artifacts..."
rm -rf dist/
rm -rf build/
rm -rf *.egg-info
rm -rf src/nife_mcp_server.egg-info
rm -rf src/nife_mcp_server/nife_mcp_server.egg-info
rm -rf nife_mcp_server.egg-info

# Logs
echo "Removing logs..."
rm -f server.log
rm -f *.log

# Cache directories
echo "Removing cache directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete
find . -name ".DS_Store" -delete

# Docker file (if not needed)
echo "Removing Docker files..."
rm -f Dockerfile

# Claude desktop config (user-specific)
echo "Removing user-specific config..."
rm -f claude_desktop_config.json

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📦 Remaining required files:"
echo "   - pyproject.toml"
echo "   - requirements.txt"
echo "   - README.md"
echo "   - src/nife_mcp_server/__init__.py"
echo "   - src/nife_mcp_server/__main__.py"
echo "   - src/nife_mcp_server/intelligent_main.py"
echo "   - src/nife_mcp_server/schema_manager.py"
echo "   - src/nife_mcp_server/routes/mcp.py"
echo ""
