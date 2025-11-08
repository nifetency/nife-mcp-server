#!/usr/bin/env python3
"""
Quick script to check Nife.io GraphQL API schema
and identify what mutations/queries are actually available
"""
import os
import sys
import requests
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.nife_mcp_server.routes.mcp import NifeGraphQLClient

def check_schema():
    """Check the actual Nife.io GraphQL schema"""
    
    # Get access token from environment
    access_token = os.environ.get('NIFE_ACCESS_TOKEN')
    if not access_token:
        print("❌ NIFE_ACCESS_TOKEN not set")
        return
    
    print("🔍 Checking Nife.io GraphQL API Schema...")
    print("=" * 60)
    
    client = NifeGraphQLClient(access_token)
    
    # Introspection query to get all mutations and queries
    introspection_query = """
    query IntrospectionQuery {
        __schema {
            queryType {
                name
                fields {
                    name
                    description
                }
            }
            mutationType {
                name
                fields {
                    name
                    description
                    args {
                        name
                        type {
                            name
                            kind
                        }
                    }
                }
            }
        }
    }
    """
    
    try:
        result = client.execute_query(introspection_query, timeout=30)
        
        if 'errors' in result:
            print(f"❌ Schema introspection failed: {result['errors']}")
            return
        
        schema = result.get('data', {}).get('__schema', {})
        
        # Print available queries
        print("\n📊 AVAILABLE QUERIES:")
        print("-" * 60)
        query_type = schema.get('queryType', {})
        queries = query_type.get('fields', [])
        
        for query in queries:
            name = query.get('name', 'unknown')
            desc = query.get('description', 'No description')
            print(f"  • {name}: {desc}")
        
        print(f"\n  Total Queries: {len(queries)}")
        
        # Print available mutations
        print("\n🔧 AVAILABLE MUTATIONS:")
        print("-" * 60)
        mutation_type = schema.get('mutationType', {})
        mutations = mutation_type.get('fields', [])
        
        for mutation in mutations:
            name = mutation.get('name', 'unknown')
            desc = mutation.get('description', 'No description')
            args = mutation.get('args', [])
            arg_names = [arg.get('name', '') for arg in args]
            print(f"  • {name}: {desc}")
            if arg_names:
                print(f"    Args: {', '.join(arg_names)}")
        
        print(f"\n  Total Mutations: {len(mutations)}")
        
        # Compare with our implemented tools
        print("\n🎯 COMPARISON WITH IMPLEMENTED TOOLS:")
        print("-" * 60)
        
        implemented_mutations = [
            'createApp', 'updateApp', 'deleteApp', 'deployApp', 'scaleApp', 'restartApp',
            'createOrganization', 'updateOrganization',
            'inviteUser', 'updateUser', 'removeUser',
            'setSecret', 'unsetSecret',
            'addCertificate', 'removeCertificate',
            'createVolume', 'deleteVolume'
        ]
        
        available_mutation_names = [m.get('name') for m in mutations]
        
        print("\n✅ Mutations we have that API supports:")
        for mut in implemented_mutations:
            if mut in available_mutation_names:
                print(f"  • {mut}")
        
        print("\n❌ Mutations we have but API might not support:")
        for mut in implemented_mutations:
            if mut not in available_mutation_names:
                print(f"  • {mut} (check naming/availability)")
        
        print("\n💡 Mutations API has that we don't implement:")
        for mut in available_mutation_names:
            # Convert to snake_case equivalent
            snake_case = ''.join(['_'+c.lower() if c.isupper() else c for c in mut]).lstrip('_')
            if snake_case not in [m.replace('_', '').lower() for m in implemented_mutations]:
                print(f"  • {mut} (could add as {snake_case})")
        
        # Save full schema to file
        schema_file = '/Users/rentsher/nife-mcp-server/nife_api_schema.json'
        with open(schema_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n💾 Full schema saved to: {schema_file}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_schema()
