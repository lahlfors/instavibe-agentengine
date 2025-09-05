# agents/app/agent_engine_app.py
import logging
from google.api_core import exceptions
from vertexai.preview import reasoning_engines

logger = logging.getLogger(__name__)

def deploy_agent_engine_app(
    agent_object,
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
) -> reasoning_engines.ReasoningEngine:
    """Deploys or updates a Reasoning Engine application."""

    with open(requirements_path, "r") as f:
        requirements = [line.strip() for line in f if line.strip()]

    # Use the 'name' attribute from the agent object for the ID.
    agent_id = agent_object.name
    display_name = agent_object.display_name

    # Prepare arguments for create/update
    eng_kwargs = {
        "reasoning_engine": agent_object,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "display_name": display_name,
        "sys_version": "3.11", # Pin Python version for compatibility
    }

    try:
        # Check if the engine exists using its resource name.
        # The ReasoningEngine constructor can take the agent_id (which is its name)
        remote_agent = reasoning_engines.ReasoningEngine(agent_id)
        logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name}. Attempting to update.")

        # Update the existing engine
        remote_agent.update(**eng_kwargs)
        logger.info(f"Engine '{display_name}' update operation finished.")

    except exceptions.NotFound:
        logger.info(f"Creating new Reasoning Engine with name: '{agent_id}' and display name: '{display_name}'")

        # Create a new engine
        remote_agent = reasoning_engines.ReasoningEngine.create(**eng_kwargs)

    return remote_agent
