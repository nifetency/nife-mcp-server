#!/bin/bash

echo "=== Nife MCP Server Installation Diagnostics ==="
echo

echo "1. Checking installed packages..."
pip list | grep nife
echo

echo "2. Package details..."
pip show nife-mcp-server
echo

echo "3. Testing Python imports..."
python -c "
try:
    import nife_mcp_server
    print('✓ nife_mcp_server imported successfully')
    print(f'Location: {nife_mcp_server.__file__}')
except ImportError as e:
    print(f'✗ Failed to import nife_mcp_server: {e}')

try:
    import nife_mcp_server.server
    print('✓ nife_mcp_server.server imported successfully')
except ImportError as e:
    print(f'✗ Failed to import nife_mcp_server.server: {e}')

try:
    from nife_mcp_server import main
    print('✓ main function imported successfully')
except ImportError as e:
    print(f'✗ Failed to import main: {e}')
"
echo

echo "4. Checking for CLI command..."
echo -n "nife-mcp-server location: "
which nife-mcp-server || echo "Not found in PATH"
echo

echo "5. Python environment info..."
python -c "
import sys
import site
print('Python executable:', sys.executable)
print('Site packages:', site.getsitepackages())
"
echo

echo "6. Package file listing..."
python -c "
import pkg_resources
try:
    dist = pkg_resources.get_distribution('nife-mcp-server')
    print(f'Package location: {dist.location}')
    files = list(dist._get_metadata('RECORD'))
    print(f'Package files ({len(files)} total):')
    for f in files[:10]:  # Show first 10 files
        print(f'  {f.strip()}')
    if len(files) > 10:
        print(f'  ... and {len(files) - 10} more files')
except Exception as e:
    print(f'Error getting package info: {e}')
"

echo
echo "=== Diagnostics Complete ==="
