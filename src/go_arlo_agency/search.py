import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_API_URL = 'https://public-api.birdeye.so/defi/v3/token/meta-data/single'
BIRDEYE_API_KEY = os.getenv('BIRDEYE_API_KEY')

if not BIRDEYE_API_KEY:
    raise ValueError("BIRDEYE_API_KEY not found in environment variables")

def detect_chain(address: str) -> str:
    if address.startswith("0x"):
        return "base"
    else:
        return "solana"

TOKEN_CACHE = []
CACHE_TIMESTAMP = 0
CACHE_DURATION = 3600

def search_by_address(address):
    """Search for token by address using Birdeye API (supports both Solana and Base)"""
    try:
        chain = detect_chain(address)
        
        headers = {
            "accept": "application/json",
            "x-chain": chain,
            "X-API-KEY": BIRDEYE_API_KEY
        }
        
        response = requests.get(
            BIRDEYE_API_URL,
            headers=headers,
            params={'address': address}
        )
        
        if response.status_code != 200:
            print(f"Birdeye API request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return []
            
        data = response.json()
        if not data.get('success') or not data.get('data'):
            print(f"No token data found for address {address} on {chain} chain")
            return []
            
        token_data = data['data']
        
        formatted_token = [{
            'symbol': token_data.get('symbol', ''),
            'name': token_data.get('name', ''),
            'address': token_data.get('address', ''),
            'chain': chain
        }]
        
        return formatted_token
        
    except Exception as e:
        print(f"Error in search_by_address: {str(e)}")
        return []

def search_by_symbol(query):
    """Search for token by symbol using Birdeye API (searches both Solana and Base)"""
    all_results = []
    
    for chain in ['solana', 'base']:
        try:
            search_url = 'https://public-api.birdeye.so/defi/v3/search'
            
            headers = {
                "accept": "application/json",
                "x-chain": chain,
                "X-API-KEY": BIRDEYE_API_KEY
            }
            
            params = {
                'chain': chain,
                'keyword': query,
                'target': 'token',
                'verify_token': 'true',
                'sort_by': 'fdv',  
                'sort_type': 'desc'
            }
            
            response = requests.get(
                search_url,
                headers=headers,
                params=params
            )
            
            if response.status_code != 200:
                print(f"Birdeye API request failed for {chain} with status code: {response.status_code}")
                continue
                
            data = response.json()
            if not data.get('success') or not data.get('data') or not data.get('data').get('items'):
                continue
                
            token_items = next(
                (item['result'] for item in data['data']['items'] 
                 if item['type'] == 'token'), 
                []
            )
            
            formatted_tokens = [{
                'symbol': token.get('symbol', ''),
                'name': token.get('name', ''),
                'address': token.get('address', ''),
                'chain': chain
            } for token in token_items if token.get('verified')]
            
            all_results.extend(formatted_tokens)
            
        except Exception as e:
            print(f"Error searching {chain} for symbol '{query}': {str(e)}")
            continue
    
    def sort_key(token):
        exact_match = token['symbol'].upper() == query.upper()
        chain_priority = 0 if token['chain'] == 'solana' else 1
        return (not exact_match, chain_priority)
    
    all_results.sort(key=sort_key)
    return all_results

def search_tokens(query):
    """Main search function that decides which API to use based on query length"""
    if not query:
        return []
        
    if len(query) > 20:
        return search_by_address(query)
    else:
        return search_by_symbol(query)

def test_search():
    """Test the search functionality with various queries including both Solana and Base tokens"""
    test_queries = [
        "bonk", 
        "wif", 
        "btc",
        "usdc",
        "So11111111111111111111111111111111111111112", 
        "0xc0634090F2Fe6c6d75e61Be2b949464aBB498973",
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "invalid" 
    ]

    print("\nTesting multi-chain search functionality:")
    print("=" * 60)

    for query in test_queries:
        print(f"\nSearching for: '{query}'")
        
        if len(query) > 20:
            chain = detect_chain(query)
            print(f"Detected as {chain} address")
        else:
            print("Symbol search - checking both chains")
            
        try:
            results = search_tokens(query)
            print(f"Found {len(results)} results:")
            
            if not results:
                print("  No results found")
            else:
                for i, token in enumerate(results[:3], 1):  # Show top 3 results
                    print(f"  {i}. {token['symbol']}: {token['name']} ({token['chain']})")
                    print(f"     Address: {token['address']}")
                    
                if len(results) > 3:
                    print(f"     ... and {len(results) - 3} more results")
                    
        except Exception as e:
            print(f"Error testing query '{query}': {str(e)}")
        print("-" * 40)

    print("\nTesting chain detection:")
    print("=" * 30)
    test_addresses = [
        "So11111111111111111111111111111111111111112",  # 
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # 
        "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump"  # 
    ]
    
    for addr in test_addresses:
        chain = detect_chain(addr)
        print(f"{addr[:20]}... → {chain}")

if __name__ == "__main__":
    test_search()
