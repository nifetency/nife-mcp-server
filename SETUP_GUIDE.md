# NIFE MCP Server - Quick Setup Guide

## Automatic Setup (Recommended)

Run the setup script:

```bash
cd /Users/rentsher/nife-mcp-server
chmod +x setup_claude_desktop.sh
./setup_claude_desktop.sh
```

The script will:
- ✅ Create Claude Desktop config directory
- ✅ Get your NIFE access token (or prompt you)
- ✅ Backup existing config
- ✅ Create/merge MCP configuration
- ✅ Test the MCP server
- ✅ Show next steps

## Manual Setup

If you prefer to set up manually:

1. **Get your NIFE token:**
   ```bash
   nifectl auth login
   nifectl auth token
   ```

2. **Create config directory:**
   ```bash
   mkdir -p ~/Library/Application\ Support/Claude
   ```

3. **Create/edit config file:**
   ```bash
   nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

4. **Add this configuration:**
   ```json
   {
     "mcpServers": {
       "nife": {
         "command": "/Users/rentsher/nife-mcp-server/.venv/bin/python",
         "args": ["-m", "nife_mcp_server"],
         "env": {
           "NIFE_ACCESS_TOKEN": "your_token_here"
         }
       }
     }
   }
   ```

5. **Restart Claude Desktop**

## Testing

Test the MCP server before connecting:

```bash
cd /Users/rentsher/nife-mcp-server
source .venv/bin/activate
python interactive_test.py
```

## Verification

After restart, you should see in Claude Desktop:
- 🔨 Tool/hammer icon
- 50+ NIFE tools available
- Tools like: get_apps, deploy_app, get_organizations, etc.

## Available Tools

### Query Tools (Read operations):
- `get_apps` - Get applications with filtering
- `get_app` - Get specific application
- `get_organizations` - Get all organizations
- `get_users` - Get users
- `get_regions` - Get available regions
- `get_builds` - Get application builds
- `get_releases` - Get releases
- `get_volumes` - Get storage volumes
- `get_certificates` - Get SSL certificates
- `get_secrets` - Get application secrets
- `get_platform_stats` - Get platform statistics

### Mutation Tools (Write operations):
- `create_app` - Create new application
- `deploy_app` - Deploy application
- `scale_app` - Scale instances
- `restart_app` - Restart application
- `set_secret` - Set secrets
- `add_certificate` - Add SSL certificate
- `create_volume` - Create storage volume
- And 20+ more...

### Legacy Tools:
- `get_nife_context` - Get model context
- `execute_nife_query` - Execute custom GraphQL
- `nife_health_check` - Check API health

## Troubleshooting

### MCP tools not appearing?
1. Check config file exists:
   ```bash
   cat ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. Verify Python path:
   ```bash
   ls -la /Users/rentsher/nife-mcp-server/.venv/bin/python
   ```

3. Test MCP server:
   ```bash
   cd /Users/rentsher/nife-mcp-server
   source .venv/bin/activate
   python interactive_test.py
   ```

4. Check Claude Desktop logs (if available)

### Token issues?
Get a fresh token:
```bash
nifectl auth login
nifectl auth token
```

Then update the config file with the new token.

## Example Usage in Claude Desktop

Once connected, you can ask Claude:

- "List all my NIFE applications"
  → Uses `get_apps` tool

- "Show me organizations"
  → Uses `get_organizations` tool

- "Deploy my app"
  → Uses `deploy_app` tool

- "Get platform statistics"
  → Uses `get_platform_stats` tool

## Configuration File Location

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Linux:** `~/.config/Claude/claude_desktop_config.json`

## Support

For issues:
1. Run: `python interactive_test.py` to test locally
2. Check MCP server logs (stderr output)
3. Verify NIFE access token is valid
4. Ensure Claude Desktop is completely restarted

## Notes

- MCP only works with Claude Desktop (not web interface)
- Requires valid NIFE access token
- Token needs appropriate permissions for the operations you want to perform
- Server automatically retries failed requests
- Includes fallback queries for robust operation
