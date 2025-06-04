from agency_swarm import Agent
from .tools.trend_analysis import TrendAnalysis
from typing import Dict

class TrendSage(Agent):
    def __init__(self):
        super().__init__(
            name="Trend Sage",
            description="Social engagement analyst",
            instructions="./instructions.md",
            tools=[TrendAnalysis],
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
                
                combined_analysis = self._analyze_trends(trend_analysis)
                metrics = self._extract_metrics(trend_analysis)
                social_score = self._calculate_social_score(metrics)
                
                return {
                    "data": {
                        "assessment": combined_analysis["assessment"],
                        "summary": combined_analysis["summary"],
                        "key_points": combined_analysis["key_points"],
                        "social_score": social_score
                    }
                }
            except Exception as e:
                print(f"Trend Sage analysis error: {str(e)}")
                return {
                    "data": {
                        "assessment": "negative",
                        "summary": "Analysis failed",
                        "key_points": ["Error processing analysis"],
                        "social_score": 0
                    }
                }
        
        return super().process_message(message, sender)

    def _extract_metrics(self, trend_data: Dict) -> Dict:
        """Extract key metrics from trend data"""
        trend_metrics = trend_data.get("data", {})
        tweet_metrics = trend_metrics.get("tweet_metrics", {})
        influence_distribution = tweet_metrics.get("influence_distribution", {})
        
        influential_account = tweet_metrics.get("influential_account", None)
        
        high_influence = influence_distribution.get("high_influence", {}).get("unique_users", 0)
        mid_influence = influence_distribution.get("mid_influence", {}).get("unique_users", 0)
        warning_tweets = tweet_metrics.get("warning_tweets_data", [])
        
        return {
            "high_influence": high_influence,
            "mid_influence": mid_influence,
            "warning_tweets": warning_tweets,
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
        
        if metrics["warning_tweets"]:
            summary_parts.append(f"with {len(metrics['warning_tweets'])} warning tweets detected suggesting potential risks")
        else:
            summary_parts.append("with no warning tweets detected")
        
        return f"Recent social analysis {'. '.join(summary_parts)}."
        
    def _analyze_trends(self, trend_data: Dict) -> Dict:
        """Analyze social trends data"""
        metrics = self._extract_metrics(trend_data)
        
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

    def _calculate_social_score(self, metrics: Dict) -> float:
        """Calculate social engagement score (0-100) based on trend metrics"""
        score = 40
        
        high_influence = metrics.get("high_influence", 0)
        if high_influence >= 3:
            score += 30
        elif high_influence >= 1:
            score += 20
        
        mid_influence = metrics.get("mid_influence", 0)
        if mid_influence >= 5:
            score += 20
        elif mid_influence >= 3:
            score += 15
        elif mid_influence >= 1:
            score += 10
            
        warning_tweets = len(metrics.get("warning_tweets", []))
        if warning_tweets >= 3:
            score -= 30
        elif warning_tweets >= 1:
            score -= 15
            
        influential_account = metrics.get("influential_account", None)
        if influential_account:
            if influential_account.get("category") == "high":
                score += 10
            elif influential_account.get("category") == "mid":
                score += 5
                
        return max(0, min(100, score))
