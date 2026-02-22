#!/usr/bin/env python3
"""
Intelligent Schema Manager for Nife.io GraphQL API
Automatically discovers and generates tools from GraphQL schema
"""
import json
import logging
import os
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Schema cache location and TTL (24 hours)
CACHE_DIR = Path.home() / ".nife"
CACHE_FILE = CACHE_DIR / "schema_cache.json"
CACHE_TTL_SECONDS = 86400  # 24 hours

class SchemaManager:
    """Manages GraphQL schema introspection and intelligent query building"""
    
    def __init__(self, api_url: str = "https://api.nife.io/graphql", access_token: Optional[str] = None):
        self.api_url = api_url
        self.access_token = access_token
        self.schema: Optional[Dict] = None
        self.queries_cache: Dict[str, Dict] = {}
        self.mutations_cache: Dict[str, Dict] = {}
        self.types_cache: Dict[str, Dict] = {}
        self.schema_loaded = False

    # ------------------------------------------------------------------
    # Schema caching
    # ------------------------------------------------------------------

    def _load_cached_schema(self) -> bool:
        """Try to load schema from disk cache. Returns True on success."""
        try:
            if not CACHE_FILE.exists():
                return False
            age = time.time() - CACHE_FILE.stat().st_mtime
            if age > CACHE_TTL_SECONDS:
                logger.info("Schema cache expired, will refresh from API")
                return False
            with CACHE_FILE.open() as f:
                self.schema = json.load(f)
            self._build_caches()
            self.schema_loaded = True
            logger.info(f"✓ Schema loaded from cache (age {int(age)}s)")
            logger.info(f"  - {len(self.queries_cache)} queries")
            logger.info(f"  - {len(self.mutations_cache)} mutations")
            logger.info(f"  - {len(self.types_cache)} types")
            return True
        except Exception as e:
            logger.warning(f"Could not read schema cache: {e}")
            return False

    def _save_schema_cache(self) -> None:
        """Persist schema to disk cache."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w") as f:
                json.dump(self.schema, f)
            logger.info(f"Schema cached to {CACHE_FILE}")
        except Exception as e:
            logger.warning(f"Could not save schema cache: {e}")
    
    def load_schema(self, force_refresh: bool = False) -> bool:
        """Load GraphQL schema via introspection query, with disk caching.

        Args:
            force_refresh: Skip cache and always fetch from API.
        """
        if not force_refresh and self._load_cached_schema():
            return True

        return self._fetch_schema_from_api()

    def _fetch_schema_from_api(self) -> bool:
        """Fetch schema from nife.io API via introspection."""
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
                self.api_url,
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
            logger.info(f"✓ Schema loaded from API")
            logger.info(f"  - {len(self.queries_cache)} queries")
            logger.info(f"  - {len(self.mutations_cache)} mutations")
            logger.info(f"  - {len(self.types_cache)} types")

            self._save_schema_cache()
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
        Build a GraphQL mutation dynamically.

        Reads actual argument names from the schema instead of assuming
        they are always called 'input'.

        Args:
            mutation_name: Name of the mutation
            input_data: Input data for mutation (passed to first argument)
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
            selected_fields = self.get_available_fields(return_type, include_nested=False)
            fields_str = self._build_fields_string(selected_fields, return_type)

        # Resolve the actual first argument name from the schema
        args = mutation_def.get('args', [])
        arg_name = args[0]['name'] if args else 'input'

        # Build input string
        input_str = self._build_input_string(input_data)

        # Construct mutation
        mutation = f"""
        mutation {mutation_name.capitalize()} {{
            {mutation_name}({arg_name}: {{{input_str}}}) {{
                {fields_str}
            }}
        }}
        """

        return mutation.strip()
    
    def _build_fields_string(self, fields: List[str], parent_type: str, depth: int = 0) -> str:
        """Build fields string with nested expansion.

        Falls back to '__typename' when no scalar fields are available so
        the generated query is always syntactically valid.
        """
        if not fields:
            return '__typename'

        if depth > 2:  # Prevent infinite recursion
            return '\n'.join(fields) if fields else '__typename'

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
                    # No scalar sub-fields — request __typename to keep query valid
                    result.append(f"{field_name} {{ __typename }}")

        return '\n'.join(result) if result else '__typename'
    
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
