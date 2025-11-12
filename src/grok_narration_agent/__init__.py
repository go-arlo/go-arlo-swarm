# Import the agent creation function instead of the agent instance
def get_grok_narration_agent():
    from .grok_narration_agent import create_grok_narration_agent

    return create_grok_narration_agent()


__all__ = ["get_grok_narration_agent"]
