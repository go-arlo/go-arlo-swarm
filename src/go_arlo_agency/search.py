import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_API_URL = 'https://public-api.birdeye.so/defi/v3/token/meta-data/single'
BIRDEYE_API_KEY = os.getenv('BIRDEYE_API_KEY')

if not BIRDEYE_API_KEY:
    raise ValueError("BIRDEYE_API_KEY not found in environment variables")

birdeye_headers = {
    "accept": "application/json",
    "x-chain": "solana",
    "X-API-KEY": BIRDEYE_API_KEY
}

TOKEN_CACHE = []
CACHE_TIMESTAMP = 0
CACHE_DURATION = 3600

def search_by_address(address):
    """Search for token by address using Birdeye API"""
    try:
        response = requests.get(
            BIRDEYE_API_URL,
            headers=birdeye_headers,
            params={'address': address}
        )
        
        if response.status_code != 200:
            print(f"Birdeye API request failed with status code: {response.status_code}")
            return []
            
        data = response.json()
        if not data.get('success') or not data.get('data'):
            return []
            
        token_data = data['data']
        
        formatted_token = [{
            'symbol': token_data.get('symbol', ''),
            'name': token_data.get('name', ''),
            'address': token_data.get('address', ''),
            'chain': 'solana'
        }]
        
        return formatted_token
        
    except Exception as e:
        print(f"Error in search_by_address: {str(e)}")
        return []

def search_by_symbol(query):
    """Search for token by symbol using Birdeye API"""
    try:
        search_url = 'https://public-api.birdeye.so/defi/v3/search'
        
        params = {
            'chain': 'solana',
            'keyword': query,
            'target': 'token',
            'verify_token': 'true',
            'sort_by': 'fdv',  
            'sort_type': 'desc'
        }
        
        response = requests.get(
            search_url,
            headers=birdeye_headers,
            params=params
        )
        
        if response.status_code != 200:
            print(f"Birdeye API request failed with status code: {response.status_code}")
            return []
            
        data = response.json()
        if not data.get('success') or not data.get('data') or not data.get('data').get('items'):
            return []
            
        token_items = next(
            (item['result'] for item in data['data']['items'] 
             if item['type'] == 'token'), 
            []
        )
        
        formatted_tokens = [{
            'symbol': token.get('symbol', ''),
            'name': token.get('name', ''),
            'address': token.get('address', ''),
            'chain': token.get('network', 'solana')
        } for token in token_items if token.get('verified')]
        
        return formatted_tokens
        
    except Exception as e:
        print(f"Error in search_by_symbol: {str(e)}")
        return []

def search_tokens(query):
    """Main search function that decides which API to use based on query length"""
    if not query:
        return []
        
    if len(query) > 20:
        return search_by_address(query)
    else:
        return search_by_symbol(query)

def test_search():
    """Test the search functionality with various queries"""
    test_queries = [
        "bonk", 
        "wif", 
        "So11111111111111111111111111111111111111112", 
        "btc",
        "invalid" 
    ]

    print("\nTesting search functionality:")
    print("=" * 50)

    for query in test_queries:
        print(f"\nSearching for: '{query}'")
        try:
            results = search_tokens(query)
            print(f"Found {len(results)} results:")
            for token in results:
                print(f"- {token['symbol']}: {token['name']}")
                print(f"  Address: {token['address']}")
                print(f"  Chain: {token['chain']}")
        except Exception as e:
            print(f"Error testing query '{query}': {str(e)}")
        print("-" * 30)
