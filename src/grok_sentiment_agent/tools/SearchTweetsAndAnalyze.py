import os
import aiohttp
from agency_swarm.tools import BaseTool
from pydantic import Field
from typing import List, Dict


class SearchTweetsAndAnalyze(BaseTool):
    """
    Comprehensive tool that searches for tweets about a token and prepares them for detailed sentiment analysis.
    Includes specific focus on highlighting negative sentiment, warnings, and risk indicators.
    The agent will handle the actual AI analysis based on the tweet data returned.
    """

    token_symbol: str = Field(..., description="Token symbol (e.g., SOL, BTC, ETH)")
    limit: int = Field(default=50, description="Maximum number of tweets to retrieve")

    async def run(self) -> str:
        """Search tweets and return formatted data for sentiment analysis by the agent"""

        try:
            # Search for tweets
            print(f"🐦 Searching tweets for ${self.token_symbol}...")
            tweets = await self._search_tweets()

            if not tweets:
                return f"No tweets found for ${self.token_symbol}. Unable to perform sentiment analysis."

            # Format tweets for analysis (use first 20 for token limits)
            tweet_content = tweets[:20]
            tweet_count = len(tweets)

            print(f"✅ Found {tweet_count} tweets for ${self.token_symbol}")

            # Prepare formatted data for the agent to analyze
            analysis_prompt = f"""
Please analyze the following tweets about ${self.token_symbol} and provide sentiment analysis:

TWEETS FOR ANALYSIS ({len(tweet_content)} of {tweet_count} total):
{tweet_content}

Please determine:
1. Overall sentiment (Bullish, Neutral, or Bearish)
2. INTERNAL USE ONLY: Assess confidence internally but DO NOT include numeric confidence in output
3. Top trending topic being discussed
4. Most representative tweet that captures the overall sentiment
5. Social volume estimate (High, Medium, or Low) based on engagement
6. IMPORTANT: Highlight any negative sentiment, warnings, or caution posts if they exist
7. Flag any scam warnings, rug pull concerns, or bearish technical analysis

Focus on content quality and credibility indicators. Weigh informed analysis more heavily than speculation.
Pay special attention to warning signals and negative sentiment that could indicate risks.

CRITICAL: Never output numeric confidence scores in your response. Use qualitative descriptions instead.
"""

            return analysis_prompt

        except Exception as e:
            error_msg = f"Error searching tweets: {str(e)}"
            print(f"❌ {error_msg}")
            return f"Error occurred while searching for tweets about ${self.token_symbol}: {error_msg}"

    async def _search_tweets(self) -> List[Dict]:
        """Search for tweets about a token using TweetScout API"""

        api_key = os.getenv("TWEET_SCOUT_ID")
        if not api_key:
            raise ValueError("TWEET_SCOUT_ID environment variable not set")

        headers = {
            "ApiKey": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Create search query for the token
        query = f"${self.token_symbol} OR {self.token_symbol} crypto"

        payload = {
            "query": query,
            "order": "popular",
            "limit": min(self.limit, 100),  # Respect API limits
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tweetscout.io/v2/search-tweets",
                headers=headers,
                json=payload,
                timeout=30,
            ) as response:
                if response.status == 401:
                    raise Exception(
                        "Unauthorized - Please check your TweetScout API Key"
                    )
                elif response.status == 429:
                    raise Exception("TweetScout API rate limit exceeded")
                elif response.status != 200:
                    raise Exception(f"TweetScout API error: {response.status}")

                data = await response.json()

        # Handle response format
        if not isinstance(data, dict):
            raise Exception("Invalid response format from TweetScout API")

        tweets = data.get("tweets", [])
        if not isinstance(tweets, list):
            tweets = []

        print(f"Retrieved {len(tweets)} tweets for ${self.token_symbol}")

        return tweets
