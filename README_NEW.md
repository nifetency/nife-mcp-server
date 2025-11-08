# Nife.io MCP Server - UPDATED SETUP GUIDE

## 🚀 Quick Start (One Command!)

```bash
cd /Users/rentsher/nife-mcp-server
chmod +x setup.sh
./setup.sh
```

This will:
- ✓ Create/activate virtual environment
- ✓ Install all dependencies
- ✓ Install the package
- ✓ Run diagnostics
- ✓ Show next steps

## 📋 What Was Fixed

The server had several issues preventing it from running:

1. **Package not installed** - Now installs with `pip install -e .`
2. **Unclear startup** - New `start.py` script handles both modes
3. **Missing diagnostics** - New `diagnose.py` checks everything
4. **Poor documentation** - Added TROUBLESHOOTING.md and FIXES.md

## 🎯 Two Ways to Use This Server

### Mode 1: MCP Server (for Claude Desktop)

The MCP server communicates via stdin/stdout using JSON-RPC protocol.

**Start the server:**
```bash
python start.py --mode mcp
```

**Configure Claude Desktop:**

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nife": {
      "command": "/Users/rentsher/nife-mcp-server/.venv/bin/python",
      "args": [
        "/Users/rentsher/nife-mcp-server/start.py",
        "--mode",
        "mcp"
      ],
      "env": {
        "NIFE_ACCESS_TOKEN": "your_nife_token_here"
      }
    }
  }
}
```

**Restart Claude Desktop** to load the MCP server.

### Mode 2: Flask HTTP Server (for Testing/API)

The Flask server provides REST API endpoints for testing and integration.

**Start the server:**
```bash
python start.py --mode flask
```

**Test it:**
```bash
# Health check
curl http://localhost:5000/api/mcp/health

# Get schema (no auth needed)
curl http://localhost:5000/api/mcp/schema

# Custom query (requires auth)
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"query": "query { __typename }"}'
```

## 🔧 Installation Steps (Manual)

If `setup.sh` doesn't work, follow these steps:

### 1. Activate Virtual Environment
```bash
cd /Users/rentsher/nife-mcp-server
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Install Package
```bash
pip install -e .
```

### 4. Run Diagnostics
```bash
python diagnose.py
```

You should see all green checkmarks (✓). If not, see TROUBLESHOOTING.md.

### 5. Get Nife.io Access Token
```bash
# Login to Nife.io
nifectl auth login

# Get your access token
nifectl auth token

# Copy the token and set it
export NIFE_ACCESS_TOKEN='paste_your_token_here'

# Verify
echo $NIFE_ACCESS_TOKEN
```

### 6. Start the Server
```bash
# For MCP mode (Claude Desktop)
python start.py --mode mcp --verbose

# For Flask mode (HTTP API)
python start.py --mode flask --debug
```

## 📚 Available Tools (45+ Operations)

The MCP server provides comprehensive tools for Nife.io management:

### Query Operations
- `get_apps` - List applications with filtering
- `get_app` - Get specific application details
- `get_organizations` - List organizations
- `get_users` - List users
- `get_regions` - Available deployment regions
- `get_builds` - Application builds
- `get_releases` - Application releases
- `get_volumes` - Storage volumes
- `get_certificates` - SSL certificates
- `get_secrets` - Application secrets
- `get_platform_stats` - Platform statistics

### Mutation Operations
- `create_app` - Create new application
- `deploy_app` - Deploy application
- `scale_app` - Scale instances
- `restart_app` - Restart application
- `set_secret` - Set application secret
- `add_certificate` - Add SSL certificate
- `create_volume` - Create storage volume
- And many more...

### Legacy/Utility
- `get_nife_context` - Get model context
- `get_nife_schema` - Get GraphQL schema
- `execute_nife_query` - Execute custom query
- `nife_health_check` - Health check

## 🧪 Testing

### Test Flask Mode
```bash
# Terminal 1: Start server
python start.py --mode flask --debug

# Terminal 2: Test endpoints
curl http://localhost:5000/api/mcp/health
curl http://localhost:5000/api/mcp/schema
```

### Test MCP Mode
```bash
# Start with verbose logging
python start.py --mode mcp --verbose

# The server will wait for stdin (JSON-RPC messages)
# This is what Claude Desktop sends to it
```

## 🐛 Troubleshooting

If something doesn't work:

1. **Run diagnostics first:**
   ```bash
   python diagnose.py
   ```

2. **Check the guides:**
   - `TROUBLESHOOTING.md` - Common issues and solutions
   - `FIXES.md` - What was wrong and how it was fixed

3. **Common issues:**

   **"Module not found"**
   ```bash
   source .venv/bin/activate
   pip install -e .
   ```

   **"Port already in use"**
   ```bash
   lsof -ti:5000 | xargs kill -9
   ```

   **"Authentication required"**
   ```bash
   export NIFE_ACCESS_TOKEN='your_token'
   ```

## 📖 API Endpoints (Flask Mode)

### GET /api/mcp/health
Health check endpoint
```bash
curl http://localhost:5000/api/mcp/health
```

### GET /api/mcp/schema
Get GraphQL schema
```bash
curl http://localhost:5000/api/mcp/schema?simplified=true
```

### GET /api/mcp/context
Get model context
```bash
curl http://localhost:5000/api/mcp/context?type=organizations&limit=10
```

### POST /api/mcp/query
Execute custom GraphQL query (requires auth)
```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "query": "query { apps { nodes { id name } } }",
    "variables": {},
    "timeout": 30
  }'
```

## 🛠️ Development

### Project Structure
```
nife-mcp-server/
├── src/nife_mcp_server/
│   ├── __init__.py
│   ├── __main__.py         # MCP entry point
│   ├── main.py             # MCP server implementation
│   ├── app.py              # Flask server implementation
│   ├── routes/
│   │   ├── mcp.py          # GraphQL client & routes
│   │   └── user.py         # User routes (template)
│   ├── models/             # Database models
│   ├── database/           # SQLite database
│   └── static/             # Static files
├── .venv/                  # Virtual environment
├── start.py                # 🆕 Unified startup script
├── diagnose.py             # 🆕 Diagnostic tool
├── setup.sh                # 🆕 Quick setup script
├── TROUBLESHOOTING.md      # 🆕 Troubleshooting guide
├── FIXES.md                # 🆕 What was fixed
├── requirements.txt        # Dependencies
├── pyproject.toml          # Package config
└── README.md               # This file
```

### Making Changes

1. **Edit the code**
2. **No need to reinstall** (installed with `-e` flag)
3. **Restart the server** to see changes
4. **Test both modes** (MCP and Flask)

## 🔒 Security

- **Never commit tokens to git**
- Use environment variables for NIFE_ACCESS_TOKEN
- The Flask server has CORS enabled (be cautious in production)
- Authentication required for mutation endpoints

## 📦 Dependencies

Core dependencies:
- `flask` - HTTP web framework
- `mcp` - Model Context Protocol library
- `httpx` - Async HTTP client (for MCP)
- `requests` - HTTP client (for Flask)
- `flask-sqlalchemy` - Database ORM
- `flask-cors` - Cross-origin resource sharing

## 🤝 Support

For issues:
1. Check `TROUBLESHOOTING.md`
2. Run `python diagnose.py`
3. Check logs in `server.log`
4. See `FIXES.md` for common problems

## 📝 License

MIT License - See LICENSE file

---

## Quick Reference Card

```bash
# Setup (one time)
./setup.sh

# Activate environment
source .venv/bin/activate

# Set token
export NIFE_ACCESS_TOKEN='your_token'

# Start MCP mode (for Claude)
python start.py --mode mcp

# Start Flask mode (for testing)
python start.py --mode flask

# Test Flask server
curl http://localhost:5000/api/mcp/health

# Run diagnostics
python diagnose.py

# View available tools
python -c "from nife_mcp_server.main import NifeMCPServer; s=NifeMCPServer(); print(f'{len(s.tools)} tools available')"
```

**Everything should now work! 🎉**
