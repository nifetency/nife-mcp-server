from flask import Blueprint, jsonify, request
import requests
import json
import os
import logging
from datetime import datetime, timezone
from functools import wraps
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp_bp = Blueprint('mcp', __name__)

# Nife.io GraphQL API endpoint
NIFE_GRAPHQL_ENDPOINT = "https://api.nife.io/graphql"

class NifeGraphQLClient:
    def __init__(self, access_token=None):
        self.access_token = access_token
        self.endpoint = NIFE_GRAPHQL_ENDPOINT
    
    def execute_query(self, query, variables=None, timeout=30):
        """Execute a GraphQL query against the Nife.io API"""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'nife-mcp-server/1.0.0'
        }
        
        # Add authorization header if token is provided
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        
        payload = {
            'query': query
        }
        
        if variables:
            payload['variables'] = variables
        
        start_time = time.time()
        
        try:
            logger.info(f"Executing GraphQL query: {query[:100]}...")
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=timeout
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"GraphQL query completed in {elapsed_time:.2f}s")
            
            response.raise_for_status()
            result = response.json()
            
            # Log errors if they exist
            if 'errors' in result:
                logger.error(f"GraphQL errors: {result['errors']}")
            
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"GraphQL query timeout after {timeout}s")
            return {
                'errors': [{'message': f'Request timeout after {timeout} seconds'}]
            }
        except requests.exceptions.ConnectionError:
            logger.error("Connection error to Nife.io API")
            return {
                'errors': [{'message': 'Connection error to Nife.io API'}]
            }
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return {
                'errors': [{'message': f'HTTP error: {str(e)}'}]
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return {
                'errors': [{'message': f'Request failed: {str(e)}'}]
            }
        except json.JSONDecodeError:
            logger.error("Invalid JSON response from API")
            return {
                'errors': [{'message': 'Invalid JSON response from API'}]
            }

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        if not access_token:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Please provide a Bearer token in the Authorization header or set NIFE_ACCESS_TOKEN environment variable'
            }), 401
        
        # Store token in request context for use in the route
        request.access_token = access_token
        return f(*args, **kwargs)
    
    return decorated_function

def get_current_timestamp():
    """Get current timestamp in ISO format"""
    return datetime.now(timezone.utc).isoformat()

def validate_json_request():
    """Validate that request contains valid JSON"""
    if not request.is_json:
        return False, "Request must be JSON"
    
    try:
        data = request.json
        if data is None:
            return False, "Request body is required"
        return True, data
    except Exception as e:
        return False, f"Invalid JSON: {str(e)}"

@mcp_bp.route('/mcp/context', methods=['GET'])
def get_model_context():
    """Get model context from Nife.io GraphQL API"""
    try:
        # Get access token from request headers or environment
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        # Get query parameters with validation
        context_type = request.args.get('type', 'general')
        limit = request.args.get('limit', 10, type=int)
        
        # Validate limit parameter
        if limit < 1 or limit > 100:
            return jsonify({
                'error': 'Invalid limit parameter',
                'message': 'Limit must be between 1 and 100'
            }), 400
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(access_token)
        
        # Try multiple query patterns with fallback
        # First attempt: Standard nodes pattern (most common)
        query_v1 = """
        query GetApps {
            apps(first: %d) {
                nodes {
                    id
                    name
                    status
                    organizationId
                    createdAt
                    updatedAt
                }
            }
        }
        """ % limit
        
        # Try the first query
        result = client.execute_query(query_v1)
        
        # If first query fails, try alternative structures
        if 'errors' in result:
            logger.warning("First query pattern failed, trying alternative...")
            
            # Second attempt: Simple list without pagination
            query_v2 = """
            query GetApps {
                apps {
                    id
                    name
                    status
                    organizationId
                    createdAt
                    updatedAt
                }
            }
            """
            
            result = client.execute_query(query_v2)
            
            # If that fails too, try with organizations query
            if 'errors' in result:
                logger.warning("Second query pattern failed, trying organizations...")
                
                query_v3 = """
                query GetContext {
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
                
                result = client.execute_query(query_v3)
        
        variables = None
        
        if 'errors' in result:
            return jsonify({
                'error': 'GraphQL query failed',
                'details': result['errors']
            }), 400
        
        # Transform GraphQL response to MCP format
        mcp_response = {
            'context_type': context_type,
            'data': result.get('data', {}),
            'metadata': {
                'source': 'nife.io',
                'timestamp': get_current_timestamp(),
                'query_parameters': {
                    'type': context_type,
                    'limit': limit
                },
                'api_version': 'v1'
            }
        }
        
        return jsonify(mcp_response)
        
    except Exception as e:
        logger.error(f"Error in get_model_context: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/context', methods=['POST'])
@require_auth
def update_model_context():
    """Update model context via Nife.io GraphQL API"""
    try:
        # Validate JSON request
        is_valid, data = validate_json_request()
        if not is_valid:
            return jsonify({'error': data}), 400
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(request.access_token)
        
        # Example mutation - adapt based on actual schema
        mutation = """
        mutation UpdateApp($input: UpdateAppInput!) {
            updateApp(input: $input) {
                app {
                    id
                    name
                    status
                    description
                    updatedAt
                }
                errors {
                    field
                    message
                }
            }
        }
        """
        
        variables = {
            'input': data
        }
        
        result = client.execute_query(mutation, variables)
        
        if 'errors' in result:
            return jsonify({
                'error': 'GraphQL mutation failed',
                'details': result['errors']
            }), 400
        
        # Check for application-level errors
        response_data = result.get('data', {})
        if 'updateApp' in response_data and 'errors' in response_data['updateApp']:
            app_errors = response_data['updateApp']['errors']
            if app_errors:
                return jsonify({
                    'error': 'Update validation failed',
                    'details': app_errors
                }), 422
        
        # Transform GraphQL response to MCP format
        mcp_response = {
            'success': True,
            'data': response_data,
            'metadata': {
                'source': 'nife.io',
                'operation': 'update',
                'timestamp': get_current_timestamp()
            }
        }
        
        return jsonify(mcp_response)
        
    except Exception as e:
        logger.error(f"Error in update_model_context: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/schema', methods=['GET'])
def get_schema():
    """Get the GraphQL schema from Nife.io API with caching support"""
    try:
        # Get access token from request headers or environment
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        # Check if client wants a simplified schema
        simplified = request.args.get('simplified', 'false').lower() == 'true'
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(access_token)
        
        if simplified:
            # Simplified schema query for basic type information
            query = """
            query GetSimplifiedSchema {
                __schema {
                    queryType { name }
                    mutationType { name }
                    types {
                        name
                        kind
                        description
                        fields {
                            name
                            type {
                                name
                                kind
                            }
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
                        ...FullType
                    }
                    directives {
                        name
                        description
                        locations
                        args {
                            ...InputValue
                        }
                    }
                }
            }
            
            fragment FullType on __Type {
                kind
                name
                description
                fields(includeDeprecated: true) {
                    name
                    description
                    args {
                        ...InputValue
                    }
                    type {
                        ...TypeRef
                    }
                    isDeprecated
                    deprecationReason
                }
                inputFields {
                    ...InputValue
                }
                interfaces {
                    ...TypeRef
                }
                enumValues(includeDeprecated: true) {
                    name
                    description
                    isDeprecated
                    deprecationReason
                }
                possibleTypes {
                    ...TypeRef
                }
            }
            
            fragment InputValue on __InputValue {
                name
                description
                type { ...TypeRef }
                defaultValue
            }
            
            fragment TypeRef on __Type {
                kind
                name
                ofType {
                    kind
                    name
                    ofType {
                        kind
                        name
                        ofType {
                            kind
                            name
                            ofType {
                                kind
                                name
                                ofType {
                                    kind
                                    name
                                    ofType {
                                        kind
                                        name
                                        ofType {
                                            kind
                                            name
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
        
        result = client.execute_query(query, timeout=60)  # Longer timeout for schema introspection
        
        if 'errors' in result:
            return jsonify({
                'error': 'Schema introspection failed',
                'details': result['errors']
            }), 400
        
        return jsonify({
            'schema': result.get('data', {}),
            'metadata': {
                'source': 'nife.io',
                'type': 'graphql_schema',
                'simplified': simplified,
                'timestamp': get_current_timestamp()
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_schema: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/query', methods=['POST'])
@require_auth
def execute_custom_query():
    """Execute a custom GraphQL query against Nife.io API"""
    try:
        # Validate JSON request
        is_valid, data = validate_json_request()
        if not is_valid:
            return jsonify({'error': data}), 400
        
        if 'query' not in data:
            return jsonify({'error': 'GraphQL query is required'}), 400
        
        query = data['query']
        variables = data.get('variables', {})
        timeout = data.get('timeout', 30)
        
        # Validate timeout
        if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
            return jsonify({
                'error': 'Invalid timeout',
                'message': 'Timeout must be an integer between 1 and 300 seconds'
            }), 400
        
        # Basic query validation
        if not query.strip():
            return jsonify({'error': 'Query cannot be empty'}), 400
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(request.access_token)
        
        result = client.execute_query(query, variables, timeout)
        
        if 'errors' in result:
            return jsonify({
                'error': 'GraphQL query failed',
                'details': result['errors']
            }), 400
        
        return jsonify({
            'data': result.get('data', {}),
            'metadata': {
                'source': 'nife.io',
                'operation': 'custom_query',
                'timestamp': get_current_timestamp(),
                'query_hash': hash(query.strip()) & 0x7FFFFFFF  # Positive 32-bit hash
            }
        })
        
    except Exception as e:
        logger.error(f"Error in execute_custom_query: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/health', methods=['GET'])
def health_check():
    """Health check endpoint for the MCP server"""
    try:
        # Test connection to Nife.io API
        client = NifeGraphQLClient()
        test_query = """
        query HealthCheck {
            __typename
        }
        """
        
        result = client.execute_query(test_query, timeout=5)
        api_healthy = 'errors' not in result or len(result.get('errors', [])) == 0
        
        return jsonify({
            'status': 'healthy' if api_healthy else 'degraded',
            'service': 'nife-mcp-server',
            'version': '1.0.0',
            'timestamp': get_current_timestamp(),
            'api_connection': 'healthy' if api_healthy else 'unhealthy',
            'endpoints': {
                'get_context': '/api/mcp/context [GET]',
                'update_context': '/api/mcp/context [POST] (auth required)',
                'get_schema': '/api/mcp/schema [GET]',
                'custom_query': '/api/mcp/query [POST] (auth required)',
                'health': '/api/mcp/health [GET]'
            },
            'features': {
                'authentication': True,
                'request_validation': True,
                'error_logging': True,
                'schema_introspection': True,
                'custom_queries': True
            }
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'service': 'nife-mcp-server',
            'version': '1.0.0',
            'timestamp': get_current_timestamp(),
            'error': str(e)
        }), 500

# Error handlers
@mcp_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Endpoint not found',
        'message': 'The requested MCP endpoint does not exist'
    }), 404

@mcp_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'error': 'Method not allowed',
        'message': 'The HTTP method is not allowed for this endpoint'
    }), 405

@mcp_bp.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500