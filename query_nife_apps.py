#!/usr/bin/env python3
"""Simple script to query Nife.io apps count"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from nife_mcp_server.schema_manager import SchemaManager
from nife_mcp_server.routes.mcp import NifeGraphQLClient

# Access token from environment variable
TOKEN = os.environ.get('NIFE_ACCESS_TOKEN')
if not TOKEN:
    print("❌ Error: NIFE_ACCESS_TOKEN environment variable not set")
    print("   Run: export NIFE_ACCESS_TOKEN=$(nifectl auth token)")
    sys.exit(1)

print("="*70)
print("🚀 Querying Nife.io for your deployed applications")
print("="*70)

# Initialize schema manager
schema_mgr = SchemaManager(access_token=TOKEN)
print("\n📡 Loading GraphQL schema...")

# Load schema
if not schema_mgr.load_schema():
    print("❌ Failed to load schema")
    sys.exit(1)

print("✅ Schema loaded successfully!")

# List available queries
queries = schema_mgr.get_available_queries()
print(f"\n📋 Found {len(queries)} available queries")

# Look for app-related queries
app_queries = [q for q in queries if 'app' in q['name'].lower()]
print(f"📱 Found {len(app_queries)} app-related queries:")
for q in app_queries[:10]:
    print(f"   • {q['name']}: {q['description']}")

# Try to query apps
print("\n" + "="*70)
print("🔍 Attempting to query applications...")
print("="*70)

# Initialize GraphQL client
client = NifeGraphQLClient(TOKEN)

# Try different possible query names
possible_queries = [
    'apps',
    'applications', 
    'listApps',
    'getApps',
    'userApps',
    'myApps'
]

for query_name in possible_queries:
    if query_name in schema_mgr.queries_cache:
        print(f"\n✓ Found query: {query_name}")
        try:
            # Build the query
            query = schema_mgr.build_query(query_name, fields='auto')
            print(f"\nExecuting query:")
            print(query)
            
            # Execute
            result = client.execute_query(query)
            
            if result and 'data' in result and query_name in result['data']:
                apps = result['data'][query_name]
                
                print(f"\n" + "="*70)
                print(f"📊 SUCCESS! You have {len(apps) if isinstance(apps, list) else 'an unknown number of'} application(s)")
                print("="*70)
                
                if isinstance(apps, list):
                    for i, app in enumerate(apps, 1):
                        print(f"\n{i}. Application Details:")
                        for key, value in app.items():
                            print(f"   {key}: {value}")
                else:
                    print(f"\n{apps}")
                
                break
            else:
                print(f"   ⚠️  Query returned no data or unexpected format")
                if result:
                    print(f"   Response: {result}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    else:
        print(f"✗ Query '{query_name}' not found in schema")

print("\n" + "="*70)
print("Query complete!")
print("="*70)
