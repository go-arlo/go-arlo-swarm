"""
Trading Analyzer for Token Data
Analyzes structured token data and makes trading decisions based on configurable criteria.
Uses data directly from data_fetchers.py and token_safety.py - no text parsing.
"""

import os
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum
from wallet_fetcher import get_sol_balance


class RiskLevel(str, Enum):
    """Risk level enum"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConcentrationLevel(str, Enum):
    """Holder concentration level enum"""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class MarketPressure(str, Enum):
    """Market buy/sell pressure enum"""
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"


class GrokSentiment(str, Enum):
    """Grok sentiment rating enum"""
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"


class ScamRisk(str, Enum):
    """Grok scam risk assessment enum"""
    UNLIKELY = "Unlikely"
    UNCERTAIN = "Uncertain"
    LIKELY = "Likely"


class StructuredTokenData(BaseModel):
    """
    Structured input for trading analysis.
    Maps directly to output from fetch_all_token_data() in data_fetchers.py
    """
    # Token identification
    token_address: str
    chain: str
    token_symbol: str
    token_name: str

    # Market data (from BirdEye)
    market_data: Optional[Dict[str, Any]] = None

    # Holder data (from Moralis)
    holder_data: Optional[Dict[str, Any]] = None

    # Bundler analysis (Solana only)
    bundler_analysis: Optional[Dict[str, Any]] = None

    # 24h market health
    market_health_24h: Optional[Dict[str, Any]] = None

    # Sentiment data (TweetScout)
    sentiment_data: Optional[Dict[str, Any]] = None

    # Safety analysis (from token_safety.py)
    safety_analysis: Optional[Dict[str, Any]] = None


class TradingCriteria(BaseModel):
    """Configurable criteria for trading decisions"""

    # Individual criteria toggles
    check_token_safety: bool = Field(default=True, description="Enable token safety checks")
    check_holder_concentration: bool = Field(
        default=True, description="Enable holder concentration checks"
    )
    check_bundler_risk: bool = Field(
        default=False, description="Enable bundler risk checks (Solana only)"
    )
    check_market_pressure: bool = Field(
        default=True, description="Enable market pressure checks"
    )

    # Token Safety criteria
    max_overall_risk: RiskLevel = Field(
        default=RiskLevel.LOW,
        description="Maximum acceptable overall risk level"
    )

    # Holder data criteria
    max_concentration: ConcentrationLevel = Field(
        default=ConcentrationLevel.HIGH,
        description="Maximum acceptable top 10 holder concentration"
    )

    # Bundler analysis criteria (Solana only)
    max_bundler_risk: RiskLevel = Field(
        default=RiskLevel.MEDIUM,
        description="Maximum acceptable bundler impact risk"
    )

    # Market health criteria
    required_pressure: List[MarketPressure] = Field(
        default=[MarketPressure.NEUTRAL, MarketPressure.BUY],
        description="Acceptable buy/sell pressure levels"
    )

    # Sentiment criteria (TweetScout score)
    min_sentiment_score: float = Field(
        default=100.0,
        description="Minimum TweetScout score required for sentiment check"
    )

    # Grok sentiment criteria
    check_grok_sentiment: bool = Field(
        default=True, description="Enable Grok sentiment checks"
    )
    allowed_grok_sentiments: List[GrokSentiment] = Field(
        default=[GrokSentiment.POSITIVE, GrokSentiment.NEUTRAL],
        description="Acceptable Grok sentiment ratings"
    )

    check_scam_likelihood: bool = Field(
        default=True, description="Enable scam likelihood checks"
    )
    allowed_scam_risks: List[ScamRisk] = Field(
        default=[ScamRisk.UNLIKELY, ScamRisk.UNCERTAIN],
        description="Acceptable Grok scam risk assessments"
    )

    # Additional safety margins (disabled by default)
    min_liquidity_usd: float = Field(
        default=0,
        description="Minimum required liquidity in USD"
    )

    min_holders: int = Field(
        default=0,
        description="Minimum number of holders required"
    )


class TradingRecommendation(BaseModel):
    """Trading recommendation result"""

    action: str = Field(description="BUY, SELL, or HOLD")
    confidence: float = Field(description="Confidence level 0-1")
    reasoning: List[str] = Field(description="Reasons for the decision")
    criteria_met: Dict[str, bool] = Field(description="Which criteria were met")
    risk_factors: List[str] = Field(description="Identified risk factors")
    position_size_percent: Optional[float] = Field(
        description="Suggested position size as % of portfolio"
    )

    # SOL trading amounts
    sol_amount: Optional[float] = Field(
        default=None, description="Actual SOL amount to trade"
    )
    sol_balance: Optional[float] = Field(
        default=None, description="Current SOL balance in wallet"
    )
    trade_size_percent: Optional[float] = Field(
        default=10.0, description="Percentage of SOL balance to trade"
    )

    # Additional extracted data for transparency
    market_health: Optional[str] = Field(
        default=None, description="Extracted market health level"
    )
    overall_score: int = Field(
        default=0, description="Overall score out of 100"
    )


class TradingAnalyzer:
    """Main trading analyzer class - uses structured data only"""

    def __init__(
        self,
        criteria: TradingCriteria = None,
        wallet_address: Optional[str] = None,
        debug: bool = False
    ):
        self.criteria = criteria or TradingCriteria()
        self.max_sol_amount = float(os.getenv("MAX_AMOUNT", "0.1"))
        self.debug = debug

    def analyze_structured_data(self, data: Dict[str, Any]) -> TradingRecommendation:
        """
        Analyze structured token data directly from data_fetchers.py output.
        No text parsing - uses structured data fields directly.

        Args:
            data: Dict from fetch_all_token_data() containing:
                - safety_analysis: Token safety from token_safety.py
                - holder_data: Holder info from Moralis
                - market_health_24h: Market pressure data from BirdEye
                - sentiment_data: TweetScout score
                - bundler_analysis: Bundle detection (Solana only)

        Returns:
            TradingRecommendation with action, confidence, and reasoning
        """
        criteria_results = {}

        if self.debug:
            print(f"\n🔍 Evaluating Trading Criteria (Structured Data):")

        # 1. Token Safety Check - uses safety_analysis.overall_risk
        if self.criteria.check_token_safety:
            criteria_results["token_safety"] = self._check_token_safety_structured(
                data.get("safety_analysis")
            )

        # 2. Holder Concentration Check - uses holder_data.top10_concentration
        if self.criteria.check_holder_concentration:
            criteria_results["holder_concentration"] = self._check_concentration_structured(
                data.get("holder_data")
            )

        # 3. Bundler Risk Check (optional) - uses bundler_analysis
        if self.criteria.check_bundler_risk:
            criteria_results["bundler_risk"] = self._check_bundler_structured(
                data.get("bundler_analysis")
            )

        # 4. Market Pressure Check - uses market_health_24h.pressure_dominance
        if self.criteria.check_market_pressure:
            criteria_results["market_pressure"] = self._check_pressure_structured(
                data.get("market_health_24h")
            )

        # 5. TweetScout Sentiment Check - conditional on market pressure
        criteria_results["tweetscout_sentiment"] = self._check_sentiment_structured(
            data.get("sentiment_data"),
            data.get("market_health_24h")
        )

        # 6. Grok Sentiment Check - uses sentiment_data.grok_sentiment only
        if self.criteria.check_grok_sentiment:
            criteria_results["grok_sentiment"] = self._check_grok_sentiment_structured(
                data.get("sentiment_data")
            )

        # 7. Scam Likelihood Check - uses sentiment_data.grok_scam_assessment
        if self.criteria.check_scam_likelihood:
            criteria_results["scam_likelihood"] = self._check_scam_likelihood_structured(
                data.get("sentiment_data")
            )

        if self.debug:
            passed = sum(criteria_results.values())
            total = len(criteria_results)
            pct = (passed / total * 100) if total > 0 else 0
            print(f"📊 Criteria Summary: {passed}/{total} passed ({pct:.0f}%)")

        # Build recommendation from criteria results
        return self._build_recommendation(criteria_results, data)

    def _check_token_safety_structured(self, safety: Optional[Dict]) -> bool:
        """Check token safety from structured safety_analysis data"""
        if not safety:
            if self.debug:
                print(f"🔐 Token Safety: No data -> FAIL")
            return False

        overall_risk = safety.get("overall_risk", "UNKNOWN")
        result = overall_risk == "LOW"

        if self.debug:
            print(f"🔐 Token Safety: Risk '{overall_risk}' -> {'PASS' if result else 'FAIL'}")
        return result

    def _check_concentration_structured(self, holder_data: Optional[Dict]) -> bool:
        """Check holder concentration from structured holder_data"""
        if not holder_data:
            if self.debug:
                print(f"👥 Holder Concentration: No data -> FAIL")
            return False

        concentration = holder_data.get("top10_concentration")
        if concentration is None:
            if self.debug:
                print(f"👥 Holder Concentration: No concentration data -> FAIL")
            return False

        # Determine concentration level from percentage
        if concentration <= 10:
            level = "LOW"
            level_num = 0
        elif concentration <= 20:
            level = "MODERATE"
            level_num = 1
        elif concentration <= 35:
            level = "HIGH"
            level_num = 2
        else:
            level = "VERY_HIGH"
            level_num = 3

        # Compare to max allowed
        max_levels = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "VERY_HIGH": 3}
        max_level_num = max_levels.get(self.criteria.max_concentration.value, 2)
        result = level_num <= max_level_num

        if self.debug:
            print(f"👥 Holder Concentration: {concentration:.1f}% ({level}) "
                  f"vs max {self.criteria.max_concentration.value} -> "
                  f"{'PASS' if result else 'FAIL'}")
        return result

    def _check_bundler_structured(self, bundler: Optional[Dict]) -> bool:
        """Check bundler risk from structured bundler_analysis data"""
        if not bundler:
            if self.debug:
                print(f"🔍 Bundler Risk: No data -> PASS (not required)")
            return True

        if not bundler.get("bundled_detected"):
            if self.debug:
                print(f"🔍 Bundler Risk: No bundles detected -> PASS")
            return True

        # Check present impact risk
        impact = bundler.get("present_impact_analysis", {})
        impact_risk = impact.get("current_impact_risk", "UNKNOWN")

        result = impact_risk in ["LOW", "MEDIUM"]

        if self.debug:
            print(f"🔍 Bundler Risk: Impact '{impact_risk}' -> "
                  f"{'PASS' if result else 'FAIL'}")
        return result

    def _check_pressure_structured(self, health: Optional[Dict]) -> bool:
        """Check market pressure from structured market_health_24h data"""
        if not health or not health.get("market_health_available"):
            if self.debug:
                print(f"📈 Market Pressure: No data -> FAIL")
            return False

        pressure = health.get("pressure_dominance", "UNKNOWN")

        # Map pressure to our expected values
        pressure_map = {
            "STRONG_BUY": "BUY",
            "BUY": "BUY",
            "NEUTRAL": "NEUTRAL",
            "SELL": "SELL",
            "STRONG_SELL": "SELL"
        }
        mapped = pressure_map.get(pressure, pressure)

        required = [p.value for p in self.criteria.required_pressure]
        result = mapped in required

        if self.debug:
            print(f"📈 Market Pressure: '{pressure}' (-> '{mapped}') "
                  f"vs required {required} -> {'PASS' if result else 'FAIL'}")
        return result

    def _check_sentiment_structured(
        self,
        sentiment: Optional[Dict],
        market_health: Optional[Dict] = None
    ) -> bool:
        """
        Check TweetScout score - conditional on market pressure.

        Logic:
        - If pressure is BUY or STRONG_BUY → TweetScout NOT required, auto-pass
        - If pressure is NEUTRAL → TweetScout score must be >= min_sentiment_score
        - If pressure is SELL/STRONG_SELL → Market pressure check will fail anyway
        """
        # Get market pressure to determine if TweetScout is required
        pressure = "UNKNOWN"
        if market_health and market_health.get("market_health_available"):
            raw_pressure = market_health.get("pressure_dominance", "UNKNOWN")
            pressure_map = {
                "STRONG_BUY": "BUY",
                "BUY": "BUY",
                "NEUTRAL": "NEUTRAL",
                "SELL": "SELL",
                "STRONG_SELL": "SELL"
            }
            pressure = pressure_map.get(raw_pressure, raw_pressure)

        # If pressure is BUY, TweetScout check is not required
        if pressure == "BUY":
            if self.debug:
                print(f"💭 TweetScout: Bypassed (pressure is BUY) -> PASS")
            return True

        # If pressure is NEUTRAL, require TweetScout score
        if pressure == "NEUTRAL":
            if not sentiment:
                if self.debug:
                    print(f"💭 TweetScout: No data (pressure NEUTRAL) -> FAIL")
                return False

            score = sentiment.get("tweet_scout_score")
            if score is None:
                if self.debug:
                    print(f"💭 TweetScout: No score (pressure NEUTRAL) -> FAIL")
                return False

            result = score >= self.criteria.min_sentiment_score

            if self.debug:
                icon = "🟢" if score >= 1000 else "🟡" if score >= 500 else "🟠" if score >= 200 else "🔴"
                print(f"💭 TweetScout: {icon} {score:.0f} vs min "
                      f"{self.criteria.min_sentiment_score} (pressure NEUTRAL) -> "
                      f"{'PASS' if result else 'FAIL'}")
            return result

        if self.debug:
            print(f"💭 TweetScout: Bypassed (pressure {pressure}) -> PASS")
        return True

    def _check_grok_sentiment_structured(self, sentiment: Optional[Dict]) -> bool:
        """Check Grok sentiment only (separate from scam likelihood)"""
        if not sentiment:
            if self.debug:
                print(f"🤖 Grok Sentiment: No data -> FAIL")
            return False

        grok_sentiment = sentiment.get("grok_sentiment")

        if not grok_sentiment:
            if self.debug:
                print(f"🤖 Grok Sentiment: Missing data -> FAIL")
            return False

        allowed_sentiments = [s.value for s in self.criteria.allowed_grok_sentiments]
        result = grok_sentiment in allowed_sentiments

        if self.debug:
            icon = "🟢" if grok_sentiment == "Positive" else "🟡" if grok_sentiment == "Neutral" else "🔴"
            print(f"🤖 Grok Sentiment: {icon} {grok_sentiment} "
                  f"(allowed: {allowed_sentiments}) -> {'PASS' if result else 'FAIL'}")
        return result

    def _check_scam_likelihood_structured(self, sentiment: Optional[Dict]) -> bool:
        """Check Grok scam likelihood assessment (separate from sentiment)"""
        if not sentiment:
            if self.debug:
                print(f"🚨 Scam Likelihood: No data -> FAIL")
            return False

        grok_scam = sentiment.get("grok_scam_assessment")

        if not grok_scam:
            if self.debug:
                print(f"🚨 Scam Likelihood: Missing data -> FAIL")
            return False

        allowed_risks = [r.value for r in self.criteria.allowed_scam_risks]
        result = grok_scam in allowed_risks

        if self.debug:
            icon = "✅" if grok_scam == "Unlikely" else "🔶" if grok_scam == "Uncertain" else "🚨"
            print(f"🚨 Scam Likelihood: {icon} {grok_scam} "
                  f"(allowed: {allowed_risks}) -> {'PASS' if result else 'FAIL'}")
        return result

    def _build_recommendation(
        self,
        criteria_results: Dict[str, bool],
        data: Dict[str, Any]
    ) -> TradingRecommendation:
        """Build trading recommendation from criteria results"""
        if not criteria_results:
            sol_balance = get_sol_balance() or 0.0
            return TradingRecommendation(
                action="HOLD",
                confidence=0.0,
                reasoning=["❌ No criteria enabled for evaluation"],
                criteria_met={},
                risk_factors=["No trading criteria configured"],
                position_size_percent=None,
                sol_amount=None,
                sol_balance=sol_balance,
                trade_size_percent=0.0,
                overall_score=0
            )

        passed = sum(criteria_results.values())
        total = len(criteria_results)
        confidence = passed / total if total > 0 else 0

        # Check if strict mode
        is_strict = (
            self.criteria.max_overall_risk == RiskLevel.LOW and
            self.criteria.min_sentiment_score >= 100.0
        )

        # Build reasoning lists
        reasoning = []
        risk_factors = []
        for criterion, passed_check in criteria_results.items():
            name = criterion.replace('_', ' ').title()
            if passed_check:
                reasoning.append(f"✅ {name}: PASSED")
            else:
                risk_factors.append(f"❌ {name}: FAILED")

        # Determine action
        if is_strict:
            # Strict mode: ALL must pass
            if passed == total:
                action = "BUY"
                position_size = 10.0
                if self.debug:
                    print(f"✅ Strict mode: All criteria passed - BUY")
            else:
                action = "HOLD"
                position_size = None
                if self.debug:
                    print(f"⛔ Strict mode: {passed}/{total} passed - HOLD")
            reasoning.append(
                "✅ STRICT MODE: All criteria passed" if action == "BUY"
                else "⛔ STRICT MODE: ALL criteria must pass"
            )
        else:
            # Normal mode: threshold-based
            if passed == total:
                action = "BUY"
                position_size = 10.0
            elif confidence >= 0.75:
                action = "BUY"
                position_size = 5.0
            else:
                action = "HOLD"
                position_size = None

        # Calculate SOL amounts
        sol_balance = get_sol_balance() or 0.0
        sol_amount = None
        trade_size_percent = 10.0

        if action == "BUY" and sol_balance > 0:
            sol_amount = min(sol_balance * 0.1, self.max_sol_amount)
            if confidence < 1.0:
                sol_amount = sol_amount * confidence
            trade_size_percent = (sol_amount / sol_balance * 100) if sol_balance > 0 else 0

        # Extract market health for transparency
        health = data.get("market_health_24h", {})
        market_health = health.get("market_health") if health.get("market_health_available") else None

        return TradingRecommendation(
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            criteria_met=criteria_results,
            risk_factors=risk_factors,
            position_size_percent=position_size,
            sol_amount=sol_amount,
            sol_balance=sol_balance,
            trade_size_percent=trade_size_percent,
            market_health=market_health,
            overall_score=int(confidence * 100)
        )


# Helper function to create default criteria
def get_conservative_criteria() -> TradingCriteria:
    """Get conservative trading criteria (safest settings)"""
    return TradingCriteria(
        check_token_safety=True,
        check_holder_concentration=True,
        check_bundler_risk=True,
        check_market_pressure=True,
        max_overall_risk=RiskLevel.LOW,
        max_concentration=ConcentrationLevel.LOW,
        max_bundler_risk=RiskLevel.LOW,
        required_pressure=[MarketPressure.BUY],
        min_sentiment_score=200.0,
        check_grok_sentiment=True,
        allowed_grok_sentiments=[GrokSentiment.POSITIVE],
        check_scam_likelihood=True,
        allowed_scam_risks=[ScamRisk.UNLIKELY],
        min_liquidity_usd=100000,
        min_holders=500
    )


def get_moderate_criteria() -> TradingCriteria:
    """Get moderate trading criteria (balanced settings) - MATCHES USER DEFAULT"""
    return TradingCriteria(
        check_token_safety=True,
        check_holder_concentration=True,
        check_bundler_risk=False,
        check_market_pressure=True,
        max_overall_risk=RiskLevel.LOW,
        max_concentration=ConcentrationLevel.HIGH,
        max_bundler_risk=RiskLevel.MEDIUM,
        required_pressure=[MarketPressure.NEUTRAL, MarketPressure.BUY],
        min_sentiment_score=100.0,
        check_grok_sentiment=True,
        allowed_grok_sentiments=[GrokSentiment.POSITIVE, GrokSentiment.NEUTRAL],
        check_scam_likelihood=True,
        allowed_scam_risks=[ScamRisk.UNLIKELY, ScamRisk.UNCERTAIN],
        min_liquidity_usd=0,
        min_holders=0
    )


def get_aggressive_criteria() -> TradingCriteria:
    """Get aggressive trading criteria (riskier settings)"""
    return TradingCriteria(
        check_token_safety=True,
        check_holder_concentration=True,
        check_bundler_risk=False,
        check_market_pressure=True,
        max_overall_risk=RiskLevel.HIGH,
        max_concentration=ConcentrationLevel.VERY_HIGH,
        max_bundler_risk=RiskLevel.HIGH,
        required_pressure=[MarketPressure.NEUTRAL, MarketPressure.BUY, MarketPressure.SELL],
        min_sentiment_score=100.0,
        check_grok_sentiment=True,
        allowed_grok_sentiments=[GrokSentiment.POSITIVE, GrokSentiment.NEUTRAL, GrokSentiment.NEGATIVE],
        check_scam_likelihood=True,
        allowed_scam_risks=[ScamRisk.UNLIKELY, ScamRisk.UNCERTAIN],
        min_liquidity_usd=10000,
        min_holders=50
    )


def get_strict_default_criteria() -> TradingCriteria:
    """
    Get strict default trading criteria - RECOMMENDED DEFAULT

    STRICT MODE REQUIREMENTS - ALL MUST PASS:
    - Token Safety: Overall Risk must be LOW only
    - Holder Concentration: ≤35% (LOW, MODERATE, or HIGH - not VERY_HIGH)
    - Grok Sentiment: Must be Positive or Neutral
    - Scam Likelihood: Must be Unlikely or Uncertain (Likely = rejected)
    - Market Pressure: BUY or NEUTRAL only (SELL = rejected)
    - TweetScout: CONDITIONAL on market pressure:
        - Pressure BUY/STRONG_BUY: TweetScout NOT required (auto-pass)
        - Pressure NEUTRAL: TweetScout score must be >= 100
        - Pressure SELL: Token REJECTED (via market_pressure check)

    Unlike other modes, this enforces that ALL criteria must pass.
    If any single criterion fails, the token purchase is blocked.
    """
    return TradingCriteria(
        check_token_safety=True,
        check_holder_concentration=True,
        check_bundler_risk=False,
        check_market_pressure=True,
        max_overall_risk=RiskLevel.LOW,
        max_concentration=ConcentrationLevel.HIGH,
        max_bundler_risk=RiskLevel.MEDIUM,
        required_pressure=[MarketPressure.NEUTRAL, MarketPressure.BUY],
        min_sentiment_score=100.0,
        check_grok_sentiment=True,
        allowed_grok_sentiments=[GrokSentiment.POSITIVE, GrokSentiment.NEUTRAL],
        check_scam_likelihood=True,
        allowed_scam_risks=[ScamRisk.UNLIKELY, ScamRisk.UNCERTAIN],
        min_liquidity_usd=0,
        min_holders=0
    )
