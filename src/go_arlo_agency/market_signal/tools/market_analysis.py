from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
TRADE_DATA_URL = "https://public-api.birdeye.so/defi/v3/token/trade-data/single"
OHLCV_URL = "https://public-api.birdeye.so/defi/ohlcv"

class MarketAnalysis(BaseTool):
    """
    Enhanced market analysis tool providing volume, liquidity and technical indicators
    """

    address: str = Field(..., description="The token address to analyze")
    trade_data: dict = Field(default_factory=dict, description="Stores trade data from API")

    def run(self):
        """
        Executes comprehensive market analysis including volume, liquidity and technical indicators
        """
        try:
            print(f"\nAttempting to fetch trade data for address: {self.address}")
            self.trade_data = self._get_trade_data()
            print(f"Trade data response: {self.trade_data}")
            
            print("\nAttempting to fetch OHLCV data...")
            ohlcv_data = self._get_ohlcv_data()
            print(f"OHLCV data response: {ohlcv_data}")
            
            df = self._prepare_ohlcv_dataframe(ohlcv_data)
            
            technical_analysis = self._calculate_technical_indicators(df)
            market_metrics = self._calculate_market_metrics(self.trade_data)
            market_score = self._calculate_market_score(market_metrics, technical_analysis)
            
            return {
                "market_metrics": market_metrics,
                "technical_analysis": technical_analysis,
                "market_score": market_score,
                "summary": self._generate_market_summary(market_metrics, technical_analysis)
            }
            
        except Exception as e:
            print(f"\nError details: {str(e)}")
            return {
                "error": f"Analysis failed: {str(e)}",
                "market_metrics": None,
                "technical_analysis": None,
                "market_score": None,
                "summary": "Analysis failed due to error"
            }

    def _get_trade_data(self):
        """Fetch trade data from Birdeye API"""
        headers = {"X-API-KEY": BIRDEYE_API_KEY}
        params = {"address": self.address}
        
        response = requests.get(TRADE_DATA_URL, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Trade data API error: {response.status_code}")
            
        return response.json().get('data', {})

    def _get_ohlcv_data(self):
        """Fetch OHLCV data from Birdeye API"""
        current_time = int(datetime.now().timestamp())
        time_from = current_time - (4 * 60 * 60)  # 4 hours ago
        
        headers = {"X-API-KEY": BIRDEYE_API_KEY}
        params = {
            "address": self.address,
            "type": "5m",
            "time_from": time_from,
            "time_to": current_time
        }
        
        response = requests.get(OHLCV_URL, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"OHLCV API error: {response.status_code}")
            
        return response.json().get('data', {}).get('items', [])

    def _prepare_ohlcv_dataframe(self, ohlcv_data):
        """Convert OHLCV data to pandas DataFrame and calculate additional metrics"""
        df = pd.DataFrame(ohlcv_data)
        if df.empty:
            return pd.DataFrame()
            
        df['datetime'] = pd.to_datetime(df['unixTime'], unit='s')
        df.set_index('datetime', inplace=True)
        
        return df

    def _calculate_technical_indicators(self, df):
        """Calculate technical indicators from OHLCV data"""
        if df.empty:
            return {}
            
        df['vwap'] = (df['h'] + df['l'] + df['c']) / 3 * df['v']
        df['vwap'] = df['vwap'].cumsum() / df['v'].cumsum()
        
        df['sma_20'] = df['c'].rolling(window=20).mean()
        df['ema_20'] = df['c'].ewm(span=20, adjust=False).mean()
        
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        latest_data = df.iloc[-1]
        
        return {
            "vwap": latest_data['vwap'],
            "sma_20": latest_data['sma_20'],
            "ema_20": latest_data['ema_20'],
            "rsi": latest_data['rsi'],
            "price_to_vwap": latest_data['c'] / latest_data['vwap'] - 1,
            "volatility": df['c'].pct_change().std() * 100,
            "volume_trend": (df['v'].iloc[-5:].mean() / df['v'].iloc[-10:-5].mean() - 1) * 100
        }

    def _calculate_market_metrics(self, trade_data):
        """Calculate comprehensive market metrics with None value handling"""
        try:
            def safe_float(value, default=0.0):
                try:
                    return float(value) if value is not None else default
                except (ValueError, TypeError):
                    return default

            volume_24h = safe_float(trade_data.get('volume_24h_usd'))
            volume_buy_24h = safe_float(trade_data.get('volume_buy_24h_usd'))
            
            return {
                "volume_metrics": {
                    "volume_24h": volume_24h,
                    "volume_change_24h": safe_float(trade_data.get('volume_24h_change_percent')),
                    "buy_volume_ratio": volume_buy_24h / volume_24h if volume_24h > 0 else 0.0,
                    "unique_wallets_24h": int(trade_data.get('unique_wallet_24h', 0))
                },
                "price_metrics": {
                    "price": safe_float(trade_data.get('price')),
                    "price_change_24h": safe_float(trade_data.get('price_change_24h_percent')),
                    "price_change_1h": safe_float(trade_data.get('price_change_1h_percent'))
                },
                "trading_metrics": {
                    "total_trades_24h": int(trade_data.get('trade_24h', 0)),
                    "buy_count_24h": int(trade_data.get('buy_24h', 0)),
                    "sell_count_24h": int(trade_data.get('sell_24h', 0))
                }
            }
        except Exception as e:
            print(f"Error in market metrics calculation: {str(e)}")
            return {
                "volume_metrics": {"volume_24h": 0, "volume_change_24h": 0, "buy_volume_ratio": 0, "unique_wallets_24h": 0},
                "price_metrics": {"price": 0, "price_change_24h": 0, "price_change_1h": 0},
                "trading_metrics": {"total_trades_24h": 0, "buy_count_24h": 0, "sell_count_24h": 0}
            }

    def _calculate_market_score(self, market_metrics, technical_analysis):
        """Calculate market score based on metrics"""
        score = 50
        positive_points = 0
        negative_points = 0
        
        volume_metrics = market_metrics['volume_metrics']
        if volume_metrics['volume_24h'] > 1000000:
            score += 10
            positive_points += 1
        elif volume_metrics['volume_24h'] > 500000:
            score += 5
        else:
            negative_points += 1
        
        volume_trend = technical_analysis.get('volume_trend', 0)
        if volume_trend < -20:
            score -= 10
            negative_points += 1
        elif volume_trend > 20:
            score += 10
            positive_points += 1
        
        price_metrics = market_metrics['price_metrics']
        price_change = abs(price_metrics['price_change_24h'])
        if price_change < 10:
            score += 10
            positive_points += 1
        elif price_change < 20:
            score += 7
        else:
            negative_points += 1
        
        rsi = technical_analysis.get('rsi', 50)
        if rsi < 30:
            score -= 10
            negative_points += 1
        elif rsi > 70:
            score -= 5
            negative_points += 1
        elif 45 <= rsi <= 65:
            score += 10
            positive_points += 1
        
        vwap_diff = technical_analysis.get('price_to_vwap', 0) * 100
        if abs(vwap_diff) > 15:
            score -= 10
            negative_points += 1
        elif abs(vwap_diff) < 5:
            score += 10
            positive_points += 1
        
        return {
            'score': max(45, min(100, score)),
            'positive_points': positive_points,
            'negative_points': negative_points
        }

    def _calculate_vwap_metrics(self, trade_data):
        """Calculate VWAP and related metrics with reasonable bounds"""
        try:
            current_price = float(trade_data.get('price', 0))
            vwap = float(trade_data.get('vwap', 0))
            
            if current_price == 0 or vwap == 0:
                return {
                    'vwap': 0,
                    'vwap_diff_percent': 0
                }
            
            diff_percent = ((current_price - vwap) / vwap) * 100
            
            diff_percent = max(min(diff_percent, 50), -50)
            
            return {
                'vwap': vwap,
                'vwap_diff_percent': round(diff_percent, 2)
            }
            
        except (ValueError, TypeError, ZeroDivisionError) as e:
            print(f"Error calculating VWAP metrics: {str(e)}")
            return {
                'vwap': 0,
                'vwap_diff_percent': 0
            }

    def _generate_market_summary(self, market_metrics, technical_analysis):
        """Generate comprehensive market summary with volume fallback logic"""
        summary = []
        
        def get_volume_data(trade_data):
            if trade_data.get('volume_history_24h', 0) != 0:
                return {
                    'volume': trade_data.get('volume_24h_usd', 0),
                    'change': trade_data.get('volume_24h_change_percent'),
                    'period': '24h'
                }
            elif trade_data.get('volume_history_4h', 0) != 0:
                return {
                    'volume': trade_data.get('volume_4h_usd', 0),
                    'change': trade_data.get('volume_4h_change_percent'),
                    'period': '4h'
                }
            else:
                return {
                    'volume': trade_data.get('volume_1h_usd', 0),
                    'change': trade_data.get('volume_1h_change_percent'),
                    'period': '1h'
                }
        
        volume_data = get_volume_data(self.trade_data)
        volume_period = volume_data['period']
        volume = volume_data['volume']
        volume_change = volume_data.get('change', 0)
        
        summary.append(f"{volume_period} Volume: ${volume:,.2f} ({volume_change:+.2f}% change)")
        
        price = market_metrics['price_metrics']['price']
        price_change_24h = market_metrics['price_metrics']['price_change_24h']
        summary.append(f"Current Price: ${price:.4f} ({price_change_24h:+.2f}% 24h change)")
        
        rsi = technical_analysis.get('rsi')
        if rsi:
            if rsi > 70:
                summary.append(f"Overbought conditions (RSI: {rsi:.2f})")
            elif rsi < 30:
                summary.append(f"Oversold conditions (RSI: {rsi:.2f})")
        
        vwap_metrics = self._calculate_vwap_metrics(self.trade_data)
        vwap = vwap_metrics['vwap']
        vwap_diff = vwap_metrics['vwap_diff_percent']
        
        if abs(vwap_diff) < 0.01:
            summary.append(f"VWAP at ${vwap:.4f} shows minimal alignment with current price")
        else:
            if vwap_diff > 0:
                term = "premium"
            else:
                term = "discount"
                vwap_diff = abs(vwap_diff)
            summary.append(f"VWAP at ${vwap:.4f} shows {vwap_diff:.2f}% {term} to price")
        
        volume_trend = technical_analysis.get('volume_trend', 0)
        summary.append(f"Volume trend (5m vs previous): {volume_trend:+.2f}%")
        
        buy_volume_ratio = market_metrics['volume_metrics']['buy_volume_ratio'] * 100
        summary.append(f"Buy volume ratio: {buy_volume_ratio:.1f}%")
        
        return summary

if __name__ == "__main__":
    tool = MarketAnalysis(
        address="xDyCR9xqMLMxQbcdZyxgoXHXZwQuGuetAjMx8vkpump"
    )
    result = tool.run()
    print("\nMarket Analysis Results:")
    print("\nMarket Metrics:")
    print(result['market_metrics'])
    print("\nTechnical Analysis:")
    print(result['technical_analysis'])
    print("\nMarket Score:")
    print(result['market_score'])
    print("\nSummary:")
    for point in result['summary']:
        print(f"- {point}") 
