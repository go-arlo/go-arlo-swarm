import re
from agency_swarm.tools import BaseTool
from pydantic import Field


class GenerateComprehensiveNarration(BaseTool):
    """
    Prepare data for narrative generation based on ALL available data:
    - Pre-fetched market data from BirdEye
    - Pre-fetched holder data from Moralis
    - Sentiment analysis from the sentiment agent

    The agent will generate the actual narrative sections based on the formatted prompt.
    """

    message_content: str = Field(
        ...,
        description="Full message content containing market data, holder data, and context",
    )

    def run(self) -> str:
        """Prepare comprehensive data for narrative generation by the agent"""

        print("📝 Preparing data for comprehensive narrative generation...")

        # Extract data from the message content
        extracted_data = self._extract_data_from_message(self.message_content)

        if not any([
            extracted_data.get("market_data"),
            extracted_data.get("holder_data"),
            extracted_data.get("sentiment_data"),
        ]):
            return "Error: Insufficient data for narrative generation. No market, holder, or sentiment data found."

        # Format data for agent analysis
        data_summary = self._format_data_for_prompt(extracted_data)

        # Get chain type for conditional prompt
        chain = extracted_data.get("token_info", {}).get("chain", "").lower()

        # Create conditional prompt based on chain type
        if chain == "solana":
            narrative_prompt = self._create_solana_prompt(data_summary)
        else:
            narrative_prompt = self._create_non_solana_prompt(data_summary, chain)

        return narrative_prompt

    def _create_solana_prompt(self, data_summary: str) -> str:
        """Create prompt for Solana tokens with bundling analysis"""
        return f"""
⚠️ ABSOLUTELY CRITICAL RULES - VIOLATIONS WILL INVALIDATE RESPONSE:
1. NEVER include character counts like "(248 chars)" in ANY section
2. NEVER mention confidence scores like "0.8 confidence" or any numeric confidence
3. NEVER repeat price, market cap, or FDV that are already shown in the header

Please generate professional narrative sections based on the following comprehensive token data:

{data_summary}

🚨 CRITICAL SOLANA BUNDLING RULES 🚨:
- Use bundling analysis with provided risk levels
- Use the exact current_impact_risk level provided (LOW/MEDIUM/HIGH/CRITICAL)
- Focus on what bundling analysis means for investors

Generate exactly 5 narrative sections with the following specifications:

1. MARKET OVERVIEW (max 500 chars):
- NEVER repeat price, market cap, or FDV numbers (already shown above)
- Focus ONLY on volume trends, market health, and trading patterns
- Analyze what the metrics mean for trading momentum
- Reference pressure dynamics, volatility, and liquidity implications

2. TOKEN SAFETY (max 500 chars):
- Contract control status (renounced/not renounced)
- Holder restrictions (taxes, blacklists, transfer limitations)
- Security analysis (honeypot, open source, verification status)
- Overall safety assessment with clear status indicators
- Chain-specific features (Jupiter verification for Solana)

3. HOLDER INSIGHTS (max 500 chars):
- Distribution patterns and concentration
- Holder count and growth trends
- Concentration risk assessment
- If no holder data available, acknowledge limitation briefly

4. RISK ASSESSMENT (max 500 chars):
- For Solana tokens: Use the exact current_impact_risk level provided (LOW/MEDIUM/HIGH/CRITICAL)
- Combine bundling risk with market health, holder concentration, volatility
- Focus on what the risks mean for investors, not technical details
- Provide actionable guidance based on the combined risk factors
- Avoid listing cluster details - summarize the overall risk impact

5. SOCIAL & TRENDS (max 500 chars):
- Sentiment analysis results
- Trending topics and community discussion
- Social volume assessment

REQUIREMENTS:
- Use only factual data provided
- Keep each section under 500 characters
- Professional, analytical tone
- No speculation beyond data
- Actionable insights where possible
- DO NOT mention data sources or APIs (BirdEye, Moralis, etc.)
- When using numbers, use them EXACTLY as provided - never round or approximate
- Focus on user-friendly risk assessment rather than technical details
- Avoid contradictory statements between metrics
- NO FLUFF LANGUAGE: Avoid phrases like "balanced but cautious", "notable participation"
- Be SPECIFIC: "Large trades indicate whale activity" not "notable participation"
- Only state what data directly supports - don't infer community health from holder counts

Format your response as exactly 5 sections with these headers:
### Market Overview
### Token Safety
### Holder Insights
### Risk Assessment
### Social & Trends

DO NOT include character counts like "(312 chars)" at the end of sections.
DO NOT include token symbols or prices in the narrative text.

EXAMPLES:

GOOD Token Safety (Solana):
"Contract ownership fully renounced reducing manipulation risk. No transfer restrictions or freeze authority detected. Jupiter strict list verified enhancing credibility. Metadata mutable but issuance control removed. Overall: POSITIVE safety profile."

GOOD Risk Assessment (Solana):
"LOW bundling risk with minimal coordination detected. GOOD 24h market health shows declining volume but balanced pressure. Moderate holder concentration creates some manipulation risk. Overall: proceed cautiously, monitor for volume recovery."

GOOD Market Overview:
"Volume down 30.8% signals declining interest despite GOOD market health. Slight sell pressure but balanced at 52% sells vs 48% buys. High trading activity per period with low 3.2% volatility indicates price stability. Liquidity sufficient for current volume levels."

GOOD Holder Insights:
"18,655 holders with 22.0% top-10 concentration creates moderate whale risk. Distribution better than many tokens but concentrated enough for potential manipulation. No recent holder growth data available."

GOOD Social & Trends:
"Bullish sentiment dominates community discussions highlighting innovation potential. Medium social volume with AI-crypto hype as key driver. Some concerns about volatility but no scam flags detected. Top trend: accumulation by major wallets."
"""

    def _create_non_solana_prompt(self, data_summary: str, chain: str) -> str:
        """Create prompt for non-Solana tokens without bundling mentions"""
        return f"""
⚠️ ABSOLUTELY CRITICAL RULES - VIOLATIONS WILL INVALIDATE RESPONSE:
1. NEVER include character counts like "(248 chars)" in ANY section
2. NEVER mention confidence scores like "0.8 confidence" or any numeric confidence
3. NEVER repeat price, market cap, or FDV that are already shown in the header
4. ABSOLUTELY NO MENTION OF: bundling, bundles, bundle analysis, launch patterns, chain limitations

Please generate professional narrative sections based on the following comprehensive token data:

{data_summary}

🚨 CRITICAL NON-SOLANA CHAIN RULES ({chain.upper()}) 🚨:
- ABSOLUTELY NO MENTION OF: bundling, bundles, bundle analysis, launch patterns
- NEVER write: "UNKNOWN bundling risk", "bundling unavailable", "chain limitations"
- Focus ONLY on: market health + holder concentration + volatility + liquidity

Generate exactly 5 narrative sections with the following specifications:

1. MARKET OVERVIEW (max 500 chars):
- NEVER repeat price, market cap, or FDV numbers (already shown above)
- Focus ONLY on volume trends, market health, and trading patterns
- Analyze what the metrics mean for trading momentum
- Reference pressure dynamics, volatility, and liquidity implications

2. TOKEN SAFETY (max 500 chars):
- Contract control status (renounced/not renounced)
- Holder restrictions (taxes, blacklists, transfer limitations)
- Security analysis (honeypot, open source, verification status)
- Overall safety assessment with clear status indicators
- Chain-specific features (proxy contracts, locked liquidity)

3. HOLDER INSIGHTS (max 500 chars):
- Distribution patterns and concentration
- Holder count and growth trends
- Concentration risk assessment
- If no holder data available, acknowledge limitation briefly

4. RISK ASSESSMENT (max 500 chars):
- ABSOLUTELY NO MENTION OF: bundling, bundles, bundle analysis, launch patterns
- START with market health status
- THEN discuss holder concentration risk
- THEN discuss volatility/liquidity risks
- Combine available risk factors into coherent risk assessment
- Focus on what the risks mean for investors
- Provide actionable guidance based on the combined risk factors

5. SOCIAL & TRENDS (max 500 chars):
- Sentiment analysis results
- Trending topics and community discussion
- Social volume assessment

REQUIREMENTS:
- Use only factual data provided
- Keep each section under 500 characters
- Professional, analytical tone
- No speculation beyond data
- Actionable insights where possible
- DO NOT mention data sources or APIs (BirdEye, Moralis, etc.)
- When using numbers, use them EXACTLY as provided - never round or approximate
- Focus on user-friendly risk assessment rather than technical details
- Avoid contradictory statements between metrics
- NO FLUFF LANGUAGE: Avoid phrases like "balanced but cautious", "notable participation"
- Be SPECIFIC: "Large trades indicate whale activity" not "notable participation"
- Only state what data directly supports - don't infer community health from holder counts

Format your response as exactly 5 sections with these headers:
### Market Overview
### Token Safety
### Holder Insights
### Risk Assessment
### Social & Trends

DO NOT include character counts like "(312 chars)" at the end of sections.
DO NOT include token symbols or prices in the narrative text.

EXAMPLES:

GOOD Token Safety ({chain.upper()}):
"Contract ownership fully renounced eliminating manipulation risk. No buy/sell taxes or transfer restrictions detected. Open source contract verified on block explorer. Majority liquidity locked reducing rug pull risk. Overall: POSITIVE safety profile with minimal concerns."

GOOD Risk Assessment ({chain.upper()}):
"GOOD 24h market health with balanced buy/sell pressure despite declining volume. Moderate 22% holder concentration creates manipulation risk from whales. Low volatility aids stability. Combined risk: medium due to whale concentration. Monitor volume recovery and watch for large holder movements before major positions."

GOOD Market Overview:
"Volume down 30.8% signals declining interest despite GOOD market health. Slight sell pressure but balanced at 52% sells vs 48% buys. High trading activity per period with low 3.2% volatility indicates price stability. Liquidity sufficient for current volume levels."

GOOD Holder Insights:
"18,655 holders with 22.0% top-10 concentration creates moderate whale risk. Distribution better than many tokens but concentrated enough for potential manipulation. No recent holder growth data available."

GOOD Social & Trends:
"Bullish sentiment dominates community discussions highlighting innovation potential. Medium social volume with AI-crypto hype as key driver. Some concerns about volatility but no scam flags detected. Top trend: accumulation by major wallets."

FORBIDDEN EXAMPLES FOR {chain.upper()}:
❌ "UNKNOWN bundling risk on {chain} chain..." (NEVER write this)
❌ "Bundle analysis unavailable..." (NEVER write this)
❌ "Cannot assess launch patterns..." (NEVER write this)
❌ "Chain limitations prevent..." (NEVER write this)
"""

    def _extract_data_from_message(self, message: str) -> dict:
        """Extract structured data from the message content"""

        extracted = {
            "token_info": {},
            "market_data": {},
            "holder_data": {},
            "sentiment_data": {},
            "bundler_data": {},
            "market_health_24h": {},
            "safety_analysis": {},
        }

        try:
            # Extract token info
            token_match = re.search(r"Token:\s*([^(]+)\s*\(([^)]+)\)", message)
            if token_match:
                extracted["token_info"]["name"] = token_match.group(1).strip()
                extracted["token_info"]["symbol"] = token_match.group(2).strip()

            chain_match = re.search(r"Chain:\s*(\w+)", message)
            if chain_match:
                extracted["token_info"]["chain"] = chain_match.group(1)

            # Extract market data
            price_match = re.search(r"Price:\s*\$([0-9.,]+)", message)
            if price_match:
                extracted["market_data"]["price_usd"] = price_match.group(1)

            fdv_match = re.search(r"FDV:\s*\$([0-9.,]+)", message)
            if fdv_match:
                extracted["market_data"]["fdv_usd"] = fdv_match.group(1)

            volume_match = re.search(r"24h Volume:\s*\$([0-9.,]+)", message)
            if volume_match:
                extracted["market_data"]["volume_24h_usd"] = volume_match.group(1)

            liquidity_match = re.search(r"Liquidity:\s*\$([0-9.,]+)", message)
            if liquidity_match:
                extracted["market_data"]["liquidity_usd"] = liquidity_match.group(1)

            market_cap_match = re.search(r"Market Cap:\s*\$([0-9.,]+)", message)
            if market_cap_match:
                extracted["market_data"]["market_cap_usd"] = market_cap_match.group(1)

            # Extract holder data
            holders_match = re.search(r"Total Holders:\s*([0-9,]+)", message)
            if holders_match:
                extracted["holder_data"]["total_holders"] = holders_match.group(1)

            concentration_match = re.search(
                r"Top 10 Concentration:\s*([0-9.]+)%", message
            )
            if concentration_match:
                extracted["holder_data"]["concentration"] = concentration_match.group(1)

            # Look for sentiment data in delegation messages
            if "sentiment" in message.lower():
                sentiment_match = re.search(r"(Bullish|Neutral|Bearish)", message)
                if sentiment_match:
                    extracted["sentiment_data"]["label"] = sentiment_match.group(1)

                confidence_match = re.search(r"confidence:\s*([0-9.]+)", message)
                if confidence_match:
                    extracted["sentiment_data"]["confidence"] = confidence_match.group(1)

            # Extract bundler analysis data (Solana only)
            if "BUNDLER ANALYSIS" in message or "bundler_analysis" in message:
                # Extract bundle detection status
                if "BUNDLED DETECTED" in message or "bundled_detected: True" in message:
                    extracted["bundler_data"]["detected"] = True
                    extracted["bundler_data"]["status"] = "DETECTED"
                elif "NO BUNDLES DETECTED" in message or "bundled_detected: False" in message:
                    extracted["bundler_data"]["detected"] = False
                    extracted["bundler_data"]["status"] = "NONE"
                elif "ANALYSIS FAILED" in message:
                    extracted["bundler_data"]["detected"] = False
                    extracted["bundler_data"]["status"] = "FAILED"

                # Extract present impact risk
                impact_match = re.search(r"current_impact_risk:\s*(CRITICAL|HIGH|MEDIUM|LOW)", message)
                if impact_match:
                    extracted["bundler_data"]["impact_risk"] = impact_match.group(1)

                # Extract risk metrics
                intensity_match = re.search(r"bundle_intensity_score:\s*([0-9.]+)", message)
                if intensity_match:
                    extracted["bundler_data"]["intensity_score"] = intensity_match.group(1)

                dominance_match = re.search(r"early_trading_dominance:\s*([0-9.]+)", message)
                if dominance_match:
                    extracted["bundler_data"]["early_dominance"] = dominance_match.group(1)

                # Extract price action analysis
                selloff_match = re.search(r"selloff_severity:\s*(SEVERE|MODERATE|MILD|NONE)", message)
                if selloff_match:
                    extracted["bundler_data"]["selloff_severity"] = selloff_match.group(1)

                decline_match = re.search(r"price_decline_from_peak_pct:\s*([0-9.]+)", message)
                if decline_match:
                    extracted["bundler_data"]["price_decline_pct"] = decline_match.group(1)

                # Extract cluster count
                cluster_match = re.search(r"bundle_cluster_count:\s*([0-9]+)", message)
                if not cluster_match:
                    cluster_match = re.search(r"Number of Bundle Clusters:\s*([0-9]+)", message)
                if cluster_match:
                    extracted["bundler_data"]["cluster_count"] = cluster_match.group(1)

                # Extract creation time
                creation_match = re.search(r"Creation Time:\s*([^\n]+)", message)
                if creation_match:
                    extracted["bundler_data"]["creation_time"] = creation_match.group(1).strip()

                # Extract cluster details
                cluster_details = []
                cluster_pattern = r"Cluster\s+(\d+):\s*(\d+)\s*txs,\s*(\d+)\s*wallets"
                for match in re.finditer(cluster_pattern, message):
                    cluster_details.append({
                        "number": match.group(1),
                        "txs": match.group(2),
                        "wallets": match.group(3)
                    })
                if cluster_details:
                    extracted["bundler_data"]["clusters"] = cluster_details[:5]  # Keep top 5

            # Extract 24h market health data
            if "24H MARKET HEALTH" in message or "market_health_24h" in message:
                # Extract market health rating
                health_match = re.search(r"market_health:\s*(EXCELLENT|GOOD|FAIR|LOW)", message)
                if health_match:
                    extracted["market_health_24h"]["health"] = health_match.group(1)

                # Extract buy/sell pressure
                buy_pressure_match = re.search(r"buy_pressure_pct:\s*([0-9.]+)", message)
                if buy_pressure_match:
                    extracted["market_health_24h"]["buy_pressure"] = buy_pressure_match.group(1)

                sell_pressure_match = re.search(r"sell_pressure_pct:\s*([0-9.]+)", message)
                if sell_pressure_match:
                    extracted["market_health_24h"]["sell_pressure"] = sell_pressure_match.group(1)

                # Extract pressure dominance
                dominance_match = re.search(r"pressure_dominance:\s*(STRONG_BUY|BUY|NEUTRAL|SELL|STRONG_SELL)", message)
                if dominance_match:
                    extracted["market_health_24h"]["dominance"] = dominance_match.group(1)

                # Extract volume change
                volume_change_match = re.search(r"volume_change_pct:\s*([+-]?[0-9.]+)", message)
                if volume_change_match:
                    extracted["market_health_24h"]["volume_change"] = volume_change_match.group(1)

                # Extract volatility
                volatility_match = re.search(r"avg_volatility_pct:\s*([0-9.]+)", message)
                if volatility_match:
                    extracted["market_health_24h"]["volatility"] = volatility_match.group(1)

            # Extract token safety analysis data
            if "TOKEN SAFETY ANALYSIS" in message:
                # Extract overall risk level
                risk_match = re.search(r"Overall Risk Level:\s*(HIGH|MEDIUM|LOW|UNKNOWN)", message)
                if risk_match:
                    extracted["safety_analysis"]["overall_risk"] = risk_match.group(1)

                # Extract contract control status
                contract_match = re.search(r"Contract Control:\s*(POSITIVE|NEGATIVE|NEUTRAL|UNKNOWN)\s*-\s*([^\\n]+)", message)
                if contract_match:
                    extracted["safety_analysis"]["contract_control"] = {
                        "status": contract_match.group(1),
                        "reason": contract_match.group(2).strip()
                    }

                # Extract holder control status
                holder_match = re.search(r"Holder Control:\s*(POSITIVE|NEGATIVE|NEUTRAL|UNKNOWN)\s*-\s*([^\\n]+)", message)
                if holder_match:
                    extracted["safety_analysis"]["holder_control"] = {
                        "status": holder_match.group(1),
                        "reason": holder_match.group(2).strip()
                    }

        except Exception as e:
            print(f"Warning: Error extracting data from message: {str(e)}")

        return extracted

    def _format_data_for_prompt(self, extracted_data: dict) -> str:
        """Format extracted data for the agent prompt"""

        sections = []

        # Token info
        if extracted_data["token_info"]:
            sections.append("TOKEN INFO:")
            for key, value in extracted_data["token_info"].items():
                sections.append(f"- {key.title()}: {value}")

            # Explicitly highlight chain for safety notes logic
            chain = extracted_data["token_info"].get("chain", "").lower()
            if chain:
                if chain == 'solana':
                    sections.append(f"- ⚠️  CHAIN TYPE: SOLANA - BUNDLING RULES APPLY")
                else:
                    sections.append(f"- ⚠️  CHAIN TYPE: {chain.upper()} - ABSOLUTELY NO BUNDLING MENTIONS ALLOWED")
                    sections.append(f"- ⚠️  FORBIDDEN: Never write 'UNKNOWN bundling risk' for {chain.upper()}")

        # Market data
        if extracted_data["market_data"]:
            sections.append("\nMARKET DATA:")
            for key, value in extracted_data["market_data"].items():
                sections.append(f"- {key.replace('_', ' ').title()}: ${value}")

        # Holder data
        if extracted_data["holder_data"]:
            sections.append("\nHOLDER DATA:")
            for key, value in extracted_data["holder_data"].items():
                sections.append(f"- {key.replace('_', ' ').title()}: {value}")

        # Sentiment data
        if extracted_data["sentiment_data"]:
            sections.append("\nSENTIMENT DATA:")
            for key, value in extracted_data["sentiment_data"].items():
                sections.append(f"- {key.replace('_', ' ').title()}: {value}")

        # Bundler data (Solana only)
        if extracted_data["bundler_data"]:
            sections.append("\nBUNDLER ANALYSIS (Solana):")
            bundler = extracted_data["bundler_data"]

            if bundler.get("status"):
                sections.append(f"- Detection Status: {bundler['status']}")

            if bundler.get("impact_risk"):
                sections.append(f"- Current Impact Risk: {bundler['impact_risk']}")

            if bundler.get("intensity_score"):
                sections.append(f"- Bundle Intensity: {bundler['intensity_score']}/100")

            if bundler.get("early_dominance"):
                sections.append(f"- Early Trading Dominance: {bundler['early_dominance']}%")

            if bundler.get("selloff_severity"):
                sections.append(f"- Price Action Selloff: {bundler['selloff_severity']}")

            if bundler.get("price_decline_pct"):
                sections.append(f"- Decline from Peak: {bundler['price_decline_pct']}%")

            if bundler.get("cluster_count"):
                sections.append(f"- Bundle Clusters: {bundler['cluster_count']}")

            if bundler.get("creation_time"):
                sections.append(f"- Token Created: {bundler['creation_time']}")

            # Add cluster details
            if bundler.get("clusters"):
                sections.append("- Top Bundle Clusters:")
                for cluster in bundler["clusters"][:3]:  # Show top 3
                    sections.append(f"  • Cluster {cluster['number']}: {cluster['txs']} txs, {cluster['wallets']} wallets")

        # 24h Market Health data
        if extracted_data["market_health_24h"]:
            sections.append("\n24H MARKET HEALTH:")
            health = extracted_data["market_health_24h"]

            if health.get("health"):
                sections.append(f"- Overall Health: {health['health']}")

            if health.get("dominance"):
                sections.append(f"- Pressure Dominance: {health['dominance']}")

            if health.get("buy_pressure") and health.get("sell_pressure"):
                sections.append(f"- Buy/Sell Pressure: {health['buy_pressure']}% / {health['sell_pressure']}%")

            if health.get("volume_change"):
                sections.append(f"- Volume Change: {health['volume_change']}%")

            if health.get("volatility"):
                sections.append(f"- Avg Volatility: {health['volatility']}%")

        # Token Safety Analysis data
        if extracted_data["safety_analysis"]:
            sections.append("\nTOKEN SAFETY ANALYSIS:")
            safety = extracted_data["safety_analysis"]
            if safety.get("overall_risk"):
                sections.append(f"- Overall Risk Level: {safety['overall_risk']}")
            if safety.get("contract_control"):
                control = safety["contract_control"]
                sections.append(f"- Contract Control: {control['status']} - {control['reason']}")
            if safety.get("holder_control"):
                holder = safety["holder_control"]
                sections.append(f"- Holder Control: {holder['status']} - {holder['reason']}")

        return "\n".join(sections) if sections else "No structured data available."