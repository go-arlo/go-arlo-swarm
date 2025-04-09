from agency_swarm import Agency
from .arlo.arlo import Arlo
from .trend_sage.trend_sage import TrendSage
from .market_signal.signal import Signal
import time

# Initialize agents
arlo = Arlo()
trend_sage = TrendSage()
signal = Signal()

agency = Agency(
    [
        arlo,
        [arlo, signal],
        [arlo, trend_sage]
    ],
    shared_instructions="""
    # Critical Rules
    1. Always perform analysis when requested, regardless of previous analyses
    2. Never reject or skip analysis requests
    3. Process each request as a new analysis
    """,
    temperature=0.2,
    max_prompt_tokens=128000
)

def handle_message(message):
    """Handle message processing and ensure analysis is complete before returning"""
    try:
        print(f"Handling message: {message}")
        response = agency.get_completion(message)
        print(f"Agency response: {response}")
        return response
    except Exception as e:
        print(f"Error in handle_message: {str(e)}")
        return None

if __name__ == "__main__":
    agency.demo_gradio()
