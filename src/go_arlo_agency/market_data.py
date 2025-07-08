import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any, Union
import json

load_dotenv()

class BirdeyeMarketData:
    """
    Class to handle Birdeye Market Data API requests.
    Documentation: https://docs.birdeye.so/reference/get_defi-v3-token-market-data
    """

    def __init__(self):
        self.api_key = os.getenv("BIRDEYE_API_KEY")
        if not self.api_key:
            raise ValueError("BIRDEYE_API_KEY not found in environment variables")
        
        self.base_url = "https://public-api.birdeye.so"
        self.headers = {
            "X-API-KEY": self.api_key,
            "Accept": "application/json"
        }

    def safe_float(self, value: Union[str, int, float, None], default: float = 0.0) -> float:
        """
        Safely convert a value to float, handling None and invalid values.
        
        Args:
            value: The value to convert to float
            default: Default value to return if conversion fails
            
        Returns:
            float: The converted value or default
        """
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def format_volume(self, volume: float) -> str:
        """
        Format volume to use M for millions and B for billions.
        """
        # Ensure volume is a valid number
        if volume is None or volume < 0:
            volume = 0.0
            
        if volume >= 1_000_000_000:
            formatted = volume / 1_000_000_000
            return f"${formatted:.2f}B".rstrip('0').rstrip('.')
        elif volume >= 1_000_000:
            formatted = volume / 1_000_000
            return f"${formatted:.2f}M".rstrip('0').rstrip('.')
        elif volume >= 1_000:
            formatted = volume / 1_000
            return f"${formatted:.2f}K".rstrip('0').rstrip('.')
        else:
            return f"${volume:,.2f}"

    def format_percentage(self, value: float) -> str:
        """Format percentage with % symbol"""
        # Ensure value is a valid number
        if value is None:
            value = 0.0
        return f"{value:.2f}%"

    def get_market_data(self, address: str) -> Dict[str, Any]:
        """
        Get market data for a specific token address.
        
        Args:
            address (str): The token's contract address
            
        Returns:
            dict: Market data response including:
                - address: token contract address
                - price: current token price
                - liquidity: total liquidity
                - supply: total supply
                - marketcap: total market cap
                - circulating_supply: circulating supply
        """
        try:
            response = requests.get(
                f"{self.base_url}/defi/v3/token/market-data",
                headers=self.headers,
                params={"address": address}
            )
            
            if response.status_code != 200:
                error_msg = f"Birdeye API returned status code {response.status_code}"
                print(f"Error: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "data": None
                }
            
            data = response.json()
            print(f"Raw Birdeye API response: {json.dumps(data, indent=2)}")
            
            token_data = data.get("data", {})
            
            return {
                "success": True,
                "data": {
                    "address": token_data.get("address", ""),
                    "price": self.safe_float(token_data.get("price"), 0),
                    "liquidity": self.safe_float(token_data.get("liquidity"), 0),
                    "supply": self.safe_float(token_data.get("total_supply"), 0),
                    "marketcap": self.safe_float(token_data.get("market_cap"), 0),
                    "circulating_supply": self.safe_float(token_data.get("circulating_supply"), 0)
                }
            }
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"Error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "data": None
            }

    def get_trade_data(self, address: str) -> Dict[str, Any]:
        """
        Get trade data for a specific token address.
        
        Args:
            address (str): The token's contract address
            
        Returns:
            dict: Trade data response including:
                - volume_24h: formatted 24h volume (with M/B suffix)
                - price_change_1h: formatted hourly price change (as percentage)
        """
        try:
            response = requests.get(
                f"{self.base_url}/defi/v3/token/trade-data/single",
                headers=self.headers,
                params={"address": address}
            )
            
            if response.status_code != 200:
                error_msg = f"Birdeye API returned status code {response.status_code}"
                print(f"Error: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "data": None
                }
            
            data = response.json().get("data", {})
            
            # Use safe_float to handle None values
            volume_24h = self.safe_float(data.get("volume_24h_usd"), 0)
            price_change = self.safe_float(data.get("price_change_1h_percent"), 0)
            
            return {
                "success": True,
                "data": {
                    "volume_24h": self.format_volume(volume_24h),
                    "price_change_1h": self.format_percentage(price_change)
                }
            }
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"Error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "data": None
            }

if __name__ == "__main__":
    birdeye = BirdeyeMarketData()
    test_address = "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL"
    
    print("\nFetching market data...")
    market_result = birdeye.get_market_data(test_address)
    if market_result["success"]:
        print("\nMarket Data Retrieved Successfully:")
        print(json.dumps(market_result["data"], indent=2))
    
    print("\nFetching trade data...")
    trade_result = birdeye.get_trade_data(test_address)
    if trade_result["success"]:
        print("\nTrade Data Retrieved Successfully:")
        print(json.dumps(trade_result["data"], indent=2)) 
