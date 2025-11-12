import os
from agency_swarm import Agent, ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv

load_dotenv()


def create_grok_narration_agent():
    return Agent(
        name="GrokNarrationAgent",
        description="Generates professional narrative sections from market data, holder statistics, and sentiment analysis using Grok reasoning",
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
