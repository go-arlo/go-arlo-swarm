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
    Enhanced market analysis tool providing volume, liquidity and technical indicators.
    Supports both Solana and Base chains with automatic detection.
    """

    address: str = Field(..., description="The token address to analyze")
    chain: str = Field(default="auto", description="The blockchain network (auto-detect, solana, or base)")
    trade_data: dict = Field(default_factory=dict, description="Stores trade data from API")

    def _detect_chain(self, address: str) -> str:
        """Auto-detect chain based on address format"""
        if address.startswith("0x"):
            return "base"
        else:
            return "solana"

    def run(self):
        """
        Executes comprehensive market analysis including volume, liquidity and technical indicators
        """
        try:
            if self.chain == "auto":
                detected_chain = self._detect_chain(self.address)
                print(f"Auto-detected chain: {detected_chain} for address: {self.address}")
            else:
                detected_chain = self.chain
            
            print(f"\nAttempting to fetch trade data for address: {self.address} on {detected_chain}")
            self.trade_data = self._get_trade_data(detected_chain)
            print(f"Trade data response: {self.trade_data}")
            
            print(f"\nAttempting to fetch OHLCV data for {detected_chain}...")
            ohlcv_data = self._get_ohlcv_data(detected_chain)
            print(f"OHLCV data response: {ohlcv_data}")
            
            df = self._prepare_ohlcv_dataframe(ohlcv_data)
            
            technical_analysis = self._calculate_technical_indicators(df)
            market_metrics = self._calculate_market_metrics(self.trade_data, detected_chain)
            market_score = self._calculate_market_score(market_metrics, technical_analysis)
            
            return {
                "success": True,
                "chain": detected_chain,
                "market_metrics": market_metrics,
                "technical_analysis": technical_analysis,
                "market_score": market_score,
                "summary": self._generate_market_summary(market_metrics, technical_analysis)
            }
            
        except Exception as e:
            print(f"\nError details: {str(e)}")
            return {
                "success": False,
                "chain": detected_chain if 'detected_chain' in locals() else "unknown",
                "error": f"Analysis failed: {str(e)}",
                "market_metrics": {
                    "volume_metrics": {"volume_24h": 0, "volume_change_24h": 0, "buy_volume_ratio": 0, "unique_wallets_24h": 0},
                    "price_metrics": {"price": 0, "price_change_24h": 0, "price_change_1h": 0},
                    "trading_metrics": {"total_trades_24h": 0, "buy_count_24h": 0, "sell_count_24h": 0}
                },
                "technical_analysis": {
                    "momentum_trading": {},
                    "day_trading": {},
                    "swing_trading": {}
                },
                "market_score": {"score": 0, "positive_points": 0, "negative_points": 0, "momentum_score": 0, "daytrading_score": 0, "swing_score": 0},
                "summary": {
                    "momentum_trading": [],
                    "day_trading": [],
                    "swing_trading": []
                }
            }

    def _get_trade_data(self, chain: str):
        """Fetch trade data from Birdeye API"""
        headers = {
            "X-API-KEY": BIRDEYE_API_KEY,
            "x-chain": chain
        }
        params = {"address": self.address}
        
        response = requests.get(TRADE_DATA_URL, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Trade data API error for {chain} chain: {response.status_code} - {response.text}")
            
        return response.json().get('data', {})

    def _get_ohlcv_data(self, chain: str):
        """Fetch OHLCV data from Birdeye API"""
        current_time = int(datetime.now().timestamp())
        time_from = current_time - (4 * 60 * 60)  # 4 hours ago
        
        headers = {
            "X-API-KEY": BIRDEYE_API_KEY,
            "x-chain": chain
        }
        params = {
            "address": self.address,
            "type": "5m",
            "time_from": time_from,
            "time_to": current_time
        }
        
        response = requests.get(OHLCV_URL, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"OHLCV API error for {chain} chain: {response.status_code} - {response.text}")
            
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
        """Calculate technical indicators organized by trading style"""
        if df.empty:
            return {
                "momentum_trading": {},
                "day_trading": {},
                "swing_trading": {}
            }
        
        price_range = df['c'].max() - df['c'].min()
        total_volume = df['v'].sum()
        has_movement = price_range > (df['c'].mean() * 0.001)  # > 0.1% price range
        
        print(f"🔍 MARKET ACTIVITY CHECK:")
        print(f"Price range: ${price_range:.8f} ({((price_range/df['c'].mean())*100):.3f}%)")
        print(f"Total volume: {total_volume}")
        print(f"Has movement: {has_movement}")
        
        if not has_movement or total_volume < 50000:
            print(f"WARNING: Low activity/flat market detected")
            print(f"Technical indicators may not be reliable in flat markets")
        
        df['vwap'] = (df['h'] + df['l'] + df['c']) / 3 * df['v']
        
        if total_volume > 0:
            df['vwap'] = df['vwap'].cumsum() / df['v'].cumsum()
        else:
            df['vwap'] = (df['h'] + df['l'] + df['c']) / 3
        
        momentum_indicators = self._calculate_momentum_indicators(df, has_movement)
        
        daytrading_indicators = self._calculate_daytrading_indicators(df)
        
        swing_indicators = self._calculate_swing_indicators(df, has_movement)
        
        return {
            "momentum_trading": momentum_indicators,
            "day_trading": daytrading_indicators,
            "swing_trading": swing_indicators
        }
    
    def _calculate_momentum_indicators(self, df, has_movement):
        """Calculate momentum trading indicators: RSI, Stochastic, Bollinger Bands"""
        df = df.copy()
        
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        loss = loss.replace(0, 0.0001)
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        if not has_movement:
            df['rsi'] = 50
        
        # Stochastic Oscillator (14, 3, 3)
        low_14 = df['l'].rolling(window=14).min()
        high_14 = df['h'].rolling(window=14).max()
        high_low_diff = high_14 - low_14
        
        high_low_diff = high_low_diff.replace(0, 0.0001)
        df['stoch_k'] = ((df['c'] - low_14) / high_low_diff) * 100
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
        
        if not has_movement:
            df['stoch_k'] = 50
            df['stoch_d'] = 50
        
        # Bollinger Bands (20-period, 2 std dev)
        df['bb_sma'] = df['c'].rolling(window=20).mean()
        df['bb_std'] = df['c'].rolling(window=20).std()
        df['bb_upper'] = df['bb_sma'] + (2 * df['bb_std'])
        df['bb_lower'] = df['bb_sma'] - (2 * df['bb_std'])
        bb_diff = df['bb_upper'] - df['bb_lower']
        bb_diff = bb_diff.replace(0, 0.0001)
        df['bb_position'] = (df['c'] - df['bb_lower']) / bb_diff
        
        latest = df.iloc[-1]
        return {
            "rsi": latest['rsi'],
            "rsi_signal": "overbought" if latest['rsi'] > 70 else "oversold" if latest['rsi'] < 30 else "neutral",
            "stochastic_k": latest['stoch_k'],
            "stochastic_d": latest['stoch_d'], 
            "stochastic_signal": "overbought" if latest['stoch_k'] > 80 else "oversold" if latest['stoch_k'] < 20 else "neutral",
            "bollinger_position": latest['bb_position'],
            "bollinger_signal": "squeeze" if latest['bb_upper'] - latest['bb_lower'] < latest['bb_sma'] * 0.1 else "expansion",
            "price_vs_bb_upper": (latest['c'] - latest['bb_upper']) / latest['bb_upper'] * 100,
            "price_vs_bb_lower": (latest['c'] - latest['bb_lower']) / latest['bb_lower'] * 100
        }
    
    def _calculate_daytrading_indicators(self, df):
        """Calculate day trading indicators: VWAP, Volume indicators"""
        latest = df.iloc[-1]
        
        df = df.copy()
        df.loc[df.index[0], 'obv'] = 0
        
        for i in range(1, len(df)):
            prev_close = df['c'].iloc[i-1]
            curr_close = df['c'].iloc[i]
            prev_obv = df['obv'].iloc[i-1]
            curr_volume = df['v'].iloc[i]
            
            if curr_close > prev_close:
                df.loc[df.index[i], 'obv'] = prev_obv + curr_volume
            elif curr_close < prev_close:
                df.loc[df.index[i], 'obv'] = prev_obv - curr_volume
            else:
                df.loc[df.index[i], 'obv'] = prev_obv
        
        high_low_diff = df['h'] - df['l']
        high_low_diff = high_low_diff.replace(0, 0.0001)
        df['mf_multiplier'] = ((df['c'] - df['l']) - (df['h'] - df['c'])) / high_low_diff
        df['mf_volume'] = df['mf_multiplier'] * df['v']
        volume_sum = df['v'].rolling(window=20).sum()
        volume_sum = volume_sum.replace(0, 0.0001)
        df['cmf'] = df['mf_volume'].rolling(window=20).sum() / volume_sum
        
        # Volume trend analysis
        volume_sma_short = df['v'].rolling(window=5).mean()
        volume_sma_long = df['v'].rolling(window=20).mean()
        
        latest = df.iloc[-1]
        
        return {
            "vwap": latest['vwap'],
            "price_to_vwap": (latest['c'] / latest['vwap'] - 1) * 100 if latest['vwap'] > 0 and not pd.isna(latest['vwap']) else 0,
            "vwap_signal": "above" if latest['c'] > latest['vwap'] else "below",
            "obv": latest['obv'],
            "obv_trend": "bullish" if df['obv'].iloc[-1] > df['obv'].iloc[-5] else "bearish",
            "cmf": latest['cmf'],
            "cmf_signal": "bullish" if latest['cmf'] > 0.1 else "bearish" if latest['cmf'] < -0.1 else "neutral",
            "volume_ratio": volume_sma_short.iloc[-1] / volume_sma_long.iloc[-1] if volume_sma_long.iloc[-1] > 0 else 1,
            "volume_trend": (volume_sma_short.iloc[-1] / volume_sma_long.iloc[-1] - 1) * 100 if volume_sma_long.iloc[-1] > 0 else 0
        }
    
    def _calculate_swing_indicators(self, df, has_movement):
        """Calculate swing trading indicators: Fibonacci, MACD, ATR, EMA 50/200"""
        df = df.copy()
        
        # EMA 50 and 200
        df['ema_50'] = df['c'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['c'].ewm(span=200, adjust=False).mean()
        
        # MACD (12, 26, 9)
        df['ema_12'] = df['c'].ewm(span=12, adjust=False).mean()
        df['ema_26'] = df['c'].ewm(span=26, adjust=False).mean()
        df['macd_line'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd_line'] - df['macd_signal']
        
        # ATR (14-period) - Fixed True Range calculation
        df = df.copy()
        df['prev_close'] = df['c'].shift(1)
        
        # Calculate True Range components
        df['tr1'] = df['h'] - df['l']  # High - Low
        df['tr2'] = abs(df['h'] - df['prev_close'])  # |High - Previous Close|
        df['tr3'] = abs(df['l'] - df['prev_close'])  # |Low - Previous Close|
        
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=14).mean()
        
        # For flat markets, set minimum ATR based on price (0.1% of current price)
        if not has_movement:
            current_price = df['c'].iloc[-1]
            min_atr = current_price * 0.001  # 0.1% minimum volatility
            df['atr'] = df['atr'].fillna(min_atr).replace(0, min_atr)
        
        # Fibonacci retracements (last 20 periods high/low)
        recent_high = df['h'].iloc[-20:].max()
        recent_low = df['l'].iloc[-20:].min()
        fib_diff = recent_high - recent_low
        
        fib_levels = {
            '23.6%': recent_high - 0.236 * fib_diff,
            '38.2%': recent_high - 0.382 * fib_diff,
            '50.0%': recent_high - 0.5 * fib_diff,
            '61.8%': recent_high - 0.618 * fib_diff,
            '78.6%': recent_high - 0.786 * fib_diff
        }
        
        # Update latest after all calculations
        latest = df.iloc[-1]
        current_price = latest['c']
        
        # Find closest Fibonacci level
        closest_fib = min(fib_levels.items(), key=lambda x: abs(x[1] - current_price))
        
        return {
            "ema_50": latest['ema_50'],
            "ema_200": latest['ema_200'],
            "ema_cross_signal": "bullish" if latest['ema_50'] > latest['ema_200'] else "bearish",
            "macd_line": latest['macd_line'],
            "macd_signal": latest['macd_signal'],
            "macd_histogram": latest['macd_histogram'],
            "macd_trend": "bullish" if latest['macd_histogram'] > 0 else "bearish",
            "atr": latest['atr'],
            "atr_percent": (latest['atr'] / current_price) * 100,
            "fibonacci_levels": fib_levels,
            "closest_fib_level": closest_fib[0],
            "closest_fib_price": closest_fib[1],
            "fib_distance": abs(current_price - closest_fib[1]) / current_price * 100,
            "recent_high": recent_high,
            "recent_low": recent_low
        }

    def _calculate_market_metrics(self, trade_data, chain: str):
        """Calculate comprehensive market metrics with None value handling"""
        try:
            def safe_float(value, default=0.0):
                """Safely convert value to float"""
                if value is None:
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            def safe_int(value, default=0):
                """Safely convert value to int"""
                if value is None:
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default

            volume_24h = safe_float(trade_data.get('volume_24h_usd'))
            volume_buy_24h = safe_float(trade_data.get('volume_buy_24h_usd'))
            price_change_24h = safe_float(trade_data.get('price_change_24h_percent'))
            price_change_1h = safe_float(trade_data.get('price_change_1h_percent'))
            volume_change_24h = safe_float(trade_data.get('volume_24h_change_percent'))
            trade_24h = safe_int(trade_data.get('trade_24h'))
            buy_24h = safe_int(trade_data.get('buy_24h'))
            sell_24h = safe_int(trade_data.get('sell_24h'))
            unique_wallets_24h = safe_int(trade_data.get('unique_wallet_24h'))
            
            if chain == "base":
                holder_count = safe_int(trade_data.get('holder'))
                print(f"ℹ️  Base chain: {unique_wallets_24h:,} unique wallets (24h), {holder_count:,} total holders")
            else:
                print(f"ℹ️  Solana chain: {unique_wallets_24h:,} unique wallets (24h)")
            
            return {
                "volume_metrics": {
                    "volume_24h": volume_24h,
                    "volume_change_24h": volume_change_24h,
                    "buy_volume_ratio": volume_buy_24h / volume_24h if volume_24h > 0 else 0.0,
                    "unique_wallets_24h": unique_wallets_24h
                },
                "price_metrics": {
                    "price": safe_float(trade_data.get('price')),
                    "price_change_24h": price_change_24h,
                    "price_change_1h": price_change_1h
                },
                "trading_metrics": {
                    "total_trades_24h": trade_24h,
                    "buy_count_24h": buy_24h,
                    "sell_count_24h": sell_24h
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
        """Calculate market score based on all trading style indicators"""
        score = 50
        positive_points = 0
        negative_points = 0
        
        # Volume metrics
        volume_metrics = market_metrics['volume_metrics']
        if volume_metrics['volume_24h'] > 1000000:
            score += 10
            positive_points += 1
        elif volume_metrics['volume_24h'] > 500000:
            score += 5
        else:
            negative_points += 1
        
        # Day trading indicators
        day_trading = technical_analysis.get('day_trading', {})
        volume_trend = day_trading.get('volume_trend', 0)
        if volume_trend < -20:
            score -= 10
            negative_points += 1
        elif volume_trend > 20:
            score += 10
            positive_points += 1
        
        vwap_diff = day_trading.get('price_to_vwap', 0)
        if abs(vwap_diff) > 15:
            score -= 10
            negative_points += 1
        elif abs(vwap_diff) < 5:
            score += 10
            positive_points += 1
        
        # Momentum indicators
        momentum = technical_analysis.get('momentum_trading', {})
        rsi = momentum.get('rsi', 50)
        if rsi < 30:
            score -= 10
            negative_points += 1
        elif rsi > 70:
            score -= 5
            negative_points += 1
        elif 45 <= rsi <= 65:
            score += 10
            positive_points += 1
        
        # Swing trading indicators
        swing = technical_analysis.get('swing_trading', {})
        if swing.get('ema_cross_signal') == 'bullish':
            score += 5
            positive_points += 1
        elif swing.get('ema_cross_signal') == 'bearish':
            score -= 5
            negative_points += 1
            
        if swing.get('macd_trend') == 'bullish':
            score += 5
            positive_points += 1
        elif swing.get('macd_trend') == 'bearish':
            score -= 5
            negative_points += 1
        
        # Price stability
        price_metrics = market_metrics['price_metrics']
        price_change = abs(price_metrics['price_change_24h'])
        if price_change < 10:
            score += 10
            positive_points += 1
        elif price_change < 20:
            score += 7
        else:
            negative_points += 1
        
        return {
            'score': max(45, min(100, score)),
            'positive_points': positive_points,
            'negative_points': negative_points,
            'momentum_score': self._get_momentum_score(momentum),
            'daytrading_score': self._get_daytrading_score(day_trading),
            'swing_score': self._get_swing_score(swing)
        }
    
    def _get_momentum_score(self, momentum):
        """Calculate momentum trading score"""
        score = 0
        if momentum.get('rsi_signal') == 'neutral':
            score += 2
        elif momentum.get('rsi_signal') in ['overbought', 'oversold']:
            score += 1
            
        if momentum.get('stochastic_signal') == 'neutral':
            score += 2
        elif momentum.get('stochastic_signal') in ['overbought', 'oversold']:
            score += 1
            
        bb_pos = momentum.get('bollinger_position', 0.5)
        if 0.2 <= bb_pos <= 0.8:
            score += 2
        elif bb_pos < 0.1 or bb_pos > 0.9:
            score += 1
            
        return min(score, 6)
    
    def _get_daytrading_score(self, daytrading):
        """Calculate day trading score"""
        score = 0
        
        vwap_diff = abs(daytrading.get('price_to_vwap', 0))
        if vwap_diff < 2:
            score += 2
        elif vwap_diff < 5:
            score += 1
            
        if daytrading.get('cmf_signal') == 'bullish':
            score += 2
        elif daytrading.get('cmf_signal') == 'neutral':
            score += 1
            
        volume_trend = daytrading.get('volume_trend', 0)
        if volume_trend > 10:
            score += 2
        elif volume_trend > 0:
            score += 1
            
        return min(score, 6)
    
    def _get_swing_score(self, swing):
        """Calculate swing trading score"""
        score = 0
        
        if swing.get('ema_cross_signal') == 'bullish':
            score += 2
        
        if swing.get('macd_trend') == 'bullish':
            score += 2
            
        atr_percent = swing.get('atr_percent', 0)
        if 1 <= atr_percent <= 5:
            score += 2
        elif atr_percent < 1:
            score += 0
        else:
            score += 1
            
        return min(score, 6)

    def _calculate_vwap_metrics(self, trade_data):
        """Calculate VWAP and related metrics with reasonable bounds"""
        try:
            def safe_float(value, default=0.0):
                if value is None:
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            current_price = safe_float(trade_data.get('price'))
            vwap = safe_float(trade_data.get('vwap'))
            
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
        """Generate market summary organized by trading styles"""
        summary = {
            "momentum_trading": [],
            "day_trading": [],
            "swing_trading": []
        }
        
        # MOMENTUM TRADING SIGNALS
        momentum = technical_analysis.get('momentum_trading', {})
        if momentum:
            rsi = momentum.get('rsi', 0)
            stoch_k = momentum.get('stochastic_k', 0)
            bb_pos = momentum.get('bollinger_position', 0) * 100
            
            summary["momentum_trading"].extend([
                f"RSI: {rsi:.1f} ({momentum.get('rsi_signal', 'neutral')})",
                f"Stochastic %K: {stoch_k:.1f} ({momentum.get('stochastic_signal', 'neutral')})", 
                f"Bollinger Bands: {bb_pos:.1f}% position ({momentum.get('bollinger_signal', 'normal')})"
            ])
            
            if momentum.get('rsi_signal') in ['overbought', 'oversold']:
                summary["momentum_trading"].append(f"⚠️ RSI showing {momentum.get('rsi_signal')} conditions")
            if momentum.get('bollinger_signal') == 'squeeze':
                summary["momentum_trading"].append("🔸 Bollinger Band squeeze detected - volatility expansion expected")
        
        # DAY TRADING / SCALPING SIGNALS  
        daytrading = technical_analysis.get('day_trading', {})
        if daytrading:
            vwap = daytrading.get('vwap', 0)
            price_to_vwap = daytrading.get('price_to_vwap', 0)
            cmf = daytrading.get('cmf', 0)
            obv_trend = daytrading.get('obv_trend', 'neutral')
            volume_trend = daytrading.get('volume_trend', 0)
  
            summary["day_trading"].extend([
                f"VWAP: ${vwap:.6f} (price {price_to_vwap:+.2f}% vs VWAP)",
                f"Chaikin Money Flow: {cmf:.3f} ({daytrading.get('cmf_signal', 'neutral')})",
                f"OBV Trend: {obv_trend}",
                f"Volume Trend: {volume_trend:+.1f}% (5-period vs 20-period)"
            ])
            
            if abs(price_to_vwap) > 5:
                direction = "above" if price_to_vwap > 0 else "below"
                summary["day_trading"].append(f"🔸 Price significantly {direction} VWAP - potential mean reversion")
            if daytrading.get('cmf_signal') == 'bullish':
                summary["day_trading"].append("🟢 Strong money flow into the token")
            elif daytrading.get('cmf_signal') == 'bearish':
                summary["day_trading"].append("🔴 Money flowing out of the token")
        
        # SWING TRADING SIGNALS
        swing = technical_analysis.get('swing_trading', {})
        if swing:
            ema_50 = swing.get('ema_50', 0)
            ema_200 = swing.get('ema_200', 0) 
            macd_line = swing.get('macd_line', 0)
            macd_signal = swing.get('macd_signal', 0)
            atr_percent = swing.get('atr_percent', 0)
            closest_fib = swing.get('closest_fib_level', 'N/A')
            fib_distance = swing.get('fib_distance', 0)
            
            summary["swing_trading"].extend([
                f"EMA 50/200: ${ema_50:.6f}/${ema_200:.6f} ({swing.get('ema_cross_signal', 'neutral')})",
                f"MACD: {macd_line:.6f} vs Signal {macd_signal:.6f} ({swing.get('macd_trend', 'neutral')})",
                f"ATR: {atr_percent:.2f}% of price",
                f"Nearest Fibonacci: {closest_fib} ({fib_distance:.2f}% away)"
            ])
            
            if swing.get('ema_cross_signal') == 'bullish':
                summary["swing_trading"].append("🟢 Bullish EMA crossover - uptrend confirmed")
            elif swing.get('ema_cross_signal') == 'bearish':
                summary["swing_trading"].append("🔴 Bearish EMA crossover - downtrend confirmed")
                
            if swing.get('macd_trend') == 'bullish':
                summary["swing_trading"].append("🟢 MACD showing bullish momentum")
            elif swing.get('macd_trend') == 'bearish':
                summary["swing_trading"].append("🔴 MACD showing bearish momentum")
                
            if fib_distance < 2:
                summary["swing_trading"].append(f"🔸 Price near key Fibonacci level ({closest_fib}) - watch for bounce/break")
        
        return summary

if __name__ == "__main__":
    import json
    from datetime import datetime
    
    def print_separator(title):
        print("\n" + "="*80)
        print(f"🔍 {title}")
        print("="*80)
    
    def print_result(token_name, address, expected_chain, result):
        print(f"\n📋 {token_name}")
        print(f"Address: {address}")
        print(f"Expected Chain: {expected_chain}")
        print(f"Detected Chain: {result.get('chain', 'unknown')}")
        
        if result.get('success'):
            print(f"✅ SUCCESS")
            print(f"Market Score: {result['market_score']['score']}/100")
            
            market_metrics = result['market_metrics']
            print(f"Price: ${market_metrics['price_metrics']['price']:.6f}")
            print(f"Volume 24h: ${market_metrics['volume_metrics']['volume_24h']:,.2f}")
            print(f"Unique Wallets: {market_metrics['volume_metrics']['unique_wallets_24h']:,}")
            
            # Show trading style scores
            scores = result['market_score']
            print(f"Momentum Score: {scores['momentum_score']}/6")
            print(f"Day Trading Score: {scores['daytrading_score']}/6") 
            print(f"Swing Trading Score: {scores['swing_score']}/6")
        else:
            print(f"❌ ERROR: {result.get('error', 'Unknown error')}")
    
    def test_token(name, address, expected_chain):
        try:
            tool = MarketAnalysis(address=address)
            result = tool.run()
            print_result(name, address, expected_chain, result)
            
            if result.get('chain') != expected_chain:
                print(f"⚠️  Chain detection mismatch!")
                
        except Exception as e:
            print(f"❌ ERROR testing {name}: {str(e)}")

    print_separator("MARKET ANALYSIS - MANUAL TESTING")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print_separator("SOLANA TOKENS")

    solana_tests = [
        {
            "name": "JTO Token (Well-known)",
            "address": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
            "expected_chain": "solana"
        },
        {
            "name": "BONK Token (Meme coin)", 
            "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "expected_chain": "solana"
        },
        {
            "name": "SOL Token (Native)",
            "address": "So11111111111111111111111111111111111111112",
            "expected_chain": "solana"
        }
    ]
    
    for test in solana_tests:
        print(f"\n🧪 Testing: {test['name']}")
        test_token(test['name'], test['address'], test['expected_chain'])
    
    print_separator("BASE TOKENS")

    base_tests = [
        {
            "name": "ZORA Token",
            "address": "0x1111111111166b7FE7bd91427724B487980aFc69",
            "expected_chain": "base"
        },
        {
            "name": "USDC on Base",
            "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "expected_chain": "base"
        },
        {
            "name": "Ethereum on Base (Wrapped)",
            "address": "0x4200000000000000000000000000000000000006",
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
        tool = MarketAnalysis(address=test['address'])
        detected = tool._detect_chain(test['address'])
        status = "✅" if detected == test['expected_chain'] else "❌"
        print(f"{status} {test['address'][:20]}... → {detected} ({test['reason']})")
    
    print_separator("DETAILED ANALYSIS EXAMPLE")
    
    # Show detailed analysis for one token
    print("\n🔬 Running detailed analysis on ZORA (Base token)...")
    tool = MarketAnalysis(address="0x1111111111166b7FE7bd91427724B487980aFc69")
    result = tool.run()
    
    if result.get('success'):
        print(f"\n📊 COMPREHENSIVE MARKET ANALYSIS - {result['chain'].upper()}")
        print("="*60)
        
        print(f"\n📈 MARKET METRICS:")
        market_metrics = result['market_metrics']
        print(f"Volume 24h: ${market_metrics['volume_metrics']['volume_24h']:,.2f}")
        print(f"Price: ${market_metrics['price_metrics']['price']:.6f}")
        print(f"Price Change 24h: {market_metrics['price_metrics']['price_change_24h']:+.2f}%")
        print(f"Holders/Wallets: {market_metrics['volume_metrics']['unique_wallets_24h']:,}")
        
        print(f"\n🎯 TRADING STYLE ANALYSIS:")
        ta = result['technical_analysis']
        
        print(f"\n🚀 MOMENTUM TRADING (Score: {result['market_score']['momentum_score']}/6):")
        momentum = ta.get('momentum_trading', {})
        if momentum:
            print(f"  RSI: {momentum.get('rsi', 0):.1f} ({momentum.get('rsi_signal', 'N/A')})")
            print(f"  Stochastic: {momentum.get('stochastic_k', 0):.1f} ({momentum.get('stochastic_signal', 'N/A')})")
            print(f"  Bollinger Position: {momentum.get('bollinger_position', 0)*100:.1f}%")
        
        print(f"\n⚡ DAY TRADING / SCALPING (Score: {result['market_score']['daytrading_score']}/6):")
        daytrading = ta.get('day_trading', {})
        if daytrading:
            print(f"  VWAP: ${daytrading.get('vwap', 0):.6f}")
            print(f"  Price vs VWAP: {daytrading.get('price_to_vwap', 0):+.2f}%")
            print(f"  CMF: {daytrading.get('cmf', 0):.3f} ({daytrading.get('cmf_signal', 'N/A')})")
            print(f"  Volume Trend: {daytrading.get('volume_trend', 0):+.1f}%")
        
        print(f"\n📈 SWING TRADING (Score: {result['market_score']['swing_score']}/6):")
        swing = ta.get('swing_trading', {})
        if swing:
            print(f"  EMA 50/200: ${swing.get('ema_50', 0):.6f}/${swing.get('ema_200', 0):.6f}")
            print(f"  EMA Signal: {swing.get('ema_cross_signal', 'N/A')}")
            print(f"  MACD: {swing.get('macd_trend', 'N/A')}")
            print(f"  ATR: {swing.get('atr_percent', 0):.2f}% of price")
            print(f"  Nearest Fib: {swing.get('closest_fib_level', 'N/A')} ({swing.get('fib_distance', 0):.1f}% away)")
        
        print(f"\n📊 OVERALL MARKET SCORE: {result['market_score']['score']}/100")
        print(f"Positive Signals: {result['market_score']['positive_points']}")
        print(f"Negative Signals: {result['market_score']['negative_points']}")
        
        print("\n💡 TRADING SIGNALS BY STYLE:")
        summary = result['summary']
        
        print("\n🚀 Momentum Trading:")
        for point in summary.get('momentum_trading', []):
            print(f"  • {point}")
            
        print("\n⚡ Day Trading:")
        for point in summary.get('day_trading', []):
            print(f"  • {point}")
            
        print("\n📈 Swing Trading:")
        for point in summary.get('swing_trading', []):
            print(f"  • {point}")
       