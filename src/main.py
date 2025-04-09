from fastapi import FastAPI, HTTPException, Query, Body, Path as FastAPIPath, BackgroundTasks, WebSocket, WebSocketDisconnect, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sys
import os
from typing import Optional, List
from pydantic import BaseModel, Field
import asyncio
from contextlib import asynccontextmanager
from queue import Queue
import threading
from time import sleep
import queue
import tweepy
from dotenv import load_dotenv
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import re
import requests
from shared import analysis_queue
from go_arlo_agency.market_data import BirdeyeMarketData
from shared.config import configure_cors
import trending_list
import token_analytics

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from go_arlo_agency.database.db import get_analysis, save_token, get_token, get_all_tokens, get_all_analyses
from go_arlo_agency.agency import handle_message
from go_arlo_agency.search import search_tokens

main_event_loop = None
birdeye_market = BirdeyeMarketData()
worker_thread = None
is_worker_running = False

security = HTTPBearer()


RATE_LIMIT_DURATION = 60 
MAX_REQUESTS = 100
request_counts = defaultdict(lambda: {"count": 0, "reset_time": 0})

def check_rate_limit(api_key: str):
    """Check if request is within rate limits"""
    now = time.time()
    if request_counts[api_key]["reset_time"] < now:
        request_counts[api_key] = {"count": 0, "reset_time": now + RATE_LIMIT_DURATION}
    
    request_counts[api_key]["count"] += 1
    if request_counts[api_key]["count"] > MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key with rate limiting"""
    api_key = credentials.credentials
    expected_api_key = os.getenv("APP_TOKEN")
    
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    
    if not secrets.compare_digest(api_key, expected_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    check_rate_limit(api_key)
    return api_key

def format_analysis_tweet(analysis_data, ticker, chain):
    """Format analysis data as a tweet"""
    try:
        market_data = birdeye_market.get_market_data(analysis_data['contract_address'])
        trade_data = birdeye_market.get_trade_data(analysis_data['contract_address'])
        
        def format_number(num):
            """Format numbers to K, M, B format with proper rounding"""
            if num >= 1_000_000_000:
                billions = num/1_000_000_000
                return f"{billions:.2f}B".rstrip('0').rstrip('.')
            elif num >= 999_500_000:
                return "1B"
            elif num >= 1_000_000:
                if num >= 999_500_000:
                    return "1B"
                elif num >= 99_950_000:
                    return f"{num/1_000_000:.0f}M"
                else:
                    millions = num/1_000_000
                    return f"{millions:.2f}M".rstrip('0').rstrip('.')
            elif num >= 999_500:
                return "1M"
            elif num >= 1_000:
                if num >= 99_950:
                    return f"{num/1_000:.0f}K"
                else:
                    thousands = num/1_000
                    return f"{thousands:.2f}K".rstrip('0').rstrip('.')
            return f"{num:.2f}".rstrip('0').rstrip('.')

        market_cap = format_number(float(market_data['data'].get('marketcap', 0)))
        supply = format_number(float(market_data['data'].get('supply', 0)))
        liquidity = format_number(float(market_data['data'].get('liquidity', 0)))
        
        print(f"Formatted metrics - Market Cap: {market_cap}, Supply: {supply}, Liquidity: {liquidity}")
        
        volume_24h = trade_data['data'].get('volume_24h', '$0')
        price_change_1h = trade_data['data'].get('price_change_1h', '0%')

        def get_assessment_icon(assessment):
            return {
                "positive": "🟢",
                "neutral": "🟠",
                "negative": "🔴"
            }.get(assessment, "⚪")

        tweet_parts = [
            f"${ticker}",
            f"⭐ Score: {analysis_data.get('final_score', 0)}",
            f"💰 Market Cap: ${market_cap}  |  🪙 Supply: {supply}  |  💧 Liquidity: ${liquidity}  |  📊 24h Vol: {volume_24h}  |  📈 1h: {price_change_1h}"
        ]

        sections = [
            ("🔒 Token Safety", "token_safety"),
            ("🏦 Market Analysis", "market_position"),
            ("🗣️ Social Sentiment", "social_sentiment"),
            ("⚖️ Holder Distribution", "holder_analysis")
        ]

        for title, key in sections:
            section = analysis_data.get(key, {})
            if section and section.get("key_points"):
                assessment = section.get("assessment", "")
                icon = get_assessment_icon(assessment)
                tweet_parts.append(f"\n## {title} {icon}")
                for i, point in enumerate(section["key_points"]):
                    if key == "token_safety":
                        point_lower = point.lower()
                        point_icon = "⚠️ " if (
                            (i == 0 and "contract" in point_lower and ("not" in point_lower or "mutable" in point_lower)) or 
                            (i == 1 and ("token" in point_lower or "holder" in point_lower) and "full control" not in point_lower)
                        ) else ""
                        tweet_parts.append(f"├─ {point_icon}{point}")
                    else:
                        tweet_parts.append(f"├─ {point}")

        captain_summary = analysis_data.get("captain_summary", "")
        if captain_summary:
            tweet_parts.append("\n## Captain's Log:\n")
            
            if "Key Insights:" in captain_summary:
                parts = captain_summary.split("Key Insights:")
                tweet_parts.append(parts[0].strip())
                tweet_parts.append(f"\nKey Insights:{parts[1]}")
            else:
                # If no "Key Insights:" section, just add the summary as is
                tweet_parts.append(captain_summary)
        
        tweet_parts.append(f"\n{analysis_data['contract_address']}")
        tweet_parts.append(f"\n#cryptomarket #{chain} #{ticker}")

        return "\n".join(tweet_parts)
    except Exception as e:
        print(f"Error formatting tweet: {str(e)}")
        return None

def get_formatted_analysis(address: str):
    """Get analysis and format as tweet"""
    try:
        analysis = get_analysis(address)
        if not analysis:
            return None
            
        ticker = analysis.get("token_ticker", "").upper()
        chain = analysis.get("chain", "solana")
        
        return format_analysis_tweet(analysis, ticker, chain)
    except Exception as e:
        print(f"Error getting formatted analysis: {str(e)}")
        return None

def extract_tweet_id(link: Optional[str]) -> Optional[str]:
    """Extract tweet ID from Twitter/X link"""
    if not link:
        return None
        
    try:
        if 'status/' in link:
            return link.split('status/')[-1].split('?')[0]
    except Exception as e:
        print(f"Error extracting tweet ID: {str(e)}")
    return None

def post_analysis_reply(tweet_id: str, analysis_text: str) -> bool:
    """Post analysis as reply to original tweet"""
    try:
        client = tweepy.Client(
            consumer_key=os.getenv("TWITTER_API_KEY"),
            consumer_secret=os.getenv("TWITTER_API_KEY_SECRET"),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        )
        
        response = client.create_tweet(
            text=analysis_text,
            in_reply_to_tweet_id=tweet_id
        )
        
        return bool(response and response.data)
    except Exception as e:
        print(f"Error posting tweet reply: {str(e)}")
        return False

def process_analysis_queue():
    """Background worker to process all analysis requests"""
    global is_worker_running
    
    while is_worker_running:
        try:
            try:
                job = analysis_queue.get(block=True, timeout=60)
            except queue.Empty:
                continue
            
            if job:
                print(f"Processing analysis for address: {job['address']}")
                try:
                    existing_analysis = get_analysis(job['address'])
                    should_analyze = True

                    if existing_analysis:
                        # Convert updated_at to UTC datetime
                        updated_at = existing_analysis['updated_at']
                        if not updated_at.tzinfo:
                            updated_at = updated_at.replace(tzinfo=timezone.utc)
                            
                        current_time = datetime.now(timezone.utc)
                        time_difference = current_time - updated_at

                        if time_difference < timedelta(minutes=15):
                            should_analyze = False
                            print(f"Using existing analysis for {job['address']} (updated {time_difference.total_seconds()/60:.1f} minutes ago)")
                            
                            tweet_text = get_formatted_analysis(job['address'])
                            if tweet_text:
                                if job.get('chat_id'):  # Telegram
                                    send_message(job['chat_id'], tweet_text, job['message_id'])
                                elif job.get('link'):  # Twitter
                                    tweet_id = extract_tweet_id(job['link'])
                                    if tweet_id:
                                        post_analysis_reply(tweet_id, tweet_text)
                            continue

                    if should_analyze:
                        query = f"token_ticker={job['ticker']}, contract_address={job['address']}, chain={job['chain']}"
                        response = handle_message(query)
                        print(f"Analysis complete for {job['address']}")
                        
                        tweet_text = get_formatted_analysis(job['address'])
                        if tweet_text:
                            if job.get('chat_id'):  # Telegram
                                send_message(job['chat_id'], tweet_text, job['message_id'])
                            elif job.get('link'):  # Twitter
                                tweet_id = extract_tweet_id(job['link'])
                                if tweet_id:
                                    post_analysis_reply(tweet_id, tweet_text)
                    
                except Exception as e:
                    print(f"Error processing analysis job: {str(e)}")
                    error_msg = "Sorry, an error occurred while processing the analysis."
                    if job.get('chat_id'):
                        send_message(job['chat_id'], error_msg, job['message_id'])
                
                finally:
                    analysis_queue.task_done()
                    
        except Exception as e:
            if not isinstance(e, queue.Empty):
                print(f"Queue processing error: {str(e)}")
            sleep(1)

def start_worker():
    """Start the background worker thread"""
    global worker_thread, is_worker_running
    
    if not worker_thread or not worker_thread.is_alive():
        is_worker_running = True
        worker_thread = threading.Thread(target=process_analysis_queue, daemon=True)
        worker_thread.start()
        print("Analysis worker thread started")

def stop_worker():
    """Stop the background worker threads"""
    global is_worker_running
    is_worker_running = False
    if worker_thread:
        worker_thread.join(timeout=5)
    print("Worker threads stopped")

async def add_address_to_queue(address):
    """Async function to add address to the notification queue."""
    await notification_queue.put(address)

async def process_notification_queue():
    while True:
        address = await notification_queue.get()
        await manager.send_message(f"analysis_complete:{address}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_event_loop
    print("Initializing application...")
    
    main_event_loop = asyncio.get_event_loop()
    print("Event loop created")
    
    print("Starting workers...")
    start_worker()
    print("Application startup complete")
    
    yield
    
    print("Shutting down application...")
    stop_worker()
    print("Cleanup complete")

app = FastAPI(lifespan=lifespan)

configure_cors(app)

class AnalysisRequest(BaseModel):
    ticker: str
    address: str
    chain: Optional[str] = "solana"

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "GOAT",
                "address": "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",
                "chain": "solana"
            }
        }

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print("WebSocket connection accepted")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print("WebSocket connection disconnected")

    async def send_message(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"Error sending WebSocket message: {str(e)}")

manager = ConnectionManager()

notification_queue = asyncio.Queue()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received message via WebSocket: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/search")
async def search_tokens_endpoint(query: str = Query(..., min_length=1)):
    """
    Search tokens using search.py
    """
    try:
        results = search_tokens(query)
        return {
            "success": True,
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TokenRequest(BaseModel):
    name: str
    ticker: str
    contract_address: str

@app.post("/api/tokens")
async def save_token_endpoint(
    request: TokenRequest = Body(...),
    api_key: str = Depends(verify_api_key)
):
    """
    Save token information to tokens collection
    """
    try:
        success = save_token({
            "name": request.name,
            "ticker": request.ticker,
            "contract_address": request.contract_address
        })
        
        return {
            "success": success,
            "message": "Token saved successfully" if success else "Failed to save token"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tokens/{contract_address}")
async def get_token_info(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get token information for",
        min_length=1
    )
):
    """
    Get token information from tokens collection
    """
    try:
        token = get_token(contract_address)
        
        if token:
            return {
                "success": True,
                "data": token
            }
            
        return {
            "success": False,
            "message": "Token not found"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tokens/exists/{contract_address}")
async def check_token_exists(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to check",
        min_length=1
    )
):
    """
    Check if a token exists in the tokens collection
    """
    try:
        token = get_token(contract_address)
        return {
            "success": True,
            "exists": token is not None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
async def analyze_token(
    background_tasks: BackgroundTasks,
    request: AnalysisRequest = Body(...),
    api_key: str = Depends(verify_api_key)
):
    """
    Save token info and analyze token using Arlo and agents asynchronously.
    """
    try:
        existing_token = get_token(request.address)
        if not existing_token:
            token_data = {
                "name": request.ticker,
                "ticker": request.ticker,
                "contract_address": request.address
            }
            save_token(token_data)
        
        existing_analysis = get_analysis(request.address)
        if existing_analysis:
            print(f"Analysis already exists for {request.address}")
            return {
                "success": True,
                "data": existing_analysis,
                "source": "database"
            }

        background_tasks.add_task(run_analysis, request.ticker, request.address, request.chain)

        return {
            "success": True,
            "message": "Analysis started",
            "data": None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_analysis(ticker, address, chain):
    """Run the analysis without blocking the event loop."""
    try:
        query = f"token_ticker={ticker}, contract_address={address}, chain={chain}"
        print(f"Query: {query}")
        print(f"Starting analysis for {address}")

        try:
            response = handle_message(query)
            print(f"Agency response: {response}")
            
            if "Please provide the token ticker" in response:
                retry_query = f"Analyze token with ticker {ticker} at address {address} on {chain} blockchain"
                print(f"Retrying with query: {retry_query}")
                response = handle_message(retry_query)
                print(f"Retry response: {response}")
                
        except Exception as e:
            print(f"Error during handle_message: {str(e)}")
            return

        try:
            analysis = get_analysis(address)
            if analysis:
                print(f"Analysis complete for {address}")
                asyncio.run_coroutine_threadsafe(add_address_to_queue(address), main_event_loop)
            else:
                print(f"No analysis found in database for {address}")
        except Exception as e:
            print(f"Error checking analysis in database: {str(e)}")

    except Exception as e:
        print(f"Error in run_analysis: {str(e)}")

@app.get("/api/analysis/{contract_address}")
async def get_token_analysis(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get analysis for",
        min_length=1
    ),
    api_key: str = Depends(verify_api_key)
):
    """
    Get existing analysis from database
    """
    try:
        analysis = get_analysis(contract_address)

        if analysis:
            return {
                "success": True,
                "data": analysis,
                "source": "database"
            }

        return {
            "success": False,
            "message": "Analysis not found",
            "data": None
        }

    except Exception as e:
        print(f"Error in get_token_analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class BatchAnalysisRequest(BaseModel):
    addresses: List[str] = Field(..., min_items=1, max_items=100)

    class Config:
        json_schema_extra = {
            "example": {
                "addresses": [
                    "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",
                    "So11111111111111111111111111111111111111112"
                ]
            }
        }

@app.post("/api/analysis/batch")
async def get_batch_analysis(
    request: BatchAnalysisRequest = Body(...),
    api_key: str = Depends(verify_api_key)
):
    """
    Get analysis scores for multiple contract addresses
    """
    try:
        results = []
        for address in request.addresses:
            analysis = get_analysis(address)
            if analysis:
                results.append({
                    "contract_address": address,
                    "token_ticker": analysis.get("token_ticker"),
                    "chain": analysis.get("chain"),
                    "final_score": analysis.get("final_score"),
                    "updated_at": analysis.get("updated_at"),
                    "exists": True
                })
            else:
                results.append({
                    "contract_address": address,
                    "exists": False
                })

        return {
            "success": True,
            "data": results
        }

    except Exception as e:
        print(f"Error in get_batch_analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis")
async def get_all_analysis(
    api_key: str = Depends(verify_api_key),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of results to return (max 1000)"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip")
):
    """
    Get all tokens from the analysis table with pagination
    """
    try:
        analyses = get_all_analyses(limit, offset)
        
        if not analyses:
            return {
                "success": True,
                "data": []
            }

        results = []
        for analysis in analyses:
            results.append({
                "contract_address": analysis.get("contract_address"),
                "token_ticker": analysis.get("token_ticker"),
                "chain": analysis.get("chain"),
                "final_score": analysis.get("final_score"),
                "updated_at": analysis.get("updated_at"),
                "exists": True
            })

        return {
            "success": True,
            "data": results
        }

    except Exception as e:
        print(f"Error in get_all_analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tokens")
async def get_all_tokens_endpoint():
    """
    Retrieve all tokens from tokens collection
    """
    try:
        tokens = get_all_tokens()
        return {
            "success": True,
            "data": tokens
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market-data/{contract_address}")
async def get_token_market_data(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get market data for",
        min_length=1
    )
):
    """
    Get market data for a token from Birdeye API
    """
    try:
        market_data = birdeye_market.get_market_data(contract_address)
        
        if market_data["success"]:
            return {
                "success": True,
                "data": market_data["data"]
            }
        else:
            return {
                "success": False,
                "message": market_data.get("error", "Failed to fetch market data"),
                "data": None
            }
            
    except Exception as e:
        print(f"Error in get_token_market_data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-report")
async def analyze_report(
    request: AnalysisRequest = Body(...),
    api_key: str = Depends(verify_api_key)
):
    """
    Trigger analysis and return the generated report immediately.
    """
    try:
        query = f"{request.ticker}, {request.address}, {request.chain}"
        print(f"Starting analysis for {request.address}")

        try:
            response = handle_message(query)
            print(f"Agency response: {response}")
        except Exception as e:
            print(f"Error during handle_message: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail="Error processing analysis"
            )

        try:
            analysis = get_analysis(request.address)
            if analysis:
                if 'timestamp' in analysis:
                    del analysis['timestamp']
                    
                return {
                    "success": True,
                    "data": analysis
                }
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Analysis not found after processing"
                )
        except Exception as e:
            print(f"Error checking analysis in database: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Error retrieving analysis results"
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

class TextAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1)
    link: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Check out this token at address CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump on Solana",
                "link": "https://twitter.com/user/status/123456789"
            }
        }

@app.post("/api/extract-token")
async def extract_token_from_text(
    request: TextAnalysisRequest = Body(...),
    api_key: str = Depends(verify_api_key)
):
    """Extract contract address or cashtag from text and queue analysis"""
    try:
        address_pattern = r'\b[a-zA-Z0-9]{32,44}\b'
        address_matches = re.findall(address_pattern, request.text)
        
        if address_matches:
            contract_address = address_matches[0]
            search_results = search_tokens(contract_address)
            
            if not search_results or not search_results[0]:
                return {
                    "success": False,
                    "message": f"No token found for address: {contract_address}",
                    "data": None
                }
                
            token_data = search_results[0]
        else:
            cashtag_pattern = r'\$([A-Za-z0-9]+)(?=[\s.,!?]|$)'
            cashtag_matches = re.findall(cashtag_pattern, request.text)
            
            if not cashtag_matches:
                return {
                    "success": False,
                    "message": "No valid contract address or cashtag found in text",
                    "data": None
                }
            
            token_symbol = cashtag_matches[0]
            search_results = search_tokens(token_symbol)
            
            if not search_results or not search_results[0]:
                return {
                    "success": False,
                    "message": f"No token found for symbol: ${token_symbol}",
                    "data": None
                }
            
            token_data = search_results[0]
            for result in search_results:
                if result['symbol'].upper() == token_symbol.upper():
                    token_data = result
                    break
        
        job = {
            "ticker": token_data['symbol'],
            "address": token_data['address'],
            "chain": token_data['chain'],
            "link": request.link
        }
        
        analysis_queue.put(job)
        queue_size = analysis_queue.qsize()
        
        return {
            "success": True,
            "message": f"Analysis queued (position: {queue_size})",
            "data": job
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing text: {str(e)}"
        )

@app.get("/api/analysis/{contract_address}/tweet")
async def get_analysis_tweet(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get formatted analysis tweet for",
        min_length=1
    )
):
    """
    Get analysis formatted as a tweet
    """
    try:
        tweet = get_formatted_analysis(contract_address)
        
        if tweet:
            return {
                "success": True,
                "data": {
                    "tweet": tweet
                }
            }
            
        return {
            "success": False,
            "message": "No analysis found or could not format tweet",
            "data": None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting analysis tweet: {str(e)}"
        )

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    update = await request.json()
    print(f"Received update: {update}")
    
    try:
        message = update.get("message") or update.get("channel_post")
        if not message:
            return {"ok": True}
            
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        message_id = message["message_id"]
        
        has_mention = False
        for entity in message.get("entities", []):
            if entity["type"] == "mention" and text[entity["offset"]:entity["offset"]+entity["length"]].lower() == os.getenv('BOT_NAME'):
                has_mention = True
                break
                

        if not has_mention:
            return {"ok": True}
            
        # First try to find contract address
        address_pattern = r'\b[a-zA-Z0-9]{32,44}\b'
        address_matches = re.findall(address_pattern, text)
        
        if address_matches:
            contract_address = address_matches[0]
            search_results = search_tokens(contract_address)
            
            if not search_results or not search_results[0]:
                send_message(chat_id, f"No token found for address: {contract_address}", message_id)
                return {"ok": True}
                
            token_data = search_results[0]
        else:
            # Look for cashtag if no contract address found
            cashtag_pattern = r'\$([A-Za-z0-9]+)(?=[\s.,!?]|$)'
            cashtag_matches = re.findall(cashtag_pattern, text)
            
            if not cashtag_matches:
                send_message(chat_id, "No valid contract address or cashtag found in text", message_id)
                return {"ok": True}
            
            token_symbol = cashtag_matches[0]
            search_results = search_tokens(token_symbol)
            
            if not search_results or not search_results[0]:
                send_message(chat_id, f"No token found for symbol: ${token_symbol}", message_id)
                return {"ok": True}
            
            token_data = search_results[0]
            for result in search_results:
                if result['symbol'].upper() == token_symbol.upper():
                    token_data = result
                    break
        
        # Add to analysis queue
        job = {
            "ticker": token_data['symbol'],
            "address": token_data['address'],
            "chain": token_data['chain'],
            "chat_id": chat_id,
            "message_id": message_id
        }
        
        analysis_queue.put(job)
        send_message(chat_id, "Copy that. Will reply with the report shortly.", message_id)
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        send_message(chat_id, "Sorry, I encountered an error processing your request.", message_id)
    
    return {"ok": True}

def send_message(chat_id, text, reply_to_message_id=None):
    """Send a message using Telegram's Bot API."""
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to_message_id
    }
    response = requests.post(url, json=payload)
    return response.json()

@app.get("/api/trending")
async def trending_tokens_endpoint(
    chain: str = Query(default="solana", description="The blockchain network (solana/base)"),
    sort_by: str = Query(default="rank", description="Sort criteria (rank/volume/price/market_cap/holders)"),
    sort_type: str = Query(default="desc", description="Sort direction (asc/desc)"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results to return (max 100)"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    api_key: str = Depends(verify_api_key)
):
    """Endpoint for trending tokens that uses the trending_list module"""
    return await trending_list.get_trending_tokens(
        chain=chain,
        sort_by=sort_by,
        sort_type=sort_type,
        limit=limit,
        offset=offset,
        api_key=api_key
    )

@app.get("/api/analytics/{contract_address}")
async def get_token_analytics_endpoint(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get analytics for",
        min_length=1
    ),
    chain: str = Query(default="solana", description="The blockchain network"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get token analytics including volume, liquidity, and valuation from Moralis
    """
    try:
        result = token_analytics.get_token_analytics(contract_address, chain)
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metadata/{contract_address}")
async def get_token_metadata(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get metadata for",
        min_length=1
    ),
    api_key: str = Depends(verify_api_key)
):
    """
    Get token metadata from Birdeye API including logo URI and social links
    """
    try:
        headers = {
            "accept": "application/json",
            "x-chain": "solana",
            "X-API-KEY": os.getenv('BIRDEYE_API_KEY')
        }
        
        response = requests.get(
            'https://public-api.birdeye.so/defi/v3/token/meta-data/single',
            headers=headers,
            params={'address': contract_address}
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch token metadata"
            )
            
        data = response.json()
        if not data.get('success') or not data.get('data'):
            raise HTTPException(
                status_code=404,
                detail="Token metadata not found"
            )
            
        token_data = data['data']
        
        formatted_response = {
            "success": True,
            "data": {
                "address": token_data.get('address'),
                "symbol": token_data.get('symbol'),
                "name": token_data.get('name'),
                "decimals": token_data.get('decimals'),
                "extensions": {
                    "coingecko_id": token_data.get('extensions', {}).get('coingecko_id'),
                    "website": token_data.get('extensions', {}).get('website'),
                    "twitter": token_data.get('extensions', {}).get('twitter'),
                    "discord": token_data.get('extensions', {}).get('discord'),
                    "medium": token_data.get('extensions', {}).get('medium'),
                    "telegram": token_data.get('extensions', {}).get('telegram'),
                    "description": token_data.get('extensions', {}).get('description')
                },
                "logo_uri": token_data.get('logo_uri')
            }
        }
        
        return formatted_response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/token-data/{contract_address}")
async def get_combined_token_data(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get combined market and trade data for",
        min_length=1
    ),
    api_key: str = Depends(verify_api_key)
):
    """
    Get both market data and trade data for a token from Birdeye API in a single response
    """
    try:
        market_data = birdeye_market.get_market_data(contract_address)
        trade_data = birdeye_market.get_trade_data(contract_address)
        
        if market_data["success"] and trade_data["success"]:
            return {
                "success": True,
                "data": {
                    "market": market_data["data"],
                    "trade": trade_data["data"]
                }
            }
        else:
            errors = []
            if not market_data["success"]:
                errors.append(market_data.get("error", "Failed to fetch market data"))
            if not trade_data["success"]:
                errors.append(trade_data.get("error", "Failed to fetch trade data"))
                
            return {
                "success": False,
                "message": " | ".join(errors),
                "data": None
            }
            
    except Exception as e:
        print(f"Error in get_combined_token_data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/token-overview/{contract_address}")
async def get_token_overview(
    contract_address: str = FastAPIPath(
        ...,
        title="Contract Address",
        description="The contract address to get token overview data for",
        min_length=1
    ),
    api_key: str = Depends(verify_api_key)
):
    """
    Get comprehensive token overview data from Birdeye API including price, volume, liquidity, and unique wallet stats
    """
    try:
        birdeye_api_key = os.getenv('BIRDEYE_API_KEY')
        if not birdeye_api_key:
            raise HTTPException(
                status_code=500,
                detail="Birdeye API key not configured"
            )
            
        headers = {
            "accept": "application/json",
            "x-chain": "solana",
            "X-API-KEY": birdeye_api_key
        }
        
        response = requests.get(
            f'https://public-api.birdeye.so/defi/token_overview',
            headers=headers,
            params={'address': contract_address}
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Birdeye API returned status code {response.status_code}"
            )
            
        data = response.json()
        
        if not data.get('success') or not data.get('data'):
            return {
                "success": False,
                "message": "Token overview data not found",
                "data": None
            }
            
        return {
            "success": True,
            "data": data['data']
        }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in get_token_overview: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 
