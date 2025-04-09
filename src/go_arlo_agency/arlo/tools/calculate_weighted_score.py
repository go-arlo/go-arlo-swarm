from agency_swarm.tools import BaseTool
from pydantic import Field, field_validator
from typing import Optional

class CalculateWeightedScore(BaseTool):
    """
    Calculates the weighted score from agent scores
    """

    contract_status: str = Field(
        ...,
        description="Contract control status (positive/neutral/negative)",
        pattern="^(positive|neutral|negative)$"
    )
    
    holder_status: str = Field(
        ...,
        description="Holder control status (positive/neutral/negative)",
        pattern="^(positive|neutral|negative)$"
    )
    
    concentration: str = Field(
        ...,
        description="Holder concentration (well-balanced/moderately concentrated/highly concentrated)",
        pattern="^(well-balanced|moderately concentrated|highly concentrated)$"
    )
    
    sentiment_score: float = Field(
        default=0,
        description="Sentiment score from Trend Sage (0-100)",
        ge=0,
        le=100
    )
    
    market_score: float = Field(
        default=0,
        description="Market score from Signal (0-100)",
        ge=0,
        le=100
    )

    def calculate_security_score(self):
        """Calculate security score based on contract and holder control"""
        if self.contract_status == "positive" and self.holder_status == "positive":
            return 95
        elif self.contract_status == "negative" and self.holder_status == "negative":
            return 50
        elif self.contract_status == "negative" or self.holder_status == "negative":
            return 65
        else:
            return 75

    def calculate_distribution_score(self):
        """Calculate distribution score based on concentration"""
        if self.concentration == "well-balanced":
            return 95
        elif self.concentration == "moderately concentrated":
            return 80
        else:
            return 65

    def run(self):
        """
        Calculates final weighted score.
        
        Weights:
        - Security: 26% - Higher weight for security as it's most critical
        - Market: 25% - Slightly higher weight for market analysis
        - Distribution: 24% - Equal weight for remaining metrics
        - Sentiment: 25% - Equal weight for remaining metrics
        """
        try:
            security_score = self.calculate_security_score()
            distribution_score = self.calculate_distribution_score()
            
            weighted_score = (
                security_score * 0.26 +
                self.market_score * 0.25 +
                distribution_score * 0.24 +
                self.sentiment_score * 0.25
            )
            
            # Cap at 85 if market score is low
            if self.market_score < 70:
                weighted_score = min(weighted_score, 85)
            
            # Ensure score stays within 0-100 range
            weighted_score = min(100, max(0, weighted_score))
            
            # Round to 2 decimal places
            return round(weighted_score, 2)
            
        except Exception as e:
            print(f"Error calculating score: {str(e)}")
            return 0

if __name__ == "__main__":
    test_cases = [
        {
            "name": "All Positive",
            "scores": {
                "contract_status": "positive",
                "holder_status": "positive",
                "concentration": "well-balanced",
                "sentiment_score": 85,
                "market_score": 85
            }
        },
        {
            "name": "Mixed with Strong Core",
            "scores": {
                "contract_status": "positive",
                "holder_status": "positive",
                "concentration": "moderately concentrated",
                "sentiment_score": 60,
                "market_score": 80
            }
        },
        {
            "name": "Weak Core Metrics",
            "scores": {
                "contract_status": "negative",
                "holder_status": "negative",
                "concentration": "highly concentrated",
                "sentiment_score": 85,
                "market_score": 45
            }
        }
    ]
    
    for case in test_cases:
        tool = CalculateWeightedScore(**case["scores"])
        final_score = tool.run()
        print(f"\n{case['name']}:")
        print(f"Scores: {case['scores']}")
        print(f"Final Score: {final_score}")