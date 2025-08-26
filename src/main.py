#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import logging
import requests
from datetime import datetime, timezone

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Configure logging to stderr only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Import your existing models and create Flask app context
from flask import Flask
from flask_cors import CORS
from src.models.user import db
from src.routes.mcp import NifeGraphQLClient

# Create Flask app for database context
app = Flask(__name__)
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Disable Flask logging completely
app.logger.handlers.clear()
app.logger.disabled = True
logging.getLogger('werkzeug').disabled = True
logging.getLogger('sqlalchemy').disabled = True

CORS(app)
db.init_app(app)

# Create database tables
with app.app_context():
    db.create_all()

class NifeMCPServer:
    def __init__(self):
        self.tools = {}
        self.setup_tools()
        logger.info("Enhanced Nife MCP Server initialized with all operations")
    
    def setup_tools(self):
        """Setup comprehensive MCP tools for all Nife.io operations"""
        
        # === QUERY TOOLS ===
        
        # Apps Management
        self.tools["get_apps"] = {
            "name": "get_apps",
            "description": "Get applications with filtering and pagination",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "first": {"type": "integer", "description": "Number of apps to retrieve", "default": 50},
                    "organization_id": {"type": "string", "description": "Filter by organization ID"},
                    "status": {"type": "string", "description": "Filter by app status"},
                    "deployed": {"type": "boolean", "description": "Filter by deployment status"},
                    "include_details": {"type": "boolean", "description": "Include detailed app information", "default": True}
                },
                "required": ["access_token"]
            }
        }
        
        self.tools["get_app"] = {
            "name": "get_app",
            "description": "Get specific application by ID or name",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "id": {"type": "string", "description": "App ID"},
                    "name": {"type": "string", "description": "App name"},
                    "include_logs": {"type": "boolean", "description": "Include recent logs", "default": False},
                    "include_allocations": {"type": "boolean", "description": "Include allocation status", "default": True}
                },
                "required": ["access_token"]
            }
        }
        
        self.tools["get_app_status"] = {
            "name": "get_app_status",
            "description": "Get application deployment and health status",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        # Organizations Management
        self.tools["get_organizations"] = {
            "name": "get_organizations",
            "description": "Get all organizations with detailed information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (optional)"},
                    "include_sub_orgs": {"type": "boolean", "description": "Include sub-organizations", "default": True},
                    "include_business_units": {"type": "boolean", "description": "Include business units", "default": True},
                    "include_app_counts": {"type": "boolean", "description": "Include app counts per organization", "default": True}
                },
                "required": []
            }
        }
        
        self.tools["get_organization"] = {
            "name": "get_organization",
            "description": "Get specific organization details",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "id": {"type": "string", "description": "Organization ID"},
                    "slug": {"type": "string", "description": "Organization slug"},
                    "include_apps": {"type": "boolean", "description": "Include apps in organization", "default": True}
                },
                "required": ["access_token"]
            }
        }
        
        # Users Management
        self.tools["get_users"] = {
            "name": "get_users",
            "description": "Get users with filtering and permissions",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "organization_id": {"type": "string", "description": "Filter by organization"},
                    "role": {"type": "string", "description": "Filter by role"},
                    "include_permissions": {"type": "boolean", "description": "Include user permissions", "default": True}
                },
                "required": ["access_token"]
            }
        }
        
        self.tools["get_user"] = {
            "name": "get_user",
            "description": "Get specific user details",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "id": {"type": "string", "description": "User ID"},
                    "email": {"type": "string", "description": "User email"},
                    "include_organizations": {"type": "boolean", "description": "Include user organizations", "default": True}
                },
                "required": ["access_token"]
            }
        }
        
        # Regions Management
        self.tools["get_regions"] = {
            "name": "get_regions",
            "description": "Get available deployment regions",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (optional)"},
                    "include_capacity": {"type": "boolean", "description": "Include region capacity info", "default": False}
                },
                "required": []
            }
        }
        
        # Builds Management
        self.tools["get_builds"] = {
            "name": "get_builds",
            "description": "Get application builds",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "limit": {"type": "integer", "description": "Number of builds to retrieve", "default": 20},
                    "include_logs": {"type": "boolean", "description": "Include build logs", "default": False}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        # Releases Management
        self.tools["get_releases"] = {
            "name": "get_releases",
            "description": "Get application releases",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "limit": {"type": "integer", "description": "Number of releases to retrieve", "default": 10}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        # Volumes Management
        self.tools["get_volumes"] = {
            "name": "get_volumes",
            "description": "Get storage volumes",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID"},
                    "organization_id": {"type": "string", "description": "Organization ID"}
                },
                "required": ["access_token"]
            }
        }
        
        # Certificates Management
        self.tools["get_certificates"] = {
            "name": "get_certificates",
            "description": "Get SSL certificates",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID"},
                    "hostname": {"type": "string", "description": "Filter by hostname"}
                },
                "required": ["access_token"]
            }
        }
        
        # IP Addresses Management
        self.tools["get_ip_addresses"] = {
            "name": "get_ip_addresses",
            "description": "Get IP addresses",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID"},
                    "type": {"type": "string", "description": "IP address type (v4, v6)"}
                },
                "required": ["access_token"]
            }
        }
        
        # Secrets Management
        self.tools["get_secrets"] = {
            "name": "get_secrets",
            "description": "Get application secrets",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        # Analytics and Stats
        self.tools["get_platform_stats"] = {
            "name": "get_platform_stats",
            "description": "Get comprehensive platform statistics",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "include_regions": {"type": "boolean", "description": "Include region-wise stats", "default": True}
                },
                "required": ["access_token"]
            }
        }
        
        # === MUTATION TOOLS ===
        
        # App Mutations
        self.tools["create_app"] = {
            "name": "create_app",
            "description": "Create a new application",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "name": {"type": "string", "description": "Application name (required)"},
                    "organization_id": {"type": "string", "description": "Organization ID (required)"},
                    "image": {"type": "string", "description": "Docker image"},
                    "regions": {"type": "array", "description": "Deployment regions", "items": {"type": "string"}},
                    "env_vars": {"type": "object", "description": "Environment variables"}
                },
                "required": ["access_token", "name", "organization_id"]
            }
        }
        
        self.tools["update_app"] = {
            "name": "update_app",
            "description": "Update application configuration",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "name": {"type": "string", "description": "New application name"},
                    "image": {"type": "string", "description": "New Docker image"},
                    "env_vars": {"type": "object", "description": "Environment variables"},
                    "regions": {"type": "array", "description": "Deployment regions", "items": {"type": "string"}}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        self.tools["delete_app"] = {
            "name": "delete_app",
            "description": "Delete an application",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "force": {"type": "boolean", "description": "Force deletion", "default": False}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        self.tools["deploy_app"] = {
            "name": "deploy_app",
            "description": "Deploy application",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "image": {"type": "string", "description": "Docker image to deploy"},
                    "strategy": {"type": "string", "description": "Deployment strategy", "enum": ["rolling", "canary", "blue-green"]},
                    "wait_for_completion": {"type": "boolean", "description": "Wait for deployment to complete", "default": False}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        self.tools["scale_app"] = {
            "name": "scale_app", 
            "description": "Scale application instances",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "count": {"type": "integer", "description": "Number of instances (required)"},
                    "region": {"type": "string", "description": "Specific region to scale"}
                },
                "required": ["access_token", "app_id", "count"]
            }
        }
        
        self.tools["restart_app"] = {
            "name": "restart_app",
            "description": "Restart application",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "region": {"type": "string", "description": "Specific region to restart"}
                },
                "required": ["access_token", "app_id"]
            }
        }
        
        # Organization Mutations
        self.tools["create_organization"] = {
            "name": "create_organization",
            "description": "Create a new organization",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "name": {"type": "string", "description": "Organization name (required)"},
                    "slug": {"type": "string", "description": "Organization slug"},
                    "type": {"type": "string", "description": "Organization type"}
                },
                "required": ["access_token", "name"]
            }
        }
        
        self.tools["update_organization"] = {
            "name": "update_organization",
            "description": "Update organization details",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "id": {"type": "string", "description": "Organization ID (required)"},
                    "name": {"type": "string", "description": "New name"},
                    "slug": {"type": "string", "description": "New slug"},
                    "is_active": {"type": "boolean", "description": "Active status"}
                },
                "required": ["access_token", "id"]
            }
        }
        
        # User Mutations
        self.tools["invite_user"] = {
            "name": "invite_user",
            "description": "Invite user to organization",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "email": {"type": "string", "description": "User email (required)"},
                    "organization_id": {"type": "string", "description": "Organization ID (required)"},
                    "role": {"type": "string", "description": "User role", "enum": ["admin", "developer", "viewer"]},
                    "permissions": {"type": "array", "description": "Specific permissions", "items": {"type": "string"}}
                },
                "required": ["access_token", "email", "organization_id"]
            }
        }
        
        self.tools["update_user"] = {
            "name": "update_user",
            "description": "Update user details and permissions",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "user_id": {"type": "string", "description": "User ID (required)"},
                    "role": {"type": "string", "description": "New role"},
                    "permissions": {"type": "array", "description": "New permissions", "items": {"type": "string"}},
                    "is_active": {"type": "boolean", "description": "Active status"}
                },
                "required": ["access_token", "user_id"]
            }
        }
        
        self.tools["remove_user"] = {
            "name": "remove_user",
            "description": "Remove user from organization",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "user_id": {"type": "string", "description": "User ID (required)"},
                    "organization_id": {"type": "string", "description": "Organization ID (required)"}
                },
                "required": ["access_token", "user_id", "organization_id"]
            }
        }
        
        # Secret Mutations
        self.tools["set_secret"] = {
            "name": "set_secret",
            "description": "Set application secret",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "name": {"type": "string", "description": "Secret name (required)"},
                    "value": {"type": "string", "description": "Secret value (required)"}
                },
                "required": ["access_token", "app_id", "name", "value"]
            }
        }
        
        self.tools["unset_secret"] = {
            "name": "unset_secret",
            "description": "Remove application secret",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "name": {"type": "string", "description": "Secret name (required)"}
                },
                "required": ["access_token", "app_id", "name"]
            }
        }
        
        # Certificate Mutations
        self.tools["add_certificate"] = {
            "name": "add_certificate",
            "description": "Add SSL certificate",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "hostname": {"type": "string", "description": "Certificate hostname (required)"},
                    "type": {"type": "string", "description": "Certificate type", "enum": ["lets_encrypt", "custom"]},
                    "certificate": {"type": "string", "description": "Certificate content (for custom)"},
                    "private_key": {"type": "string", "description": "Private key (for custom)"}
                },
                "required": ["access_token", "app_id", "hostname"]
            }
        }
        
        self.tools["remove_certificate"] = {
            "name": "remove_certificate",
            "description": "Remove SSL certificate",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "hostname": {"type": "string", "description": "Certificate hostname (required)"}
                },
                "required": ["access_token", "app_id", "hostname"]
            }
        }
        
        # Volume Mutations
        self.tools["create_volume"] = {
            "name": "create_volume",
            "description": "Create storage volume",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "name": {"type": "string", "description": "Volume name (required)"},
                    "size": {"type": "string", "description": "Volume size (e.g., '10GB')"},
                    "region": {"type": "string", "description": "Region for volume"}
                },
                "required": ["access_token", "app_id", "name"]
            }
        }
        
        self.tools["delete_volume"] = {
            "name": "delete_volume",
            "description": "Delete storage volume",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "Nife.io access token (required)"},
                    "app_id": {"type": "string", "description": "Application ID (required)"},
                    "volume_id": {"type": "string", "description": "Volume ID (required)"}
                },
                "required": ["access_token", "app_id", "volume_id"]
            }
        }
        
        # === LEGACY TOOLS (Keep for compatibility) ===
        
        self.tools["get_nife_context"] = {
            "name": "get_nife_context",
            "description": "Get model context from Nife.io GraphQL API (organizations, user info, platform data)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "context_type": {
                        "type": "string",
                        "description": "Type of context to retrieve",
                        "enum": ["organizations", "user_permissions", "platform", "all"],
                        "default": "organizations"
                    },
                    "include_apps": {
                        "type": "boolean",
                        "description": "Attempt to include apps data (may fail due to permissions)",
                        "default": False
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of items to retrieve (1-100) - only for apps",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "access_token": {
                        "type": "string",
                        "description": "Nife.io access token (optional if NIFE_ACCESS_TOKEN env var is set)"
                    }
                },
                "required": []
            }
        }
        
        self.tools["get_nife_schema"] = {
            "name": "get_nife_schema",
            "description": "Get the GraphQL schema from Nife.io API",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "simplified": {
                        "type": "boolean",
                        "description": "Whether to return simplified schema",
                        "default": False
                    },
                    "access_token": {
                        "type": "string",
                        "description": "Nife.io access token (optional)"
                    }
                },
                "required": []
            }
        }
        
        self.tools["execute_nife_query"] = {
            "name": "execute_nife_query",
            "description": "Execute a custom GraphQL query against Nife.io API with automatic retry and fallback",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "access_token": {
                        "type": "string",
                        "description": "Nife.io access token (required)"
                    },
                    "query": {
                        "type": "string",
                        "description": "GraphQL query to execute"
                    },
                    "variables": {
                        "type": "object",
                        "description": "GraphQL query variables",
                        "default": {}
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Query timeout in seconds (1-300)",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 300
                    },
                    "retry_on_error": {
                        "type": "boolean",
                        "description": "Whether to retry on 'internal system error'",
                        "default": True
                    }
                },
                "required": ["access_token", "query"]
            }
        }
        
        self.tools["nife_health_check"] = {
            "name": "nife_health_check",
            "description": "Check the health of Nife.io API connection",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        logger.info(f"Setup {len(self.tools)} comprehensive MCP tools for Nife.io")
    
    async def execute_query_with_fallback(self, client, primary_query, fallback_queries=None, variables=None, timeout=30, max_retries=2):
        """Execute query with fallback options and retry logic"""
        variables = variables or {}
        fallback_queries = fallback_queries or []
        
        # Try primary query with retries
        for attempt in range(max_retries + 1):
            try:
                result = client.execute_query(primary_query, variables, timeout)
                
                # Check for internal system errors
                if 'errors' in result:
                    errors = result['errors']
                    has_system_error = any('internal system error' in str(error).lower() for error in errors)
                    
                    if has_system_error and attempt < max_retries:
                        logger.warning(f"Internal system error, retrying... (attempt {attempt + 1}/{max_retries + 1})")
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue
                    elif not has_system_error:
                        return result  # Other errors, don't retry
                else:
                    return result  # Success
                    
            except Exception as e:
                logger.error(f"Query execution failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                break
        
        # If primary query failed, try fallbacks
        logger.warning("Primary query failed, trying fallback queries...")
        fallback_results = {}
        
        for fallback_query in fallback_queries:
            try:
                result = client.execute_query(fallback_query, {}, timeout)
                if 'errors' not in result:
                    fallback_results[fallback_query.split('{')[0].strip()] = result
                    logger.info(f"Fallback query succeeded: {fallback_query[:50]}...")
            except Exception as e:
                logger.error(f"Fallback query failed: {e}")
                continue
        
        if fallback_results:
            return {
                'data': fallback_results,
                'fallback_used': True,
                'primary_query_failed': True
            }
        
        # All queries failed
        return {
            'errors': ['All queries failed, including fallbacks'],
            'primary_query_failed': True,
            'fallback_failed': True
        }

    # === QUERY HANDLERS ===
    
    async def handle_get_apps(self, args):
        """Handle get_apps tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            first = args.get('first', 50)
            org_id = args.get('organization_id')
            status = args.get('status')
            deployed = args.get('deployed')
            include_details = args.get('include_details', True)
            
            # Build query based on parameters
            if include_details:
                query = f"""
                query GetApps($first: Int) {{
                    apps(first: $first) {{
                        nodes {{
                            id
                            name
                            status
                            deployed
                            hostname
                            appUrl
                            version
                            organizationId
                            organizationName
                            subOrganizationId
                            subOrganizationName
                            businessUnitId
                            businessUnitName
                            imageName
                            port
                            replicas
                            deploymentTime
                            buildTime
                            createdAt
                            regions {{
                                code
                                name
                            }}
                            vmSize {{
                                name
                                cpuCores
                                memoryMb
                            }}
                            autoscaling {{
                                enabled
                                minCount
                                maxCount
                            }}
                        }}
                    }}
                }}
                """
            else:
                query = f"""
                query GetApps($first: Int) {{
                    apps(first: $first) {{
                        nodes {{
                            id
                            name
                            status
                            deployed
                            hostname
                            organizationName
                        }}
                    }}
                }}
                """
            
            variables = {'first': first}
            result = await self.execute_query_with_fallback(client, query, variables=variables)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve apps", "details": result['errors']}
            
            # Process and filter results if needed
            apps = result.get('data', {}).get('apps', {}).get('nodes', [])
            
            # Apply filters
            if org_id:
                apps = [app for app in apps if app.get('organizationId') == org_id]
            if status:
                apps = [app for app in apps if app.get('status') == status]
            if deployed is not None:
                apps = [app for app in apps if app.get('deployed') == deployed]
            
            return {
                'apps': apps,
                'total_count': len(apps),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_apps',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'filters': {
                        'organization_id': org_id,
                        'status': status,
                        'deployed': deployed
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_apps: {e}")
            return {"error": str(e)}
    
    async def handle_get_app(self, args):
        """Handle get_app tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('id')
            app_name = args.get('name')
            include_logs = args.get('include_logs', False)
            include_allocations = args.get('include_allocations', True)
            
            if not app_id and not app_name:
                return {"error": "Either app ID or name is required"}
            
            # Build query
            logs_field = "recentLogs { timestamp level message }" if include_logs else ""
            allocations_field = """
                allocations {
                    id
                    status
                    region
                    healthy
                    version
                    createdAt
                    updatedAt
                }
            """ if include_allocations else ""
            
            if app_id:
                query = f"""
                query GetApp($id: ID!) {{
                    app(id: $id) {{
                        id
                        name
                        status
                        deployed
                        hostname
                        appUrl
                        version
                        organizationId
                        organizationName
                        imageName
                        port
                        replicas
                        deploymentTime
                        buildTime
                        createdAt
                        regions {{
                            code
                            name
                        }}
                        vmSize {{
                            name
                            cpuCores
                            memoryMb
                        }}
                        autoscaling {{
                            enabled
                            minCount
                            maxCount
                        }}
                        {allocations_field}
                        {logs_field}
                        secrets {{
                            name
                        }}
                        services {{
                            protocol
                            internalPort
                            ports {{
                                port
                                handlers
                            }}
                        }}
                    }}
                }}
                """
                variables = {'id': app_id}
            else:
                query = f"""
                query GetAppByName($name: String!) {{
                    apps(name: $name) {{
                        nodes {{
                            id
                            name
                            status
                            deployed
                            hostname
                            appUrl
                            version
                            organizationId
                            organizationName
                            imageName
                            port
                            replicas
                            deploymentTime
                            buildTime
                            createdAt
                            regions {{
                                code
                                name
                            }}
                            vmSize {{
                                name
                                cpuCores
                                memoryMb
                            }}
                            autoscaling {{
                                enabled
                                minCount
                                maxCount
                            }}
                            {allocations_field}
                            {logs_field}
                            secrets {{
                                name
                            }}
                            services {{
                                protocol
                                internalPort
                                ports {{
                                    port
                                    handlers
                                }}
                            }}
                        }}
                    }}
                }}
                """
                variables = {'name': app_name}
            
            result = await self.execute_query_with_fallback(client, query, variables=variables)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve app", "details": result['errors']}
            
            app_data = result.get('data', {})
            if app_id:
                app = app_data.get('app')
            else:
                apps = app_data.get('apps', {}).get('nodes', [])
                app = apps[0] if apps else None
            
            if not app:
                return {"error": f"App not found: {app_id or app_name}"}
            
            return {
                'app': app,
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_app',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'query_type': 'by_id' if app_id else 'by_name'
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_app: {e}")
            return {"error": str(e)}
    
    async def handle_get_organizations(self, args):
        """Handle get_organizations tool call"""
        try:
            access_token = args.get('access_token') or os.environ.get('NIFE_ACCESS_TOKEN')
            client = NifeGraphQLClient(access_token)
            
            include_sub_orgs = args.get('include_sub_orgs', True)
            include_business_units = args.get('include_business_units', True)
            include_app_counts = args.get('include_app_counts', True)
            
            # Build comprehensive query
            query = """
            query GetOrganizations {
                organizations {
                    nodes {
                        id
                        name
                        slug
                        type
                        isActive
                    }
                }
            }
            """
            
            results = {}
            
            # Get basic organizations
            result = await self.execute_query_with_fallback(client, query)
            results['organizations'] = result.get('data', {}).get('organizations', {}).get('nodes', [])
            
            # Get app counts if requested
            if include_app_counts and access_token:
                try:
                    stats_query = """
                    query GetPlatformStats {
                        appsAndOrgsCountDetails {
                            totalOrgCount
                            totalAppCount
                            orgByAppCount {
                                organization
                                appsCount
                                newApp
                                activeApp
                                inActiveApp
                            }
                        }
                    }
                    """
                    stats_result = await self.execute_query_with_fallback(client, stats_query)
                    results['app_counts'] = stats_result.get('data', {}).get('appsAndOrgsCountDetails')
                except Exception as e:
                    logger.warning(f"Failed to get app counts: {e}")
            
            return {
                'data': results,
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_organizations',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'includes': {
                        'sub_orgs': include_sub_orgs,
                        'business_units': include_business_units,
                        'app_counts': include_app_counts
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_organizations: {e}")
            return {"error": str(e)}
    
    async def handle_get_platform_stats(self, args):
        """Handle get_platform_stats tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            include_regions = args.get('include_regions', True)
            
            query = """
            query GetPlatformStats {
                appsAndOrgsAndSubOrgCountDetails {
                    totalOrgCount
                    totalSubOrgCount
                    totalBusinessUnitCount
                    totalAppCount
                    orgByAppCount {
                        organization
                        appsCount
                        newApp
                        activeApp
                        inActiveApp
                        subOrganization {
                            subOrgName
                            appsCount
                            newApp
                            activeApp
                            inActiveApp
                        }
                    }
                    region {
                        regionName
                        appsCount
                        newApp
                        activeApp
                        inActiveApp
                    }
                }
            }
            """
            
            result = await self.execute_query_with_fallback(client, query)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve platform stats", "details": result['errors']}
            
            stats = result.get('data', {}).get('appsAndOrgsAndSubOrgCountDetails', {})
            
            return {
                'platform_stats': stats,
                'summary': {
                    'total_organizations': stats.get('totalOrgCount', 0),
                    'total_sub_organizations': stats.get('totalSubOrgCount', 0),
                    'total_business_units': stats.get('totalBusinessUnitCount', 0),
                    'total_applications': stats.get('totalAppCount', 0)
                },
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_platform_stats',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'include_regions': include_regions
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_platform_stats: {e}")
            return {"error": str(e)}
    
    # === MUTATION HANDLERS ===
    
    async def handle_create_app(self, args):
        """Handle create_app tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            name = args.get('name')
            organization_id = args.get('organization_id')
            image = args.get('image')
            regions = args.get('regions', [])
            env_vars = args.get('env_vars', {})
            
            mutation = """
            mutation CreateApp($input: CreateAppInput!) {
                createApp(input: $input) {
                    app {
                        id
                        name
                        status
                        hostname
                        organizationId
                        createdAt
                    }
                    errors {
                        field
                        message
                    }
                }
            }
            """
            
            input_data = {
                'name': name,
                'organizationId': organization_id
            }
            
            if image:
                input_data['image'] = image
            if regions:
                input_data['regions'] = regions
            if env_vars:
                input_data['envVars'] = env_vars
            
            variables = {'input': input_data}
            result = await self.execute_query_with_fallback(client, mutation, variables=variables, timeout=60)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to create app", "details": result['errors']}
            
            create_result = result.get('data', {}).get('createApp', {})
            
            if create_result.get('errors'):
                return {"error": "App creation failed", "details": create_result['errors']}
            
            return {
                'success': True,
                'app': create_result.get('app'),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'create_app',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in create_app: {e}")
            return {"error": str(e)}
    
    async def handle_deploy_app(self, args):
        """Handle deploy_app tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            image = args.get('image')
            strategy = args.get('strategy', 'rolling')
            wait_for_completion = args.get('wait_for_completion', False)
            
            mutation = """
            mutation DeployApp($input: DeployAppInput!) {
                deployApp(input: $input) {
                    release {
                        id
                        version
                        status
                        createdAt
                    }
                    errors {
                        field
                        message
                    }
                }
            }
            """
            
            input_data = {
                'appId': app_id,
                'strategy': strategy.upper()
            }
            
            if image:
                input_data['image'] = image
            
            variables = {'input': input_data}
            result = await self.execute_query_with_fallback(client, mutation, variables=variables, timeout=120)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to deploy app", "details": result['errors']}
            
            deploy_result = result.get('data', {}).get('deployApp', {})
            
            if deploy_result.get('errors'):
                return {"error": "App deployment failed", "details": deploy_result['errors']}
            
            return {
                'success': True,
                'release': deploy_result.get('release'),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'deploy_app',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'strategy': strategy,
                    'wait_for_completion': wait_for_completion
                }
            }
            
        except Exception as e:
            logger.error(f"Error in deploy_app: {e}")
            return {"error": str(e)}
    
    async def handle_scale_app(self, args):
        """Handle scale_app tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            count = args.get('count')
            region = args.get('region')
            
            mutation = """
            mutation ScaleApp($input: ScaleAppInput!) {
                scaleApp(input: $input) {
                    app {
                        id
                        name
                        replicas
                    }
                    errors {
                        field
                        message
                    }
                }
            }
            """
            
            input_data = {
                'appId': app_id,
                'count': count
            }
            
            if region:
                input_data['region'] = region
            
            variables = {'input': input_data}
            result = await self.execute_query_with_fallback(client, mutation, variables=variables, timeout=60)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to scale app", "details": result['errors']}
            
            scale_result = result.get('data', {}).get('scaleApp', {})
            
            if scale_result.get('errors'):
                return {"error": "App scaling failed", "details": scale_result['errors']}
            
            return {
                'success': True,
                'app': scale_result.get('app'),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'scale_app',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'target_count': count,
                    'region': region
                }
            }
            
        except Exception as e:
            logger.error(f"Error in scale_app: {e}")
            return {"error": str(e)}
    
    async def handle_set_secret(self, args):
        """Handle set_secret tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            name = args.get('name')
            value = args.get('value')
            
            mutation = """
            mutation SetSecret($input: SetSecretInput!) {
                setSecret(input: $input) {
                    app {
                        id
                        secrets {
                            name
                        }
                    }
                    errors {
                        field
                        message
                    }
                }
            }
            """
            
            input_data = {
                'appId': app_id,
                'name': name,
                'value': value
            }
            
            variables = {'input': input_data}
            result = await self.execute_query_with_fallback(client, mutation, variables=variables, timeout=30)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to set secret", "details": result['errors']}
            
            secret_result = result.get('data', {}).get('setSecret', {})
            
            if secret_result.get('errors'):
                return {"error": "Secret setting failed", "details": secret_result['errors']}
            
            return {
                'success': True,
                'app': secret_result.get('app'),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'set_secret',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'secret_name': name
                }
            }
            
        except Exception as e:
            logger.error(f"Error in set_secret: {e}")
            return {"error": str(e)}
    
    # === LEGACY HANDLERS (Keep for compatibility) ===
    
    async def handle_get_nife_context(self, args):
        """Handle get_nife_context tool call with corrected queries"""
        try:
            context_type = args.get('context_type', 'organizations')
            include_apps = args.get('include_apps', False)
            limit = args.get('limit', 10)
            access_token = args.get('access_token') or os.environ.get('NIFE_ACCESS_TOKEN')
            
            # Validate limit
            if limit < 1 or limit > 100:
                return {"error": "Limit must be between 1 and 100"}
            
            client = NifeGraphQLClient(access_token)
            
            # Define context-specific queries (corrected structure)
            queries = {
                "organizations": """
                query GetOrganizations {
                    organizations {
                        nodes {
                            id
                            name
                            slug
                            type
                            isActive
                        }
                    }
                }
                """,
                
                "user_permissions": """
                query GetUserPermissions {
                    getUserPermissions {
                        id
                        permissions
                        role
                        organizationId
                    }
                }
                """,
                
                "platform": """
                query GetPlatformInfo {
                    platform {
                        version
                        features
                        regions
                    }
                }
                """
            }
            
            # Apps query (may fail due to permissions)
            apps_query = f"""
            query GetApps($first: Int) {{
                apps(first: $first) {{
                    nodes {{
                        id
                        name
                        status
                        deployed
                        hostname
                        organizationId
                        organizationName
                    }}
                }}
            }}
            """
            
            # Fallback queries if main queries fail
            fallback_queries = [
                "query GetParentOrgs { getAllParentOrganizations { id name } }",
                "query GetSubOrgs { subOrganizations { id name slug } }"
            ]
            
            results = {}
            
            if context_type == "all":
                # Execute all context queries
                for ctx_type, query in queries.items():
                    try:
                        result = await self.execute_query_with_fallback(
                            client, query, fallback_queries, timeout=30
                        )
                        results[ctx_type] = result
                    except Exception as e:
                        results[ctx_type] = {"errors": [str(e)]}
                        
                # Try apps if requested
                if include_apps:
                    try:
                        apps_result = await self.execute_query_with_fallback(
                            client, apps_query, fallback_queries, 
                            variables={'first': limit}, timeout=30
                        )
                        results["apps"] = apps_result
                    except Exception as e:
                        results["apps"] = {"errors": [str(e)], "note": "Apps query often fails due to permissions"}
            
            else:
                # Execute specific context query
                query = queries.get(context_type)
                if not query:
                    return {"error": f"Unknown context_type: {context_type}. Available: {list(queries.keys())} or 'all'"}
                
                result = await self.execute_query_with_fallback(
                    client, query, fallback_queries, timeout=30
                )
                results[context_type] = result
                
                # Try apps if requested and not already included
                if include_apps and context_type != "all":
                    try:
                        apps_result = await self.execute_query_with_fallback(
                            client, apps_query, fallback_queries, 
                            variables={'first': limit}, timeout=30
                        )
                        results["apps"] = apps_result
                    except Exception as e:
                        results["apps"] = {"errors": [str(e)], "note": "Apps query often fails due to permissions"}
            
            return {
                'context_type': context_type,
                'data': results,
                'metadata': {
                    'source': 'nife.io',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'query_parameters': {
                        'type': context_type, 
                        'limit': limit,
                        'include_apps': include_apps
                    },
                    'notes': [
                        'Using corrected query structure with nodes (not edges)',
                        'Apps queries may fail due to permission issues',
                        'Fallback queries used if primary queries fail'
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_nife_context: {e}")
            return {"error": str(e)}
    
    async def handle_get_nife_schema(self, args):
        """Handle get_nife_schema tool call"""
        try:
            simplified = args.get('simplified', False)
            access_token = args.get('access_token') or os.environ.get('NIFE_ACCESS_TOKEN')
            
            client = NifeGraphQLClient(access_token)
            
            if simplified:
                query = """
                query GetSimplifiedSchema {
                    __schema {
                        queryType { 
                            name
                            fields {
                                name
                                description
                                type { name kind }
                            }
                        }
                        mutationType { 
                            name
                            fields {
                                name
                                description
                            }
                        }
                    }
                }
                """
            else:
                # Full introspection query
                query = """
                query IntrospectionQuery {
                    __schema {
                        queryType { name }
                        mutationType { name }
                        subscriptionType { name }
                        types {
                            kind
                            name
                            description
                            fields(includeDeprecated: true) {
                                name
                                description
                                type { 
                                    name 
                                    kind
                                    ofType {
                                        name
                                        kind
                                    }
                                }
                                isDeprecated
                                deprecationReason
                                args {
                                    name
                                    description
                                    type { name kind }
                                }
                            }
                        }
                        directives {
                            name
                            description
                            locations
                        }
                    }
                }
                """
            
            result = await self.execute_query_with_fallback(
                client, query, timeout=60
            )
            
            if 'errors' in result:
                return {"error": "Schema introspection failed", "details": result['errors']}
            
            return {
                'schema': result.get('data', {}),
                'metadata': {
                    'source': 'nife.io',
                    'type': 'graphql_schema',
                    'simplified': simplified,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_nife_schema: {e}")
            return {"error": str(e)}
    
    async def handle_execute_nife_query(self, args):
        """Handle execute_nife_query tool call with retry logic"""
        try:
            access_token = args.get('access_token')
            query = args.get('query')
            variables = args.get('variables', {})
            timeout = args.get('timeout', 30)
            retry_on_error = args.get('retry_on_error', True)
            
            if not access_token:
                return {"error": "Access token is required"}
            if not query:
                return {"error": "GraphQL query is required"}
            if not query.strip():
                return {"error": "Query cannot be empty"}
            
            client = NifeGraphQLClient(access_token)
            
            if retry_on_error:
                result = await self.execute_query_with_fallback(
                    client, query, variables=variables, timeout=timeout, max_retries=2
                )
            else:
                result = client.execute_query(query, variables, timeout)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "GraphQL query failed", "details": result['errors']}
            
            return {
                'data': result.get('data', {}),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'custom_query',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'query_hash': hash(query.strip()) & 0x7FFFFFFF,
                    'fallback_used': result.get('fallback_used', False),
                    'retry_enabled': retry_on_error
                },
                'warnings': result.get('warnings', [])
            }
            
        except Exception as e:
            logger.error(f"Error in execute_nife_query: {e}")
            return {"error": str(e)}
    
    async def handle_nife_health_check(self, args):
        """Handle nife_health_check tool call with comprehensive testing"""
        try:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
            client = NifeGraphQLClient(access_token)
            
            # Test multiple endpoints
            tests = [
                {
                    "name": "basic_connection",
                    "query": "query HealthCheck { __typename }",
                    "timeout": 5
                },
                {
                    "name": "organizations_access",
                    "query": "query TestOrgs { organizations { nodes { id } } }",
                    "timeout": 10
                },
                {
                    "name": "schema_introspection",
                    "query": "query TestSchema { __schema { queryType { name } } }",
                    "timeout": 15
                }
            ]
            
            test_results = {}
            overall_health = True
            
            for test in tests:
                try:
                    result = client.execute_query(test["query"], timeout=test["timeout"])
                    test_results[test["name"]] = {
                        "status": "healthy" if 'errors' not in result else "degraded",
                        "errors": result.get('errors', [])
                    }
                    if 'errors' in result:
                        overall_health = False
                except Exception as e:
                    test_results[test["name"]] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
                    overall_health = False
            
            return {
                'status': 'healthy' if overall_health else 'degraded',
                'service': 'nife-mcp-server',
                'version': '2.0.0',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'test_results': test_results,
                'available_tools': list(self.tools.keys()),
                'tool_categories': {
                    'queries': [name for name in self.tools.keys() if name.startswith('get_')],
                    'mutations': [name for name in self.tools.keys() if any(name.startswith(prefix) for prefix in ['create_', 'update_', 'delete_', 'deploy_', 'scale_', 'restart_', 'invite_', 'remove_', 'set_', 'unset_', 'add_'])],
                    'legacy': ['get_nife_context', 'get_nife_schema', 'execute_nife_query', 'nife_health_check']
                },
                'notes': [
                    'Enhanced MCP server with comprehensive Nife.io operations',
                    'Includes all major queries and mutations',
                    'Automatic retry and fallback mechanisms',
                    'Legacy tools maintained for compatibility'
                ]
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'service': 'nife-mcp-server',
                'version': '2.0.0',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }
    
    async def handle_tool_call(self, tool_name: str, arguments: dict):
        """Route tool calls to appropriate handlers"""
        handlers = {
            # Query handlers
            "get_apps": self.handle_get_apps,
            "get_app": self.handle_get_app,
            "get_app_status": self.handle_get_app,  # Same as get_app for now
            "get_organizations": self.handle_get_organizations,
            "get_organization": self.handle_get_organizations,  # Will filter by ID/slug
            "get_users": self.handle_get_users,
            "get_user": self.handle_get_user,
            "get_regions": self.handle_get_regions,
            "get_builds": self.handle_get_builds,
            "get_releases": self.handle_get_releases,
            "get_volumes": self.handle_get_volumes,
            "get_certificates": self.handle_get_certificates,
            "get_ip_addresses": self.handle_get_ip_addresses,
            "get_secrets": self.handle_get_secrets,
            "get_platform_stats": self.handle_get_platform_stats,
            
            # Mutation handlers
            "create_app": self.handle_create_app,
            "update_app": self.handle_update_app,
            "delete_app": self.handle_delete_app,
            "deploy_app": self.handle_deploy_app,
            "scale_app": self.handle_scale_app,
            "restart_app": self.handle_restart_app,
            "create_organization": self.handle_create_organization,
            "update_organization": self.handle_update_organization,
            "invite_user": self.handle_invite_user,
            "update_user": self.handle_update_user,
            "remove_user": self.handle_remove_user,
            "set_secret": self.handle_set_secret,
            "unset_secret": self.handle_unset_secret,
            "add_certificate": self.handle_add_certificate,
            "remove_certificate": self.handle_remove_certificate,
            "create_volume": self.handle_create_volume,
            "delete_volume": self.handle_delete_volume,
            
            # Legacy handlers
            "get_nife_context": self.handle_get_nife_context,
            "update_nife_context": self.handle_update_nife_context,
            "get_nife_schema": self.handle_get_nife_schema,
            "execute_nife_query": self.handle_execute_nife_query,
            "nife_health_check": self.handle_nife_health_check
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        
        logger.info(f"Executing tool: {tool_name}")
        return await handler(arguments)
    
    # === PLACEHOLDER HANDLERS FOR MISSING IMPLEMENTATIONS ===
    
    async def handle_get_users(self, args):
        """Handle get_users tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            
            query = """
            query GetUsers {
                users {
                    nodes {
                        id
                        email
                        name
                        role
                        isActive
                        organizationId
                        createdAt
                    }
                }
            }
            """
            
            result = await self.execute_query_with_fallback(client, query)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve users", "details": result['errors']}
            
            users = result.get('data', {}).get('users', {}).get('nodes', [])
            
            return {
                'users': users,
                'total_count': len(users),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_users',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_users: {e}")
            return {"error": str(e)}
    
    async def handle_get_user(self, args):
        """Handle get_user tool call"""
        return {"error": "get_user not yet implemented - use execute_nife_query for custom queries"}
    
    async def handle_get_regions(self, args):
        """Handle get_regions tool call"""
        try:
            access_token = args.get('access_token') or os.environ.get('NIFE_ACCESS_TOKEN')
            client = NifeGraphQLClient(access_token)
            
            query = """
            query GetRegions {
                platform {
                    regions {
                        code
                        name
                        processGroup
                    }
                }
            }
            """
            
            result = await self.execute_query_with_fallback(client, query)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve regions", "details": result['errors']}
            
            regions = result.get('data', {}).get('platform', {}).get('regions', [])
            
            return {
                'regions': regions,
                'total_count': len(regions),
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_regions',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_regions: {e}")
            return {"error": str(e)}
    
    async def handle_get_builds(self, args):
        """Handle get_builds tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            limit = args.get('limit', 20)
            include_logs = args.get('include_logs', False)
            
            logs_field = "logs" if include_logs else ""
            
            query = f"""
            query GetBuilds($appId: ID!, $first: Int) {{
                app(id: $appId) {{
                    builds(first: $first) {{
                        nodes {{
                            id
                            status
                            image
                            createdAt
                            updatedAt
                            inProgress
                            {logs_field}
                            user {{
                                id
                                email
                                name
                            }}
                        }}
                    }}
                }}
            }}
            """
            
            variables = {'appId': app_id, 'first': limit}
            result = await self.execute_query_with_fallback(client, query, variables=variables)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve builds", "details": result['errors']}
            
            builds = result.get('data', {}).get('app', {}).get('builds', {}).get('nodes', [])
            
            return {
                'builds': builds,
                'total_count': len(builds),
                'app_id': app_id,
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_builds',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_builds: {e}")
            return {"error": str(e)}
    
    async def handle_get_releases(self, args):
        """Handle get_releases tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            limit = args.get('limit', 10)
            
            query = f"""
            query GetReleases($appId: ID!, $first: Int) {{
                app(id: $appId) {{
                    releases(first: $first) {{
                        nodes {{
                            id
                            version
                            status
                            description
                            stable
                            createdAt
                            user {{
                                id
                                email
                                name
                            }}
                        }}
                    }}
                }}
            }}
            """
            
            variables = {'appId': app_id, 'first': limit}
            result = await self.execute_query_with_fallback(client, query, variables=variables)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve releases", "details": result['errors']}
            
            releases = result.get('data', {}).get('app', {}).get('releases', {}).get('nodes', [])
            
            return {
                'releases': releases,
                'total_count': len(releases),
                'app_id': app_id,
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_releases',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_releases: {e}")
            return {"error": str(e)}
    
    async def handle_get_volumes(self, args):
        """Handle get_volumes tool call"""
        return {"error": "get_volumes not yet implemented - use execute_nife_query for custom queries"}
    
    async def handle_get_certificates(self, args):
        """Handle get_certificates tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            hostname = args.get('hostname')
            
            if app_id:
                query = """
                query GetCertificates($appId: ID!) {
                    app(id: $appId) {
                        certificates {
                            nodes {
                                id
                                hostname
                                source
                                configured
                                certificateAuthority
                                clientStatus
                                createdAt
                                issued {
                                    serial
                                    subject
                                    issuer
                                    expiresAt
                                }
                            }
                        }
                    }
                }
                """
                variables = {'appId': app_id}
            else:
                query = """
                query GetAllCertificates {
                    certificates {
                        nodes {
                            id
                            hostname
                            source
                            configured
                            certificateAuthority
                            clientStatus
                            createdAt
                        }
                    }
                }
                """
                variables = {}
            
            result = await self.execute_query_with_fallback(client, query, variables=variables)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve certificates", "details": result['errors']}
            
            if app_id:
                certificates = result.get('data', {}).get('app', {}).get('certificates', {}).get('nodes', [])
            else:
                certificates = result.get('data', {}).get('certificates', {}).get('nodes', [])
            
            # Filter by hostname if specified
            if hostname:
                certificates = [cert for cert in certificates if cert.get('hostname') == hostname]
            
            return {
                'certificates': certificates,
                'total_count': len(certificates),
                'filters': {'app_id': app_id, 'hostname': hostname},
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_certificates',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_certificates: {e}")
            return {"error": str(e)}
    
    async def handle_get_ip_addresses(self, args):
        """Handle get_ip_addresses tool call"""
        return {"error": "get_ip_addresses not yet implemented - use execute_nife_query for custom queries"}
    
    async def handle_get_secrets(self, args):
        """Handle get_secrets tool call"""
        try:
            access_token = args.get('access_token')
            if not access_token:
                return {"error": "Access token is required"}
            
            client = NifeGraphQLClient(access_token)
            app_id = args.get('app_id')
            
            query = """
            query GetSecrets($appId: ID!) {
                app(id: $appId) {
                    secrets {
                        name
                        digest
                        createdAt
                    }
                }
            }
            """
            
            variables = {'appId': app_id}
            result = await self.execute_query_with_fallback(client, query, variables=variables)
            
            if 'errors' in result and 'fallback_used' not in result:
                return {"error": "Failed to retrieve secrets", "details": result['errors']}
            
            secrets = result.get('data', {}).get('app', {}).get('secrets', [])
            
            return {
                'secrets': secrets,
                'total_count': len(secrets),
                'app_id': app_id,
                'metadata': {
                    'source': 'nife.io',
                    'operation': 'get_secrets',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'note': 'Secret values are not returned for security reasons'
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_secrets: {e}")
            return {"error": str(e)}
    
    # Placeholder mutation handlers
    async def handle_update_app(self, args):
        """Handle update_app tool call"""
        return {"error": "update_app not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_delete_app(self, args):
        """Handle delete_app tool call"""
        return {"error": "delete_app not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_restart_app(self, args):
        """Handle restart_app tool call"""
        return {"error": "restart_app not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_create_organization(self, args):
        """Handle create_organization tool call"""
        return {"error": "create_organization not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_update_organization(self, args):
        """Handle update_organization tool call"""  
        return {"error": "update_organization not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_invite_user(self, args):
        """Handle invite_user tool call"""
        return {"error": "invite_user not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_update_user(self, args):
        """Handle update_user tool call"""
        return {"error": "update_user not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_remove_user(self, args):
        """Handle remove_user tool call"""
        return {"error": "remove_user not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_unset_secret(self, args):
        """Handle unset_secret tool call"""
        return {"error": "unset_secret not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_add_certificate(self, args):
        """Handle add_certificate tool call"""
        return {"error": "add_certificate not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_remove_certificate(self, args):
        """Handle remove_certificate tool call"""
        return {"error": "remove_certificate not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_create_volume(self, args):
        """Handle create_volume tool call"""
        return {"error": "create_volume not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_delete_volume(self, args):
        """Handle delete_volume tool call"""
        return {"error": "delete_volume not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_update_nife_context(self, args):
        """Handle update_nife_context tool call"""
        return {"error": "update_nife_context not yet implemented - use execute_nife_query for custom mutations"}
    
    async def handle_request(self, request: dict):
        """Handle MCP JSON-RPC requests"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        logger.info(f"Handling MCP request: {method}")
        
        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "nife-mcp-server",
                            "version": "2.0.0"
                        }
                    }
                }
            
            elif method == "notifications/initialized":
                logger.info("Enhanced Nife MCP server initialized successfully")
                return None  # No response for notifications
            
            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": tool["name"],
                                "description": tool["description"],
                                "inputSchema": tool["inputSchema"]
                            }
                            for tool in self.tools.values()
                        ]
                    }
                }
            
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_arguments = params.get("arguments", {})
                
                result = await self.handle_tool_call(tool_name, tool_arguments)
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2)
                            }
                        ]
                    }
                }
            
            else:
                raise Exception(f"Unknown method: {method}")
                
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
    
    async def run(self):
        """Main MCP server loop"""
        logger.info("Starting Enhanced Nife MCP server v2.0.0...")
        logger.info(f"Available tools: {len(self.tools)}")
        logger.info("Features: comprehensive queries, mutations, automatic retry, fallback support")
        
        while True:
            try:
                # Read JSON-RPC request from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    logger.info("No more input, exiting MCP loop")
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                logger.info(f"Received MCP request: {line}")
                
                # Parse and handle request
                request = json.loads(line)
                response = await self.handle_request(request)
                
                # Send response to stdout
                if response is not None:
                    response_json = json.dumps(response)
                    print(response_json, flush=True)  # This goes to stdout for MCP client
                    logger.info(f"Sent MCP response: {response_json}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    }
                }
                print(json.dumps(error_response), flush=True)
                
            except Exception as e:
                logger.error(f"Unexpected MCP error: {e}")
                break
        
        logger.info("Enhanced Nife MCP server stopped")

async def main():
    """Main entry point"""
    server = NifeMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())