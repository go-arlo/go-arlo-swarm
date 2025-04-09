from agency_swarm import Agent
from .tools.market_analysis import MarketAnalysis
from .tools.liquidity_analysis import LiquidityAnalysis
from .tools.bundle_detector import BundleDetector

class Signal(Agent):
    def __init__(self):
        super().__init__(
            name="Signal",
            description="Market and liquidity metrics analyst",
            instructions="./instructions.md",
            tools=[MarketAnalysis, LiquidityAnalysis, BundleDetector],
            temperature=0.5,
            max_prompt_tokens=128000,
            model="gpt-4o"
        )

    def process_message(self, message, sender):
        """Fast message processing with error handling"""
        if sender == "Arlo":
            try:
                # Run bundle detection first
                bundle_tool = BundleDetector()
                bundle_analysis = bundle_tool.analyze_transactions(message)
                
                # Run other analysis tools
                market_tool = MarketAnalysis(address=message)
                liquidity_tool = LiquidityAnalysis(address=message)
                
                market_analysis = market_tool.run()
                liquidity_analysis = liquidity_tool.run()
                
                # Combine all analysis
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
                        "key_findings": ["Error processing analysis"]
                    }
                }
        
        return super().process_message(message, sender)
    
    def _combine_analysis(self, bundle_analysis, market_analysis, liquidity_analysis):
        """Combine all analysis results considering bundle context"""
        
        # Get base metrics
        market_score = market_analysis.get("market_score", 0)
        liquidity_score = liquidity_analysis.get("liquidity_score", 0)
        
        # Extract bundle info
        has_bundles = bundle_analysis.get("has_bundled_trades", False)
        bundle_details = bundle_analysis.get("details", "")
        bundle_risk = self._extract_risk_level(bundle_details)
        bundle_percentage = self._extract_bundle_percentage(bundle_details)
        
        # Adjust score based on bundle risk and liquidity
        final_score = self._calculate_final_score(
            market_score,
            liquidity_score,
            bundle_risk,
            liquidity_analysis
        )
        
        # Get points from each analysis
        market_points = market_analysis.get('market_metrics', {})
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
        if has_bundles:
            findings.append(f"Top 5 bundles on launch date totaled {bundle_percentage:.2f}% of supply - {bundle_risk}")
        
        findings.extend(market_analysis.get("key_findings", [])[:2])
        findings.extend(liquidity_analysis.get("key_metrics", [])[:2])
        
        assessment = self._get_assessment(
            total_positive,
            total_negative,
            findings,
            final_score
        )
        
        bundle_summary = self._get_bundle_summary(bundle_analysis, liquidity_analysis)
        market_summary = market_analysis.get("market_summary", "")
        
        return {
            "data": {
                "market_score": final_score,
                "assessment": assessment,
                "summary": f"{bundle_summary}\n\n{market_summary}",
                "key_findings": findings
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
    
    def _calculate_final_score(self, market_score, liquidity_score, bundle_risk, liquidity_analysis):
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
            reduction = max(reduction * 0.6, 0)
        
        final_score = max(0, min(base_score, base_score - reduction))
        
        return final_score
    
    def _get_bundle_summary(self, bundle_analysis, liquidity_analysis) -> str:
        """Create bundle summary with liquidity context"""
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

    def _get_assessment(self, positive_points: int, negative_points: int, key_findings: list, final_score: float) -> str:
        """Determine assessment based on positive vs negative points"""
        critical_negative_signals = [
            "CONSIDERABLE RISK", "HIGH RISK", "VERY HIGH RISK",
            "limited liquidity", "careful position sizing",
            "discount to price",
            "oversold", "declining", "decreasing market interest",
            "trend decline", "suggests decreasing"
        ]
        
        if final_score < 65:
            return "negative"
        
        negative_count = 0
        for finding in key_findings:
            finding_lower = finding.lower()
            for signal in critical_negative_signals:
                if signal.lower() in finding_lower:
                    negative_count += 1
                    break
        
        if negative_count >= 2:
            return "negative"
        if negative_points > positive_points:
            return "negative"
        elif positive_points >= 2 and positive_points > negative_points:
            return "positive"
        return "neutral" 
