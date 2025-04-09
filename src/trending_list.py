from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import requests
from dotenv import load_dotenv
from shared.config import configure_cors
import logging
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

configure_cors(app)

security = HTTPBearer()
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
TRENDING_URL = "https://public-api.birdeye.so/defi/token_trending"

class TrendingRequest(BaseModel):
    chain: str = Field(default="solana", description="The blockchain network (solana/base)")
    sort_by: str = Field(default="rank", description="Sort criteria (rank/volume/price/market_cap/holders)")
    sort_type: str = Field(default="desc", description="Sort direction (asc/desc)")
    limit: int = Field(default=20, ge=1, le=100, description="Number of results to return (max 100)")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key"""
    api_key = credentials.credentials
    expected_api_key = os.getenv("APP_TOKEN")
    
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    
    if api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key

@app.get("/api/trending")
async def get_trending_tokens(
    chain: str = Query(default="solana", description="The blockchain network (solana/base)"),
    sort_by: str = Query(default="rank", description="Sort criteria (rank/volume/price/market_cap/holders)"),
    sort_type: str = Query(default="desc", description="Sort direction (asc/desc)"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results to return (max 100)"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    api_key: str = Security(verify_api_key)
):
    """Get trending tokens from Birdeye API"""
    try:
        if chain.lower() not in ["solana", "base"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid chain. Supported chains: solana, base"
            )

        valid_sort_fields = ["rank", "volume", "price", "market_cap", "holders"]
        if sort_by.lower() not in valid_sort_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort_by. Supported fields: {', '.join(valid_sort_fields)}"
            )

        if sort_type.lower() not in ["asc", "desc"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid sort_type. Supported values: asc, desc"
            )

        sort_by_mapping = {
            "rank": "rank",
            "volume": "volume24hUSD",
            "price": "price",
            "market_cap": "marketcap",
            "holders": "holders"
        }
        
        birdeye_sort_by = sort_by_mapping.get(sort_by.lower(), "rank")

        params = {
            "sort_by": birdeye_sort_by,
            "sort_type": sort_type.lower(),
            "offset": offset,
            "limit": limit
        }

        headers = {
            "accept": "application/json",
            "x-chain": chain.lower(),
            "X-API-KEY": BIRDEYE_API_KEY
        }

        logger.info(f"Making request to Birdeye API for chain: {chain}")
        logger.info(f"API URL: {TRENDING_URL}")
        logger.info(f"Params: {params}")
        logger.info(f"Headers: {headers}")
        
        response = requests.get(
            TRENDING_URL,
            params=params,
            headers=headers
        )

        logger.info(f"API Response Status: {response.status_code}")
        logger.info(f"API Response Headers: {response.headers}")
        
        if response.status_code == 200:
            try:
                raw_data = response.json()
                logger.info(f"API Response Text: {json.dumps(raw_data)[:500]}...")
                return raw_data
            except Exception as e:
                logger.error(f"Error parsing API response: {str(e)}")
                return {
                    "success": False,
                    "message": f"Error parsing API response: {str(e)}",
                    "raw_response": response.text
                }
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return {
                "success": False,
                "message": f"API request failed with status code: {response.status_code}",
                "raw_response": response.text
            }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching trending list: {str(e)}")
        return {
            "success": False,
            "message": f"Error fetching trending list: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("trending_list:app", host="0.0.0.0", port=8001, reload=True) 
    