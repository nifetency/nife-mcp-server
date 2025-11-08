#!/usr/bin/env python3
"""Diagnostic script to identify nife-mcp-server issues"""

import sys
import os

print("=" * 60)
print("NIFE-MCP-SERVER DIAGNOSTICS")
print("=" * 60)

# 1. Check Python version
print(f"\n1. Python Version: {sys.version}")
print(f"   Python Executable: {sys.executable}")

# 2. Check if we're in virtual environment
in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
print(f"\n2. Virtual Environment: {'Yes' if in_venv else 'No'}")
if in_venv:
    print(f"   VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV', 'Not set')}")

# 3. Check critical imports
print("\n3. Checking Dependencies:")
critical_modules = [
    'flask', 'flask_cors', 'flask_sqlalchemy', 'requests', 
    'mcp', 'httpx', 'asyncio'
]

missing_modules = []
for module in critical_modules:
    try:
        __import__(module)
        print(f"   ✓ {module}")
    except ImportError as e:
        print(f"   ✗ {module} - {e}")
        missing_modules.append(module)

# 4. Check if src structure is accessible
print("\n4. Project Structure:")
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
nife_mcp_path = os.path.join(src_path, 'nife_mcp_server')

print(f"   Project Root: {project_root}")
print(f"   Src Path Exists: {os.path.exists(src_path)}")
print(f"   nife_mcp_server Exists: {os.path.exists(nife_mcp_path)}")

if os.path.exists(nife_mcp_path):
    key_files = ['__init__.py', '__main__.py', 'main.py', 'app.py']
    for file in key_files:
        file_path = os.path.join(nife_mcp_path, file)
        print(f"   - {file}: {'✓' if os.path.exists(file_path) else '✗'}")

# 5. Try importing the package
print("\n5. Package Import Test:")
sys.path.insert(0, src_path)
try:
    import nife_mcp_server
    print(f"   ✓ nife_mcp_server imported successfully")
    print(f"   Package location: {nife_mcp_server.__file__}")
except ImportError as e:
    print(f"   ✗ Failed to import nife_mcp_server: {e}")

# 6. Try importing main components
print("\n6. Component Import Tests:")
components = [
    ('nife_mcp_server.main', 'NifeMCPServer'),
    ('nife_mcp_server.app', 'app'),
    ('nife_mcp_server.routes.mcp', 'NifeGraphQLClient')
]

for module_name, component in components:
    try:
        module = __import__(module_name, fromlist=[component])
        obj = getattr(module, component)
        print(f"   ✓ {module_name}.{component}")
    except Exception as e:
        print(f"   ✗ {module_name}.{component} - {e}")

# 7. Check environment variables
print("\n7. Environment Variables:")
env_vars = ['NIFE_ACCESS_TOKEN', 'FLASK_APP', 'FLASK_ENV']
for var in env_vars:
    value = os.environ.get(var)
    if value:
        print(f"   {var}: {'*' * 10} (set)")
    else:
        print(f"   {var}: (not set)")

# 8. Check database
print("\n8. Database Check:")
db_path = os.path.join(nife_mcp_path, 'database', 'app.db')
print(f"   Database Path: {db_path}")
print(f"   Database Exists: {os.path.exists(db_path)}")

# 9. Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

if missing_modules:
    print(f"\n⚠️  Missing {len(missing_modules)} module(s): {', '.join(missing_modules)}")
    print("   Run: pip install -r requirements.txt")
else:
    print("\n✓ All dependencies installed")

print("\n" + "=" * 60)
print("RECOMMENDED ACTIONS:")
print("=" * 60)

if missing_modules:
    print("1. Install missing dependencies:")
    print("   pip install -r requirements.txt")

print("\n2. For MCP Server (stdin/stdout):")
print("   python -m nife_mcp_server")
print("   or")
print("   python src/nife_mcp_server/main.py")

print("\n3. For Flask REST API:")
print("   python src/nife_mcp_server/app.py")
print("   or")
print("   flask --app src/nife_mcp_server/app.py run --host 0.0.0.0 --port 5000")

print("\n4. Set environment variable:")
print("   export NIFE_ACCESS_TOKEN='your_token_here'")

print("\n" + "=" * 60)
