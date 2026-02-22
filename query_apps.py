#!/usr/bin/env python3
"""
Query Nife.io apps using the GraphQL API
"""
import os
import sys
import requests
import json

# Access token from environment variable
TOKEN = os.environ.get('NIFE_ACCESS_TOKEN')
if not TOKEN:
    print("❌ Error: NIFE_ACCESS_TOKEN environment variable not set")
    print("   Run: export NIFE_ACCESS_TOKEN=$(nifectl auth token)")
    sys.exit(1)

def query_nife_api(endpoint, query):
    """Query the Nife GraphQL API"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {TOKEN}',
        'User-Agent': 'nife-mcp-query/1.0.0'
    }
    
    payload = {'query': query}
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ HTTP Error {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None

def main():
    print("="*70)
    print("🚀 Querying Nife.io Applications")
    print("="*70)
    
    # Try different possible endpoints
    endpoints = [
        "https://api.nife.io/graphql",
        "https://api.nife.io/v1/graphql",
    ]
    
    # Query to get apps
    apps_query = """
    query GetApps {
        apps {
            id
            name
            status
            createdAt
            updatedAt
        }
    }
    """
    
    # Try schema introspection first
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
        }
    }
    """
    
    for endpoint in endpoints:
        print(f"\n📡 Trying endpoint: {endpoint}")
        print("-" * 70)
        
        # Try introspection first
        print("\n1️⃣ Testing schema introspection...")
        result = query_nife_api(endpoint, introspection_query)
        
        if result and 'data' in result:
            print("✅ Schema introspection successful!")
            
            if '__schema' in result['data']:
                query_fields = result['data']['__schema']['queryType']['fields']
                print(f"\n📋 Available queries ({len(query_fields)}):")
                for field in query_fields[:10]:  # Show first 10
                    print(f"   • {field['name']}")
                if len(query_fields) > 10:
                    print(f"   ... and {len(query_fields) - 10} more")
            
            # Now try to get apps
            print(f"\n2️⃣ Querying for applications...")
            apps_result = query_nife_api(endpoint, apps_query)
            
            if apps_result and 'data' in apps_result:
                print("✅ Apps query successful!")
                
                if 'apps' in apps_result['data']:
                    apps = apps_result['data']['apps']
                    
                    print(f"\n" + "="*70)
                    print(f"📊 RESULTS: You have {len(apps)} application(s) deployed on Nife")
                    print("="*70)
                    
                    if apps:
                        for i, app in enumerate(apps, 1):
                            print(f"\n{i}. {app.get('name', 'Unnamed')}")
                            print(f"   ID: {app.get('id', 'N/A')}")
                            print(f"   Status: {app.get('status', 'Unknown')}")
                            print(f"   Created: {app.get('createdAt', 'N/A')}")
                    else:
                        print("\n📝 No applications found.")
                    
                    print("\n" + "="*70)
                    return  # Success!
                else:
                    print("⚠️  'apps' field not found in response")
                    print(f"Available fields: {list(apps_result['data'].keys())}")
            else:
                print("❌ Apps query failed")
                if apps_result:
                    print(f"Response: {json.dumps(apps_result, indent=2)}")
        else:
            print("❌ Schema introspection failed")
            if result:
                print(f"Response: {json.dumps(result, indent=2)}")
    
    print("\n" + "="*70)
    print("❌ Could not retrieve apps from any endpoint")
    print("="*70)
    print("\n💡 Suggestions:")
    print("1. Verify the GraphQL endpoint URL with Nife.io support")
    print("2. Check if your token has the correct permissions")
    print("3. Try: nifectl apps list")

if __name__ == "__main__":
    main()
