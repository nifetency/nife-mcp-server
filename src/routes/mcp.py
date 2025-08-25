from flask import Blueprint, jsonify, request
import requests
import json
import os

mcp_bp = Blueprint('mcp', __name__)

# Nife.io GraphQL API endpoint
NIFE_GRAPHQL_ENDPOINT = "https://api.nife.io/graphql"

class NifeGraphQLClient:
    def __init__(self, access_token=None):
        self.access_token = access_token
        self.endpoint = NIFE_GRAPHQL_ENDPOINT
    
    def execute_query(self, query, variables=None):
        """Execute a GraphQL query against the Nife.io API"""
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Add authorization header if token is provided
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        
        payload = {
            'query': query
        }
        
        if variables:
            payload['variables'] = variables
        
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                'errors': [{'message': f'Request failed: {str(e)}'}]
            }

@mcp_bp.route('/mcp/context', methods=['GET'])
def get_model_context():
    """Get model context from Nife.io GraphQL API"""
    try:
        # Get access token from request headers or environment
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]  # Remove 'Bearer ' prefix
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        # Get query parameters
        context_type = request.args.get('type', 'general')
        limit = request.args.get('limit', 10, type=int)
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(access_token)
        
        # Example query - this would need to be adapted based on actual Nife.io schema
        query = """
        query GetContext($limit: Int) {
            # This is a placeholder query - replace with actual Nife.io schema
            # Based on the introspection, you would use actual types and fields
            apps(limit: $limit) {
                id
                name
                status
                createdAt
                updatedAt
            }
        }
        """
        
        variables = {
            'limit': limit
        }
        
        result = client.execute_query(query, variables)
        
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
                'timestamp': None,  # Add current timestamp
                'query_parameters': {
                    'type': context_type,
                    'limit': limit
                }
            }
        }
        
        return jsonify(mcp_response)
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/context', methods=['POST'])
def update_model_context():
    """Update model context via Nife.io GraphQL API"""
    try:
        # Get access token from request headers or environment
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        # Get request data
        data = request.json
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(access_token)
        
        # Example mutation - this would need to be adapted based on actual Nife.io schema
        mutation = """
        mutation UpdateContext($input: UpdateContextInput!) {
            # This is a placeholder mutation - replace with actual Nife.io schema
            updateApp(input: $input) {
                id
                name
                status
                updatedAt
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
        
        # Transform GraphQL response to MCP format
        mcp_response = {
            'success': True,
            'data': result.get('data', {}),
            'metadata': {
                'source': 'nife.io',
                'operation': 'update',
                'timestamp': None  # Add current timestamp
            }
        }
        
        return jsonify(mcp_response)
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/schema', methods=['GET'])
def get_schema():
    """Get the GraphQL schema from Nife.io API"""
    try:
        # Get access token from request headers or environment
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(access_token)
        
        # GraphQL introspection query
        introspection_query = """
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
        
        result = client.execute_query(introspection_query)
        
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
                'timestamp': None  # Add current timestamp
            }
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/query', methods=['POST'])
def execute_custom_query():
    """Execute a custom GraphQL query against Nife.io API"""
    try:
        # Get access token from request headers or environment
        auth_header = request.headers.get('Authorization')
        access_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        else:
            access_token = os.environ.get('NIFE_ACCESS_TOKEN')
        
        # Get request data
        data = request.json
        if not data or 'query' not in data:
            return jsonify({'error': 'GraphQL query is required'}), 400
        
        query = data['query']
        variables = data.get('variables', {})
        
        # Initialize GraphQL client
        client = NifeGraphQLClient(access_token)
        
        result = client.execute_query(query, variables)
        
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
                'timestamp': None  # Add current timestamp
            }
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@mcp_bp.route('/mcp/health', methods=['GET'])
def health_check():
    """Health check endpoint for the MCP server"""
    return jsonify({
        'status': 'healthy',
        'service': 'nife-mcp-server',
        'version': '1.0.0',
        'endpoints': {
            'get_context': '/api/mcp/context [GET]',
            'update_context': '/api/mcp/context [POST]',
            'get_schema': '/api/mcp/schema [GET]',
            'custom_query': '/api/mcp/query [POST]',
            'health': '/api/mcp/health [GET]'
        }
    })

