# 🚀 Quick Start: Fixing and Running Nife MCP Server

## The Problem

You're facing two issues:
1. ❌ `https://api.nife.io/graphql` is not accessible
2. ❓ You don't know how to access the GraphQL playground
3. ❓ You're unsure how to execute the server

## The Solution (3 Steps)

### Step 1: Find the Correct Endpoint 🔍

Run the endpoint test script:

```bash
cd /Users/rentsher/nife-mcp-server

# Set your access token first
export NIFE_ACCESS_TOKEN="your_token_here"

# Or get it from Nife CLI
export NIFE_ACCESS_TOKEN=$(nifectl auth token)

# Test all possible endpoints
python test_endpoint.py
```

This will test multiple endpoints and tell you which one works.

### Step 2: Update the Endpoint (if needed) ⚙️

If the test script found a different working endpoint, update it:

**Option A: Use the configurator script (easiest)**
```bash
python configure_endpoint.py https://correct-endpoint-here
```

**Option B: Manual update**
Edit these two files:
- `src/nife_mcp_server/schema_manager.py` (line 18)
- `src/nife_mcp_server/routes/mcp.py` (line 16)

### Step 3: Run the Server 🎯

```bash
# Make sure your token is set
export NIFE_ACCESS_TOKEN="your_token"

# Run the intelligent MCP server
python -m nife_mcp_server.intelligent_main
```

The server will:
- Load the GraphQL schema automatically
- Generate tools from the schema
- Listen for MCP protocol messages on stdin/stdout

---

## How to Access GraphQL Playground

### Option 1: Browser-Based Playground
Try opening these URLs in your browser:
- `https://api.nife.io/graphql`
- `https://api.nife.io/playground`
- `https://playground.nife.io`

### Option 2: Use a GraphQL Client
Download and use one of these:
- **Altair GraphQL Client** (Recommended): https://altair.sirmuel.design/
- **Insomnia**: https://insomnia.rest/
- **Postman**: https://www.postman.com/

Configure them with:
- **Endpoint**: `https://api.nife.io/graphql` (or the working one from Step 1)
- **Header**: `Authorization: Bearer YOUR_TOKEN`

### Option 3: Test with curl
```bash
curl -X POST https://api.nife.io/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $NIFE_ACCESS_TOKEN" \
  -d '{"query": "{ __typename }"}'
```

---

## Files Created for You

I've created three helpful scripts:

### 1. `test_endpoint.py`
Tests multiple possible GraphQL endpoints to find the working one.

**Usage:**
```bash
python test_endpoint.py
```

### 2. `configure_endpoint.py`
Updates the endpoint across all files in the codebase.

**Usage:**
```bash
python configure_endpoint.py https://new-endpoint-here
```

### 3. `ENDPOINT_GUIDE.md`
Comprehensive guide with troubleshooting and detailed instructions.

**Usage:**
```bash
cat ENDPOINT_GUIDE.md
```

---

## Troubleshooting

### "Connection Error"
- ✅ Check internet connection
- ✅ Verify endpoint URL
- ✅ Try accessing api.nife.io in browser

### "401 Unauthorized"
- ✅ Get new token: `nifectl auth token`
- ✅ Set token: `export NIFE_ACCESS_TOKEN="token"`
- ✅ Verify: `echo $NIFE_ACCESS_TOKEN`

### "GraphQL errors"
- ✅ Check query syntax
- ✅ Verify permissions
- ✅ Read Nife.io API documentation

### Still Not Working?
Contact Nife.io support and ask for:
- The correct GraphQL API endpoint
- Authentication requirements
- GraphQL Playground URL (if available)

---

## Complete Example Workflow

```bash
# 1. Navigate to project
cd /Users/rentsher/nife-mcp-server

# 2. Get your access token
export NIFE_ACCESS_TOKEN=$(nifectl auth token)

# 3. Test the endpoint
python test_endpoint.py

# 4. If needed, update endpoint (example)
# python configure_endpoint.py https://api.nife.io/v1/graphql

# 5. Run the server
python -m nife_mcp_server.intelligent_main
```

---

## What Happens When You Run the Server?

1. ✅ Loads GraphQL schema from Nife.io API
2. ✅ Analyzes all queries and mutations
3. ✅ Generates MCP tools dynamically
4. ✅ Waits for MCP client (like Claude Desktop) to connect
5. ✅ Processes tool calls and returns results

---

## Next Steps After Server is Running

1. Connect Claude Desktop to the MCP server
2. Ask Claude to list available Nife.io operations
3. Use Claude to query and manage your Nife.io resources

Example prompts:
- "List all available Nife.io queries"
- "Show me information about my applications"
- "Get the schema information for Nife.io"

---

## Need Help?

Check these resources:
1. `ENDPOINT_GUIDE.md` - Detailed endpoint configuration guide
2. `README.md` - Project documentation
3. Nife.io documentation - https://docs.nife.io
4. MCP documentation - https://modelcontextprotocol.io

Good luck! 🚀
