#!/usr/bin/env python3
"""
Test different GraphQL query patterns against Nife.io API
"""
import os
import requests
import json

NIFE_API_ENDPOINT = "https://api.nife.io/graphql"

def test_query(query_name, query, access_token=None):
    """Test a GraphQL query"""
    print(f"\n{'='*60}")
    print(f"Testing: {query_name}")
    print(f"{'='*60}")
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'nife-mcp-server-test/1.0.0'
    }
    
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
    
    payload = {'query': query}
    
    try:
        response = requests.post(
            NIFE_API_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Success: {json.dumps(result, indent=2)}")
            return True, result
        else:
            print(f"Error: {response.text}")
            return False, response.text
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False, str(e)

def main():
    """Run all test queries"""
    access_token = os.environ.get('NIFE_ACCESS_TOKEN')
    
    if not access_token:
        print("Warning: No NIFE_ACCESS_TOKEN found, testing without authentication")
    
    # Test 1: Organizations query (this one works based on your output)
    query1 = """
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
    test_query("Organizations Query", query1, access_token)
    
    # Test 2: Simple apps query
    query2 = """
    query GetApps {
        apps {
            id
            name
            status
            organizationId
        }
    }
    """
    test_query("Simple Apps Query", query2, access_token)
    
    # Test 3: Apps with nodes
    query3 = """
    query GetAppsNodes {
        apps {
            nodes {
                id
                name
                status
                organizationId
            }
        }
    }
    """
    test_query("Apps Nodes Query", query3, access_token)
    
    # Test 4: Apps with pagination
    query4 = """
    query GetAppsWithPagination {
        apps(first: 10) {
            nodes {
                id
                name
                status
            }
        }
    }
    """
    test_query("Apps with Pagination", query4, access_token)
    
    # Test 5: Schema introspection (minimal)
    query5 = """
    query IntrospectSchema {
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
    test_query("Schema Introspection", query5, access_token)

if __name__ == "__main__":
    main()
