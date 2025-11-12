import os
from agency_swarm import Agent, ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv

load_dotenv()

def create_grok_sentiment_agent():
    return Agent(
        name="GrokSentimentAgent",
        description="Collects market data, holder statistics, and social sentiment data for crypto tokens, then performs AI-powered sentiment analysis",
        instructions="./instructions.md",
        tools_folder="./tools",
        model=LitellmModel(
            model="xai/grok-4-fast-reasoning",
            api_key=os.getenv("XAI_API_KEY")
        ),
        model_settings=ModelSettings(
            temperature=0.1,
            max_tokens=128000
        ),
    )
