from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
from dotenv import load_dotenv

load_dotenv()

LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY")

class SocialSentiment(BaseTool):
    """
    Analyzes social media sentiment and engagement metrics using LunarCrush API.
    Provides structured sentiment analysis output.
    """

    token_symbol: str = Field(
        ..., 
        description="The token symbol to analyze (e.g., 'BTC', 'SOL')"
    )

    class Config:
        json_schema_extra = {
            "response_format": {
                "type": "object",
                "properties": {
                    "sentiment_score": {
                        "type": "number",
                        "description": "Sentiment score from 0-100"
                    },
                    "sentiment_summary": {
                        "type": "string",
                        "description": "One-line summary of social sentiment"
                    },
                    "key_findings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 5,
                        "description": "Key sentiment metrics and findings"
                    }
                }
            }
        }

    def run(self):
        """
        Executes comprehensive sentiment analysis
        """
        try:
            lunar_data = self._get_lunar_crush_data()
            
            print("\nLunarCrush API Response:")
            print(f"Status Code: {lunar_data.get('status_code')}")
            print("Response Data:")
            print(lunar_data)
            print("\n")
            
            sentiment_score = self._calculate_sentiment_score(lunar_data)
            
            sentiment_summary = self._generate_sentiment_summary(lunar_data)
            key_findings = self._generate_key_findings(lunar_data)
            
            return {
                "sentiment_score": sentiment_score,
                "sentiment_summary": sentiment_summary,
                "key_findings": key_findings
            }
            
        except Exception as e:
            return {
                "sentiment_score": 50,
                "sentiment_summary": f"Error analyzing sentiment: {str(e)}",
                "key_findings": [
                    "Analysis failed due to error",
                    "Sentiment status cannot be determined",
                    "Manual verification recommended"
                ]
            }

    def _get_lunar_crush_data(self):
        """Fetch sentiment data from LunarCrush API"""
        url = "https://lunarcrush.com/api4/public/coins/list/v1"
        
        headers = {
            "Authorization": f"Bearer {LUNARCRUSH_API_KEY}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"LunarCrush API error: {response.status_code}")
        
        data = response.json().get('data', [])
        token_data = next(
            (token for token in data if token['symbol'].lower() == self.token_symbol.lower()),
            None
        )
        
        if token_data:
            token_data['status_code'] = response.status_code
            return token_data
        else:
            return {
                'galaxy_score': 50,
                'galaxy_score_previous': 50,
                'social_volume_24h': 0,
                'social_dominance': 0,
                'sentiment': 50,
                'interactions_24h': 0,
                'alt_rank': 0,
                'alt_rank_previous': 0,
                'name': self.token_symbol,
                'symbol': self.token_symbol,
                'not_found': True
            }

    def _calculate_sentiment_score(self, data):
        """Calculate sentiment score with adjusted neutral ranges"""
        base_score = 50
        
        social_volume = data.get('social_volume_24h', 0)
        if social_volume > 1000:
            base_score += 12
        elif social_volume > 100:
            base_score += 6
            
        sentiment = data.get('sentiment', 50)
        if sentiment > 60:
            base_score += 12
        elif sentiment > 50:
            base_score += 6
        elif sentiment < 40:
            base_score -= 12
            
        galaxy_score = data.get('galaxy_score', 50)
        if galaxy_score > 60:
            base_score += 11
        elif galaxy_score > 50:
            base_score += 5
        
        return min(100, max(45, base_score))

    def _generate_sentiment_summary(self, data):
        """Generate summary of sentiment analysis"""
        if data.get('not_found', False):
            return {
                "sentiment_score": 0,
                "summary": "Current sentiment limited pending more active discussions.",
                "key_metrics": []
            }
        
        galaxy_score = data.get('galaxy_score', 0)
        sentiment = data.get('sentiment')
        social_volume = data.get('social_volume_24h', 0)
        
        if sentiment is None:
            if galaxy_score > 70:
                return "Strong social engagement metrics with growing community presence"
            elif galaxy_score > 50:
                return "Moderate social activity with potential for growth"
            elif social_volume > 100:
                return "Active social discussion with developing sentiment trends"
            else:
                return "Limited social volume currently observed"
        
        if galaxy_score > 70 and sentiment > 60:
            return "Strong positive social sentiment with high engagement"
        elif galaxy_score > 50 or sentiment > 50:
            return "Moderate positive sentiment with growing social presence"
        elif social_volume > 100:
            return "Active social discussion with mixed sentiment"
        else:
            return "Limited social activity with neutral sentiment"

    def _generate_key_findings(self, data):
        """Generate key sentiment findings"""
        if data.get('not_found', False):
            return [
                "Overall social presence indicates more momentum needed from the community"
            ]
            
        findings = []
        
        galaxy_score = data.get('galaxy_score', 0)
        galaxy_score_prev = data.get('galaxy_score_previous', 0)
        score_change = galaxy_score - galaxy_score_prev
        findings.append(f"Galaxy Score: {galaxy_score:.1f} ({score_change:+.1f} change)")
        
        social_volume = data.get('social_volume_24h', 0)
        findings.append(f"24h Social Volume: {social_volume:,} interactions")
        
        sentiment = data.get('sentiment')
        if sentiment is not None:
            findings.append(f"Sentiment Score: {sentiment:.1f}/100")
        else:
            findings.append("Limited visibility into sentiment pending more active discussions")
        
        social_dominance = data.get('social_dominance', 0)
        findings.append(f"Social Dominance: {social_dominance:.2f}%")
        
        alt_rank = data.get('alt_rank', 0)
        alt_rank_prev = data.get('alt_rank_previous', 0)
        if alt_rank > 0 and alt_rank_prev > 0:
            rank_change = alt_rank_prev - alt_rank
            findings.append(f"Alt Rank: #{alt_rank:,} ({rank_change:+d} positions)")
            
        return findings[:5]

if __name__ == "__main__":
    tool = SocialSentiment(token_symbol="arc")
    result = tool.run()
    print(result) 
