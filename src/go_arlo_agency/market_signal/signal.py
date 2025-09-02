from agency_swarm import Agent
from .tools.market_analysis import MarketAnalysis
from .tools.liquidity_analysis import LiquidityAnalysis
from .tools.bundle_detector import BundleDetector

class Signal(Agent):
    def __init__(self):
        super().__init__(
            name="Signal",
            description="Market and liquidity metrics analyst supporting both Solana and Base chains",
            instructions="./instructions.md",
            tools=[MarketAnalysis, LiquidityAnalysis, BundleDetector],
            temperature=0.5,
            max_prompt_tokens=128000,
            model="gpt-4.1"
        )

    def process_message(self, message, sender):
        """Fast message processing with error handling"""
        if sender == "Arlo":
            try:
                bundle_tool = BundleDetector()
                bundle_analysis = bundle_tool.analyze_transactions(message)
                
                market_tool = MarketAnalysis(address=message)
                liquidity_tool = LiquidityAnalysis(address=message)
                
                market_analysis = market_tool.run()
                liquidity_analysis = liquidity_tool.run()
                
                combined_analysis = self._combine_analysis(
                    bundle_analysis,
                    market_analysis,
                    liquidity_analysis
                )
                
                return combined_analysis
                
            except Exception as e:
                print(f"Signal analysis error: {str(e)}")
                return {
                    "data": {
                        "market_score": 0,
                        "assessment": "negative",
                        "summary": "Analysis failed",
                        "key_points": ["Error processing analysis"]
                    }
                }
        
        return super().process_message(message, sender)
    
    def _combine_analysis(self, bundle_analysis, market_analysis, liquidity_analysis):
        """Combine all analysis results considering bundle context"""
        
        bundle_supported = bundle_analysis.get("supported") != False
        detected_chain = market_analysis.get("chain", "unknown") if market_analysis.get("success") else "unknown"
        
        # Get base metrics
        market_score = market_analysis.get("market_score", {}).get("score", 0)
        liquidity_score = liquidity_analysis.get("health_score", 0)
        
        if bundle_supported:
            has_bundles = bundle_analysis.get("has_bundled_trades", False)
            bundle_details = bundle_analysis.get("details", "")
            bundle_risk = self._extract_risk_level(bundle_details)
            bundle_percentage = self._extract_bundle_percentage(bundle_details)
        else:
            has_bundles = False
            bundle_details = bundle_analysis.get("details", "Bundle analysis not supported")
            bundle_risk = "LOW" 
            bundle_percentage = 0.0
        
        final_score = self._calculate_final_score(
            market_score,
            liquidity_score,
            bundle_risk if bundle_supported else "LOW",
            liquidity_analysis,
            bundle_analysis if bundle_supported else None
        )
        
        market_points = market_analysis.get('market_score', {})
        liquidity_points = liquidity_analysis.get('health_score', {})
        
        total_positive = (
            market_points.get('positive_points', 0) + 
            liquidity_points.get('positive_points', 0)
        )
        total_negative = (
            market_points.get('negative_points', 0) + 
            liquidity_points.get('negative_points', 0)
        )
        
        findings = []
        
        if bundle_supported:
            if has_bundles and bundle_percentage >= 1.0:
                findings.append(f"Top 5 bundles on launch date totaled {bundle_percentage:.1f}% of supply - {bundle_risk}")
            else:
                findings.append("Not a significant amount of bundles detected on launch date.")
        
        momentum_finding = self._get_momentum_finding(market_analysis)
        day_trading_finding = self._get_day_trading_finding(market_analysis)
        swing_trading_finding = self._get_swing_trading_finding(market_analysis)
        
        findings.extend([momentum_finding, day_trading_finding, swing_trading_finding])
        
        liquidity_findings = self._get_liquidity_findings(liquidity_analysis)
        findings.extend(liquidity_findings)
        
        assessment = self._get_assessment(
            total_positive,
            total_negative,
            findings,
            final_score,
            bundle_supported
        )
        
        bundle_summary = self._get_bundle_summary(bundle_analysis, liquidity_analysis, bundle_supported)
        trading_summary = self._get_trading_styles_summary(market_analysis)
        
        if bundle_summary:
            combined_summary = f"{bundle_summary}\n\n{trading_summary}"
        else:
            combined_summary = trading_summary
        
        return {
            "data": {
                "market_score": final_score,
                "assessment": assessment,
                "summary": combined_summary,
                "key_points": findings,
                "chain": detected_chain,
                "bundle_supported": bundle_supported
            }
        }
    
    def _extract_risk_level(self, bundle_details: str) -> str:
        """Extract risk level from bundle details"""
        if "VERY HIGH" in bundle_details:
            return "VERY HIGH"
        elif "HIGH" in bundle_details:
            return "HIGH"
        elif "CONSIDERABLE" in bundle_details:
            return "CONSIDERABLE"
        elif "MODERATE" in bundle_details:
            return "MODERATE"
        return "LOW"
    
    def _calculate_final_score(self, market_score, liquidity_score, bundle_risk, liquidity_analysis, bundle_analysis=None):
        """Calculate final score considering bundle risk in context"""
        base_score = (market_score + liquidity_score) / 2
        
        liquidity = float(liquidity_analysis.get('total_liquidity', 0))
        volume_24h = float(liquidity_analysis.get('volume_24h', 0))
        price_impact = float(liquidity_analysis.get('average_price_impact', 0))
        
        risk_reductions = {
            "VERY HIGH": 50,
            "HIGH": 40,  
            "CONSIDERABLE": 30,      
            "MODERATE": 20,
            "LOW": 0
        }
        
        reduction = risk_reductions[bundle_risk]
        
        if liquidity > 1000000 and volume_24h > 500000:
            reduction = max(reduction * 0.8, 0)
        
        final_score = max(0, min(base_score, base_score - reduction))
        
        return final_score
    
    def _get_bundle_summary(self, bundle_analysis, liquidity_analysis, bundle_supported: bool) -> str:
        """Create bundle summary with liquidity context"""
        if not bundle_supported:
            return ""
            
        if not bundle_analysis.get("has_bundled_trades"):
            return "No suspicious bundle trading patterns detected."
            
        details = bundle_analysis.get("details", "")
        liquidity = float(liquidity_analysis.get("total_liquidity", 0))
        volume_24h = float(liquidity_analysis.get("volume_24h", 0))
        
        risk_level = self._extract_risk_level(details)
        
        if risk_level in ["HIGH", "VERY HIGH"]:
            if liquidity < 100000:
                return f"{details}\n\nThis is especially concerning given the low liquidity of ${liquidity:,.2f}."
            elif volume_24h < 50000:
                return f"{details}\n\nThis is concerning despite moderate liquidity due to low 24h volume of ${volume_24h:,.2f}."
            else:
                return f"{details}\n\nRisk is partially mitigated by good liquidity of ${liquidity:,.2f} and 24h volume of ${volume_24h:,.2f}."
        else:
            return details
    
    def _get_bundle_highlight(self, bundle_details: str) -> str:
        """Extract key bundle metrics for findings"""
        for line in bundle_details.split("\n"):
            if "Bundle buy percentage of supply:" in line:
                return line.strip()
        return "Bundle metrics not available"

    def _extract_bundle_percentage(self, bundle_details: str) -> float:
        """Extract bundle percentage from details"""
        try:
            for line in bundle_details.split("\n"):
                if "Bundle buy percentage of supply:" in line:
                    return float(line.split(":")[1].strip().replace("%", ""))
            return 0.0
        except (ValueError, IndexError):
            return 0.0

    def _get_assessment(self, positive_points: int, negative_points: int, key_findings: list, final_score: float, bundle_supported: bool) -> str:
        """Determine assessment based on positive vs negative points"""
        critical_negative_signals = [
            "CONSIDERABLE RISK", "HIGH RISK", "VERY HIGH RISK",
            "limited liquidity", "careful position sizing",
            "discount to price",
            "oversold", "declining", "decreasing market interest",
            "trend decline", "suggests decreasing", "bearish", "overbought",
            "below vwap", "downtrend", "mixed signals", "trend uncertainty",
            "momentum conflict", "pullback likely", "mean reversion", "above vwap"
        ]
        
        has_high_bundle_risk = False
        if bundle_supported:
            has_high_bundle_risk = any("HIGH RISK" in finding or "VERY HIGH RISK" in finding for finding in key_findings)
        
        if final_score < 65:
            return "negative"
        
        negative_count = 0
        for finding in key_findings:
            finding_lower = finding.lower()
            for signal in critical_negative_signals:
                if signal.lower() in finding_lower:
                    negative_count += 1
                    break
        
        if bundle_supported and has_high_bundle_risk:
            if final_score < 75:
                return "negative"
            else:
                return "neutral"
        
        if negative_count >= 2:
            return "negative"
        if negative_points > positive_points:
            return "negative"
        elif positive_points >= 2 and positive_points > negative_points:
            return "positive"
        return "neutral" 

    def _get_momentum_finding(self, market_analysis) -> str:
        """Extract momentum trading key finding"""
        momentum = market_analysis.get('technical_analysis', {}).get('momentum_trading', {})
        
        rsi = momentum.get('rsi', 50)
        rsi_signal = momentum.get('rsi_signal', 'neutral')
        stoch_signal = momentum.get('stochastic_signal', 'neutral')
        bb_signal = momentum.get('bollinger_signal', 'normal')
        
        if rsi_signal == 'overbought':
            return f"Momentum Trading: RSI {rsi:.0f} overbought, potential correction ahead"
        elif rsi_signal == 'oversold':
            return f"Momentum Trading: RSI {rsi:.0f} oversold, potential bounce opportunity"
        elif bb_signal == 'squeeze':
            return f"Momentum Trading: Bollinger Band squeeze detected, volatility expansion expected"
        elif stoch_signal == 'overbought':
            return f"Momentum Trading: Stochastic overbought, short-term pullback likely"
        elif stoch_signal == 'oversold':
            return f"Momentum Trading: Stochastic oversold, short-term bounce expected"
        else:
            return f"Momentum Trading: RSI {rsi:.0f} neutral, balanced momentum conditions"

    def _get_day_trading_finding(self, market_analysis) -> str:
        """Extract day trading key finding"""
        daytrading = market_analysis.get('technical_analysis', {}).get('day_trading', {})
        
        price_to_vwap = daytrading.get('price_to_vwap', 0)
        cmf_signal = daytrading.get('cmf_signal', 'neutral')
        volume_trend = daytrading.get('volume_trend', 0)
        
        if abs(price_to_vwap) > 5:
            direction = "above" if price_to_vwap > 0 else "below"
            return f"Day Trading: Price {abs(price_to_vwap):.1f}% {direction} VWAP, mean reversion opportunity"
        elif cmf_signal == 'bullish':
            return f"Day Trading: Strong money flow into token, institutional buying pressure"
        elif cmf_signal == 'bearish':
            return f"Day Trading: Money flowing out, selling pressure evident"
        elif volume_trend > 20:
            return f"Day Trading: Volume surge {volume_trend:.0f}%, increased activity"
        elif volume_trend < -20:
            return f"Day Trading: Volume decline {abs(volume_trend):.0f}%, decreasing interest"
        else:
            return f"Day Trading: Price {abs(price_to_vwap):.1f}% from VWAP, balanced intraday conditions"

    def _get_swing_trading_finding(self, market_analysis) -> str:
        """Extract swing trading key finding"""
        swing = market_analysis.get('technical_analysis', {}).get('swing_trading', {})
        
        ema_signal = swing.get('ema_cross_signal', 'neutral')
        macd_trend = swing.get('macd_trend', 'neutral')
        atr_percent = swing.get('atr_percent', 0)
        fib_distance = swing.get('fib_distance', 0)
        closest_fib = swing.get('closest_fib_level', 'N/A')
        
        if ema_signal == 'bullish' and macd_trend == 'bullish':
            return f"Swing Trading: Bullish EMA crossover + MACD, strong uptrend confirmed"
        elif ema_signal == 'bearish' and macd_trend == 'bearish':
            return f"Swing Trading: Bearish EMA crossover + MACD, downtrend confirmed"
        elif ema_signal == 'bearish' and macd_trend == 'bullish':
            return f"Swing Trading: Mixed signals - bearish EMA crossover despite bullish MACD, trend uncertainty"
        elif ema_signal == 'bullish' and macd_trend == 'bearish':
            return f"Swing Trading: Mixed signals - bullish EMA crossover despite bearish MACD, momentum conflict"
        elif fib_distance < 2 and closest_fib != 'N/A':
            return f"Swing Trading: Price near {closest_fib} Fibonacci level, key support/resistance"
        elif atr_percent > 5:
            return f"Swing Trading: High volatility {atr_percent:.1f}%, favorable for swing trades"
        elif atr_percent < 1:
            return f"Swing Trading: Low volatility {atr_percent:.1f}%, limited swing opportunities"
        else:
            return f"Swing Trading: {ema_signal.title()} trend with {atr_percent:.1f}% volatility"

    def _get_liquidity_findings(self, liquidity_analysis) -> list:
        """Extract liquidity key findings with separate exit liquidity for Base tokens"""
        findings = []
        
        key_metrics = liquidity_analysis.get('key_metrics', [])
        exit_liquidity_metric = None
        
        for metric in key_metrics:
            if metric.startswith('Exit liquidity:'):
                exit_liquidity_metric = metric
                break
        
        price_impact = liquidity_analysis.get('average_price_impact', 0)
        
        if price_impact < 0.01:
            findings.append("Liquidity: Minimal price impact indicating exceptional depth")
        elif price_impact < 1.0:
            findings.append(f"Liquidity: Low average price impact of {price_impact:.2f}% indicates strong liquidity")
        elif price_impact < 3.0:
            findings.append(f"Liquidity: Moderate average price impact of {price_impact:.2f}%")
        else:
            findings.append(f"Liquidity: High average price impact of {price_impact:.2f}% indicates limited liquidity")
        
        if exit_liquidity_metric:
            findings.append(exit_liquidity_metric)
        
        return findings

    def _get_trading_styles_summary(self, market_analysis) -> str:
        """Create comprehensive summary explaining trading style indicators"""
        technical_analysis = market_analysis.get('technical_analysis', {})
        momentum = technical_analysis.get('momentum_trading', {})
        daytrading = technical_analysis.get('day_trading', {})
        swing = technical_analysis.get('swing_trading', {})
        
        # Momentum trading explanation
        rsi = momentum.get('rsi', 50)
        stoch_k = momentum.get('stochastic_k', 50)
        bb_pos = momentum.get('bollinger_position', 0.5) * 100
        
        momentum_summary = f"Momentum trading indicators show RSI at {rsi:.0f} and Stochastic at {stoch_k:.0f}, with price at {bb_pos:.0f}% of Bollinger Band range. These oscillators help identify overbought/oversold conditions and potential reversal points for short-term momentum plays."
        
        # Day trading explanation
        price_to_vwap = daytrading.get('price_to_vwap', 0)
        cmf = daytrading.get('cmf', 0)
        volume_trend = daytrading.get('volume_trend', 0)
        
        day_summary = f"Day trading analysis reveals price trading {abs(price_to_vwap):.1f}% {'above' if price_to_vwap > 0 else 'below'} VWAP with Chaikin Money Flow at {cmf:.3f} and volume trend at {volume_trend:+.0f}%. VWAP acts as dynamic support/resistance while CMF indicates institutional money flow direction."
        
        # Swing trading explanation  
        ema_signal = swing.get('ema_cross_signal', 'neutral')
        macd_trend = swing.get('macd_trend', 'neutral')
        atr_percent = swing.get('atr_percent', 0)
        
        swing_summary = f"Swing trading setup shows {ema_signal} EMA trend with {macd_trend} MACD momentum and {atr_percent:.1f}% volatility (ATR). EMA crossovers signal trend changes while MACD confirms momentum direction and ATR measures volatility for position sizing."
        
        return f"{momentum_summary}\n\n{day_summary}\n\n{swing_summary}"
