from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
from dotenv import load_dotenv

load_dotenv()

MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
BASE_URL = "https://solana-gateway.moralis.io/token"

class LiquidityAnalysis(BaseTool):
    """
    Analyzes token liquidity across different DEXes using Moralis API.
    Provides structured liquidity analysis output.
    """

    address: str = Field(
        ..., 
        description="The token address to analyze"
    )
    
    network: str = Field(
        default="mainnet",
        description="The network to query (mainnet or devnet)"
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

    def run(self):
        """
        Executes comprehensive liquidity analysis
        """
        try:
            pairs_data = self._get_pairs_data()
            
            print("\nMoralis API Response:")
            print(f"Status Code: {pairs_data.get('status_code')}")
            print("Response Data:")
            print(pairs_data)
            print("\n")
            
            health_score = self._calculate_health_score(pairs_data)
            
            liquidity_summary = self._generate_liquidity_summary(pairs_data)
            key_metrics = self._generate_key_metrics(pairs_data)
            
            return {
                "health_score": health_score['score'],
                "liquidity_summary": liquidity_summary,
                "key_metrics": key_metrics
            }
            
        except Exception as e:
            return {
                "health_score": 0,
                "liquidity_summary": f"Error analyzing liquidity: {str(e)}",
                "key_metrics": [
                    "Analysis failed due to error",
                    "Liquidity status cannot be determined",
                    "Manual verification recommended"
                ]
            }

    def _get_pairs_data(self):
        """Fetch liquidity pairs data from Moralis API"""
        endpoint = f"{BASE_URL}/{self.network}/{self.address}/pairs"
        
        headers = {
            "X-API-KEY": MORALIS_API_KEY,
            "Accept": "application/json"
        }
        
        response = requests.get(endpoint, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Moralis API error: {response.status_code}")
            
        data = response.json()
        data['status_code'] = response.status_code
        return data

    def _calculate_health_score(self, data):
        """Calculate liquidity health score (0-100)"""
        try:
            pairs = data.get("pairs", [])
            if not pairs:
                return {
                    'score': 0,
                    'positive_points': 0,
                    'negative_points': 1
                }
            
            positive_points = 0
            negative_points = 0
            
            total_liquidity = sum(float(pair.get("liquidityUsd", 0)) for pair in pairs)
            
            unique_exchanges = len(set(pair.get("exchangeName") for pair in pairs))
            
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
            total_volume = sum(float(pair.get("volume24hrUsd", 0)) for pair in pairs)
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
            
            for pair in pairs:
                try:
                    price_change = abs(float(pair.get("usdPrice24hrPercentChange", 0)))
                    if price_change > 1000:  # >1000% price change
                        final_score = min(final_score, 90)
                        negative_points += 1
                        break
                except (ValueError, TypeError):
                    continue
            
            return {
                'score': min(final_score, 100),
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

    def _generate_liquidity_summary(self, data):
        """Generate one-line liquidity summary"""
        pairs = data.get("pairs", [])
        if not pairs:
            return "No active liquidity pairs found"
            
        total_liquidity = sum(float(pair.get("liquidityUsd", 0)) for pair in pairs)
        unique_exchanges = len(set(pair.get("exchangeName") for pair in pairs))
        
        if total_liquidity > 1000000 and unique_exchanges >= 3:
            return "Strong liquidity across multiple exchanges with healthy depth"
        elif total_liquidity > 500000:
            return f"Moderate liquidity of ${total_liquidity:,.2f} with {unique_exchanges} active exchanges"
        elif total_liquidity > 100000:
            return "Limited liquidity requiring careful position sizing"
        else:
            return "Low liquidity presenting significant trading risks"

    def _calculate_price_impact(self, pair_data):
        """Calculate price impact using constant product AMM formula"""
        try:
            STANDARD_TRADE_SIZE = 1000
            
            active_pairs = [p for p in pair_data if not p.get('inactivePair', True)]
            sorted_pairs = sorted(active_pairs, key=lambda x: float(x.get('liquidityUsd', 0)), reverse=True)[:3]
            
            if not sorted_pairs:
                return 100.00
            
            total_impact = 0
            total_liquidity = sum(float(pair.get('liquidityUsd', 0)) for pair in sorted_pairs)
            
            for pair in sorted_pairs:
                try:
                    token0_liq = float(pair['pair'][0]['liquidityUsd'])
                    token1_liq = float(pair['pair'][1]['liquidityUsd'])
                    
                    pool_liquidity = token0_liq + token1_liq
                    pool_weight = pool_liquidity / total_liquidity
                    
                    trade_amount = STANDARD_TRADE_SIZE * pool_weight
                    
                    # Calculate price impact using constant product formula
                    # Δy/y = x/(x+Δx) - 1
                    x = token0_liq
                    impact = (x / (x + trade_amount) - 1) * -100
                    
                    total_impact += impact
                    
                except (KeyError, ValueError, ZeroDivisionError):
                    continue
            
            return min(round(total_impact, 2), 100.00)
            
        except Exception as e:
            print(f"Error calculating price impact: {str(e)}")
            return 100.00

    def _generate_key_metrics(self, data):
        """Generate key liquidity metrics"""
        pairs = data.get("pairs", [])
        metrics = []
        
        exchanges = set(pair.get("exchangeName") for pair in pairs)
        metrics.append(f"Active on {len(exchanges)} exchanges: {', '.join(exchanges)}")
        
        liquidity_changes = []
        for pair in pairs:
            try:
                change = float(pair.get("liquidityChange24h", 0))
                if change != 0:
                    liquidity_changes.append(change)
            except (ValueError, TypeError):
                continue
        
        if liquidity_changes:
            avg_change = sum(liquidity_changes) / len(liquidity_changes)
            metrics.append(f"24h liquidity change: {avg_change:+.2f}%")
        
        price_impact = self._calculate_price_impact(pairs)
        if abs(price_impact) < 0.01:
            metrics.append("Minimal price impact indicating exceptional liquidity depth")
        else:
            metrics.append(f"Average price impact: {price_impact:.2f}%")
        
        return metrics[:4]

if __name__ == "__main__":
    tool = LiquidityAnalysis(
        address="AshG5mHt4y4etsjhKFb2wA2rq1XZxKks1EPzcuXwpump",
        network="mainnet"
    )
    result = tool.run()
    print(result) 
