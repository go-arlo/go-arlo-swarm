from agency_swarm.tools import BaseTool
from pydantic import Field
from typing import Dict, Any, Optional
import re


class Summary(BaseTool):
    """
    Tool for generating a comprehensive summary of token analysis based on all collected data.
    Combines insights from token safety, market position, social sentiment, and holder analysis
    to provide a holistic assessment with original insights.
    """

    token_safety: Dict[str, Any] = Field(
        ...,
        description="Token safety analysis data including assessment, summary, and key points"
    )
    
    market_position: Dict[str, Any] = Field(
        ...,
        description="Market position analysis data including assessment, summary, and key points"
    )
    
    social_sentiment: Dict[str, Any] = Field(
        ...,
        description="Social sentiment analysis data including assessment, summary, and key points"
    )
    
    holder_analysis: Dict[str, Any] = Field(
        ...,
        description="Holder analysis data including assessment, summary, and key points"
    )
    
    final_score: float = Field(
        ...,
        description="The final weighted score for the token (0-100)"
    )
    
    token_ticker: str = Field(
        ...,
        description="The token ticker symbol"
    )

    def __init__(self, **data):
        if "token_safety" not in data:
            print(f"ERROR: token_safety is missing from Summary tool parameters!")
            print(f"Provided parameters: {data.keys()}")
        
        super().__init__(**data)

    def run(self) -> Dict[str, Any]:
        """
        Generate a concise, insightful summary based on all analysis components.
        Returns a formatted summary with an original overall assessment.
        """
        try:
            if len(self.token_ticker) > 20 or not self.token_ticker.replace('_', '').replace('-', '').isalnum():
                print(f"WARNING: token_ticker appears to be a contract address: {self.token_ticker}")
                if len(self.token_ticker) > 20:
                    self.token_ticker = f"TOKEN_{self.token_ticker[:6]}..."
                    print(f"Using simplified ticker: {self.token_ticker}")
            else:
                print(f"Using ticker: {self.token_ticker}")
            
            if not isinstance(self.token_safety, dict):
                print(f"Warning: token_safety is not a dictionary: {type(self.token_safety)}")
                self.token_safety = {}
            if not isinstance(self.market_position, dict):
                print(f"Warning: market_position is not a dictionary: {type(self.market_position)}")
                self.market_position = {}
            if not isinstance(self.social_sentiment, dict):
                print(f"Warning: social_sentiment is not a dictionary: {type(self.social_sentiment)}")
                self.social_sentiment = {}
            if not isinstance(self.holder_analysis, dict):
                print(f"Warning: holder_analysis is not a dictionary: {type(self.holder_analysis)}")
                self.holder_analysis = {}
            
            if not isinstance(self.final_score, (int, float)):
                try:
                    self.final_score = float(self.final_score)
                    print(f"Converted final_score from {type(self.final_score)} to float: {self.final_score}")
                except (ValueError, TypeError):
                    print(f"Error converting final_score to float: {self.final_score}, using default 50.0")
                    self.final_score = 50.0
            
            if self.final_score < 0 or self.final_score > 100:
                print(f"Warning: final_score {self.final_score} is outside of range 0-100, clamping")
                self.final_score = max(0, min(self.final_score, 100))
                
            safety_assessment = self.token_safety.get("assessment", "neutral")
            market_assessment = self.market_position.get("assessment", "neutral")
            sentiment_assessment = self.social_sentiment.get("assessment", "neutral")
            holder_assessment = self.holder_analysis.get("assessment", "neutral")
            
            safety_points = self.token_safety.get("key_points", [])
            market_points = self.market_position.get("key_points", [])
            sentiment_points = self.social_sentiment.get("key_points", [])
            holder_points = self.holder_analysis.get("key_points", [])
            
            assessments = [safety_assessment, market_assessment, sentiment_assessment, holder_assessment]
            positive_count = assessments.count("positive")
            negative_count = assessments.count("negative")
            neutral_count = assessments.count("neutral")
            
            score_percent = int(self.final_score)
            
            overall_sentiment = self._determine_overall_sentiment(positive_count, negative_count, neutral_count, self.final_score)
            
            strengths = self._identify_strengths(safety_points, market_points, sentiment_points, holder_points)
            concerns = self._identify_concerns(safety_points, market_points, sentiment_points, holder_points)
            
            conclusion = self._generate_actionable_conclusion(overall_sentiment, score_percent, self.token_ticker, strengths, concerns)
            
            market_insights = self._generate_market_liquidity_paragraph(strengths, concerns, market_points)
            social_insights = self._generate_social_paragraph(strengths, concerns, sentiment_points)
            security_holder_insights = self._generate_security_holder_paragraph(strengths, concerns, safety_points, holder_points)
            
            full_summary = f"{conclusion}\n\n"
            
            full_summary += "Key Insights:\n"
            if market_insights:
                full_summary += f"{market_insights}\n\n"
            if social_insights:
                full_summary += f"{social_insights}\n\n"
            if security_holder_insights:
                full_summary += f"{security_holder_insights}"
            
            if len(full_summary) > 4000:
                full_summary = full_summary[:3980] + "... (truncated)"
                print(f"Truncated summary to 4000 characters in Summary tool")
            
            return {
                "summary": full_summary,
                "overall_sentiment": overall_sentiment
            }
            
        except Exception as e:
            import traceback
            print(f"Error in Summary tool: {str(e)}")
            print(traceback.format_exc())
            default_summary = f"${self.token_ticker} has received a {int(self.final_score)}% rating based on our analysis."
            return {
                "summary": default_summary,
                "overall_sentiment": "neutral",
                "error": str(e)
            }
    
    def _determine_overall_sentiment(self, positive_count, negative_count, neutral_count, score):
        """Determine overall sentiment based on component assessments and score"""
        if score >= 80:
            return "very positive"
        elif score >= 70:
            return "positive"
        elif score >= 60:
            return "cautiously positive"
        elif score >= 50:
            return "neutral"
        elif score >= 40:
            return "cautious"
        elif score >= 30:
            return "concerning"
        else:
            return "negative"
    
    def _identify_strengths(self, safety_points, market_points, sentiment_points, holder_points):
        """Extract key strengths from all analysis points"""
        strengths = []
        
        strength_terms = []
        
        for point in safety_points:
            if any(term in point.lower() for term in ["renounced", "secure", "audit", "verified", "safe"]):
                if "risk" not in point.lower() and "concern" not in point.lower():
                    strengths.append(f"Security: {point}")
                    for term in ["renounced", "secure", "audit", "verified", "safe"]:
                        if term in point.lower():
                            strength_terms.append(term)
        
        for point in market_points:
            if "strong liquidity" in point.lower() or "indicates strong liquidity" in point.lower():
                strengths.append(f"Market: {point}")
                strength_terms.append("strong liquidity")
            elif any(term in point.lower() for term in ["increas", "growth", "bull", "uptrend", "momentum", "depth"]):
                if "limited" not in point.lower() and "low" not in point.lower() and "concern" not in point.lower():
                    strengths.append(f"Market: {point}")
                    for term in ["increas", "growth", "bull", "uptrend", "momentum", "depth"]:
                        if term in point.lower():
                            strength_terms.append(term)
        
        for point in sentiment_points:
            if any(term in point.lower() for term in ["positive", "strong", "engage", "growing", "community"]):
                if "low" not in point.lower() and "limited" not in point.lower() and "weak" not in point.lower():
                    strengths.append(f"Social: {point}")
                    for term in ["positive", "strong", "engage", "growing", "community"]:
                        if term in point.lower():
                            strength_terms.append(term)
        
        for point in holder_points:
            if any(term in point.lower() for term in ["well-balanced", "distribution", "retail", "balanced"]):
                if "highly concentrated" not in point.lower() and "risk" not in point.lower():
                    strengths.append(f"Distribution: {point}")
                    for term in ["well-balanced", "distribution", "retail", "balanced"]:
                        if term in point.lower():
                            strength_terms.append(term)
        
        return strengths
    
    def _identify_concerns(self, safety_points, market_points, sentiment_points, holder_points):
        """Extract key concerns from all analysis points"""
        concerns = []
        
        for point in safety_points:
            if any(term in point.lower() for term in ["risk", "vulnerab", "centralized", "concern", "issue"]):
                concerns.append(f"Security: {point}")
        
        for point in market_points:
            if any(term in point.lower() for term in ["limited liquidity", "overbought", "price impact", "decrease", "downtrend", "warning"]):
                concerns.append(f"Market: {point}")
        
        for point in sentiment_points:
            if any(term in point.lower() for term in ["warning", "negative", "fake", "scam", "concern", "weak"]):
                concerns.append(f"Social: {point}")
        
        for point in holder_points:
            if any(term in point.lower() for term in ["highly concentrated", "whale", "risk", "centralized"]):
                concerns.append(f"Distribution: {point}")
        
        filtered_concerns = []
        for concern in concerns:
            is_duplicate = False
            for strength in self._identify_strengths(safety_points, market_points, sentiment_points, holder_points):
                if concern.split(": ", 1)[1] == strength.split(": ", 1)[1]:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_concerns.append(concern)
        
        return filtered_concerns
    
    def _generate_actionable_conclusion(self, overall_sentiment, score, ticker, strengths, concerns):
        """Generate an original, actionable conclusion - now used as the opening statement"""
        if overall_sentiment in ["very positive", "positive"]:
            strong_liquidity = any("liquidity" in s.lower() and "strong" in s.lower() for s in strengths)
            liquidity_concern = any("liquidity" in s.lower() and "limited" in s.lower() for s in concerns)
            
            if liquidity_concern:
                action = "Consider small position sizes due to liquidity constraints and monitor volume trends closely."
            elif strong_liquidity:
                action = "Take advantage of strong liquidity conditions while monitoring continued momentum."
            else:
                action = "Consider appropriate position sizing and monitor for continued momentum."
                
            outlook = "near-term upside potential"
                
        elif overall_sentiment in ["cautiously positive", "neutral"]:
            action = "Monitor key metrics closely before establishing significant positions."
            outlook = "balanced risk-reward profile"
            if any("momentum" in s.lower() for s in strengths):
                action = "Consider limited exposure with tight risk management and clear exit parameters."
                
        else:
            action = "Exercise significant caution and consider avoiding exposure until risk factors improve."
            outlook = "elevated risk profile"
            if any("distribution" in s.lower() for s in strengths):
                action = "If entering, use minimal position sizing with strict risk controls and short timeframes."
        
        conclusion = f"${ticker} presents a {score}% rating with {outlook}. {action}"
        
        if overall_sentiment in ["very positive", "positive"]:
            conclusion += f" The token shows potential for both short and medium-term positioning based on current metrics."
        elif overall_sentiment in ["cautiously positive"]:
            conclusion += f" Current conditions favor short-term tactical positioning rather than strategic holdings."
        else:
            conclusion += f" Current analysis suggests this token is primarily suitable for short-term tactical trading with appropriate risk controls."
            
        return conclusion
        
    def _generate_market_liquidity_paragraph(self, strengths, concerns, market_points):
        """Generate a paragraph focused on market and liquidity insights"""
        bundle_finding = next((point for point in self.market_position.get("key_points", []) if "bundle" in point.lower()), "")
        
        bundle_analysis = ""
        if "not a significant amount" in bundle_finding.lower():
            bundle_analysis = "Bundle trading activity on launch date was minimal, reducing concerns about coordinated manipulation or artificial price inflation."
        elif "%" in bundle_finding and any(risk in bundle_finding.upper() for risk in ["HIGH RISK", "VERY HIGH RISK", "CONSIDERABLE RISK", "MODERATE"]):
            risk_level = "HIGH RISK" if "HIGH RISK" in bundle_finding.upper() else "VERY HIGH RISK" if "VERY HIGH RISK" in bundle_finding.upper() else "CONSIDERABLE RISK" if "CONSIDERABLE RISK" in bundle_finding.upper() else "MODERATE"
            
            strong_liquidity = any("strong liquidity" in point.lower() for point in self.market_position.get("key_points", []))
            well_balanced_distribution = self.holder_analysis.get("concentration") == "well-balanced"
            
            if risk_level in ["HIGH RISK", "VERY HIGH RISK"]:
                bundle_analysis = f"Launch date bundle activity presents {risk_level.lower()} due to coordinated buying patterns. "
                if strong_liquidity and well_balanced_distribution:
                    bundle_analysis += "However, this risk is partially mitigated by strong current liquidity conditions and well-balanced holder distribution that has developed since launch."
                elif strong_liquidity:
                    bundle_analysis += "Strong liquidity conditions provide some mitigation, though holder concentration should be monitored."
                elif well_balanced_distribution:
                    bundle_analysis += "The well-balanced current holder distribution provides some mitigation of the initial coordination concerns."
                else:
                    bundle_analysis += "This risk remains elevated and requires careful consideration for position sizing."
            else:
                bundle_analysis = f"Launch date bundle activity shows {risk_level.lower()}, with current market conditions providing adequate mitigation through improved liquidity and distribution patterns."
        
        market_summary = self.market_position.get("summary", "")
        
        paragraphs = market_summary.split('\n\n')
        
        remaining_paragraphs = paragraphs[1:] if len(paragraphs) > 1 else []
        remaining_paragraphs = [p.strip() for p in remaining_paragraphs if p.strip()]
        remaining_summary = '\n\n'.join(remaining_paragraphs)
        
        if bundle_analysis and remaining_summary:
            return f"{bundle_analysis}\n\n{remaining_summary}"
        elif bundle_analysis:
            return bundle_analysis
        else:
            return remaining_summary or "Market analysis not available."
        
    def _generate_social_paragraph(self, strengths, concerns, sentiment_points):
        """Generate a paragraph focused on social sentiment insights"""
        social_insights = []
        
        high_follower_post = next((point for point in sentiment_points if "high-follower" in point.lower() and "@" in point), None)
        if high_follower_post:
            social_insights.append(f"Notable recent high-follower posts detected from {high_follower_post.split('(e.g. ')[1].split(')')[0] if '(e.g. ' in high_follower_post else 'significant engagement'}.")
        
        elif next((point for point in sentiment_points if "high-follower" in point.lower()), None) is None:
            mid_follower_post = next((point for point in sentiment_points if "mid-follower" in point.lower() and "@" in point), None)
            if mid_follower_post:
                social_insights.append(f"Recent active engagement through mid-follower posts with {mid_follower_post.split('(e.g. ')[1].split(')')[0] if '(e.g. ' in mid_follower_post else 'moderate engagement'}.")
        
        warning_tweet = next((point for point in sentiment_points if "warning:" in point.lower()), None)
        if warning_tweet:
            warning_detail = warning_tweet.split("WARNING: ")[1] if "WARNING: " in warning_tweet else warning_tweet
            social_insights.append(f"Warning signals detected including {warning_detail}.")
        
        warning_flags = any("warning" in s.lower() or "scam" in s.lower() or "fake" in s.lower() for s in sentiment_points)
        if warning_flags and not warning_tweet:
            social_insights.append("Warning signals detected in social channels suggest potential for manipulation or misleading information.")
        
        community_engagement_point = next((point for point in sentiment_points if "community engagement" in point.lower()), None)
        if community_engagement_point:
            if "strong" in community_engagement_point.lower():
                community_statement = "Community engagement is strong."
                social_insights.append(community_statement)
            elif "moderate" in community_engagement_point.lower():
                community_statement = "Community engagement is moderate."
                social_insights.append(community_statement)
            elif "limited" in community_engagement_point.lower() or "weak" in community_engagement_point.lower() or "low" in community_engagement_point.lower():
                community_statement = "Community engagement is limited."
                social_insights.append(community_statement)
            else:
                split_result = community_engagement_point.split('community', 1)
                if len(split_result) > 1 and split_result[1].strip():
                    community_statement = f"Community {split_result[1].strip()}."
                    social_insights.append(community_statement)
        
        social_presence_point = next((point for point in sentiment_points if "overall social presence" in point.lower()), None)
        if social_presence_point:
            split_result = social_presence_point.split('overall', 1)
            if len(split_result) > 1 and split_result[1].strip():
                presence_statement = f"Overall {split_result[1].strip()}."
                social_insights.append(presence_statement)
        
        limited_engagement = any("limited engagement" in s.lower() or "low engagement" in s.lower() for s in sentiment_points)
        if limited_engagement:
            social_insights.append("Limited social engagement indicates either low market awareness or cooling interest, presenting both risk and potential opportunity if traction increases.")
        
        negative_sentiment = any("negative sentiment" in p.lower() or "weak sentiment" in p.lower() for p in sentiment_points)
        if negative_sentiment:
            social_insights.append("Negative sentiment trends could suppress price appreciation in the near term.")
        
        community_strength = any("community" in s.lower() and "strong" in s.lower() for s in strengths)
        if community_strength:
            social_insights.append("Strong community foundation provides potential for sustained interest and organic growth.")
        
        if not social_insights:
            return "Social metrics show neutral sentiment with no significant positive or negative signals detected."
        
        return " ".join(social_insights)
        
    def _generate_security_holder_paragraph(self, strengths, concerns, safety_points, holder_points):
        """Generate a paragraph focused on security and holder distribution insights"""
        security_holder_insights = []
        
        ownership_renounced = any("ownership" in point.lower() and "renounced" in point.lower() and "not" not in point.lower() for point in safety_points)
        ownership_not_renounced = any("ownership" in point.lower() and "not" in point.lower() and "renounced" in point.lower() for point in safety_points)
        metadata_mutable = any("metadata" in point.lower() and "mutable" in point.lower() for point in safety_points)
        
        if metadata_mutable:
            security_holder_insights.append("Contract metadata remains mutable, which presents a potential risk despite ownership renunciation.")
        
        if ownership_renounced:
            if not metadata_mutable:
                security_holder_insights.append("Contract ownership renunciation reduces centralization risk and potential for malicious changes.")
            else:
                if not any("mutability" in insight for insight in security_holder_insights):
                    security_holder_insights.append("Contract ownership has been partially renounced, but metadata mutability presents a moderate risk.")
        elif ownership_not_renounced:
            security_holder_insights.append("Contract ownership has not been renounced, which presents potential centralization risk.")
        
        security_concerns = any("vulnerab" in s.lower() or "concern" in s.lower() for s in concerns)
        if security_concerns:
            security_holder_insights.append("Identified security vulnerabilities represent fundamental risk factors that could impact long-term viability.")
        
        concentration_concern = any("highly concentrated" in point.lower() for point in holder_points) or any("highly concentrated" in s.lower() or "whale" in s.lower() for s in concerns)
        if concentration_concern:
            security_holder_insights.append("High holder concentration increases vulnerability to market manipulation and potential for sudden price movements from large selling events.")
        
        balanced_distribution = any("well-balanced" in point.lower() for point in holder_points) or any("balanced" in s.lower() or "distribution" in s.lower() and "retail" in s.lower() for s in strengths)
        if balanced_distribution:
            security_holder_insights.append("Well-distributed token ownership provides resistance to manipulation and supports price stability.")
        
        if not security_holder_insights:
            return "Security and holder distribution metrics present a standard risk profile with no outstanding concerns or strengths identified."
        
        return " ".join(security_holder_insights)
