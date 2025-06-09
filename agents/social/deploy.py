from agents.social import agent as social_adk_agent_module
from agents.social.social_agent import SocialAgent
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Instantiate the ReasoningEngine wrapper (SocialAgent)
social_reasoning_engine_instance = SocialAgent()

# Define display_name and description for the agent
display_name = "Social Agent"
description = """This agent analyzes social profiles, including posts, friend networks, and event participation, to generate comprehensive summaries and identify common ground between individuals."""

# Create the AdkApp instance for local execution (using the ReasoningEngine)
app = AdkApp(
    agent=social_reasoning_engine_instance,
    enable_tracing=True,
)

# Create the deployed agent for Vertex AI Agent Engines (using the ADK agent module)
# The 'app' parameter here refers to the ADK agent or module to be deployed.
# The 'requirements_path' should be relative to this deploy.py file.
deployed_agent = agent_engines.create(
    app=social_adk_agent_module,
    display_name=display_name,
    description=description,
    requirements_path="./requirements.txt", # Assuming requirements.txt is in the same directory (agents/social/)
)
