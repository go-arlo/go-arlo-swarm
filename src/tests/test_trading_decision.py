#!/usr/bin/env python3
"""
Isolated test for MakeTradingDecision tool to evaluate decision quality
Tests how well the tool assesses information from the grok narration agent
"""

import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.append(os.path.join(parent_dir, "trading_agent"))

from tools.MakeTradingDecision import MakeTradingDecision

load_dotenv()


def create_test_narratives():
    """Create sample narratives with different risk/quality profiles"""

    narratives = {
        "high_quality_buy": """
Token: SuperToken (SUPER)
Chain: Solana
Address: ABC123...
Price: $1.25
FDV: $125,000,000
Market Cap: $120,000,000
24h Volume: $15,000,000
Liquidity: $8,500,000
Total Holders: 45,000
Top 10 Concentration: 12.5%

### Market Overview
Exceptional volume surge of +245% indicates massive institutional interest.
Balanced buy/sell pressure at 78%/22% shows strong bullish momentum with minimal
selling pressure. Low 1.2% volatility provides stability for large position entries.
Deep liquidity of $8.5M supports institutional-sized trades without slippage concerns.

### Token Safety
Contract ownership fully renounced eliminating manipulation risk. No transfer
restrictions or freeze authority detected. Jupiter strict list verified enhancing
credibility. No honeypot flags detected. Overall: EXCELLENT safety profile.

### Holder Insights
45,000 holders with excellent 12.5% top-10 concentration eliminates whale
manipulation risk. Massive holder growth trend with +5,000 new holders in 24h
indicates explosive adoption. Distribution superior to established projects.

### Risk Assessment
NO bundling risk detected - completely organic launch patterns. EXCELLENT 24h
market health with dominant buy pressure. Extremely low holder concentration
creates zero manipulation risk. Overall: optimal risk profile for maximum position.

### Social & Trends
Overwhelmingly bullish sentiment with viral social media presence. Massive social
volume with revolutionary technology narrative driving adoption. Strong community
with verified partnerships. Top trend: institutional accumulation confirmed.

24H MARKET HEALTH:
- Overall Health: EXCELLENT
- Pressure Dominance: BUY
- Buy/Sell Pressure: 78% / 22%
- Volume Change: +245.0%
- Avg Volatility: 1.2%

TOKEN SAFETY ANALYSIS:
- Overall Risk Level: VERY LOW
- Contract Control: POSITIVE - Ownership fully renounced
- Holder Control: POSITIVE - No restrictions detected
""",

        "moderate_quality_buy": """
Token: DecentCoin (DECENT)
Chain: Ethereum
Address: 0x456...
Price: $0.85
FDV: $85,000,000
Market Cap: $75,000,000
24h Volume: $5,000,000
Liquidity: $2,500,000
Total Holders: 18,500
Top 10 Concentration: 28.5%

### Market Overview
Volume increase of +45% shows growing interest. Buy/sell pressure at 58%/42%
indicates mild bullish sentiment. Moderate 3.8% volatility requires careful timing.
Adequate liquidity supports normal trading volumes.

### Token Safety
Contract ownership renounced. No major red flags detected but some minor concerns
about metadata mutability. Basic security audit completed. Overall: GOOD safety
profile with minor considerations.

### Holder Insights
18,500 holders with moderate 28.5% top-10 concentration creates some whale risk.
Steady holder growth of +500 in 24h shows consistent interest. Distribution typical
for mid-cap tokens.

### Risk Assessment
LOW to MEDIUM bundling risk with some coordination detected. GOOD 24h market health
with balanced dynamics. Moderate holder concentration requires position size limits.
Overall: acceptable risk with standard precautions.

### Social & Trends
Positive sentiment with growing community. Moderate social engagement with utility-
focused narrative. Some community concerns about roadmap execution. Mixed signals
require careful evaluation.

24H MARKET HEALTH:
- Overall Health: GOOD
- Pressure Dominance: BUY
- Buy/Sell Pressure: 58% / 42%
- Volume Change: +45.0%
- Avg Volatility: 3.8%

TOKEN SAFETY ANALYSIS:
- Overall Risk Level: MEDIUM
- Contract Control: POSITIVE - Ownership renounced
- Holder Control: NEUTRAL - Minor metadata concerns
""",

        "poor_quality_avoid": """
Token: RiskyCoin (RISKY)
Chain: Solana
Address: DEF789...
Price: $0.0015
FDV: $1,500,000
Market Cap: $750,000
24h Volume: $125,000
Liquidity: $45,000
Total Holders: 2,450
Top 10 Concentration: 67.8%

### Market Overview
Volume declining -35% indicates waning interest. Heavily skewed sell pressure at
25%/75% shows major distribution phase. Extreme 15.7% volatility creates high risk
environment. Thin liquidity of $45K causes severe slippage concerns.

### Token Safety
Contract ownership NOT renounced - major red flag. Multiple transfer restrictions
detected including potential freeze functions. NOT on Jupiter strict list. Multiple
honeypot warning flags detected. Overall: DANGEROUS safety profile.

### Holder Insights
Only 2,450 holders with concerning 67.8% top-10 concentration creates extreme whale
manipulation risk. Declining holder count with -150 holders lost in 24h indicates
abandonment. Distribution heavily skewed to early insiders.

### Risk Assessment
EXTREME bundling risk with coordinated dumping patterns detected. POOR 24h market
health with sell pressure dominance. Extreme holder concentration enables price
manipulation. Overall: unacceptable risk profile - avoid completely.

### Social & Trends
Overwhelmingly negative sentiment with scam allegations. Declining social volume
with community exodus ongoing. Multiple red flags including dev team anonymity.
Top trend: coordinated exit by insiders.

24H MARKET HEALTH:
- Overall Health: POOR
- Pressure Dominance: SELL
- Buy/Sell Pressure: 25% / 75%
- Volume Change: -35.0%
- Avg Volatility: 15.7%

TOKEN SAFETY ANALYSIS:
- Overall Risk Level: VERY HIGH
- Contract Control: NEGATIVE - Ownership retained
- Holder Control: NEGATIVE - Multiple restrictions detected
""",

        "neutral_hold": """
Token: StableCoin (STABLE)
Chain: Base
Address: 0x789...
Price: $2.50
FDV: $250,000,000
Market Cap: $245,000,000
24h Volume: $8,000,000
Liquidity: $12,000,000
Total Holders: 35,000
Top 10 Concentration: 22.0%

### Market Overview
Volume stable at +2% shows consistent but unremarkable activity. Neutral buy/sell
pressure at 50%/50% indicates price equilibrium. Standard 4.5% volatility within
normal ranges. Good liquidity supports trading but no exceptional factors present.

### Token Safety
Contract ownership renounced following standard practices. No major security issues
but also no standout safety features. Standard ERC-20 implementation. Overall:
ACCEPTABLE safety profile meeting basic standards.

### Holder Insights
35,000 holders with standard 22.0% top-10 concentration typical for established
tokens. Minimal holder change of +25 in 24h shows stable but unremarkable growth.
Distribution patterns normal for mature projects.

### Risk Assessment
NO significant bundling concerns detected. NEUTRAL 24h market health with balanced
metrics. Standard holder concentration within acceptable ranges. Overall: standard
risk profile with no major concerns or opportunities.

### Social & Trends
Mixed sentiment with balanced community opinions. Average social engagement with
steady-state discussions. No major catalysts or concerns identified. Consensus:
wait-and-see approach recommended.

24H MARKET HEALTH:
- Overall Health: NEUTRAL
- Pressure Dominance: NEUTRAL
- Buy/Sell Pressure: 50% / 50%
- Volume Change: +2.0%
- Avg Volatility: 4.5%

TOKEN SAFETY ANALYSIS:
- Overall Risk Level: MEDIUM
- Contract Control: POSITIVE - Standard renunciation
- Holder Control: NEUTRAL - No restrictions detected
""",

        "edge_case_missing_data": """
Token: DataPoor (POOR)
Chain: Ethereum
Address: 0xABC...
Price: $0.45
FDV: Data unavailable
Market Cap: $2,300,000
24h Volume: Data unavailable
Liquidity: $125,000
Total Holders: Data unavailable
Top 10 Concentration: Data unavailable

### Market Overview
Limited volume data available but shows concerning liquidity constraints.
Buy/sell pressure data incomplete making trend analysis difficult. Volatility
measurements unreliable due to data gaps. Shallow liquidity creates execution risks.

### Token Safety
Contract verification status unknown. Safety audit information not available.
Jupiter listing status unclear. Multiple data gaps prevent comprehensive safety
assessment. Overall: UNKNOWN safety profile - proceed with extreme caution.

### Holder Insights
Holder data completely unavailable preventing concentration analysis. No growth
metrics available to assess adoption trends. Distribution patterns cannot be
evaluated without holder information.

### Risk Assessment
Bundling analysis impossible without transaction data. Market health assessment
severely limited by missing metrics. Risk evaluation compromised by data
insufficiency. Overall: HIGH risk due to information gaps.

### Social & Trends
Social sentiment data limited. Community engagement metrics unavailable. No clear
narrative or trend identification possible. Insufficient information for confident
assessment.

24H MARKET HEALTH:
- Overall Health: UNKNOWN
- Pressure Dominance: UNKNOWN
- Buy/Sell Pressure: N/A / N/A
- Volume Change: N/A
- Avg Volatility: N/A

TOKEN SAFETY ANALYSIS:
- Overall Risk Level: UNKNOWN
- Contract Control: UNKNOWN - Insufficient data
- Holder Control: UNKNOWN - No verification available
"""
    }

    return narratives


def test_decision_quality(narrative_name, narrative_content):
    """Test decision making for a single narrative"""

    print(f"\n{'='*80}")
    print(f"🧪 TESTING: {narrative_name.upper()}")
    print(f"{'='*80}")

    # Create decision tool
    decision_tool = MakeTradingDecision(message_content=narrative_content)

    # Get decision
    try:
        result = decision_tool.run()

        # Extract key metrics from result for analysis
        lines = result.split('\n')
        metrics = {}

        for line in lines:
            if '📊 Recommendation:' in line and '**' in line:
                # Extract recommendation from: ### 📊 Recommendation: **BUY**
                parts = line.split('**')
                if len(parts) >= 3:
                    metrics['recommendation'] = parts[1].strip()
            elif line.startswith('**Confidence:**') and '**' in line:
                # Extract confidence from: **Confidence:** **HIGH**
                parts = line.split('**')
                if len(parts) >= 5:
                    metrics['confidence'] = parts[3].strip()
            elif line.startswith('**Trading Score:**') and '**' in line:
                # Extract score from: **Trading Score:** **100/100**
                parts = line.split('**')
                if len(parts) >= 5:
                    score_text = parts[3].strip()
                    metrics['score'] = int(score_text.split('/')[0]) if '/' in score_text else 0
            elif line.startswith('**Risk Score:**') and '**' in line:
                # Extract risk score from: **Risk Score:** **0/100**
                parts = line.split('**')
                if len(parts) >= 5:
                    risk_text = parts[3].strip()
                    metrics['risk_score'] = int(risk_text.split('/')[0]) if '/' in risk_text else 0
            elif line.startswith('**Position Size:**') and '**' in line:
                # Extract position size from: **Position Size:** **LARGE**
                parts = line.split('**')
                if len(parts) >= 5:
                    metrics['position_size'] = parts[3].strip()

        # Print summary
        print(f"📊 DECISION SUMMARY:")
        print(f"   Recommendation: {metrics.get('recommendation', 'N/A')}")
        print(f"   Confidence: {metrics.get('confidence', 'N/A')}")
        print(f"   Trading Score: {metrics.get('score', 'N/A')}/100")
        print(f"   Risk Score: {metrics.get('risk_score', 'N/A')}/100")
        print(f"   Position Size: {metrics.get('position_size', 'N/A')}")

        # Print first 500 chars of full result
        print(f"\n📝 FULL DECISION OUTPUT (first 500 chars):")
        print("-" * 50)
        print(result[:500] + ("..." if len(result) > 500 else ""))

        return metrics

    except Exception as e:
        print(f"❌ Error making decision: {str(e)}")
        return None


def analyze_decision_patterns(results):
    """Analyze patterns across all decision results"""

    print(f"\n{'='*80}")
    print(f"📊 DECISION PATTERN ANALYSIS")
    print(f"{'='*80}")

    # Expected patterns for validation
    expected_patterns = {
        "high_quality_buy": {
            "recommendation": "BUY",
            "confidence": ["HIGH"],
            "score_range": (75, 100),
            "risk_range": (0, 25)
        },
        "moderate_quality_buy": {
            "recommendation": "BUY",
            "confidence": ["MEDIUM", "HIGH"],
            "score_range": (60, 80),
            "risk_range": (20, 40)
        },
        "poor_quality_avoid": {
            "recommendation": "AVOID",
            "confidence": ["HIGH", "MEDIUM"],
            "score_range": (0, 30),
            "risk_range": (70, 100)
        },
        "neutral_hold": {
            "recommendation": "HOLD",
            "confidence": ["MEDIUM", "LOW"],
            "score_range": (40, 60),
            "risk_range": (30, 60)
        },
        "edge_case_missing_data": {
            "recommendation": ["HOLD", "AVOID"],
            "confidence": ["LOW"],
            "score_range": (0, 50),
            "risk_range": (50, 100)
        }
    }

    print(f"\n✅ VALIDATION RESULTS:")
    print("-" * 40)

    all_passed = True

    for test_name, metrics in results.items():
        if metrics is None:
            print(f"❌ {test_name}: Failed to execute")
            all_passed = False
            continue

        expected = expected_patterns.get(test_name, {})
        passed = True
        issues = []

        # Check recommendation
        exp_rec = expected.get('recommendation')
        if isinstance(exp_rec, list):
            if metrics.get('recommendation') not in exp_rec:
                issues.append(f"recommendation should be in {exp_rec}")
                passed = False
        elif exp_rec and metrics.get('recommendation') != exp_rec:
            issues.append(f"recommendation should be {exp_rec}")
            passed = False

        # Check confidence
        exp_conf = expected.get('confidence', [])
        if exp_conf and metrics.get('confidence') not in exp_conf:
            issues.append(f"confidence should be in {exp_conf}")
            passed = False

        # Check score range
        score_range = expected.get('score_range')
        if score_range and metrics.get('score'):
            score = metrics['score']
            if not (score_range[0] <= score <= score_range[1]):
                issues.append(f"score {score} outside range {score_range}")
                passed = False

        # Check risk range
        risk_range = expected.get('risk_range')
        if risk_range and metrics.get('risk_score'):
            risk = metrics['risk_score']
            if not (risk_range[0] <= risk <= risk_range[1]):
                issues.append(f"risk {risk} outside range {risk_range}")
                passed = False

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")

        if issues:
            for issue in issues:
                print(f"     - {issue}")

        if not passed:
            all_passed = False

    print(f"\n{'🎉 ALL TESTS PASSED' if all_passed else '⚠️  SOME TESTS FAILED'}")

    # Print recommendations for improvement
    if not all_passed:
        print(f"\n💡 IMPROVEMENT RECOMMENDATIONS:")
        print("- Review scoring algorithm for edge cases")
        print("- Adjust confidence thresholds based on data quality")
        print("- Fine-tune risk assessment for missing data scenarios")
        print("- Consider narrative weighting adjustments")


def check_environment():
    """Check if required environment variables are set"""

    required_vars = ["OPENAI_API_KEY", "XAI_API_KEY"]

    print("🔧 Environment Check:")
    print("-" * 25)

    all_good = True
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"❌ {var} (Required)")
            all_good = False

    return all_good


def main():
    """Run the isolated MakeTradingDecision test suite"""

    print("🧪 MakeTradingDecision Isolated Test Suite")
    print("=" * 80)
    print("Testing decision quality across various narrative scenarios")
    print("=" * 80)

    if not check_environment():
        print("\n❌ Missing required environment variables")
        return

    # Get test narratives
    narratives = create_test_narratives()
    results = {}

    # Test each narrative
    for name, content in narratives.items():
        try:
            metrics = test_decision_quality(name, content)
            results[name] = metrics
        except KeyboardInterrupt:
            print("\n⚠️  Test interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Test failed for {name}: {str(e)}")
            results[name] = None

    # Analyze patterns
    if results:
        analyze_decision_patterns(results)

    print(f"\n📚 TEST COMPLETE")
    print("-" * 40)
    print("This test evaluates how well MakeTradingDecision assesses")
    print("information from the grok narration agent across different")
    print("token quality and risk scenarios.")


if __name__ == "__main__":
    main()