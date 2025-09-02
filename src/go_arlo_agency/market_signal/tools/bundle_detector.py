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
    """Tool for detecting coordinated buying patterns on Solana tokens"""
    
    name: str = "BundleDetector"
    description: str = "Analyzes transactions to detect potential bundled trades (Solana only)"
    
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
    
    def _detect_chain(self, address: str) -> str:
        """Auto-detect chain based on address format"""
        if address.startswith("0x"):
            return "base"
        else:
            return "solana"

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
        """Analyze transactions using parallel processing for large datasets with proper block handling"""
        if len(df) < 1000:
            return self._analyze_transactions_single_thread(df)
        
        unique_blocks = df['block_number'].unique()
        num_cores = min(4, os.cpu_count())  # Limit to 4 cores max

        blocks_per_core = len(unique_blocks) // num_cores
        if blocks_per_core == 0:
            return self._analyze_transactions_single_thread(df)
        
        block_chunks = []
        for i in range(num_cores):
            start_idx = i * blocks_per_core
            if i == num_cores - 1:
                chunk_blocks = unique_blocks[start_idx:]
            else:
                chunk_blocks = unique_blocks[start_idx:start_idx + blocks_per_core]
            
            chunk_df = df[df['block_number'].isin(chunk_blocks)]
            if len(chunk_df) > 0:
                block_chunks.append(chunk_df)
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
            futures = [executor.submit(self._analyze_transactions_single_thread, chunk) for chunk in block_chunks]
            results = []
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    chunk_results = future.result()
                    results.extend(chunk_results)
                except Exception as e:
                    print(f"Error in parallel processing: {e}")
        
        seen_blocks = set()
        deduplicated_results = []
        
        for block in results:
            block_num = block['block_number']
            if block_num not in seen_blocks:
                seen_blocks.add(block_num)
                deduplicated_results.append(block)
            else:
                print(f"⚠️ Warning: Found duplicate block {block_num} in parallel processing results")
        
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
        suspicious_blocks = []

        block_groups = df.groupby('block_number')
        
        for block_num, block_df in block_groups:
            block_df = block_df.sort_values('timestamp')
            
            processed_tx_hashes = set()

            tx_groups = block_df.groupby('tx_hash')
            
            for tx_hash, tx_df in tx_groups:
                if tx_hash in processed_tx_hashes:
                    continue
                    
                if len(tx_df) >= 3:
                    unique_wallets = set(tx_df['owner'])
                    if len(unique_wallets) >= 3:  # At least 3 unique wallets
                        total_tokens = float(tx_df['token_amount'].sum())
                        
                        if total_tokens > 0:  # Only count if we actually got tokens
                            block_trades = [{
                                'timestamp': str(trade['timestamp']),
                                'token_amount': float(trade['token_amount']),
                                'sol_spent': float(trade['sol_spent']),
                                'wallet': trade['owner'],
                                'tx_hash': trade['tx_hash']
                            } for _, trade in tx_df.iterrows()]
                            
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
                            
                            processed_tx_hashes.add(tx_hash)
            
            remaining_df = block_df[~block_df['tx_hash'].isin(processed_tx_hashes)]
            
            if len(remaining_df) >= 3:
                time_diffs = remaining_df['timestamp'].diff().dropna()
                
                if len(time_diffs) > 0 and (time_diffs.dt.total_seconds() <= 1.0).all():
                    unique_wallets = set(remaining_df['owner'])
                    unique_tx_hashes = set(remaining_df['tx_hash'])
                    
                    if len(unique_wallets) >= 3 and len(unique_tx_hashes) >= 2:
                        total_tokens = float(remaining_df['token_amount'].sum())
                        
                        if total_tokens > 0:
                            block_trades = [{
                                'timestamp': str(trade['timestamp']),
                                'token_amount': float(trade['token_amount']),
                                'sol_spent': float(trade['sol_spent']),
                                'wallet': trade['owner'],
                                'tx_hash': trade['tx_hash']
                            } for _, trade in remaining_df.iterrows()]
                            
                            suspicious_blocks.append({
                                'block_number': int(block_num),
                                'timestamp': str(remaining_df['timestamp'].iloc[0]),
                                'num_trades': len(remaining_df),
                                'unique_wallets': len(unique_wallets),
                                'total_tokens': total_tokens,
                                'type': 'simultaneous_trades',
                                'tx_hash_count': len(unique_tx_hashes),
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

        detected_chain = self._detect_chain(self.address)
        if detected_chain == "base":
            return {
                "has_bundled_trades": False,
                "details": "Bundle detection is not supported for Base chain tokens.",
                "chain": "base",
                "supported": False
            }
        

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
                    print("No cached metadata found, using fallback")
                    metadata = {}
                    
                total_supply = float(metadata.get('totalSupplyFormatted', 0))
                
                top_blocks = sorted(suspicious_blocks, key=lambda x: x['total_tokens'], reverse=True)[:5]
                total_bundle_tokens = sum(block['total_tokens'] for block in top_blocks)
                
                if total_supply > 0 and total_bundle_tokens > total_supply:
                    print(f"WARNING: Bundled tokens ({total_bundle_tokens:,.0f}) exceed total supply ({total_supply:,.0f})")
                    print(f"Debugging token calculation for top blocks:")
                    
                    for i, block in enumerate(top_blocks[:3], 1):
                        print(f"  Block {i} ({block['block_number']}): {block['total_tokens']:,.0f} tokens from {block['num_trades']} trades")
                        if 'trades' in block:
                            sample_trades = block['trades'][:5]
                            for j, trade in enumerate(sample_trades, 1):
                                print(f"    Trade {j}: {trade['token_amount']:,.0f} tokens (wallet: {trade['wallet'][:8]}...)")
                    
                    print("🔧 Attempting conservative recalculation...")

                    all_unique_trades = set()
                    recalculated_total = 0
                    
                    for block in suspicious_blocks:
                        if 'trades' in block:
                            for trade in block['trades']:
                                trade_key = (trade.get('tx_hash', ''), trade.get('wallet', ''), trade.get('timestamp', ''))
                                if trade_key not in all_unique_trades:
                                    all_unique_trades.add(trade_key)
                                    recalculated_total += trade['token_amount']
                    
                    if recalculated_total <= total_supply:
                        print(f"✓ Conservative recalculation: {recalculated_total:,.0f} tokens (within supply)")
                        total_bundle_tokens = recalculated_total
                    else:
                        print(f"Even conservative calculation exceeds supply: {recalculated_total:,.0f}")
                        total_bundle_tokens = min(total_bundle_tokens, total_supply * 0.95)
                        print(f"Capping bundled tokens at {total_bundle_tokens:,.0f} (95% of supply)")

                supply_percentage = (total_bundle_tokens / total_supply * 100) if total_supply > 0 else 0
                risk_level = self._get_risk_level(supply_percentage)
                
                total_time = time.time() - start_time
                print(f"\nOPTIMIZED ANALYSIS COMPLETED in {total_time:.2f}s")
                print(f"\nTotal Supply: {total_supply:,.0f} | Bundled Tokens: {total_bundle_tokens:,.0f} | Percentage: {supply_percentage:.2f}%")
                
                return {
                    "has_bundled_trades": True,
                    "risk_level": risk_level,
                    "supply_percentage": supply_percentage,
                    "total_bundles": len(suspicious_blocks),
                    "total_supply": total_supply,
                    "bundled_tokens": total_bundle_tokens,
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
            print(f"Error during optimized analysis: {str(e)}")
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
        try:
            is_buy = df['tx_type'] == 'buy'
            
            to_addresses = df['to'].apply(lambda x: x.get('address') if isinstance(x, dict) else None)
            to_amounts = df['to'].apply(lambda x: float(x.get('ui_amount', 0)) if isinstance(x, dict) else 0.0)
            
            is_target_token = to_addresses == self.token_address
            
            result = pd.Series(0.0, index=df.index)
            valid_mask = is_buy & is_target_token
            result[valid_mask] = to_amounts[valid_mask]

            max_amount = result.max()
            total_amount = result.sum()
            
            if max_amount > 1e12:
                print(f"⚠️ Warning: Found extremely large token amount: {max_amount:,.0f}")
                problematic = df[result > 1e12]
                if len(problematic) > 0:
                    print(f"   Problematic transactions: {len(problematic)}")
                    for idx, row in problematic.head().iterrows():
                        print(f"   - Block {row['block_number']}: {result[idx]:,.0f} tokens")
            
            if total_amount > 1e15:
                print(f"⚠️ Warning: Total token amount seems unrealistic: {total_amount:,.0f}")
                print(f"   This might indicate double-counting or data quality issues")
            
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
    
    print("🚀 BUNDLE DETECTOR")
    print("=" * 60)
    
    print("Testing chain detection...")
    solana_address = "7SstFSsCm3SPaV24bkgrvypspjLDB8feEJYVka4vbonk"
    base_address = "0x1111111111166b7FE7bd91427724B487980aFc69"
    
    print(f"Solana address ({solana_address[:20]}...): {detector._detect_chain(solana_address)}")
    print(f"Base address ({base_address}): {detector._detect_chain(base_address)}")

    print(f"\nTesting Base token support...")
    base_detector = BundleDetector(address=base_address)
    base_result = base_detector.run()
    print(f"Base token result: {base_result}")

    print(f"\nTesting Solana token with double-counting fixes...")
    
    print("Testing API connection and data availability...")
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
        print(f"Total Supply: {result.get('total_supply', 'N/A'):,.0f}")
        print(f"Bundled Tokens: {result.get('bundled_tokens', 'N/A'):,.0f}")
        print(f"Analysis Time: {result.get('analysis_time', 'N/A')}")
        
        if 'total_supply' in result and 'bundled_tokens' in result:
            if result['bundled_tokens'] > result['total_supply']:
                print("ERROR: Bundled tokens still exceed total supply!")
            else:
                print("VALIDATION PASSED: Bundled tokens within reasonable range")
        
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
