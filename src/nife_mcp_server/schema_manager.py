#!/usr/bin/env python3
"""
Intelligent Schema Manager for Nife.io GraphQL API
Automatically discovers and generates tools from GraphQL schema
"""
import logging
import requests
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SchemaManager:
    """Manages GraphQL and REST API schema introspection and intelligent query building"""
    
    def __init__(
        self, 
        graphql_url: Optional[str] = None, 
        rest_api_url: Optional[str] = None,
        access_token: Optional[str] = None
    ):
        # Load from environment variables if not provided
        self.graphql_url = graphql_url or os.getenv('GRAPHQL_ENDPOINT')
        self.rest_api_url = rest_api_url or os.getenv('REST_API_ENDPOINT', '')
        self.access_token = access_token or os.getenv('API_ACCESS_TOKEN')
        
        self.schema: Optional[Dict] = None
        self.rest_api_spec: Optional[Dict] = None
        self.queries_cache: Dict[str, Dict] = {}
        self.mutations_cache: Dict[str, Dict] = {}
        self.types_cache: Dict[str, Dict] = {}
        self.rest_endpoints_cache: Dict[str, Dict] = {}
        self.schema_loaded = False
        self.rest_spec_loaded = False
    
    def load_schema(self) -> bool:
        """Load GraphQL schema via introspection query"""
        introspection_query = """
        query IntrospectionQuery {
            __schema {
                queryType { name }
                mutationType { name }
                types {
                    kind
                    name
                    description
                    fields(includeDeprecated: true) {
                        name
                        description
                        type {
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
                        args {
                            name
                            description
                            type {
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
                            defaultValue
                        }
                        isDeprecated
                        deprecationReason
                    }
                    inputFields {
                        name
                        description
                        type {
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
                        defaultValue
                    }
                    interfaces {
                        name
                    }
                    possibleTypes {
                        name
                    }
                    enumValues(includeDeprecated: true) {
                        name
                        description
                        isDeprecated
                        deprecationReason
                    }
                }
            }
        }
        """
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            logger.info("Loading GraphQL schema via introspection...")
            response = requests.post(
                self.graphql_url,
                json={"query": introspection_query},
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"HTTP {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            if 'errors' in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return False
            
            # Store schema
            self.schema = data['data']['__schema']
            
            # Build caches
            self._build_caches()
            
            self.schema_loaded = True
            logger.info(f"✓ GraphQL schema loaded successfully")
            logger.info(f"  - GraphQL URL: {self.graphql_url}")
            logger.info(f"  - {len(self.queries_cache)} queries")
            logger.info(f"  - {len(self.mutations_cache)} mutations")
            logger.info(f"  - {len(self.types_cache)} types")
            
            return True
            
        except Exception as e:
            logger.error(f"Schema loading failed: {e}")
            return False
    
    def _build_caches(self):
        """Build internal caches from schema"""
        if not self.schema:
            return
        
        # Build types cache
        for type_def in self.schema['types']:
            type_name = type_def['name']
            self.types_cache[type_name] = type_def
        
        # Find query and mutation root types
        query_type = self.schema.get('queryType', {}).get('name')
        mutation_type = self.schema.get('mutationType', {}).get('name')
        
        # Build queries cache
        if query_type and query_type in self.types_cache:
            query_def = self.types_cache[query_type]
            if query_def.get('fields'):
                for field in query_def['fields']:
                    self.queries_cache[field['name']] = field
        
        # Build mutations cache
        if mutation_type and mutation_type in self.types_cache:
            mutation_def = self.types_cache[mutation_type]
            if mutation_def.get('fields'):
                for field in mutation_def['fields']:
                    self.mutations_cache[field['name']] = field
    
    def get_available_queries(self) -> List[Dict]:
        """Get list of all available queries"""
        return [
            {
                'name': name,
                'description': query.get('description', 'No description'),
                'args': query.get('args', []),
                'returnType': self._get_base_type(query['type'])
            }
            for name, query in self.queries_cache.items()
            if not name.startswith('_')  # Skip introspection queries
        ]
    
    def get_available_mutations(self) -> List[Dict]:
        """Get list of all available mutations"""
        return [
            {
                'name': name,
                'description': mutation.get('description', 'No description'),
                'args': mutation.get('args', []),
                'returnType': self._get_base_type(mutation['type'])
            }
            for name, mutation in self.mutations_cache.items()
        ]
    
    def get_available_fields(self, type_name: str, include_nested: bool = False) -> List[str]:
        """Get available fields for a type"""
        if type_name not in self.types_cache:
            return []
        
        type_def = self.types_cache[type_name]
        fields = type_def.get('fields', [])
        
        if not include_nested:
            # Only return scalar fields
            return [
                field['name'] 
                for field in fields 
                if self._is_scalar_type(self._get_base_type(field['type']))
            ]
        else:
            # Return all fields
            return [field['name'] for field in fields]
    
    def build_query(
        self, 
        query_name: str, 
        args: Optional[Dict] = None,
        fields: str = 'auto',
        custom_fields: Optional[List[str]] = None
    ) -> str:
        """
        Build a GraphQL query dynamically
        
        Args:
            query_name: Name of the query
            args: Query arguments
            fields: Field selection mode ('auto', 'all', 'custom')
            custom_fields: Custom field list (required if fields='custom')
        """
        if not self.schema_loaded:
            raise RuntimeError("Schema not loaded. Call load_schema() first.")
        
        if query_name not in self.queries_cache:
            raise ValueError(f"Query '{query_name}' not found in schema")
        
        query_def = self.queries_cache[query_name]
        return_type = self._get_base_type(query_def['type'])
        
        # Determine fields to request
        if fields == 'custom':
            if not custom_fields:
                raise ValueError("custom_fields required when fields='custom'")
            selected_fields = custom_fields
        elif fields == 'all':
            selected_fields = self.get_available_fields(return_type, include_nested=True)
        else:  # 'auto'
            selected_fields = self.get_available_fields(return_type, include_nested=False)
        
        # Build fields string with nesting
        fields_str = self._build_fields_string(selected_fields, return_type)
        
        # Build arguments string
        args_str = self._build_args_string(args) if args else ""
        
        # Construct query
        query = f"""
        query {query_name.capitalize()} {{
            {query_name}{args_str} {{
                {fields_str}
            }}
        }}
        """
        
        return query.strip()
    
    def build_mutation(
        self,
        mutation_name: str,
        input_data: Dict,
        return_fields: Optional[List[str]] = None
    ) -> str:
        """
        Build a GraphQL mutation dynamically
        
        Args:
            mutation_name: Name of the mutation
            input_data: Input data for mutation
            return_fields: Fields to return (auto-detected if None)
        """
        if not self.schema_loaded:
            raise RuntimeError("Schema not loaded. Call load_schema() first.")
        
        if mutation_name not in self.mutations_cache:
            raise ValueError(f"Mutation '{mutation_name}' not found in schema")
        
        mutation_def = self.mutations_cache[mutation_name]
        return_type = self._get_base_type(mutation_def['type'])
        
        # Determine return fields
        if return_fields:
            fields_str = '\n'.join(return_fields)
        else:
            # Auto-detect from return type
            selected_fields = self.get_available_fields(return_type, include_nested=False)
            fields_str = self._build_fields_string(selected_fields, return_type)
        
        # Build input string
        input_str = self._build_input_string(input_data)
        
        # Construct mutation
        mutation = f"""
        mutation {mutation_name.capitalize()} {{
            {mutation_name}(input: {{{input_str}}}) {{
                {fields_str}
            }}
        }}
        """
        
        return mutation.strip()
    
    def _build_fields_string(self, fields: List[str], parent_type: str, depth: int = 0) -> str:
        """Build fields string with nested expansion"""
        if depth > 2:  # Prevent infinite recursion
            return '\n'.join(fields)
        
        if parent_type not in self.types_cache:
            return '\n'.join(fields)
        
        type_def = self.types_cache[parent_type]
        type_fields = {f['name']: f for f in type_def.get('fields', [])}
        
        result = []
        for field_name in fields:
            if field_name not in type_fields:
                result.append(field_name)
                continue
            
            field_def = type_fields[field_name]
            field_type = self._get_base_type(field_def['type'])
            
            # If scalar, just add field name
            if self._is_scalar_type(field_type):
                result.append(field_name)
            # If object, expand recursively
            else:
                nested_fields = self.get_available_fields(field_type, include_nested=False)
                if nested_fields:
                    nested_str = self._build_fields_string(nested_fields, field_type, depth + 1)
                    result.append(f"{field_name} {{\n{nested_str}\n}}")
                else:
                    result.append(field_name)
        
        return '\n'.join(result)
    
    def _build_args_string(self, args: Dict) -> str:
        """Build arguments string for query"""
        if not args:
            return ""
        
        arg_parts = []
        for key, value in args.items():
            if isinstance(value, str):
                arg_parts.append(f'{key}: "{value}"')
            elif isinstance(value, bool):
                arg_parts.append(f'{key}: {str(value).lower()}')
            elif isinstance(value, (int, float)):
                arg_parts.append(f'{key}: {value}')
            elif isinstance(value, list):
                list_str = ', '.join([f'"{v}"' if isinstance(v, str) else str(v) for v in value])
                arg_parts.append(f'{key}: [{list_str}]')
            elif isinstance(value, dict):
                dict_str = self._build_input_string(value)
                arg_parts.append(f'{key}: {{{dict_str}}}')
        
        return f"({', '.join(arg_parts)})"
    
    def _build_input_string(self, input_data: Dict) -> str:
        """Build input string for mutation"""
        parts = []
        for key, value in input_data.items():
            if isinstance(value, str):
                parts.append(f'{key}: "{value}"')
            elif isinstance(value, bool):
                parts.append(f'{key}: {str(value).lower()}')
            elif isinstance(value, (int, float)):
                parts.append(f'{key}: {value}')
            elif isinstance(value, list):
                list_str = ', '.join([f'"{v}"' if isinstance(v, str) else str(v) for v in value])
                parts.append(f'{key}: [{list_str}]')
            elif isinstance(value, dict):
                nested_str = self._build_input_string(value)
                parts.append(f'{key}: {{{nested_str}}}')
        
        return ', '.join(parts)
    
    def _get_base_type(self, type_info: Dict) -> str:
        """Unwrap type to get base type name"""
        if not type_info:
            return "Unknown"
        
        # Handle NON_NULL wrapper
        if type_info.get('kind') == 'NON_NULL':
            return self._get_base_type(type_info.get('ofType', {}))
        
        # Handle LIST wrapper
        if type_info.get('kind') == 'LIST':
            return self._get_base_type(type_info.get('ofType', {}))
        
        # Return the actual type name
        return type_info.get('name', 'Unknown')
    
    def _is_scalar_type(self, type_name: str) -> bool:
        """Check if a type is scalar"""
        scalar_types = {
            'String', 'Int', 'Float', 'Boolean', 'ID',
            'DateTime', 'Date', 'Time', 'JSON', 'UUID'
        }
        return type_name in scalar_types
    
    def get_type_info(self, type_name: str) -> Optional[Dict]:
        """Get detailed information about a type"""
        return self.types_cache.get(type_name)
    
    def search_queries(self, search_term: str) -> List[Dict]:
        """Search for queries by name or description"""
        search_lower = search_term.lower()
        results = []
        
        for name, query in self.queries_cache.items():
            if search_lower in name.lower():
                results.append({
                    'name': name,
                    'description': query.get('description', 'No description'),
                    'match_type': 'name'
                })
            elif search_lower in (query.get('description', '')).lower():
                results.append({
                    'name': name,
                    'description': query.get('description', 'No description'),
                    'match_type': 'description'
                })
        
        return results
    
    def get_query_signature(self, query_name: str) -> Optional[str]:
        """Get human-readable signature for a query"""
        if query_name not in self.queries_cache:
            return None
        
        query_def = self.queries_cache[query_name]
        args = query_def.get('args', [])
        return_type = self._get_base_type(query_def['type'])
        
        arg_strs = []
        for arg in args:
            arg_type = self._get_base_type(arg['type'])
            required = arg['type'].get('kind') == 'NON_NULL'
            arg_str = f"{arg['name']}: {arg_type}" + (" (required)" if required else " (optional)")
            arg_strs.append(arg_str)
        
        args_signature = ', '.join(arg_strs) if arg_strs else 'no arguments'
        return f"{query_name}({args_signature}) -> {return_type}"
    
    # REST API Methods
    
    def load_rest_api_spec(self) -> bool:
        """
        Load REST API specification from OpenAPI/Swagger endpoint
        Supports OpenAPI 3.0 and Swagger 2.0 specifications
        """
        if not self.rest_api_url:
            logger.warning("REST_API_ENDPOINT not configured. Set it in environment variables.")
            return False
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            # Common OpenAPI spec paths
            spec_paths = [
                f"{self.rest_api_url.rstrip('/')}/openapi.json",
                f"{self.rest_api_url.rstrip('/')}/swagger.json",
                f"{self.rest_api_url.rstrip('/')}/api/openapi.json",
                f"{self.rest_api_url.rstrip('/')}/api/swagger.json",
            ]
            
            logger.info(f"Loading REST API specification from {self.rest_api_url}...")
            
            spec_data = None
            for spec_path in spec_paths:
                try:
                    logger.info(f"Trying: {spec_path}")
                    response = requests.get(spec_path, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        spec_data = response.json()
                        logger.info(f"Successfully loaded from: {spec_path}")
                        break
                except Exception as e:
                    logger.debug(f"Failed to load from {spec_path}: {e}")
                    continue
            
            if not spec_data:
                logger.error(f"Could not find REST API specification at {self.rest_api_url}")
                return False
            
            self.rest_api_spec = spec_data
            self._build_rest_endpoints_cache()
            
            self.rest_spec_loaded = True
            logger.info(f"✓ REST API specification loaded successfully")
            logger.info(f"  - REST API URL: {self.rest_api_url}")
            logger.info(f"  - {len(self.rest_endpoints_cache)} endpoints found")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load REST API specification: {e}")
            return False
    
    def _build_rest_endpoints_cache(self):
        """Build cache of REST API endpoints from OpenAPI spec"""
        if not self.rest_api_spec:
            return
        
        paths = self.rest_api_spec.get('paths', {})
        
        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method.lower() not in ['get', 'post', 'put', 'patch', 'delete', 'options', 'head']:
                    continue
                
                endpoint_key = f"{method.upper()} {path}"
                operation_id = operation.get('operationId', endpoint_key)
                
                self.rest_endpoints_cache[operation_id] = {
                    'path': path,
                    'method': method.upper(),
                    'description': operation.get('description', operation.get('summary', 'No description')),
                    'parameters': operation.get('parameters', []),
                    'requestBody': operation.get('requestBody'),
                    'responses': operation.get('responses', {}),
                    'tags': operation.get('tags', []),
                    'operationId': operation_id
                }
    
    def get_available_rest_endpoints(self, filter_by_tag: Optional[str] = None) -> List[Dict]:
        """Get list of all available REST API endpoints"""
        if not self.rest_spec_loaded:
            logger.warning("REST API spec not loaded. Call load_rest_api_spec() first.")
            return []
        
        results = []
        for op_id, endpoint in self.rest_endpoints_cache.items():
            if filter_by_tag and filter_by_tag not in endpoint.get('tags', []):
                continue
            
            results.append({
                'operationId': op_id,
                'method': endpoint['method'],
                'path': endpoint['path'],
                'description': endpoint['description'],
                'tags': endpoint['tags'],
                'parameters': [
                    {
                        'name': p.get('name'),
                        'in': p.get('in'),
                        'required': p.get('required', False),
                        'schema': p.get('schema', {})
                    }
                    for p in endpoint.get('parameters', [])
                ]
            })
        
        return results
    
    def get_rest_endpoint_details(self, operation_id: str) -> Optional[Dict]:
        """Get detailed information about a specific REST API endpoint"""
        if operation_id not in self.rest_endpoints_cache:
            logger.warning(f"Endpoint '{operation_id}' not found")
            return None
        
        endpoint = self.rest_endpoints_cache[operation_id]
        return {
            'operationId': operation_id,
            'method': endpoint['method'],
            'path': endpoint['path'],
            'description': endpoint['description'],
            'tags': endpoint['tags'],
            'parameters': endpoint.get('parameters', []),
            'requestBody': endpoint.get('requestBody'),
            'responses': endpoint.get('responses', {})
        }
    
    def search_rest_endpoints(self, search_term: str) -> List[Dict]:
        """Search REST endpoints by operation ID, path, or description"""
        search_lower = search_term.lower()
        results = []
        
        for op_id, endpoint in self.rest_endpoints_cache.items():
            if (search_lower in op_id.lower() or 
                search_lower in endpoint['path'].lower() or
                search_lower in endpoint['description'].lower()):
                
                results.append({
                    'operationId': op_id,
                    'method': endpoint['method'],
                    'path': endpoint['path'],
                    'description': endpoint['description']
                })
        
        return results
    
    def get_rest_endpoint_signature(self, operation_id: str) -> Optional[str]:
        """Get human-readable signature for a REST endpoint"""
        if operation_id not in self.rest_endpoints_cache:
            return None
        
        endpoint = self.rest_endpoints_cache[operation_id]
        method = endpoint['method']
        path = endpoint['path']
        
        # Extract path parameters
        path_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'path']
        query_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'query']
        
        signature = f"{method} {path}"
        
        if path_params:
            param_strs = [f"{p['name']}" for p in path_params]
            signature += f" (path: {', '.join(param_strs)})"
        
        if query_params:
            param_strs = [f"{p['name']}{'*' if p.get('required') else ''}" for p in query_params]
            signature += f" (query: {', '.join(param_strs)})"
        
        if endpoint.get('requestBody'):
            signature += " (with request body)"
        
        return signature
    
    def build_rest_request(self, operation_id: str, **kwargs) -> Dict[str, Any]:
        """
        Build a REST API request configuration
        
        Args:
            operation_id: ID of the REST endpoint
            **kwargs: Request parameters (path_params, query_params, body)
        
        Returns:
            Dictionary with method, url, params, json, headers
        """
        if not self.rest_spec_loaded:
            raise RuntimeError("REST API spec not loaded. Call load_rest_api_spec() first.")
        
        if operation_id not in self.rest_endpoints_cache:
            raise ValueError(f"Endpoint '{operation_id}' not found")
        
        endpoint = self.rest_endpoints_cache[operation_id]
        
        # Build URL with path parameters
        url = self.rest_api_url.rstrip('/') + endpoint['path']
        path_params = kwargs.get('path_params', {})
        
        for key, value in path_params.items():
            url = url.replace(f"{{{key}}}", str(value))
        
        # Prepare headers
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        # Build request config
        request_config = {
            'method': endpoint['method'],
            'url': url,
            'headers': headers
        }
        
        # Add query parameters
        query_params = kwargs.get('query_params', {})
        if query_params:
            request_config['params'] = query_params
        
        # Add request body
        body = kwargs.get('body')
        if body:
            request_config['json'] = body
        
        return request_config
    
    def get_api_info(self) -> Dict[str, Any]:
        """Get information about both GraphQL and REST APIs"""
        return {
            'graphql': {
                'endpoint': self.graphql_url,
                'loaded': self.schema_loaded,
                'queries_count': len(self.queries_cache),
                'mutations_count': len(self.mutations_cache),
                'types_count': len(self.types_cache)
            },
            'rest_api': {
                'endpoint': self.rest_api_url,
                'loaded': self.rest_spec_loaded,
                'endpoints_count': len(self.rest_endpoints_cache)
            },
            'authentication': {
                'access_token_configured': bool(self.access_token)
            }
        }
