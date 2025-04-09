import os
import requests
from typing import Optional
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
MORALIS_BASE_URL = "https://deep-index.moralis.io/api/v2.2"

def get_token_analytics(address: str, chain: str = "solana") -> dict:
    """
    Fetch token analytics from Moralis API and process the data.
    
    Args:
        address (str): Token contract address
        chain (str): Blockchain network (default: solana)
        
    Returns:
        dict: Processed analytics data including volumes, liquidity, and valuation
    """
    if not MORALIS_API_KEY:
        raise HTTPException(status_code=500, detail="Moralis API key not configured")

    headers = {
        "Accept": "application/json",
        "X-API-Key": MORALIS_API_KEY
    }

    try:
        response = requests.get(
            f"{MORALIS_BASE_URL}/tokens/{address}/analytics",
            headers=headers,
            params={"chain": chain}
        )
        
        if not response.ok:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Moralis API error: {response.text}"
            )

        data = response.json()
        
        total_volume = {
            "5m": float(data["totalBuyVolume"].get("5m", 0) or 0) + float(data["totalSellVolume"].get("5m", 0) or 0),
            "1h": float(data["totalBuyVolume"].get("1h", 0) or 0) + float(data["totalSellVolume"].get("1h", 0) or 0),
            "6h": float(data["totalBuyVolume"].get("6h", 0) or 0) + float(data["totalSellVolume"].get("6h", 0) or 0),
            "24h": float(data["totalBuyVolume"].get("24h", 0) or 0) + float(data["totalSellVolume"].get("24h", 0) or 0)
        }

        return {
            "success": True,
            "data": {
                "tokenAddress": data["tokenAddress"],
                "totalVolume": total_volume,
                "totalLiquidityUsd": float(data.get("totalLiquidityUsd", 0) or 0),
                "totalFullyDilutedValuation": float(data.get("totalFullyDilutedValuation", 0) or 0)
            }
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching token analytics: {str(e)}"
        ) 
