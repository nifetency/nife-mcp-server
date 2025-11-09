#!/usr/bin/env python3
"""
Test script to verify Nife.io GraphQL endpoint accessibility
"""
import requests
import json
import os

def test_endpoint(url, token=None):
    """Test a GraphQL endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing endpoint: {url}")
    print(f"{'='*60}")
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'nife-mcp-test/1.0.0'
    }
    
    if token:
        headers['Authorization'] = f'Bearer {token}'
        print(f"✓ Using authentication token")
    else:
        print(f"⚠️  No authentication token")
    
    # Simple introspection query
    query = """
    query HealthCheck {
        __typename
    }
    """
    
    payload = {'query': query}
    
    try:
        print(f"\n📤 Sending request...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"\n✅ SUCCESS!")
                print(f"Response data:")
                print(json.dumps(data, indent=2))
                return True
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response")
                print(f"Response text: {response.text[:500]}")
                return False
        else:
            print(f"\n❌ HTTP Error {response.status_code}")
            print(f"Response text: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection Error: Cannot connect to {url}")
        print(f"   {str(e)}")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Timeout: Request took longer than 10 seconds")
        return False
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        return False

def main():
    """Main test function"""
    print("="*60)
    print("Nife.io GraphQL Endpoint Tester")
    print("="*60)
    
    # Get token from environment
    token = os.environ.get('NIFE_ACCESS_TOKEN')
    
    if token:
        print(f"✓ Found NIFE_ACCESS_TOKEN in environment")
    else:
        print(f"⚠️  NIFE_ACCESS_TOKEN not found in environment")
        print(f"   You can set it with: export NIFE_ACCESS_TOKEN=your_token")
    
    # Test different possible endpoints
    endpoints = [
        "https://api.nife.io/graphql",
        "https://api.nife.io/v1/graphql",
        "https://api.nife.io",
        "https://graphql.nife.io",
    ]
    
    results = {}
    for endpoint in endpoints:
        results[endpoint] = test_endpoint(endpoint, token)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for endpoint, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{status}: {endpoint}")
    
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    successful = [e for e, s in results.items() if s]
    if successful:
        print(f"✓ Use this endpoint: {successful[0]}")
    else:
        print("❌ No accessible endpoints found")
        print("\nTroubleshooting:")
        print("1. Ensure NIFE_ACCESS_TOKEN is set correctly")
        print("2. Check if you have network access to api.nife.io")
        print("3. Verify your token is valid: nifectl auth token")
        print("4. Contact Nife.io support for the correct GraphQL endpoint")

if __name__ == "__main__":
    main()
