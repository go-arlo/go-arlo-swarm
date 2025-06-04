from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TWEET_SCOUT_ID = os.getenv("TWEET_SCOUT_ID")
SEARCH_URL = "https://api.tweetscout.io/v2/search-tweets"

class TrendAnalysis(BaseTool):

    """
    Analyzes recent tweets about a token to determine trend strength and sentiment.
    Uses TweetScout API for tweet search.
    """

    token_symbol: str = Field(
        ..., 
        description="The token symbol to analyze (e.g., 'SOL', 'BTC')"
    )

    def run(self):
        """
        Executes trend analysis using TweetScout API
        """
        try:
            print(f"Analyzing trends for ${self.token_symbol}")
            
            tweets_data = self._get_recent_tweets()
            
            analysis = self._analyze_tweets(tweets_data)
            
            print(f"Analysis complete for ${self.token_symbol}")
            
            return {
                "status": "success",
                "data": analysis,
                "message": "Trend analysis completed successfully"
            }
            
        except Exception as e:
            print(f"Error: {str(e)}")
            return {
                "status": "error",
                "message": f"Error analyzing trends: {str(e)}"
            }

    def _get_recent_tweets(self):
        """Fetch recent tweets about the token"""
        if not TWEET_SCOUT_ID:
            raise ValueError("TWEET_SCOUT_ID environment variable is not set")

        headers = {
            "ApiKey": TWEET_SCOUT_ID,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        query = f"${self.token_symbol} OR {self.token_symbol} crypto"
        
        print(f"\nFetching tweets for ${self.token_symbol}...")
        
        try:
            response = requests.post(
                SEARCH_URL,
                headers=headers,
                json={
                    "query": query,
                    "order": "popular"
                },
                timeout=30
            )
            
            if response.status_code == 401:
                raise Exception("Unauthorized - Please check your TweetScout API Key")
            elif response.status_code != 200:
                raise Exception(f"TweetScout API error: {response.status_code} - {response.text}")
            
            response_data = response.json()
            if not isinstance(response_data, dict):
                raise Exception("Invalid response format from TweetScout API")
            
            if 'tweets' not in response_data:
                response_data['tweets'] = []
            elif not isinstance(response_data['tweets'], list):
                response_data['tweets'] = []
                
            print(f"Retrieved {len(response_data['tweets'])} tweets")
            return response_data
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def _calculate_sentiment_score(self, tweets, negative_tweets):
        """Calculate sentiment score with negative tweet weighting and follower influence"""
        total_score = 0
        total_weight = 0
        
        negative_ids = set()
        if isinstance(negative_tweets, list):
            for tweet in negative_tweets:
                if isinstance(tweet, dict) and 'id' in tweet:
                    negative_ids.add(tweet['id'])
        
        processed_tweets = tweets[:20] if len(tweets) > 20 else tweets
        
        for tweet in processed_tweets:
            if not isinstance(tweet, dict):
                continue
                
            user = tweet.get('user', {})
            if not isinstance(user, dict):
                continue
                
            follower_count = user.get('followers_count', 0)
            follower_multiplier = min(2.0, max(1.0, 1 + (follower_count / 100000)))
            
            retweets = tweet.get('retweet_count', 0)
            replies = tweet.get('reply_count', 0)
            likes = tweet.get('favorite_count', 0)
            quotes = tweet.get('quote_count', 0)
            views = tweet.get('view_count', 0)
            
            engagement_weights = {
                'retweets': (retweets * 2.0) * follower_multiplier,
                'quotes': (quotes * 1.8) * follower_multiplier,
                'replies': (replies * 1.5) * follower_multiplier,
                'likes': (likes * 1.0) * follower_multiplier,
                'views': (views * 0.1) * follower_multiplier
            }
            
            weighted_engagement = sum(engagement_weights.values())
            
            relevancy_weight = min(1.0, weighted_engagement / 5000)
            
            tweet_id = tweet.get('id')
            sentiment_multiplier = -1.5 if tweet_id in negative_ids else 1.0
            
            tweet_score = weighted_engagement * relevancy_weight * sentiment_multiplier
            
            total_score += tweet_score
            total_weight += relevancy_weight
            
            print(f"\nTweet Metrics:")
            print(f"Text: {tweet.get('full_text')}")
            print(f"Author: {tweet.get('user', {}).get('screen_name')} ({follower_count:,} followers)")
            print(f"Follower Multiplier: {follower_multiplier:.2f}x")
            print(f"Is Negative: {tweet_id in negative_ids}")
            print(f"Base Metrics:")
            print(f"  Retweets: {retweets}")
            print(f"  Replies: {replies}")
            print(f"  Likes: {likes}")
            print(f"  Quotes: {quotes}")
            print(f"  Views: {views}")
            print(f"Weighted Metrics:")
            print(f"  Retweets: {engagement_weights['retweets']:.2f}")
            print(f"  Quotes: {engagement_weights['quotes']:.2f}")
            print(f"  Replies: {engagement_weights['replies']:.2f}")
            print(f"  Likes: {engagement_weights['likes']:.2f}")
            print(f"  Views: {engagement_weights['views']:.2f}")
            print(f"Final Calculations:")
            print(f"  Weighted Engagement: {weighted_engagement:.2f}")
            print(f"  Relevancy Weight: {relevancy_weight:.2f}")
            print(f"  Sentiment Multiplier: {sentiment_multiplier}")
            print(f"  Tweet Score: {tweet_score:.2f}")
        
        normalized_score = ((total_score / total_weight) + 100) / 2 if total_weight > 0 else 50
        return max(0, min(100, normalized_score))

    def _determine_sentiment(self, sentiment_score):
        """Determine overall sentiment based on score"""
        if sentiment_score > 50:
            return "positive"
        elif sentiment_score > 20:
            return "neutral"
        else:
            return "negative"

    def _calculate_trend_strength(self, tweet_count, engagement_rate, engagement_metrics):
        """Calculate overall trend strength based primarily on impressions and engagement"""
        if not isinstance(engagement_metrics, dict):
            return 0

        total_impressions = engagement_metrics.get("total_impressions", 0) or 0
        total_retweets = engagement_metrics.get("total_retweets", 0) or 0
        total_quotes = engagement_metrics.get("total_quotes", 0) or 0
        total_replies = engagement_metrics.get("total_replies", 0) or 0
        
        try:
            total_impressions = float(total_impressions)
            total_retweets = float(total_retweets)
            total_quotes = float(total_quotes)
            total_replies = float(total_replies)
        except (ValueError, TypeError):
            return 0
        
        impression_score = min(total_impressions / 20000, 1) * 50
        
        retweet_score = min(total_retweets / 500, 1) * 20
        quote_score = min(total_quotes / 200, 1) * 15
        reply_score = min(total_replies / 300, 1) * 15
        
        engagement_score = retweet_score + quote_score + reply_score
        
        return round(impression_score + engagement_score, 2)

    def _generate_trend_summary(self, trend_strength, high_percent, mid_percent, low_percent, warning_count, high_influence=None, mid_influence=None, low_influence=None):
        """Generate human-readable trend summary based on influence distribution"""
        summary = []

        trend_strength = float(trend_strength) if trend_strength is not None else 0
        high_percent = float(high_percent) if high_percent is not None else 0
        mid_percent = float(mid_percent) if mid_percent is not None else 0
        low_percent = float(low_percent) if low_percent is not None else 0
        warning_count = int(warning_count) if warning_count is not None else 0
        
        if high_influence is None or not hasattr(high_influence, '__len__'):
            high_influence = set()
        if mid_influence is None or not hasattr(mid_influence, '__len__'):
            mid_influence = set()
        if low_influence is None or not hasattr(low_influence, '__len__'):
            low_influence = set()

        if trend_strength >= 50:
            summary.append("Strong trending activity")
        elif trend_strength >= 30:
            summary.append("Moderate trending activity")
        elif trend_strength >= 15:
            summary.append("Weak trending activity")
        else:
            summary.append("Very weak trending activity")

        if len(high_influence) >= 3:
            summary.append("High influencer presence")
        elif len(high_influence) > 0 or len(mid_influence) >= 3:
            summary.append("Notable influencer activity")
        elif len(mid_influence) > 0:
            summary.append("Some influencer participation")
        elif len(low_influence) > 0:
            summary.append("Only small accounts participating")
        else:
            summary.append("Limited activity")

        if warning_count > 0:
            summary.append(f"{warning_count} warning tweets found")

        return " | ".join(summary)
    
    def _select_influential_account(self, high_influence, mid_influence):
        """
        Select one influential account with engagement metrics to showcase
        
        Returns a dict with screen_name, replies, and views if available,
        otherwise returns None
        """
        if not isinstance(high_influence, list):
            high_influence = []
        if not isinstance(mid_influence, list):
            mid_influence = []
            
        if high_influence and len(high_influence) > 0:
            try:
                sorted_tweets = sorted(
                    high_influence, 
                    key=lambda t: (t.get('view_count', 0), t.get('reply_count', 0)), 
                    reverse=True
                )
                best_tweet = sorted_tweets[0]
                screen_name = best_tweet.get('user', {}).get('screen_name', '')
                replies = best_tweet.get('reply_count', 0)
                views = best_tweet.get('view_count', 0)
                
                return {
                    "screen_name": screen_name,
                    "replies": replies,
                    "views": views,
                    "category": "high"
                }
            except (IndexError, TypeError, AttributeError):
                pass
            
        elif mid_influence and len(mid_influence) >= 3:
            try:
                sorted_tweets = sorted(
                    mid_influence, 
                    key=lambda t: (t.get('view_count', 0), t.get('reply_count', 0)), 
                    reverse=True
                )
                best_tweet = sorted_tweets[0]
                screen_name = best_tweet.get('user', {}).get('screen_name', '')
                replies = best_tweet.get('reply_count', 0)
                views = best_tweet.get('view_count', 0)
                
                return {
                    "screen_name": screen_name,
                    "replies": replies,
                    "views": views,
                    "category": "mid"
                }
            except (IndexError, TypeError, AttributeError):
                pass
            
        return None

    def _is_token_mentioned(self, tweet_text):
        """Check if a tweet mentions the token symbol in any format"""
        if not isinstance(tweet_text, str):
            return False
        tweet_text = tweet_text.lower()
        return (
            self.token_symbol.lower() in tweet_text or 
            f"${self.token_symbol.lower()}" in tweet_text or 
            f"#{self.token_symbol.lower()}" in tweet_text
        )

    def _analyze_tweets(self, data):
        """Analyze tweets based on user influence categories and warning signals"""
        if not isinstance(data, dict):
            raise ValueError("Invalid data format: expected dictionary")

        all_tweets = data.get('tweets', [])
        if not isinstance(all_tweets, list):
            raise ValueError("Invalid tweets format: expected list")
            
        if not all_tweets:
            return self._get_empty_analysis()

        print(f"Analyzing {len(all_tweets)} tweets")
        
        low_influence_users = set()
        mid_influence_users = set()
        high_influence_users = set()

        high_influence = []
        mid_influence = []
        low_influence = []

        users_with_min_views = set()
        
        for tweet in all_tweets:
            if not isinstance(tweet, dict):
                continue
                
            user = tweet.get('user', {})
            if not isinstance(user, dict):
                continue
                
            screen_name = user.get('screen_name', '')
            view_count = tweet.get('view_count', 0)
            tweet_text = tweet.get('full_text', '')
            
            if not self._is_token_mentioned(tweet_text):
                continue
            
            if isinstance(view_count, (int, float)) and view_count >= 500:
                users_with_min_views.add(screen_name)

        for tweet in all_tweets:
            if not isinstance(tweet, dict):
                continue
                
            user = tweet.get('user', {})
            if not isinstance(user, dict):
                continue
                
            follower_count = user.get('followers_count', 0)
            screen_name = user.get('screen_name', '')
            tweet_text = tweet.get('full_text', '')
            
            if not self._is_token_mentioned(tweet_text):
                continue
            
            has_min_views = screen_name in users_with_min_views

            if isinstance(follower_count, (int, float)):
                if follower_count >= 10000 and has_min_views:
                    high_influence_users.add(screen_name)
                    high_influence.append(tweet)
                elif follower_count >= 2000 and has_min_views:
                    mid_influence_users.add(screen_name)
                    mid_influence.append(tweet)
                else:
                    low_influence_users.add(screen_name)
                    low_influence.append(tweet)

        total_tweets = len(all_tweets)
        unique_high = len(high_influence_users)
        unique_mid = len(mid_influence_users)
        unique_low = len(low_influence_users)
        total_unique = unique_high + unique_mid + unique_low

        high_percent = (len(high_influence) / total_tweets * 100) if total_tweets > 0 else 0
        mid_percent = (len(mid_influence) / total_tweets * 100) if total_tweets > 0 else 0
        low_percent = (len(low_influence) / total_tweets * 100) if total_tweets > 0 else 0

        negative_keywords = ['scam', 'rug', 'fake', 'ponzi', 'stole', 'bundled']
        positive_phrases = ['not a scam', 'no scam', 'legit', 'legitimate', 'safe', 'solid', 'reliable', 'trustworthy', 'not fake']
        general_phrases = ['stay ready', 'stay safe', 'dyor', 'be careful', 'always research', 'remember to', 'don\'t forget', 'learn about']
        
        potential_negative_tweets = []
        for tweet in all_tweets:
            if not isinstance(tweet, dict):
                continue
                
            tweet_text = tweet.get('full_text', '')
            
            if not self._is_token_mentioned(tweet_text):
                continue
            
            if any(positive in tweet_text.lower() for positive in positive_phrases):
                continue
                
            has_general_phrase = any(phrase in tweet_text.lower() for phrase in general_phrases)
            
            if has_general_phrase and not self._is_token_mentioned(tweet_text):
                continue
                
            if any(keyword in tweet_text.lower() for keyword in negative_keywords):
                potential_negative_tweets.append(tweet)

        negative_tweets = []
        for tweet in potential_negative_tweets:
            tweet_text = tweet.get('full_text', '')
            
            if not self._is_token_mentioned(tweet_text):
                continue
            
            has_specific_warning = any(term in tweet_text.lower() for term in [
                'contract', 'vulnerab', 'risk', 'issue', 'security', 'honeypot', 'lock', 
                'withdraw', 'liquidity', 'sell', 'dump', 'dev wallet', 'team wallet'
            ])
            
            is_comparison = ('unlike' in tweet_text.lower() or 'better than' in tweet_text.lower() or 'compared to' in tweet_text.lower())
            
            if self._is_token_mentioned(tweet_text) and has_specific_warning and not is_comparison:
                negative_tweets.append(tweet)
                
            elif self._is_token_mentioned(tweet_text) and any(strong_term in tweet_text.lower() for strong_term in ['confirmed scam', 'proven rug', '100% fake']):
                negative_tweets.append(tweet)

        warning_tweets_data = [
            {
                'text': tweet.get('full_text', ''),
                'author': tweet.get('user', {}).get('screen_name', ''),
                'followers': tweet.get('user', {}).get('followers_count', 0),
                'created_at': tweet.get('created_at', '')
            } 
            for tweet in negative_tweets
        ]
        
        influential_account = self._select_influential_account(high_influence, mid_influence)

        high_influence_weight = 10
        high_influence_score = min(50, unique_high * high_influence_weight)
        
        mid_influence_weight = 5
        mid_influence_score = min(35, unique_mid * mid_influence_weight)
        
        has_higher_influence = unique_high + unique_mid > 0
        low_influence_score = min(15, low_percent * 0.3) if has_higher_influence else 0

        trend_strength = max(0, high_influence_score + mid_influence_score + low_influence_score)

        total_impressions = 0
        total_retweets = 0
        total_quotes = 0
        total_replies = 0
        
        for tweet in all_tweets:
            if not isinstance(tweet, dict):
                continue
                
            total_impressions += int(tweet.get('view_count', 0) or 0)
            total_retweets += int(tweet.get('retweet_count', 0) or 0)
            total_quotes += int(tweet.get('quote_count', 0) or 0)
            total_replies += int(tweet.get('reply_count', 0) or 0)
            
        engagement_metrics = {
            "total_impressions": total_impressions,
            "total_retweets": total_retweets,
            "total_quotes": total_quotes,
            "total_replies": total_replies
        }
        
        tweet_count = len(all_tweets)
        engagement_rate = sum(engagement_metrics.values()) / (tweet_count * 4) if tweet_count > 0 else 0
        
        trend_strength_engagement = self._calculate_trend_strength(tweet_count, engagement_rate, engagement_metrics)
        
        final_trend_strength = trend_strength if trend_strength > 0 else trend_strength_engagement

        print("\nTweet Analysis Breakdown:")
        print(f"Total Tweets: {total_tweets}")
        print(f"Total Unique Users: {total_unique}")
        print("\nUser Influence Distribution:")
        print(f"High Influence ({unique_high:,} users, {len(high_influence):,} tweets): {high_percent:.1f}% (≥10k followers)")
        for screen_name in high_influence_users:
            user_tweet = next((t for t in high_influence if t.get('user', {}).get('screen_name') == screen_name), None)
            if user_tweet:
                print(f"  @{screen_name}: {user_tweet.get('user', {}).get('followers_count'):,} followers")
        
        print(f"Mid Influence ({unique_mid:,} users, {len(mid_influence):,} tweets): {mid_percent:.1f}% (2k-9.9k followers)")
        for screen_name in mid_influence_users:
            user_tweet = next((t for t in mid_influence if t.get('user', {}).get('screen_name') == screen_name), None)
            if user_tweet:
                print(f"  @{screen_name}: {user_tweet.get('user', {}).get('followers_count'):,} followers")
        
        print(f"Low Influence ({unique_low:,} users, {len(low_influence):,} tweets): {low_percent:.1f}% (<2k followers)")
        
        if influential_account:
            print("\nSelected Influential Account for Highlight:")
            print(f"  @{influential_account['screen_name']}")
            print(f"  Category: {'High Influence' if influential_account['category'] == 'high' else 'Mid Influence'}")
            print(f"  Replies: {influential_account['replies']}")
            print(f"  Views: {influential_account['views']}")

        sentiment_score = 0
        if all_tweets:
            try:
                sentiment_score = self._calculate_sentiment_score(all_tweets, negative_tweets)
                print(f"Sentiment score: {sentiment_score}")
            except Exception as e:
                print(f"Error calculating sentiment score: {str(e)}")
                sentiment_score = 50
                
        sentiment = self._determine_sentiment(sentiment_score)
        print(f"Sentiment: {sentiment}")

        return {
            "trend_strength": round(final_trend_strength, 2),
            "tweet_metrics": {
                "total_tweets": total_tweets,
                "total_unique_users": total_unique,
                "influence_distribution": {
                    "high_influence": {
                        "unique_users": unique_high,
                        "total_tweets": len(high_influence),
                        "percentage": round(high_percent, 2)
                    },
                    "mid_influence": {
                        "unique_users": unique_mid,
                        "total_tweets": len(mid_influence),
                        "percentage": round(mid_percent, 2)
                    },
                    "low_influence": {
                        "unique_users": unique_low,
                        "total_tweets": len(low_influence),
                        "percentage": round(low_percent, 2)
                    }
                },
                "warning_tweets": len(negative_tweets),
                "warning_tweets_data": warning_tweets_data,
                "influential_account": influential_account,
                "sentiment": {
                    "score": round(sentiment_score, 2),
                    "label": sentiment
                }
            },
            "trend_summary": self._generate_trend_summary(
                final_trend_strength,
                high_percent,
                mid_percent,
                low_percent,
                len(negative_tweets),
                high_influence_users if isinstance(high_influence_users, set) else set(),
                mid_influence_users if isinstance(mid_influence_users, set) else set(),
                low_influence_users if isinstance(low_influence_users, set) else set()
            )
        }

    def _get_empty_analysis(self):
        """Return empty analysis structure"""
        return {
            "trend_strength": 0,
            "tweet_metrics": {
                "total_tweets": 0,
                "total_unique_users": 0,
                "influence_distribution": {
                    "high_influence": {
                        "unique_users": 0,
                        "total_tweets": 0,
                        "percentage": 0
                    },
                    "mid_influence": {
                        "unique_users": 0,
                        "total_tweets": 0,
                        "percentage": 0
                    },
                    "low_influence": {
                        "unique_users": 0,
                        "total_tweets": 0,
                        "percentage": 0
                    }
                },
                "warning_tweets": 0,
                "warning_tweets_data": [],
                "influential_account": None
            },
            "trend_summary": f"No relevant tweets found for ${self.token_symbol}"
        }

if __name__ == "__main__":
    tool = TrendAnalysis(
        token_symbol="FULLSEND"
    )
    result = tool.run()
    print(result) 
