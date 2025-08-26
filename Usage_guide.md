# Nife.io MCP Server

A Model Context Protocol (MCP) server for managing Nife.io cloud platform resources through Claude and other MCP-compatible AI assistants.

## Overview

This MCP server provides comprehensive access to Nife.io's cloud platform capabilities, allowing you to manage applications, organizations, users, and infrastructure resources through natural language conversations with AI assistants.

## Features

### 📱 Application Management
- **Lifecycle Operations**: Create, read, update, delete applications
- **Deployment Control**: Deploy apps with different strategies (rolling, canary, blue-green)
- **Scaling**: Scale application instances across regions
- **Status Monitoring**: Check deployment and health status
- **Build & Release Management**: Access build history and releases

### 🏢 Organization Management
- **Organization CRUD**: Create and manage organizations
- **User Management**: Invite users, manage roles and permissions
- **Team Collaboration**: Role-based access control (admin, developer, viewer)

### 🔧 Infrastructure Operations
- **Multi-Region Deployment**: Deploy across global regions
- **Storage Management**: Create and manage persistent volumes
- **SSL Certificates**: Manage Let's Encrypt and custom certificates
- **IP Address Management**: Handle IPv4 and IPv6 addresses
- **Secret Management**: Secure environment variable and secret handling

### 📊 Monitoring & Analytics
- **Platform Statistics**: Comprehensive platform-wide metrics
- **Resource Monitoring**: Track usage across organizations and regions
- **Health Checks**: API connectivity and status monitoring

## Prerequisites

- **Nife.io Account**: Active account with appropriate permissions
- **Access Token**: Valid Nife.io API access token
- **MCP-Compatible Client**: Claude Desktop, Claude Web, or other MCP client

## Installation

### 1. MCP Client Configuration

Add the server configuration to your MCP client settings:

```json

{
  "mcpServers": {
    "nife-mcp-server": {
      "command": "<path>python",
      "args": ["<path>/nife-mcp-server/src/main.py"],
      "env": {
        "NIFE_ACCESS_TOKEN":"your-access-token-here",
        "FLASK_ENV": "production",
        "FLASK_RUN_HOST": "127.0.0.1",
        "FLASK_RUN_PORT": "5000"
      }
    }
  }
}
```

### 2. Environment Variables

Set your Nife.io access token:

```bash
export NIFE_ACCESS_TOKEN="your-access-token-here"
```

## Quick Start

Once configured, you can interact with Nife.io through natural language:

### Application Operations
```
"Show me all my applications"
"Create a new app called 'my-api' in organization 'my-org'"
"Deploy my-api to production regions"
"Scale my-api to 3 instances"
"What's the status of my-api?"
```

### Organization Management
```
"List all organizations I have access to"
"Create a new organization called 'startup-xyz'"
"Invite john@company.com as a developer to my-org"
"Show me all users in organization 'my-org'"
```

### Infrastructure Management
```
"Show available deployment regions"
"Create a 10GB volume for my-api"
"Add SSL certificate for api.mydomain.com"
"List all secrets for my-api"
```

## Available Functions

### Core Operations
- `get_apps` - List applications with filtering
- `get_app` - Get specific application details
- `create_app` - Create new application
- `update_app` - Update application configuration
- `delete_app` - Delete application
- `deploy_app` - Deploy application
- `scale_app` - Scale application instances
- `restart_app` - Restart application

### Organization Management
- `get_organizations` - List organizations
- `get_organization` - Get organization details
- `create_organization` - Create new organization
- `update_organization` - Update organization
- `invite_user` - Invite user to organization
- `remove_user` - Remove user from organization

### Infrastructure
- `get_regions` - List deployment regions
- `get_volumes` - List storage volumes
- `create_volume` - Create storage volume
- `delete_volume` - Delete storage volume
- `get_certificates` - List SSL certificates
- `add_certificate` - Add SSL certificate
- `remove_certificate` - Remove SSL certificate

### Monitoring
- `get_app_status` - Application health status
- `get_platform_stats` - Platform-wide statistics
- `nife_health_check` - API health check

### Advanced
- `get_nife_context` - Get platform context
- `get_nife_schema` - Get GraphQL schema
- `execute_nife_query` - Execute custom GraphQL queries

## Authentication

All operations require a valid Nife.io access token. You can obtain one from:
1. Nife.io Dashboard → Settings → API Tokens
2. Nife CLI: `nife auth token`

## Usage Examples

### Example 1: Create and Deploy Application
```
User: "I want to create a new Node.js API called 'user-service' and deploy it to US and EU regions"

Response: The AI will:
1. Get your organizations to find the target org
2. Create the application with Node.js configuration
3. Set up deployment to US and EU regions
4. Provide status updates and deployment URLs
```

### Example 2: Monitor Application Health
```
User: "Check the health of all my production applications and show me any issues"

Response: The AI will:
1. List all your applications
2. Check status for each production app
3. Identify any unhealthy instances
4. Suggest remediation steps if issues are found
```

### Example 3: Team Management
```
User: "Add Sarah as a developer to the 'mobile-team' organization and show me the current team structure"

Response: The AI will:
1. Find the 'mobile-team' organization
2. Invite Sarah with developer permissions
3. Display current team members and their roles
4. Confirm the invitation was sent
```

## Error Handling

The MCP server includes robust error handling:

- **Authentication Errors**: Clear messages for invalid or expired tokens
- **Permission Errors**: Detailed explanations of required permissions
- **Rate Limiting**: Automatic retry with exponential backoff
- **Network Issues**: Graceful handling of connectivity problems
- **Validation Errors**: Helpful feedback for invalid parameters

## Troubleshooting

### Common Issues

**"Access token required"**
- Ensure `NIFE_ACCESS_TOKEN` environment variable is set
- Verify token hasn't expired
- Check token permissions in Nife.io dashboard

**"Organization not found"**
- Verify organization name or ID is correct
- Ensure you have access to the organization
- Use `get_organizations` to list available orgs

**"Insufficient permissions"**
- Check your role in the organization
- Contact organization admin for permission upgrade
- Review required permissions in error message

**"Internal system error"**
- Temporary API issues, will auto-retry
- Check Nife.io status page for incidents
- Contact support if persistent

### Debug Mode

Enable detailed logging by setting:
```bash
export MCP_DEBUG=1
```

## API Rate Limits

- **Standard Operations**: 100 requests per minute
- **Bulk Operations**: 20 requests per minute
- **GraphQL Queries**: Custom timeout support (1-300 seconds)

Rate limits are automatically handled with retry logic.

## Security Considerations

- **Token Storage**: Store access tokens securely, never commit to code
- **Permission Scoping**: Use minimal required permissions
- **Regular Rotation**: Rotate access tokens regularly
- **Audit Logging**: Monitor API usage through Nife.io dashboard

## Advanced Usage

### Custom GraphQL Queries

For advanced use cases, you can execute custom GraphQL queries:

```
User: "Execute a GraphQL query to get all applications with their resource usage metrics"
```

The AI can construct and execute complex queries using the `execute_nife_query` function.

### Platform Statistics

Get comprehensive platform insights:

```
User: "Show me platform-wide statistics including regional distribution and resource usage"
```

## Support

- **Documentation**: [Nife.io Docs](https://docs.nife.io)
- **API Reference**: [Nife.io API](https://docs.nife.io/api)
- **Support**: support@nife.io
- **Community**: [Nife.io Community](https://community.nife.io)

## Contributing

This MCP server is part of the Nife.io ecosystem. For feature requests or bug reports:

1. Check existing issues in the repository
2. Create detailed bug reports with reproduction steps
3. Suggest enhancements with clear use cases

## License

Licensed under the MIT License. See LICENSE file for details.

---

## Version History

- **v1.0.0**: Initial release with core functionality
- **v1.1.0**: Added custom GraphQL query support
- **v1.2.0**: Enhanced error handling and retry logic
- **v1.3.0**: Platform statistics and health monitoring

## Roadmap

- [ ] Webhook integration
- [ ] Real-time log streaming  
- [ ] Enhanced monitoring dashboards
- [ ] Multi-cloud region expansion
- [ ] Advanced deployment strategies