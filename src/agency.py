import os
import sys
from dotenv import load_dotenv
from agency_swarm import Agency

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from grok_sentiment_agent import get_grok_sentiment_agent  # noqa: E402
from grok_narration_agent import get_grok_narration_agent  # noqa: E402

# Load environment variables
load_dotenv()

# Create agents
grok_sentiment_agent = get_grok_sentiment_agent()
grok_narration_agent = get_grok_narration_agent()

# Create the agency with two-agent communication flow
agency = Agency(
    grok_sentiment_agent,  # Entry point
    communication_flows=[
        (grok_sentiment_agent, grok_narration_agent),
    ],
    shared_instructions="./shared_instructions.md",
)


if __name__ == "__main__":
    # Test the agency in terminal mode
    print("GoArlo Crypto Summary Bot Agency")
    print("=" * 40)
    print("This agency processes sentiment analysis and narrative generation.")
    print("Market and holder data should be pre-fetched externally.")
    print("Use main.py for complete workflow including data fetching.")
    print()

    agency.terminal_demo()
