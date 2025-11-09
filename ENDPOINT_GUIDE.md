# Nife.io GraphQL Endpoint Configuration Guide

## Quick Test

Run this command to test the endpoint:

```bash
cd /Users/rentsher/nife-mcp-server
python test_endpoint.py
```

## How to Find the Correct GraphQL Endpoint

### Method 1: Use Nife CLI

```bash
# Login to Nife
nifectl auth login

# Get your access token
nifectl auth token

# Check API configuration
nifectl config show
```

### Method 2: Check Nife Documentation

Visit the Nife.io documentation or developer portal to find:
- GraphQL API endpoint URL
- Authentication requirements
- GraphQL Playground URL

Common patterns:
- `https://api.nife.io/graphql`
- `https://api.nife.io/v1/graphql`
- `https://graphql.nife.io`

### Method 3: Contact Nife Support

If the endpoint is not publicly documented, contact Nife.io support to get:
- The correct GraphQL endpoint URL
- Authentication method (Bearer token, API key, etc.)
- Whether a GraphQL Playground is available

## GraphQL Playground Access

GraphQL Playgrounds are typically accessed through:

1. **Browser-based playground**:
   - Usually at the same endpoint as the API
   - Example: `https://api.nife.io/graphql` (open in browser)
   
2. **Separate playground URL**:
   - Some APIs have a dedicated playground
   - Example: `https://playground.nife.io`

3. **Use GraphQL clients**:
   - [Altair GraphQL Client](https://altair.sirmuel.design/)
   - [GraphQL Playground Desktop](https://github.com/graphql/graphql-playground)
   - [Insomnia](https://insomnia.rest/)
   - [Postman](https://www.postman.com/)

## How to Execute the MCP Server

### Step 1: Set Your Access Token

```bash
export NIFE_ACCESS_TOKEN="your_token_here"
```

Or get it from Nife CLI:
```bash
export NIFE_ACCESS_TOKEN=$(nifectl auth token)
```

### Step 2: Run the Test Script

```bash
cd /Users/rentsher/nife-mcp-server
python test_endpoint.py
```

This will test multiple possible endpoints and tell you which one works.

### Step 3: Update the Endpoint (if needed)

If the working endpoint is different, update these files:

**File 1:** `src/nife_mcp_server/schema_manager.py` (line 18)
```python
def __init__(self, api_url: str = "CORRECT_ENDPOINT_HERE", access_token: Optional[str] = None):
```

**File 2:** `src/nife_mcp_server/routes/mcp.py` (line 16)
```python
NIFE_GRAPHQL_ENDPOINT = "CORRECT_ENDPOINT_HERE"
```

### Step 4: Run the MCP Server

**Option A: Run the intelligent server (recommended)**
```bash
cd /Users/rentsher/nife-mcp-server
export NIFE_ACCESS_TOKEN="your_token"
python -m nife_mcp_server.intelligent_main
```

**Option B: Run the Flask server**
```bash
cd /Users/rentsher/nife-mcp-server/src
export NIFE_ACCESS_TOKEN="your_token"
python main.py
```

### Step 5: Test the Server

```bash
# Test with Claude Desktop or MCP Inspector
# The server will listen on stdin/stdout for MCP protocol messages
```

## Troubleshooting

### Error: "Connection Error"
- Check your internet connection
- Verify the endpoint URL is correct
- Ensure api.nife.io is accessible from your network

### Error: "401 Unauthorized"
- Your token might be expired
- Regenerate token: `nifectl auth token`
- Verify token is set: `echo $NIFE_ACCESS_TOKEN`

### Error: "GraphQL errors"
- Check if the query syntax is correct
- Verify you have permissions for the requested data
- Check Nife.io API documentation for available queries

### Can't Access Playground
- Some GraphQL APIs don't have public playgrounds
- Try opening `https://api.nife.io/graphql` in your browser
- Use a GraphQL client like Altair or Insomnia instead

## Example: Testing with curl

```bash
# Test the endpoint directly
curl -X POST https://api.nife.io/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $NIFE_ACCESS_TOKEN" \
  -d '{"query": "{ __typename }"}'
```

If this returns valid JSON, your endpoint and token are working correctly.

## Next Steps

1. Run `test_endpoint.py` to find the working endpoint
2. Update the endpoint in the code if needed
3. Run the intelligent MCP server
4. Connect it to Claude Desktop or your MCP client
5. Start using the Nife.io integration!
