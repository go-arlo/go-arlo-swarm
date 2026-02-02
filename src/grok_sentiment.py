"""
Grok Sentiment Analyzer

Uses xAI with x_search to analyze crypto token sentiment and scam likelihood.
Returns structured output for integration with token analysis pipeline.
"""

import os
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field

from xai_sdk import AsyncClient
from xai_sdk.chat import system, user
from xai_sdk.search import SearchParameters, x_source


class SentimentRating(str, Enum):
    """Overall sentiment rating from social media analysis"""
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"


class ScamAssessment(str, Enum):
    """Scam likelihood assessment"""
    UNLIKELY = "Unlikely"
    UNCERTAIN = "Uncertain"
    LIKELY = "Likely"


class GrokSentimentResult(BaseModel):
    """Structured output from Grok sentiment analysis"""
    overall_sentiment: SentimentRating = Field(
        description="Overall sentiment rating based on total discussions"
    )
    scam_assessment: ScamAssessment = Field(
        description="Assessment of whether the token is likely a scam"
    )
    overview: str = Field(
        description="3-5 sentence explanation of the sentiment and scam assessment"
    )


class GrokSentimentResponse(BaseModel):
    """Full response wrapper for Grok sentiment analysis"""
    success: bool
    result: Optional[GrokSentimentResult] = None
    error: Optional[str] = None
    citations_count: int = 0
    sources_used: int = 0


async def analyze_token_sentiment(token_symbol: str) -> GrokSentimentResponse:
    """
    Analyze crypto token sentiment using Grok with X search.

    Args:
        token_symbol: The token symbol to analyze (e.g., "SOL", "PEPE")

    Returns:
        GrokSentimentResponse with structured sentiment analysis
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return GrokSentimentResponse(
            success=False,
            error="XAI_API_KEY not set in environment variables"
        )

    if not token_symbol or not token_symbol.strip():
        return GrokSentimentResponse(
            success=False,
            error="Token symbol is required"
        )

    # Clean the token symbol
    symbol = token_symbol.strip().upper()
    print(f"🤖 Analyzing sentiment for ${symbol} using Grok...")

    try:
        client = AsyncClient(api_key=api_key, timeout=60)

        # Create chat with x_search enabled and structured output
        chat = client.chat.create(
            model="grok-4-1-fast",
            response_format=GrokSentimentResult,
            search_parameters=SearchParameters(
                mode="on",
                sources=[x_source()]
            ),
            messages=[
                system(
                    "You are a crypto risk analyst. Analyze social media posts "
                    "about crypto tokens and provide objective assessments. "
                    "Be concise and factual in your analysis."
                )
            ]
        )

        # Build the analysis prompt
        prompt = (
            f"You are acting as a crypto risk analyst reviewing posts "
            f"related to the crypto token symbol: ${symbol}.\n\n"
            "Task:\n"
            "1. Assess the overall sentiment based on total discussions.\n"
            "2. Evaluate whether the token is likely a scam based on available signals.\n\n"
            "Consider:\n"
            "- Tone of posts (bullish, bearish, neutral)\n"
            "- Consistency of narratives\n"
            "- Presence of scam warnings, rugs, or red flags\n"
            "- Bot-like or coordinated shilling behavior\n"
            "- Credibility of posters (when apparent)\n\n"
            "Provide your analysis in the structured format."
        )

        chat.append(user(prompt))

        # Get response with structured output
        response = await chat.sample()

        # Parse the structured response
        result = GrokSentimentResult.model_validate_json(response.content)

        print(f"✅ Grok sentiment analysis complete for ${symbol}")
        print(f"   Sentiment: {result.overall_sentiment.value}")
        print(f"   Scam Assessment: {result.scam_assessment.value}")
        citation_count = len(response.citations)
        sources_count = response.usage.num_sources_used
        print(f"   Citations: {citation_count}, Sources: {sources_count}")

        return GrokSentimentResponse(
            success=True,
            result=result,
            citations_count=len(response.citations),
            sources_used=response.usage.num_sources_used
        )

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Grok sentiment analysis failed: {error_msg}")
        return GrokSentimentResponse(
            success=False,
            error=f"Grok analysis failed: {error_msg}"
        )
