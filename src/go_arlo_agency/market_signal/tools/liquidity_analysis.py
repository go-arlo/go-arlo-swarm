from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
BASE_URL = "https://public-api.birdeye.so"

class LiquidityAnalysis(BaseTool):
    """
    Analyzes token liquidity across different DEXes using Birdeye API.
    Supports both Solana and Base chains with automatic detection.
    Provides structured liquidity analysis output.
    """

    address: str = Field(
        ..., 
        description="The token address to analyze"
    )
    
    chain: str = Field(
        default="auto",
        description="The blockchain network (auto-detect, solana, or base)"
    )

    class Config:
        json_schema_extra = {
            "response_format": {
                "type": "object",
                "properties": {
                    "health_score": {
                        "type": "number",
                        "description": "Liquidity health score from 0-100"
                    },
                    "liquidity_summary": {
                        "type": "string",
                        "description": "One-line summary of liquidity status"
                    },
                    "key_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 5,
                        "description": "Key liquidity metrics and findings"
                    }
                }
            }
        }

    def _detect_chain(self, address: str) -> str:
        """Auto-detect chain based on address format"""
        if address.startswith("0x"):
            return "base"
        else:
            return "solana"

    def run(self):
        """
        Executes comprehensive liquidity analysis
        """
        try:
            if self.chain == "auto":
                detected_chain = self._detect_chain(self.address)
                print(f"Auto-detected chain: {detected_chain} for address: {self.address}")
            else:
                detected_chain = self.chain
            
            pairs_data = self._get_pairs_data(detected_chain)

            exit_liquidity_data = None
            if detected_chain == "base":
                exit_liquidity_data = self._get_exit_liquidity_data(detected_chain)
            
            print(f"\nBirdeye API Response for {detected_chain}:")
            print(f"Status Code: {pairs_data.get('status_code')}")
            print("Response Data:")
            print(pairs_data)
            print("\n")
            
            if exit_liquidity_data:
                print(f"Exit Liquidity API Response for {detected_chain}:")
                print(f"Status Code: {exit_liquidity_data.get('status_code')}")
                print("Response Data:")
                print(exit_liquidity_data)
                print("\n")
            
            health_score = self._calculate_health_score(pairs_data, detected_chain, exit_liquidity_data)
            
            liquidity_summary = self._generate_liquidity_summary(pairs_data, detected_chain, exit_liquidity_data)
            key_metrics = self._generate_key_metrics(pairs_data, detected_chain, exit_liquidity_data)
            
            return {
                "success": True,
                "chain": detected_chain,
                "health_score": health_score['score'],
                "liquidity_summary": liquidity_summary,
                "key_metrics": key_metrics
            }
            
        except Exception as e:
            return {
                "success": False,
                "chain": detected_chain if 'detected_chain' in locals() else "unknown",
                "health_score": 0,
                "liquidity_summary": f"Error analyzing liquidity: {str(e)}",
                "key_metrics": [
                    "Analysis failed due to error",
                    "Liquidity status cannot be determined",
                    "Manual verification recommended"
                ]
            }

    def _get_pairs_data(self, chain: str):
        """Fetch liquidity pairs data from Birdeye API"""
        endpoint = f"{BASE_URL}/defi/v2/markets"
        
        headers = {
            "accept": "application/json",
            "x-chain": chain,
            "X-API-KEY": BIRDEYE_API_KEY
        }
        
        params = {
            "address": self.address,
            "time_frame": "24h",
            "sort_type": "desc",
            "sort_by": "liquidity",
            "offset": 0,
            "limit": 20
        }
        
        response = requests.get(endpoint, headers=headers, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Birdeye API error for {chain} chain: {response.status_code} - {response.text}")
            
        data = response.json()
        data['status_code'] = response.status_code
        return data

    def _get_exit_liquidity_data(self, chain: str):
        """Fetch token exit liquidity data from Birdeye API"""
        endpoint = f"{BASE_URL}/defi/v3/token/exit-liquidity"

        headers = {
            "accept": "application/json",
            "x-chain": chain,
            "X-API-KEY": BIRDEYE_API_KEY
        }

        params = {
            "address": self.address
        }

        response = requests.get(endpoint, headers=headers, params=params)

        if response.status_code != 200:
            raise Exception(f"Birdeye exit-liquidity API error for {chain} chain: {response.status_code} - {response.text}")

        data = response.json()
        data['status_code'] = response.status_code
        return data

    def _safe_float(self, value, default=0.0):
        """Safely convert value to float"""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _get_exchange_name(self, pair: dict, chain: str) -> str:
        """Get exchange name based on chain type"""
        if chain == "base":
            source = pair.get("source", "")
            if source:
                return f"DEX-{source[:6]}..."  # Abbreviated address
            else:
                return "Unknown DEX"
        else:
            # For Solana, source is the exchange name
            return pair.get("source", "Unknown")

    def _calculate_health_score(self, data, chain: str, exit_data=None):
        """Calculate liquidity health score (0-100)"""
        try:
            pairs = data.get("data", {}).get("items", [])
            if not pairs:
                return {
                    'score': 0,
                    'positive_points': 0,
                    'negative_points': 1
                }
            
            positive_points = 0
            negative_points = 0
            
            total_liquidity = sum(self._safe_float(pair.get("liquidity", 0)) for pair in pairs)
            
            if chain == "base":
                unique_exchanges = len(set(pair.get("source") for pair in pairs if pair.get("source")))
            else:
                unique_exchanges = len(set(pair.get("source") for pair in pairs if pair.get("source")))
            
            # Base score on liquidity depth (max 40 points)
            if total_liquidity > 1_000_000:
                liquidity_score = 40
                positive_points += 1
            elif total_liquidity > 500_000:
                liquidity_score = 30
                positive_points += 1
            elif total_liquidity > 100_000:
                liquidity_score = 20
            elif total_liquidity > 50_000:
                liquidity_score = 10
                negative_points += 1
            else: 
                liquidity_score = 0
                negative_points += 1
            
            # Add points for exchange diversity (max 30 points)
            if unique_exchanges >= 3:
                exchange_score = 30
                positive_points += 1
            elif unique_exchanges == 2:
                exchange_score = 20
            else:
                exchange_score = 10
                negative_points += 1
            
            # Add points for volume/liquidity ratio (max 30 points)
            total_volume = sum(self._safe_float(pair.get("volume24h", 0)) for pair in pairs)
            volume_ratio = total_volume / total_liquidity if total_liquidity > 0 else 0
            
            if volume_ratio > 1.0:
                volume_score = 30
                positive_points += 1
            elif volume_ratio > 0.5:
                volume_score = 20
                positive_points += 1
            elif volume_ratio > 0.1:
                volume_score = 10
            else:
                volume_score = 0
                negative_points += 1
            
            final_score = liquidity_score + exchange_score + volume_score

            # Integrate exit-liquidity signal (Base chain only)
            try:
                exit_info = (exit_data or {}).get('data', {})
                exit_liquidity_value = self._safe_float(exit_info.get('exit_liquidity', 0))

                # Exit liquidity contribution based on absolute values
                if exit_liquidity_value > 1_000_000:
                    final_score += 15
                    positive_points += 1
                elif exit_liquidity_value > 500_000:
                    final_score += 10
                    positive_points += 1
                elif exit_liquidity_value > 100_000:
                    final_score += 5
                elif exit_liquidity_value > 0 and exit_liquidity_value < 50_000:
                    final_score -= 10
                    negative_points += 1
            except Exception:
                pass
            
            for pair in pairs:
                try:
                    trade_change = abs(self._safe_float(pair.get("trade24hChangePercent", 0)))
                    if trade_change > 1000:
                        final_score = min(final_score, 90)
                        negative_points += 1
                        break
                except (ValueError, TypeError):
                    continue
            
            return {
                'score': max(min(final_score, 100), 0),
                'positive_points': positive_points,
                'negative_points': negative_points
            }
            
        except Exception as e:
            print(f"Error calculating health score: {str(e)}")
            return {
                'score': 0,
                'positive_points': 0,
                'negative_points': 1
            }

    def _generate_liquidity_summary(self, data, chain: str, exit_data=None):
        """Generate one-line liquidity summary"""
        pairs = data.get("data", {}).get("items", [])
        exit_info = (exit_data or {}).get('data', {})
        exit_liquidity_value = self._safe_float(exit_info.get('exit_liquidity', 0))
        
        if not pairs and exit_liquidity_value == 0:
            return f"No active liquidity pairs or exit liquidity found on {chain}"
            
        total_liquidity = sum(self._safe_float(pair.get("liquidity", 0)) for pair in pairs)
        
        if chain == "base":
            unique_exchanges = len(set(pair.get("source") for pair in pairs if pair.get("source")))
        else:
            unique_exchanges = len(set(pair.get("source") for pair in pairs if pair.get("source")))

        if exit_liquidity_value > 0:
            if total_liquidity > 1_000_000 and unique_exchanges >= 3 and exit_liquidity_value > 500_000:
                return f"Strong liquidity across multiple {chain} DEXes with institutional-grade exit liquidity"
            elif total_liquidity > 500_000 and exit_liquidity_value > 200_000:
                return f"Moderate liquidity (${total_liquidity:,.0f}) with substantial exit liquidity available"
            elif exit_liquidity_value >= 100_000:
                return f"Moderate {chain} liquidity suitable for medium-sized positions"
            elif exit_liquidity_value >= 50_000:
                return f"Limited {chain} liquidity requiring careful position sizing"
            else:
                return f"Constrained {chain} liquidity with severely limited exit options"
        
        if total_liquidity > 1_000_000 and unique_exchanges >= 3:
            return f"Strong liquidity across multiple {chain} DEXes with healthy depth"
        elif total_liquidity > 500_000:
            return f"Moderate liquidity of ${total_liquidity:,.0f} with {unique_exchanges} active {chain} DEXes"
        elif total_liquidity > 100_000:
            return f"Limited {chain} liquidity requiring careful position sizing"
        else:
            return f"Low {chain} liquidity presenting significant trading risks"

    def _calculate_price_impact(self, pair_data, chain: str):
        """Calculate price impact estimate using available data"""
        try:
            STANDARD_TRADE_SIZE = 1000
            
            active_pairs = [p for p in pair_data if self._safe_float(p.get('volume24h', 0)) > 0]

            sorted_pairs = sorted(active_pairs, key=lambda x: self._safe_float(x.get('liquidity', 0)), reverse=True)[:3]
            
            if not sorted_pairs:
                return 100.00
            
            total_impact = 0
            total_liquidity = sum(self._safe_float(pair.get('liquidity', 0)) for pair in sorted_pairs)
            
            if total_liquidity == 0:
                return 100.00
            
            for pair in sorted_pairs:
                try:
                    pool_liquidity = self._safe_float(pair.get('liquidity', 0))
                    pool_weight = pool_liquidity / total_liquidity if total_liquidity > 0 else 0
                    
                    trade_amount = STANDARD_TRADE_SIZE * pool_weight

                    if pool_liquidity > 0:
                        impact = (trade_amount / (2 * pool_liquidity)) * 100
                        total_impact += impact
                    
                except (KeyError, ValueError, ZeroDivisionError):
                    continue
            
            return min(round(total_impact, 2), 100.00)
            
        except Exception as e:
            print(f"Error calculating price impact: {str(e)}")
            return 100.00

    def _generate_key_metrics(self, data, chain: str, exit_data=None):
        """Generate key liquidity metrics"""
        pairs = data.get("data", {}).get("items", [])
        metrics = []
        
        if chain == "base":
            exchanges = set(pair.get("source") for pair in pairs if pair.get("source"))
            exchange_names = [f"DEX-{addr[:6]}..." for addr in sorted(exchanges)]
            metrics.append(f"Active on {len(exchanges)} Base DEXes: {', '.join(exchange_names[:3])}{'...' if len(exchange_names) > 3 else ''}")
        else:
            exchanges = set(pair.get("source") for pair in pairs if pair.get("source"))
            metrics.append(f"Active on {len(exchanges)} Solana DEXes: {', '.join(sorted(exchanges))}")

        try:
            exit_info = (exit_data or {}).get('data', {})
            exit_liquidity_value = self._safe_float(exit_info.get('exit_liquidity', 0))
            if exit_liquidity_value > 0:
                if exit_liquidity_value >= 1_000_000:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - institutional-grade capacity for large positions")
                elif exit_liquidity_value >= 500_000:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - suitable for mid-tier institutional trades")
                elif exit_liquidity_value >= 200_000:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - adequate for substantial retail positions")
                elif exit_liquidity_value >= 100_000:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - moderate capacity for medium-sized trades")
                elif exit_liquidity_value >= 50_000:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - limited to smaller position sizes")
                elif exit_liquidity_value >= 25_000:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - constrained exit capacity, exercise caution")
                else:
                    metrics.append(f"Exit liquidity: ${exit_liquidity_value:,.0f} - severely limited, high slippage risk")
        except Exception:
            pass
        
        liquidity_changes = []
        for pair in pairs:
            try:
                change = self._safe_float(pair.get("liquidityChangePercentage24h"))
                if change != 0:
                    liquidity_changes.append(change)
            except (ValueError, TypeError):
                continue
        
        if liquidity_changes:
            avg_change = sum(liquidity_changes) / len(liquidity_changes)
            metrics.append(f"24h liquidity change: {avg_change:+.2f}%")
        else:
            metrics.append("24h liquidity change: No data available")
        
        price_impact = self._calculate_price_impact(pairs, chain)
        if abs(price_impact) < 0.01:
            metrics.append("Minimal price impact indicating exceptional liquidity depth")
        else:
            metrics.append(f"Estimated price impact for $1K trade: {price_impact:.2f}%")

        total_trades = sum(self._safe_float(pair.get("trade24h", 0)) for pair in pairs)
        if total_trades > 0:
            metrics.append(f"24h trading activity: {int(total_trades)} trades across all pairs")
        
        return metrics[:4]

if __name__ == "__main__":
    import json
    from datetime import datetime
    
    def print_separator(title):
        print("\n" + "="*80)
        print(f"{title}")
        print("="*80)
    
    def print_result(token_name, address, expected_chain, result):
        print(f"\n📋 {token_name}")
        print(f"Address: {address}")
        print(f"Expected Chain: {expected_chain}")
        print(f"Detected Chain: {result.get('chain', 'unknown')}")
        
        if result.get('success'):
            print(f"SUCCESS")
            print(f"Health Score: {result['health_score']}/100")
            print(f"Summary: {result['liquidity_summary']}")
            print("Key Metrics:")
            for metric in result['key_metrics']:
                print(f"  • {metric}")
        else:
            print(f"ERROR: {result['liquidity_summary']}")
    
    def test_token(name, address, expected_chain):
        try:
            tool = LiquidityAnalysis(address=address)
            result = tool.run()
            print_result(name, address, expected_chain, result)
            
            if result.get('chain') != expected_chain:
                print(f"Chain detection mismatch!")
                
        except Exception as e:
            print(f"ERROR testing {name}: {str(e)}")

    print_separator("LIQUIDITY ANALYSIS - MANUAL TESTING")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print_separator("SOLANA TOKENS")

    solana_tests = [
        {
            "name": "JTO Token (Well-known)",
            "address": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
            "expected_chain": "solana"
        }
    ]
    
    for test in solana_tests:
        print(f"\n🧪 Testing: {test['name']}")
        test_token(test['name'], test['address'], test['expected_chain'])
    
    print_separator("BASE TOKENS")

    base_tests = [
        {
            "name": "AERO Token",
            "address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
            "expected_chain": "base"
        }
    ]
    
    for test in base_tests:
        print(f"\n🧪 Testing: {test['name']}")
        test_token(test['name'], test['address'], test['expected_chain'])
    
    print_separator("CHAIN AUTO-DETECTION TESTS")

    detection_tests = [
        {
            "address": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
            "expected_chain": "solana",
            "reason": "No 0x prefix"
        },
        {
            "address": "0x1111111111166b7FE7bd91427724B487980aFc69",
            "expected_chain": "base",
            "reason": "0x prefix (ZORA token)"
        }
    ]
    
    for test in detection_tests:
        tool = LiquidityAnalysis(address=test['address'])
        detected = tool._detect_chain(test['address'])
        status = "✅" if detected == test['expected_chain'] else "❌"
        print(f"{status} {test['address'][:20]}... → {detected} ({test['reason']})")
