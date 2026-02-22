#!/usr/bin/env python3
"""
Inline script to list organizations - runs directly without imports
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

API_ENDPOINT = "https://api.nife.io/graphql"

def execute_query(query):
    """Execute GraphQL query"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {TOKEN}'
    }
    
    response = requests.post(
        API_ENDPOINT,
        json={'query': query},
        headers=headers,
        timeout=30
    )
    
    return response.json()

print("="*80)
print("🏢 LISTING ORGANIZATIONS IN NIFE.IO")
print("="*80)

# Try different organization queries
queries_to_try = [
    # Standard query
    """
    query GetOrganizations {
        organizations {
            id
            name
            slug
            type
            isActive
            createdAt
        }
    }
    """,
    # With nodes
    """
    query GetOrganizations {
        organizations {
            nodes {
                id
                name
                slug
                type
                isActive
                createdAt
            }
        }
    }
    """,
    # Current user's organization
    """
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
                type
            }
        }
    }
    """,
    # Try me query
    """
    query GetMe {
        me {
            id
            email
            organization {
                id
                name
                slug
            }
        }
    }
    """,
    # Try viewer query
    """
    query GetViewer {
        viewer {
            id
            email
            organization {
                id
                name
            }
        }
    }
    """
]

for i, query in enumerate(queries_to_try, 1):
    print(f"\n{'='*80}")
    print(f"Attempt #{i}")
    print(f"{'='*80}")
    print(f"Query:\n{query.strip()}")
    print(f"\n🔄 Executing...")
    
    try:
        result = execute_query(query)
        
        print(f"\n📊 Response:")
        print(json.dumps(result, indent=2))
        
        if 'errors' not in result and 'data' in result:
            data = result['data']
            
            # Check for organizations in various formats
            if 'organizations' in data:
                orgs = data['organizations']
                
                if isinstance(orgs, list):
                    print(f"\n✅ SUCCESS! Found {len(orgs)} organizations")
                    for j, org in enumerate(orgs, 1):
                        print(f"\n{'─'*80}")
                        print(f"Organization #{j}")
                        print(f"{'─'*80}")
                        for key, value in org.items():
                            print(f"   {key:20s}: {value}")
                    break
                    
                elif isinstance(orgs, dict) and 'nodes' in orgs:
                    nodes = orgs['nodes']
                    print(f"\n✅ SUCCESS! Found {len(nodes)} organizations")
                    for j, org in enumerate(nodes, 1):
                        print(f"\n{'─'*80}")
                        print(f"Organization #{j}")
                        print(f"{'─'*80}")
                        for key, value in org.items():
                            print(f"   {key:20s}: {value}")
                    break
            
            elif 'currentUser' in data and 'organization' in data['currentUser']:
                org = data['currentUser']['organization']
                print(f"\n✅ SUCCESS! Found user's organization:")
                print(f"\n{'─'*80}")
                for key, value in org.items():
                    print(f"   {key:20s}: {value}")
                break
            
            elif 'me' in data and 'organization' in data['me']:
                org = data['me']['organization']
                print(f"\n✅ SUCCESS! Found user's organization:")
                print(f"\n{'─'*80}")
                for key, value in org.items():
                    print(f"   {key:20s}: {value}")
                break
            
            elif 'viewer' in data and 'organization' in data['viewer']:
                org = data['viewer']['organization']
                print(f"\n✅ SUCCESS! Found user's organization:")
                print(f"\n{'─'*80}")
                for key, value in org.items():
                    print(f"   {key:20s}: {value}")
                break
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}")
print("Query Complete!")
print("="*80)
