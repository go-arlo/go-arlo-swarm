from agency_swarm import Agent
from .tools.social_sentiment import SocialSentiment
from .tools.trend_analysis import TrendAnalysis
from typing import Dict

class TrendSage(Agent):
    def __init__(self):
        super().__init__(
            name="Trend Sage",
            description="Social sentiment analyst",
            instructions="./instructions.md",
            tools=[SocialSentiment, TrendAnalysis],
            temperature=0.5,
            max_prompt_tokens=128000,
            model="gpt-4o"
        )

    def process_message(self, message, sender):
        """Fast message processing with error handling"""
        if sender == "Arlo":
            try:
                trend_tool = TrendAnalysis(token_symbol=message)
                trend_analysis = trend_tool.run()
                
                sentiment_tool = SocialSentiment(token_symbol=message)
                sentiment_analysis = sentiment_tool.run()
                
                combined_analysis = self._analyze_trends(sentiment_analysis, trend_analysis)
                
                return {
                    "data": {
                        "sentiment_score": sentiment_analysis.get("sentiment_score", 0),
                        "assessment": combined_analysis["assessment"],
                        "summary": combined_analysis["summary"],
                        "key_points": combined_analysis["key_points"]
                    }
                }
            except Exception as e:
                print(f"Trend Sage analysis error: {str(e)}")
                return {
                    "data": {
                        "sentiment_score": 0,
                        "assessment": "negative",
                        "summary": "Analysis failed",
                        "key_points": ["Error processing analysis"]
                    }
                }
        
        return super().process_message(message, sender)

    def _extract_metrics(self, trend_data: Dict, sentiment_data: Dict) -> Dict:
        """Extract key metrics from trend and sentiment data"""
        trend_metrics = trend_data.get("data", {})
        tweet_metrics = trend_metrics.get("tweet_metrics", {})
        influence_distribution = tweet_metrics.get("influence_distribution", {})
        
        influential_account = tweet_metrics.get("influential_account", None)
        
        high_influence = influence_distribution.get("high_influence", {}).get("unique_users", 0)
        mid_influence = influence_distribution.get("mid_influence", {}).get("unique_users", 0)
        warning_tweets = tweet_metrics.get("warning_tweets_data", [])
        
        sentiment_score = sentiment_data.get("sentiment_score", 0)
        sentiment_summary = sentiment_data.get("sentiment_summary", "")
        
        return {
            "high_influence": high_influence,
            "mid_influence": mid_influence,
            "warning_tweets": warning_tweets,
            "sentiment_score": sentiment_score,
            "sentiment_summary": sentiment_summary,
            "influential_account": influential_account
        }

    def _generate_key_points(self, metrics: Dict) -> tuple:
        """Generate key points and count positive points"""
        key_points = []
        positive_points = 0
        negative_points = 0
        
        influential_account = metrics.get("influential_account", None)
        
        if metrics["high_influence"] > 0:
            if influential_account and influential_account.get("category") == "high":
                screen_name = influential_account.get("screen_name", "")
                replies = influential_account.get("replies", 0)
                views = influential_account.get("views", 0)
                key_points.append(f"Notable recent high-follower X posts (e.g. @{screen_name} with {replies} replies and {views} views)")
            else:
                key_points.append("Notable recent high-follower X posts")
            positive_points += 1
        elif metrics["mid_influence"] >= 3:
            if influential_account and influential_account.get("category") == "mid":
                screen_name = influential_account.get("screen_name", "")
                replies = influential_account.get("replies", 0)
                views = influential_account.get("views", 0)
                key_points.append(f"Recent active engagement through mid-follower X posts (e.g. @{screen_name} with {replies} replies and {views} views)")
            else:
                key_points.append("Recent active engagement through mid-follower X posts")
            positive_points += 1
        else:
            key_points.append("Limited engagement from recent X posts")
            negative_points += 1
        
        if metrics["high_influence"] == 0:
            negative_points += 1
        if metrics["mid_influence"] < 3:
            negative_points += 1
        
        if metrics["sentiment_score"] > 0:
            if metrics["sentiment_score"] >= 70:
                key_points.append("Strong positive sentiment detected from social volume")
                positive_points += 1
            elif metrics["sentiment_score"] >= 60:
                key_points.append("Neutral sentiment detected from social volume")
            else:
                key_points.append("Weak or negative sentiment detected from social volume")
                negative_points += 1
        
        return key_points, positive_points, negative_points

    def _get_assessment(self, positive_points: int, negative_points: int) -> str:
        """Determine assessment based on positive vs negative points"""
        if negative_points > positive_points or negative_points >= 2:
            return "negative"
        elif positive_points >= 3 and positive_points > negative_points:
            return "positive"
        return "neutral"

    def _generate_summary(self, metrics: Dict) -> str:
        """Generate analysis summary"""
        summary_parts = []
        
        influential_account = metrics.get("influential_account", None)
        
        if metrics["sentiment_score"] > 0:
            if metrics["high_influence"] > 0:
                if influential_account and influential_account.get("category") == "high":
                    screen_name = influential_account.get("screen_name", "")
                    replies = influential_account.get("replies", 0)
                    views = influential_account.get("views", 0)
                    summary_parts.append(f"shows notable high-follower X posts, with @{screen_name}'s post generating {replies} replies and {views} views")
                else:
                    summary_parts.append("shows notable recent high-follower X posts")
            elif metrics["mid_influence"] >= 3:
                if influential_account and influential_account.get("category") == "mid":
                    screen_name = influential_account.get("screen_name", "")
                    replies = influential_account.get("replies", 0)
                    views = influential_account.get("views", 0)
                    summary_parts.append(f"shows active engagement through mid-follower X posts, with @{screen_name}'s post generating {replies} replies and {views} views")
                else:
                    summary_parts.append("shows recent active engagement through mid-follower X posts")
            else:
                summary_parts.append("shows engagement primarily from small accounts")
            
            if metrics["sentiment_score"] >= 70:
                summary_parts.append("showing strong positive sentiment")
            elif metrics["sentiment_score"] >= 60:
                summary_parts.append("showing neutral sentiment")
            else:
                summary_parts.append("showing weak or negative sentiment")
            
            if metrics["warning_tweets"]:
                summary_parts.append(f"with {len(metrics['warning_tweets'])} warning tweets detected suggesting potential risks")
            else:
                summary_parts.append("with no warning tweets detected")
            
            return f"Recent social analysis {'. '.join(summary_parts)}."
        
        return ""

    def _analyze_trends(self, sentiment_data: Dict, trend_data: Dict) -> Dict:
        """Analyze social trends and sentiment data"""
        metrics = self._extract_metrics(trend_data, sentiment_data)
        
        key_points, positive_points, negative_points = self._generate_key_points(metrics)
        
        if metrics["warning_tweets"]:
            for warning in metrics["warning_tweets"][:2]:
                key_points.append(
                    f"Warning tweet from @{warning.get('author', 'unknown')}: {warning.get('text', '')[:100]}..."
                )
        
        assessment = self._get_assessment(positive_points, negative_points)
        summary = self._generate_summary(metrics)
        
        return {
            "summary": summary,
            "assessment": assessment,
            "key_points": key_points[:5]
        }
