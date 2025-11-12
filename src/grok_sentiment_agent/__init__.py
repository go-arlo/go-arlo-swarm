# Import the agent creation function instead of the agent instance
def get_grok_sentiment_agent():
    from .grok_sentiment_agent import create_grok_sentiment_agent

    return create_grok_sentiment_agent()


__all__ = ["get_grok_sentiment_agent"]
