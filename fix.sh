#!/bin/bash

echo "=== Fixing Nife MCP Server Installation ==="
echo

echo "1. Checking current directory structure..."
echo "Current directory: $(pwd)"
ls -la
echo

echo "2. Looking for Python module files..."
find . -name "*.py" -type f | head -20
echo

echo "3. Checking for __init__.py files..."
find . -name "__init__.py" -type f
echo

echo "4. Testing the CLI command..."
echo "CLI command location: $(which nife-mcp-server)"
nife-mcp-server --help || echo "CLI command failed"
echo

echo "5. Checking package structure expectations..."
echo "Expected module location for imports:"
python -c "
import sys
print('Python path:')
for p in sys.path:
    print(f'  {p}')

# Check if there should be a nife_mcp_server directory
import os
expected_locations = [
    './nife_mcp_server',
    './src/nife_mcp_server', 
    './nife-mcp-server',
    './src/nife-mcp-server'
]

for loc in expected_locations:
    if os.path.exists(loc):
        print(f'Found directory: {loc}')
        print(f'Contents: {os.listdir(loc)}')
    else:
        print(f'Not found: {loc}')
"
echo

echo "6. Checking pyproject.toml or setup.py for module configuration..."
if [ -f "pyproject.toml" ]; then
    echo "Found pyproject.toml:"
    cat pyproject.toml
elif [ -f "setup.py" ]; then
    echo "Found setup.py:"
    cat setup.py
else
    echo "No pyproject.toml or setup.py found"
fi
echo

echo "=== Investigation Complete ==="

echo
echo "7. Suggested fixes based on findings:"
echo "   - Create missing __init__.py files"
echo "   - Fix module structure"
echo "   - Reinstall in development mode"
