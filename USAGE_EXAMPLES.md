# Nife.io MCP Server - Usage Examples

This document provides practical examples of how to use the Nife.io MCP Server.

## Prerequisites

1. **Nife.io Access Token**: You need a valid Nife.io access token. Get one using:
   ```bash
   nifectl auth login
   nifectl auth token
   ```

2. **Running Server**: Make sure the MCP server is running:
   ```bash
   cd nife-mcp-server
   source venv/bin/activate
   python src/main.py
   ```

## Basic Examples

### 1. Health Check

Check if the MCP server is running and healthy:

```bash
curl -X GET http://localhost:5000/api/mcp/health
```

**Response:**
```json
{
  "endpoints": {
    "custom_query": "/api/mcp/query [POST]",
    "get_context": "/api/mcp/context [GET]",
    "get_schema": "/api/mcp/schema [GET]",
    "health": "/api/mcp/health [GET]",
    "update_context": "/api/mcp/context [POST]"
  },
  "service": "nife-mcp-server",
  "status": "healthy",
  "version": "1.0.0"
}
```

### 2. Schema Introspection

Get the complete GraphQL schema from Nife.io:

```bash
curl -X GET http://localhost:5000/api/mcp/schema \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN"
```

This returns the full GraphQL schema with all types, queries, and mutations available.

### 3. Simple GraphQL Query

Execute a basic GraphQL query:

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{
    "query": "query { __typename }"
  }'
```

**Response:**
```json
{
  "data": {
    "__typename": "Query"
  },
  "metadata": {
    "operation": "custom_query",
    "source": "nife.io",
    "timestamp": null
  }
}
```

## Advanced Examples

### 4. Query Applications (Example)

Based on the Nife.io schema, you can query applications:

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{
    "query": "query GetApps($limit: Int) { apps(limit: $limit) { id name status createdAt } }",
    "variables": { "limit": 5 }
  }'
```

### 5. Query with Variables

Execute a query with variables:

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{
    "query": "query GetApp($id: ID!) { app(id: $id) { id name status description } }",
    "variables": { "id": "your-app-id" }
  }'
```

### 6. Execute Mutation (Example)

Execute a GraphQL mutation to update data:

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{
    "query": "mutation UpdateApp($id: ID!, $input: UpdateAppInput!) { updateApp(id: $id, input: $input) { id name status } }",
    "variables": {
      "id": "your-app-id",
      "input": { "name": "Updated App Name" }
    }
  }'
```

## MCP Context Operations

### 7. Get Model Context

Retrieve model context data:

```bash
curl -X GET "http://localhost:5000/api/mcp/context?type=general&limit=10" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN"
```

### 8. Update Model Context

Update model context via GraphQL mutation:

```bash
curl -X POST http://localhost:5000/api/mcp/context \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{
    "name": "My App",
    "description": "Updated description"
  }'
```

## Error Handling Examples

### 9. Invalid Query Syntax

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{
    "query": "invalid query syntax"
  }'
```

**Response:**
```json
{
  "details": [
    {
      "message": "Request failed: 422 Client Error: Unprocessable Entity for url: https://api.nife.io/graphql"
    }
  ],
  "error": "GraphQL query failed"
}
```

### 10. Missing Query Parameter

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_NIFE_TOKEN" \
  -d '{}'
```

**Response:**
```json
{
  "error": "GraphQL query is required"
}
```

### 11. Authentication Error

```bash
curl -X POST http://localhost:5000/api/mcp/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { __typename }"
  }'
```

This will return an authentication error if no valid token is provided.

## Python Client Example

Here's how to use the MCP server from Python:

```python
import requests
import json

class NifeMCPClient:
    def __init__(self, base_url="http://localhost:5000", token=None):
        self.base_url = base_url
        self.token = token
        self.headers = {
            'Content-Type': 'application/json'
        }
        if token:
            self.headers['Authorization'] = f'Bearer {token}'
    
    def health_check(self):
        response = requests.get(f"{self.base_url}/api/mcp/health")
        return response.json()
    
    def get_schema(self):
        response = requests.get(
            f"{self.base_url}/api/mcp/schema",
            headers=self.headers
        )
        return response.json()
    
    def execute_query(self, query, variables=None):
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        response = requests.post(
            f"{self.base_url}/api/mcp/query",
            headers=self.headers,
            json=payload
        )
        return response.json()
    
    def get_context(self, context_type="general", limit=10):
        response = requests.get(
            f"{self.base_url}/api/mcp/context",
            params={"type": context_type, "limit": limit},
            headers=self.headers
        )
        return response.json()

# Usage
client = NifeMCPClient(token="YOUR_NIFE_TOKEN")

# Health check
print(client.health_check())

# Execute a query
result = client.execute_query("query { __typename }")
print(result)

# Get schema
schema = client.get_schema()
print(schema)
```

## Environment Variables

You can also set the token as an environment variable:

```bash
export NIFE_ACCESS_TOKEN="your-token-here"
```

Then the server will automatically use this token if no Authorization header is provided.

## Notes

- Replace `YOUR_NIFE_TOKEN` with your actual Nife.io access token
- The server runs on `http://localhost:5000` by default
- All GraphQL queries and mutations depend on the actual Nife.io schema
- Use the schema introspection endpoint to discover available operations
- The MCP server handles authentication, error handling, and response formatting automatically

