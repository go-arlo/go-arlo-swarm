from agency_swarm.tools import BaseTool
from pydantic import Field
from typing import Dict, Any, List, Optional
import os
import requests
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
import asyncio
import aiohttp
import concurrent.futures
import time

load_dotenv()

class BundleDetector(BaseTool):
    """Tool for detecting coordinated buying patterns"""
    
    name: str = "BundleDetector"
    description: str = "Analyzes transactions to detect potential bundled trades"
    
    address: str = Field(
        description="Token address to analyze for bundle patterns"
    )
    birdeye_api_key: str = Field(
        default=os.getenv("BIRDEYE_API_KEY"),
        description="Birdeye API key for data access"
    )
    base_url: str = Field(
        default="https://public-api.birdeye.so/defi/v3/token",
        description="Base URL for Birdeye API"
    )
    token_address: str = Field(
        default=None,
        description="Current token being analyzed"
    )
    max_concurrent_requests: int = Field(
        default=5,
        description="Maximum concurrent API requests"
    )
    
    async def _get_token_creation_time_async(self, session: aiohttp.ClientSession, token_address: str) -> Optional[int]:
        """Get token creation time asynchronously"""
        try:
            headers = {
                "accept": "application/json",
                "x-chain": "solana",
                "X-API-KEY": self.birdeye_api_key
            }
            
            async with session.get(
                "https://public-api.birdeye.so/defi/token_creation_info",
                headers=headers,
                params={"address": token_address},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('success'):
                        creation_data = data.get('data', {})
                        creation_time = (creation_data.get('blockUnixTime') or  
                                       creation_data.get('block_unix_time') or 
                                       creation_data.get('creation_time') or 
                                       creation_data.get('created_at') or 
                                       creation_data.get('timestamp'))
                        
                        if creation_time:
                            return creation_time
                    
        except Exception as e:
            print(f"Error getting creation time: {e}")
        
        return None

    async def _get_token_metadata_async(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Get token market data asynchronously"""
        try:
            headers = {
                "accept": "application/json",
                "x-chain": "solana",
                "X-API-KEY": self.birdeye_api_key
            }
            
            async with session.get(
                "https://public-api.birdeye.so/defi/v3/token/market-data",
                headers=headers,
                params={"address": self.token_address},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('success') and data.get('data'):
                        market_data = data['data']
                        total_supply = market_data.get('total_supply', 0)
                        circulating_supply = market_data.get('circulating_supply', 0)
                        
                        return {
                            'totalSupplyFormatted': float(total_supply),
                            'circulatingSupply': float(circulating_supply),
                            'price': market_data.get('price', 0),
                            'market_cap': market_data.get('market_cap', 0),
                            'liquidity': market_data.get('liquidity', 0)
                        }
                return {}
        except Exception as e:
            print(f"Error getting market data: {str(e)}")
            return {}

    async def _fetch_multiple_pages_concurrent(self, session: aiohttp.ClientSession, 
                                             params: Dict, headers: Dict, 
                                             max_pages: int = 20) -> List[Dict]:
        """Optimized concurrent page fetching with early exit and memory management"""
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        
        async def fetch_page_with_semaphore(offset: int) -> tuple[List[Dict], bool]:
            async with semaphore:
                page_data = await self._fetch_page(session, offset, params, headers)
                if page_data.get('success') and page_data.get('data', {}).get('items'):
                    items = page_data['data']['items']
                    has_more = page_data['data'].get('has_next', False)
                    return items, has_more
                return [], False
        
        first_page = await self._fetch_page(session, 0, params, headers)
        
        if not first_page.get('success') or not first_page.get('data', {}).get('items'):
            return []
        
        all_items = first_page['data']['items']
        page_size = len(all_items)
        
        if not first_page['data'].get('has_next'):
            return all_items
        
        batch_size = 10
        current_offset = page_size
        all_batches_completed = False
        
        while not all_batches_completed and len(all_items) < 50000:
            tasks = []
            for i in range(batch_size):
                offset = current_offset + (i * page_size)
                if offset >= 50000:
                    break
                task = fetch_page_with_semaphore(offset)
                tasks.append(task)
            
            if not tasks:
                break
            
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful_pages = 0
            has_more_data = False
            
            for result in results:
                if isinstance(result, tuple) and len(result) == 2:
                    items, has_more = result
                    if items:
                        all_items.extend(items)
                        successful_pages += 1
                        if has_more:
                            has_more_data = True
                elif not isinstance(result, Exception):
                    all_batches_completed = True
                    break
            
            current_offset += batch_size * page_size
            
            if not has_more_data or successful_pages == 0:
                all_batches_completed = True
        
        return all_items

    async def _get_token_swaps_optimized(self, token_address: str) -> List[Dict]:
        """Optimized token swaps fetching with concurrent requests"""
        connector = aiohttp.TCPConnector(
            ssl=False,
            limit=20,  # Connection pool size
            limit_per_host=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=60
        )
        
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            creation_task = self._get_token_creation_time_async(session, token_address)
            metadata_task = self._get_token_metadata_async(session)
            
            creation_time, metadata = await asyncio.gather(creation_task, metadata_task)
            
            if not creation_time:
                return []
            
            self._cached_metadata = metadata
            
            launch_time = creation_time
            end_time = launch_time + 3600  # 1 hour after launch
            search_start_time = launch_time - 1
            
            headers = {
                "accept": "application/json",
                "x-chain": "solana",
                "X-API-KEY": self.birdeye_api_key
            }
            
            params = {
                "address": token_address,
                "limit": 100,
                "sort_by": "block_unix_time",
                "sort_type": "desc",
                "tx_type": "buy",
                "after_time": search_start_time,
                "before_time": end_time
            }
            
            all_swaps = await self._fetch_multiple_pages_concurrent(session, params, headers)
            
            filtered_swaps = [swap for swap in all_swaps if swap['block_unix_time'] >= launch_time]
            
            return filtered_swaps

    def _analyze_transactions_parallel(self, df: pd.DataFrame) -> List[Dict]:
        """Analyze transactions using parallel processing for large datasets"""
        if len(df) < 1000:
            return self._analyze_transactions_single_thread(df)
        
        num_cores = min(4, os.cpu_count())  # Limit to 4 cores max
        chunk_size = len(df) // num_cores
        chunks = [df[i:i + chunk_size] for i in range(0, len(df), chunk_size)]
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
            futures = [executor.submit(self._analyze_transactions_single_thread, chunk) for chunk in chunks]
            results = []
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    chunk_results = future.result()
                    results.extend(chunk_results)
                except Exception as e:
                    print(f"Error in parallel processing: {e}")
        
        deduplicated_results = self._deduplicate_suspicious_blocks(results)
        
        return deduplicated_results

    def _deduplicate_suspicious_blocks(self, suspicious_blocks: List[Dict]) -> List[Dict]:
        """Deduplicate suspicious blocks that may have been detected across multiple chunks"""
        block_map = {}
        
        for block in suspicious_blocks:
            block_num = block['block_number']
            
            if block_num not in block_map:
                block_map[block_num] = block
            else:
                existing = block_map[block_num]
                
                if (block['total_tokens'] > existing['total_tokens'] or 
                    (block['total_tokens'] == existing['total_tokens'] and 
                     block['num_trades'] > existing['num_trades'])):
                    
                    block_map[block_num] = block
        
        deduplicated = list(block_map.values())
        deduplicated.sort(key=lambda x: x['total_tokens'], reverse=True)
        
        return deduplicated

    def _analyze_transactions_single_thread(self, df: pd.DataFrame) -> List[Dict]:
        """Single-threaded transaction analysis (used for small datasets or as part of parallel processing)"""
        suspicious_blocks = []
            
        block_groups = df.groupby('block_number')
        
        for block_num, block_df in block_groups:
            block_df = block_df.sort_values('timestamp')
            
            block_trades = [{
                'timestamp': str(trade['timestamp']),
                'token_amount': float(trade['token_amount']),
                'sol_spent': float(trade['sol_spent']),
                'wallet': trade['owner']
            } for _, trade in block_df.iterrows()]
                
            tx_groups = block_df.groupby('tx_hash')
            for tx_hash, tx_df in tx_groups:
                if len(tx_df) >= 3:
                    unique_wallets = set(tx_df['owner'])
                    if len(unique_wallets) >= 3:
                        total_tokens = float(tx_df['token_amount'].sum())
                    
                        suspicious_blocks.append({
                            'block_number': int(block_num),
                            'timestamp': str(tx_df['timestamp'].iloc[0]),
                            'num_trades': len(tx_df),
                            'unique_wallets': len(unique_wallets),
                            'total_tokens': total_tokens,
                            'type': 'bundled_transaction',
                            'tx_hash': tx_hash[:10] + '...', 
                            'trades': block_trades
                        })
                
            if len(block_df) >= 3:
                time_diffs = block_df['timestamp'].diff().dropna()
                if (time_diffs.dt.total_seconds() <= 0.4).all():
                    unique_wallets = set(block_df['owner'])
                    if len(unique_wallets) >= 3:
                        total_tokens = float(block_df['token_amount'].sum())
                    
                        suspicious_blocks.append({
                            'block_number': int(block_num),
                            'timestamp': str(block_df['timestamp'].iloc[0]),
                            'num_trades': len(block_df),
                            'unique_wallets': len(unique_wallets),
                            'total_tokens': total_tokens,
                            'type': 'simultaneous_trades',
                            'trades': block_trades
                        })
        
        return suspicious_blocks

    async def _fetch_page(self, session: aiohttp.ClientSession, offset: int, 
                         params: Dict, headers: Dict) -> Dict:
        """Fetch a single page of transaction data"""
        try:
            if 'after_time' in params or 'before_time' in params:
                params['sort_by'] = 'block_unix_time'
                if 'sort_type' not in params:
                    params['sort_type'] = 'desc'
            
            params = {**params, "offset": offset}
            
            async with session.get(
                f"{self.base_url}/txs",
                headers=headers,
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Error Response Status: {response.status}")
                    print(f"Error Response Body: {error_text}")
                    print(f"Request URL: {response.url}")
                    print(f"Request params: {params}")
                    raise Exception(f"Birdeye API error: {response.status}")
                    
                data = await response.json()
                if not data.get('success'):
                    print(f"API returned unsuccessful response: {data}")
                    return {"data": {"items": []}, "success": False}
                
                return data
                
        except Exception as e:
            print(f"Error fetching page at offset {offset}: {str(e)}")
            return {"data": {"items": []}, "success": False}

    def run(self) -> Dict[str, Any]:
        """Run bundle detection analysis"""
        if not self.birdeye_api_key:
            raise ValueError("BIRDEYE_API_KEY not found in environment variables")
        return self.analyze_transactions(self.address)

    def analyze_transactions(self, token_address: str, minutes_to_analyze: int = 5) -> Dict[str, Any]:
        """Analyze transactions for potential bundling patterns"""
        try:
            self.token_address = token_address
            
            start_time = time.time()
            
            swaps = asyncio.run(self._get_token_swaps_optimized(token_address))
            
            if not swaps:
                return {
                    "has_bundled_trades": False,
                    "details": "No trades found in analysis period"
                }
            
            df = pd.DataFrame(swaps)
            df['timestamp'] = pd.to_datetime(df['block_unix_time'], unit='s')
            
            df = df[df['tx_type'] == 'buy']
            
            processing_start = time.time()
            
            df['token_amount'] = self._get_token_amount_vectorized(df)
            df['sol_spent'] = self._get_sol_spent_vectorized(df)
            
            processing_time = time.time() - processing_start
            
            analysis_start = time.time()
            
            suspicious_blocks = self._analyze_transactions_parallel(df)
            
            analysis_time = time.time() - analysis_start
            
            single_thread_blocks = self._analyze_transactions_single_thread(df)
            
            parallel_by_block = {b['block_number']: b for b in suspicious_blocks}
            single_by_block = {b['block_number']: b for b in single_thread_blocks}
            
            accuracy_fallback_needed = False
            for block_num in single_by_block:
                if block_num in parallel_by_block:
                    single_tokens = single_by_block[block_num]['total_tokens']
                    parallel_tokens = parallel_by_block[block_num]['total_tokens']
                    if single_tokens > parallel_tokens * 1.01:  # 1% tolerance
                        accuracy_fallback_needed = True
                        break
                elif single_by_block[block_num]['total_tokens'] > 1000000:
                    accuracy_fallback_needed = True
                    break
            
            if accuracy_fallback_needed:
                suspicious_blocks = single_thread_blocks
            
            if suspicious_blocks:
                metadata = getattr(self, '_cached_metadata', {})
                if not metadata:
                    print("⚠️ No cached metadata found, using fallback")
                    metadata = {}
                    
                total_supply = float(metadata.get('totalSupplyFormatted', 0))
                
                top_blocks = sorted(suspicious_blocks, key=lambda x: x['total_tokens'], reverse=True)[:5]
                total_bundle_tokens = sum(block['total_tokens'] for block in top_blocks)
                
                supply_percentage = (total_bundle_tokens / total_supply * 100) if total_supply > 0 else 0
                risk_level = self._get_risk_level(supply_percentage)
                
                total_time = time.time() - start_time
                print(f"\n🎯 OPTIMIZED ANALYSIS COMPLETED in {total_time:.2f}s")
                
                return {
                    "has_bundled_trades": True,
                    "risk_level": risk_level,
                    "supply_percentage": supply_percentage,
                    "total_bundles": len(suspicious_blocks),
                    "analysis_time": f"{total_time:.2f}s",
                    "performance_metrics": {
                        "total_time": total_time,
                        "fetch_time": "included in total",
                        "processing_time": processing_time,
                        "analysis_time": analysis_time,
                        "transactions_analyzed": len(df),
                        "bundles_found": len(suspicious_blocks)
                    },
                    "top_bundles": [{
                        "block": block['block_number'],
                        "trades": len(block['trades']) if 'trades' in block else block.get('num_trades', 0),
                        "wallets": block['unique_wallets'],
                        "tokens": block['total_tokens']
                    } for block in top_blocks]
                }
            
            total_time = time.time() - start_time
            print(f"\n✓ Analysis completed in {total_time:.2f}s - No bundles detected")
            
            return {
                "has_bundled_trades": False,
                "details": "No suspicious trading patterns detected",
                "analysis_time": f"{total_time:.2f}s",
                "performance_metrics": {
                    "total_time": total_time,
                    "transactions_analyzed": len(df),
                    "bundles_found": 0
                }
            }
            
        except Exception as e:
            print(f"Error during analysis: {str(e)}")
            return {
                "has_bundled_trades": False,
                "details": f"Error during analysis: {str(e)}",
                "analysis_time": "failed"
            }

    def _get_risk_level(self, supply_percentage: float) -> str:
        """Determine risk level based on supply percentage"""
        if supply_percentage >= 25:
            return "VERY HIGH"
        elif supply_percentage >= 10:
            return "HIGH"
        elif supply_percentage >= 5:
            return "CONSIDERABLE"
        elif supply_percentage >= 1:
            return "MODERATE"
        return "Not a significant amount of bundles detected on launch date."

    def _get_token_amount_vectorized(self, df: pd.DataFrame) -> pd.Series:
        """Vectorized token amount calculation for better performance"""
        try:
            is_buy = df['tx_type'] == 'buy'
            
            to_addresses = df['to'].apply(lambda x: x.get('address') if isinstance(x, dict) else None)
            to_amounts = df['to'].apply(lambda x: float(x.get('ui_amount', 0)) if isinstance(x, dict) else 0.0)
            
            is_target_token = to_addresses == self.token_address
            
            result = pd.Series(0.0, index=df.index)
            result[is_buy & is_target_token] = to_amounts[is_buy & is_target_token]
            
            return result
            
        except Exception as e:
            print(f"Error in vectorized token amount calculation: {e}")

            return df.apply(self._get_token_amount, axis=1)

    def _get_sol_spent_vectorized(self, df: pd.DataFrame) -> pd.Series:
        """Vectorized SOL spent calculation for better performance"""
        try:
            from_symbols = df['from'].apply(lambda x: x.get('symbol') if isinstance(x, dict) else None)
            from_amounts = df['from'].apply(lambda x: float(x.get('ui_amount', 0)) if isinstance(x, dict) else 0.0)
            
            to_symbols = df['to'].apply(lambda x: x.get('symbol') if isinstance(x, dict) else None)
            to_amounts = df['to'].apply(lambda x: float(x.get('ui_amount', 0)) if isinstance(x, dict) else 0.0)
            
            is_buy_sol = (df['tx_type'] == 'buy') & (from_symbols == 'SOL')
            is_sell_sol = to_symbols == 'SOL'
            
            result = pd.Series(0.0, index=df.index)
            result[is_buy_sol] = from_amounts[is_buy_sol]
            result[is_sell_sol] = to_amounts[is_sell_sol]
            
            return result
            
        except Exception as e:
            print(f"Error in vectorized SOL calculation: {e}")

            return df.apply(self._get_sol_spent, axis=1)

    def _get_token_amount(self, row):
        """Get bought amount of the target token - matching Moralis logic"""
        try:
            if row.get('tx_type') != 'buy':
                return 0

            if row.get('to', {}).get('address') == self.token_address:
                amount = float(row['to']['ui_amount'])
                return amount
                
            return 0
            
        except (KeyError, TypeError, ValueError) as e:
            print(f"Error extracting token amount: {e}")
            return 0

    def _get_sol_spent(self, row):
        """Get SOL spent on buying the target token"""
        try:
            if row.get('tx_type') == 'buy' and row.get('from', {}).get('symbol') == 'SOL':
                amount = float(row['from']['ui_amount'])
                return amount
            elif row.get('to', {}).get('symbol') == 'SOL':
                amount = float(row['to']['ui_amount'])
                return amount
            return 0
        except (KeyError, TypeError, ValueError) as e:
            print(f"Error extracting SOL amount: {e}")
            return 0

if __name__ == "__main__":
    test_address = "288k7P6sZA7cHGPATbKBHjqgditapKkVXjkAXKH3pump"
    detector = BundleDetector(address=test_address)
    
    print("🚀 OPTIMIZED BUNDLE DETECTOR - PERFORMANCE TEST")
    print("=" * 60)
    
    headers = {
        "accept": "application/json",
        "x-chain": "solana", 
        "X-API-KEY": detector.birdeye_api_key
    }
    test_params = {
        "address": test_address,
        "limit": 5,
        "tx_type": "buy"
    }
    
    response = requests.get(
        f"{detector.base_url}/txs",
        headers=headers,
        params=test_params
    )
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success') and data.get('data', {}).get('items'):
            print(f"✓ Found {len(data['data']['items'])} transactions for this token")
            first_tx = data['data']['items'][0]
            print(f"Most recent transaction: {first_tx.get('block_unix_time')} ({datetime.fromtimestamp(first_tx.get('block_unix_time'))})")
        else:
            print("✗ No transactions found for this token")
    else:
        print(f"✗ API request failed: {response.status_code}")
        print(f"Response: {response.text}")
    
    start_time = time.time()
    result = detector.run()
    total_execution_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("📊 BUNDLE ANALYSIS RESULTS")
    print("=" * 60)
    print(f"Bundled Trades Detected: {result['has_bundled_trades']}")
    
    if result['has_bundled_trades']:
        print(f"Risk Level: {result['risk_level']}")
        print(f"Supply Percentage: {result['supply_percentage']:.2f}%")
        print(f"Total Bundles Found: {result['total_bundles']}")
        print(f"Analysis Time: {result.get('analysis_time', 'N/A')}")
        
        if 'performance_metrics' in result:
            metrics = result['performance_metrics']
            print(f"\n📈 PERFORMANCE METRICS:")
            print(f"- Total Execution Time: {total_execution_time:.2f}s")
            print(f"- Transactions Analyzed: {metrics.get('transactions_analyzed', 'N/A')}")
            print(f"- Bundles Found: {metrics.get('bundles_found', 'N/A')}")
            print(f"- Processing Time: {metrics.get('processing_time', 'N/A'):.2f}s")
            print(f"- Analysis Time: {metrics.get('analysis_time', 'N/A'):.2f}s")
        
        print(f"\n🔍 TOP BUNDLE DETAILS:")
        for i, bundle in enumerate(result['top_bundles'][:5], 1):
            print(f"  {i}. Block {bundle['block']}: {bundle['trades']} trades, {bundle['wallets']} wallets, {bundle['tokens']:,.2f} tokens")
    else:
        print(result.get('details', 'No suspicious trading patterns detected'))
        if 'analysis_time' in result:
            print(f"Analysis Time: {result['analysis_time']}")
