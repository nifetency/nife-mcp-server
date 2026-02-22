#!/usr/bin/env python3
"""Script to list all organizations in Nife.io"""
import sys
import os

# Add the src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from nife_mcp_server.schema_manager import SchemaManager
from nife_mcp_server.routes.mcp import NifeGraphQLClient

# Access token from environment variable
TOKEN = os.environ.get('NIFE_ACCESS_TOKEN')
if not TOKEN:
    print("❌ Error: NIFE_ACCESS_TOKEN environment variable not set")
    print("   Run: export NIFE_ACCESS_TOKEN=$(nifectl auth token)")
    sys.exit(1)

def main():
    print("="*80)
    print("🏢 LISTING ORGANIZATIONS IN NIFE.IO")
    print("="*80)
    
    # Initialize schema manager
    print("\n📡 Loading GraphQL schema...")
    schema_mgr = SchemaManager(access_token=TOKEN)
    
    if not schema_mgr.load_schema():
        print("❌ Failed to load schema")
        return 1
    
    print("✅ Schema loaded successfully!")
    
    # Search for organization-related queries
    print("\n🔍 Searching for organization queries...")
    org_queries = schema_mgr.search_queries("organization")
    
    if org_queries:
        print(f"\n📋 Found {len(org_queries)} organization-related queries:")
        for q in org_queries:
            print(f"   • {q['name']}: {q['description']}")
    else:
        print("⚠️  No organization queries found by search")
    
    # List all queries to see what's available
    print("\n📚 Checking all available queries...")
    all_queries = schema_mgr.get_available_queries()
    
    # Filter for organization-related queries
    org_related = [q for q in all_queries if 'org' in q['name'].lower()]
    
    if org_related:
        print(f"\n✓ Found {len(org_related)} queries with 'org' in the name:")
        for q in org_related:
            print(f"   • {q['name']}: {q['description']}")
    
    # Try common organization query names
    print("\n" + "="*80)
    print("🎯 ATTEMPTING TO QUERY ORGANIZATIONS")
    print("="*80)
    
    client = NifeGraphQLClient(TOKEN)
    
    # Possible query names to try
    possible_queries = [
        'organizations',
        'listOrganizations',
        'getOrganizations',
        'allOrganizations',
        'myOrganizations',
        'userOrganizations'
    ]
    
    success = False
    
    for query_name in possible_queries:
        if query_name in schema_mgr.queries_cache:
            print(f"\n✓ Found query: {query_name}")
            
            try:
                # Get query signature
                signature = schema_mgr.get_query_signature(query_name)
                print(f"   Signature: {signature}")
                
                # Build the query
                query = schema_mgr.build_query(query_name, fields='auto')
                print(f"\n   Generated Query:")
                print(f"   {query}")
                
                # Execute
                print(f"\n   Executing...")
                result = client.execute_query(query)
                
                if result and 'data' in result:
                    data = result['data']
                    
                    if query_name in data:
                        orgs = data[query_name]
                        
                        print(f"\n" + "="*80)
                        print(f"✅ SUCCESS! Found Organizations")
                        print("="*80)
                        
                        if isinstance(orgs, list):
                            print(f"\n📊 Total Organizations: {len(orgs)}")
                            
                            for i, org in enumerate(orgs, 1):
                                print(f"\n{'─'*80}")
                                print(f"Organization #{i}")
                                print(f"{'─'*80}")
                                
                                for key, value in org.items():
                                    print(f"   {key:20s}: {value}")
                        
                        elif isinstance(orgs, dict):
                            # Might be paginated
                            if 'nodes' in orgs:
                                nodes = orgs['nodes']
                                print(f"\n📊 Total Organizations: {len(nodes)}")
                                
                                for i, org in enumerate(nodes, 1):
                                    print(f"\n{'─'*80}")
                                    print(f"Organization #{i}")
                                    print(f"{'─'*80}")
                                    
                                    for key, value in org.items():
                                        print(f"   {key:20s}: {value}")
                            else:
                                print(f"\n{orgs}")
                        else:
                            print(f"\nData: {orgs}")
                        
                        success = True
                        break
                    else:
                        print(f"   ⚠️  '{query_name}' not in response data")
                        print(f"   Available keys: {list(data.keys())}")
                
                elif result and 'errors' in result:
                    print(f"   ❌ Query failed with errors:")
                    for error in result['errors']:
                        print(f"      • {error.get('message', error)}")
                else:
                    print(f"   ⚠️  Unexpected response format")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"✗ Query '{query_name}' not found")
    
    if not success:
        # Try a custom introspection to see what's really available
        print("\n" + "="*80)
        print("🔍 FALLBACK: Trying custom query to find organization data")
        print("="*80)
        
        # Try getting the current user's organization
        custom_query = """
        query GetCurrentUser {
            currentUser {
                id
                email
                firstName
                lastName
                organization {
                    id
                    name
                    slug
                }
            }
        }
        """
        
        print("\nTrying to get current user's organization...")
        result = client.execute_query(custom_query)
        
        if result:
            print(f"\nResult: {result}")
    
    print("\n" + "="*80)
    print("Query Complete!")
    print("="*80)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
