from agency_swarm.tools import BaseTool
from pydantic import Field
from typing import Dict, Any, List
import os
import requests
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
import asyncio
import aiohttp

load_dotenv()

class BundleDetector(BaseTool):
    """Tool for detecting coordinated buying patterns"""
    
    name: str = "BundleDetector"
    description: str = "Analyzes transactions to detect potential bundled trades"
    
    address: str = Field(
        description="Token address to analyze for bundle patterns"
    )
    moralis_api_key: str = Field(
        default=os.getenv("MORALIS_API_KEY"),
        description="Moralis API key for data access"
    )
    base_url: str = Field(
        default="https://solana-gateway.moralis.io/token",
        description="Base URL for Moralis API"
    )
    token_address: str = Field(
        default=None,
        description="Current token being analyzed"
    )
    
    def run(self) -> Dict[str, Any]:
        """Run bundle detection analysis"""
        if not self.moralis_api_key:
            raise ValueError("MORALIS_API_KEY not found in environment variables")
        return self.analyze_transactions(self.address)

    def analyze_transactions(self, token_address: str, minutes_to_analyze: int = 5) -> Dict[str, Any]:
        """Analyze transactions for potential bundling patterns"""
        try:
            self.token_address = token_address
            swaps = self._get_token_swaps(token_address, minutes_to_analyze)
            if not swaps:
                return {
                    "has_bundled_trades": False,
                    "details": "No trades found in analysis period"
                }
            
            df = pd.DataFrame(swaps)
            df['timestamp'] = pd.to_datetime(df['blockTimestamp'])
            df = df[df['transactionType'] == 'buy']
            
            df['token_amount'] = df.apply(self._get_token_amount, axis=1)
            df['sol_spent'] = df.apply(self._get_sol_spent, axis=1)
            
            suspicious_blocks = []
            
            block_groups = df.groupby('blockNumber')
            for block_num, block_df in block_groups:
                block_df = block_df.sort_values('timestamp')
                
                block_trades = [{
                    'timestamp': str(trade['timestamp']),
                    'token_amount': float(trade['token_amount']),
                    'sol_spent': float(trade['sol_spent']),
                    'wallet': trade['walletAddress']
                } for _, trade in block_df.iterrows()]
                
                tx_groups = block_df.groupby('transactionHash')
                for tx_hash, tx_df in tx_groups:
                    if len(tx_df) >= 3:
                        unique_wallets = set(tx_df['walletAddress'])
                        if len(unique_wallets) >= 3:
                            suspicious_blocks.append({
                                'block_number': int(block_num),
                                'timestamp': str(tx_df['timestamp'].iloc[0]),
                                'num_trades': len(tx_df),
                                'unique_wallets': len(unique_wallets),
                                'total_tokens': float(tx_df['token_amount'].sum()),
                                'type': 'bundled_transaction',
                                'tx_hash': tx_hash[:10] + '...', 
                                'trades': block_trades
                            })
                
                if len(block_df) >= 3:
                    time_diffs = block_df['timestamp'].diff().dropna()
                    if (time_diffs.dt.total_seconds() <= 0.4).all():
                        unique_wallets = set(block_df['walletAddress'])
                        if len(unique_wallets) >= 3:
                            suspicious_blocks.append({
                                'block_number': int(block_num),
                                'timestamp': str(block_df['timestamp'].iloc[0]),
                                'num_trades': len(block_df),
                                'unique_wallets': len(unique_wallets),
                                'total_tokens': float(block_df['token_amount'].sum()),
                                'type': 'simultaneous_trades',
                                'trades': block_trades
                            })
            
            if suspicious_blocks:
                metadata = self._get_token_metadata()
                total_supply = float(metadata.get('totalSupplyFormatted', 0))
                
                # Calculate total bundle tokens from top 5 blocks only
                top_blocks = sorted(suspicious_blocks, key=lambda x: x['total_tokens'], reverse=True)[:5]
                total_bundle_tokens = sum(block['total_tokens'] for block in top_blocks)
                
                # Calculate risk metrics
                supply_percentage = (total_bundle_tokens / total_supply * 100) if total_supply > 0 else 0
                risk_level = self._get_risk_level(supply_percentage)
                
                return {
                    "has_bundled_trades": True,
                    "risk_level": risk_level,
                    "supply_percentage": supply_percentage,
                    "total_bundles": len(suspicious_blocks),
                    "top_bundles": [{
                        "block": block['block_number'],
                        "trades": len(block['trades']),
                        "wallets": block['unique_wallets'],
                        "tokens": block['total_tokens']
                    } for block in top_blocks]
                }
            
            return {
                "has_bundled_trades": False,
                "details": "No suspicious trading patterns detected"
            }
            
        except Exception as e:
            return {
                "has_bundled_trades": False,
                "details": f"Error during analysis: {str(e)}"
            }
    
    async def _fetch_page(self, session: aiohttp.ClientSession, cursor: str, 
                         params: Dict, headers: Dict) -> Dict:
        """Fetch a single page of swap data"""
        if cursor:
            params = {**params, "cursor": cursor}
            
        try:
            async with session.get(
                f"{self.base_url}/mainnet/{self.token_address}/swaps",
                headers=headers,
                params=params
            ) as response:
                if response.status != 200:
                    print(f"Error Response: {await response.text()}")
                    raise Exception(f"Moralis API error: {response.status}")
                return await response.json()
        except Exception as e:
            print(f"Error fetching page: {str(e)}")
            return {"result": [], "cursor": None}

    async def _get_token_swaps_async(self, token_address: str, minutes: int) -> List[Dict]:
        """Get token swaps using parallel API calls"""
        headers = {
            "X-API-Key": self.moralis_api_key,
            "Accept": "application/json"
        }
        
        initial_params = {
            "network": "mainnet",
            "order": "ASC",
            "pageSize": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/mainnet/{token_address}/swaps",
                headers=headers,
                params=initial_params
            ) as response:
                if response.status != 200:
                    raise Exception(f"Moralis API error: {response.status}")
                data = await response.json()
                
                if not data.get('result'):
                    return []
                
                launch_time = datetime.fromisoformat(data['result'][0]['blockTimestamp'])
                end_time = launch_time + timedelta(hours=1)
                
                params = {
                    "network": "mainnet",
                    "order": "ASC",
                    "fromDate": launch_time.isoformat(),
                    "toDate": end_time.isoformat()
                }
                
                first_page = await self._fetch_page(session, "", params, headers)
                all_swaps = first_page.get('result', [])
                cursors = []

                cursor = first_page.get('cursor')
                while cursor and len(cursors) < 9:
                    cursors.append(cursor)
                    page = await self._fetch_page(session, cursor, params, headers)
                    cursor = page.get('cursor')
                
                tasks = [
                    self._fetch_page(session, cursor, params, headers)
                    for cursor in cursors
                ]
                
                results = await asyncio.gather(*tasks)
                
                for result in results:
                    all_swaps.extend(result.get('result', []))
                
                print(f"\nFound {len(all_swaps)} trades in first hour using parallel API calls")
                return all_swaps

    def _get_token_swaps(self, token_address: str, minutes: int) -> List[Dict]:
        """Synchronous wrapper for async swap fetching"""
        self.token_address = token_address
        return asyncio.run(self._get_token_swaps_async(token_address, minutes))
    
    def _check_current_holdings(self, wallet_address: str) -> float:
        """Check current token holdings for a wallet using Moralis API"""
        try:
            print(f"\nChecking holdings for wallet: {wallet_address}")
            
            headers = {
                "X-API-Key": self.moralis_api_key,
                "Accept": "application/json"
            }
            
            response = requests.get(
                f"https://solana-gateway.moralis.io/account/mainnet/{wallet_address}/tokens",
                headers=headers
            )
            
            if response.status_code == 200:
                tokens = response.json()
                for token in tokens:
                    if token.get('mint') == self.token_address:
                        amount = float(token.get('amount', 0))
                        print(f"Found {amount} tokens")
                        return amount
                print("No holdings found")
                return 0
            else:
                print(f"API error: {response.status_code}")
                return 0
        except Exception as e:
            print(f"Error checking holdings: {str(e)}")
            return 0

    def _get_current_holders(self) -> Dict[str, float]:
        """Get current token holders using Birdeye API"""
        try:
            headers = {
                "X-API-KEY": os.getenv("BIRDEYE_API_KEY"),
                "Accept": "application/json"
            }
            
            print(f"\nFetching holders for token: {self.token_address}")
            
            response = requests.get(
                f"https://public-api.birdeye.so/defi/v3/token/holder",
                headers=headers,
                params={
                    "address": self.token_address,
                    "limit": 100
                }
            )
            
            print(f"Birdeye API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                holders = {}
                
                print("\nSample holders from Birdeye:")
                for i, holder in enumerate(data.get('data', {}).get('items', [])[:3]):
                    print(f"Holder {i+1}: {holder['owner']} = {holder['ui_amount']}")
                
                for holder in data.get('data', {}).get('items', []):
                    holders[holder['owner']] = float(holder['ui_amount'])
                
                print(f"Total holders found: {len(holders)}")
                return holders
                
            print(f"Error response: {response.text}")
            return {}
        except Exception as e:
            print(f"Error getting holders: {str(e)}")
            return {}

    def _get_token_metadata(self) -> Dict[str, Any]:
        """Get token metadata using Moralis API"""
        try:
            headers = {
                "X-API-Key": self.moralis_api_key,
                "Accept": "application/json"
            }
            
            response = requests.get(
                f"https://solana-gateway.moralis.io/token/mainnet/{self.token_address}/metadata",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            print(f"Error getting metadata: {response.text}")
            return {}
        except Exception as e:
            print(f"Error getting metadata: {str(e)}")
            return {}

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

    def _generate_details(self, suspicious_blocks: List[Dict]) -> str:
        """Generate human-readable details about suspicious blocks"""
        if not suspicious_blocks:
            return "No suspicious patterns detected"
        
        metadata = self._get_token_metadata()
        total_supply = float(metadata.get('totalSupplyFormatted', 0))
        token_name = metadata.get('name', 'Unknown Token')
        token_symbol = metadata.get('symbol', '')
        
        unique_blocks = {block['block_number']: block for block in suspicious_blocks}
        
        blocks = sorted(unique_blocks.values(), key=lambda x: x['total_tokens'], reverse=True)[:5]
        
        details = []
        total_bundle_tokens = 0
        
        for block in blocks:
            total_bundle_tokens += block['total_tokens']
            total_usd = sum(float(trade.get('totalValueUsd', 0)) for trade in block.get('trades', []))
            
            if block['type'] == 'bundled_transaction':
                details.append(
                    f"Block {block['block_number']}: "
                    f"{block['num_trades']} trades "
                    f"({block['unique_wallets']} unique wallets) "
                    f"bought {block['total_tokens']:,.2f} {token_symbol} "
                    f"for ${total_usd:,.2f} USD "
                    f"[TX: {block['tx_hash'][:10]}...]"
                )
            else:
                details.append(
                    f"Block {block['block_number']}: "
                    f"{block['num_trades']} trades "
                    f"({block['unique_wallets']} unique wallets) "
                    f"bought {block['total_tokens']:,.2f} {token_symbol} "
                    f"for ${total_usd:,.2f} USD"
                )
        
        supply_percentage = (total_bundle_tokens / total_supply * 100) if total_supply > 0 else 0
        risk_level = self._get_risk_level(supply_percentage)
        
        details.extend([
            "",
            f"Summary for {token_name} ({token_symbol}):",
            f"Total {token_symbol} bought in top 5 bundles: {total_bundle_tokens:,.2f}",
            f"Total token supply: {total_supply:,.2f}",
            f"Bundle buy percentage of supply: {supply_percentage:.4f}%",
            f"Risk Level: {risk_level}"
        ])
        
        risk_messages = {
            "VERY HIGH": "\nVERY HIGH RISK ALERT: Massive bundle buying detected! Over 25% of supply bought in bundles.",
            "HIGH": "\nHIGH RISK ALERT: Large-scale bundle buying detected! Over 10% of supply bought in bundles.",
            "CONSIDERABLE": "\nRISK ALERT: Sizeable bundle buying detected! Over 5% of supply bought in bundles.",
            "MODERATE": "\nMODERATE RISK: Notable bundle buying detected (1-5% of supply).",
            "LOW": "\nLOW RISK: Bundle buying activity less than 1% of supply."
        }
        details.append(risk_messages[risk_level])
        
        total_bundles = len(suspicious_blocks)
        if total_bundles > 5:
            details.append(f"\nShowing top 5 of {total_bundles} total bundles")
        
        return "\n".join(details)

    def _get_token_amount(self, row):
        """Get bought amount of the target token"""
        try:
            if row['baseToken'] == self.token_address:
                return float(row['bought']['amount'])
            elif row['quoteToken'] == self.token_address:
                return float(row['sold']['amount'])
            return 0
        except (KeyError, TypeError, ValueError):
            return 0

    def _get_sol_spent(self, row):
        """Get SOL spent on buying the target token"""
        try:
            if row['transactionType'] == 'buy':
                if row['baseToken'] == self.token_address:
                    return float(row['sold']['amount'])
                elif row['quoteToken'] == self.token_address:
                    return float(row['bought']['amount'])
            return 0
        except (KeyError, TypeError, ValueError):
            return 0

if __name__ == "__main__":
    test_address = "AnXE9mZYWReqBw4v5HrY2S2utt42uEtcBGmuCXASvRAi"
    detector = BundleDetector(address=test_address)
    
    result = detector.run()
    
    print("\nBundle Analysis Results:")
    print(f"Bundled Trades Detected: {result['has_bundled_trades']}")
    print("\nDetails:")
    
    if result['has_bundled_trades']:
        print(f"Risk Level: {result['risk_level']}")
        print(f"Supply Percentage: {result['supply_percentage']:.2f}%")
        print(f"Total Bundles Found: {result['total_bundles']}")
        print("\nTop Bundle Details:")
        for bundle in result['top_bundles']:
            print(f"Block {bundle['block']}: {bundle['trades']} trades, {bundle['wallets']} unique wallets, {bundle['tokens']:.2f} tokens")
    else:
        print(result.get('details', 'No suspicious trading patterns detected'))
    