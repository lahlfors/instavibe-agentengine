# agents/app/agent_engine_app.py
import logging
from google.api_core import exceptions
from vertexai.preview import reasoning_engines

logger = logging.getLogger(__name__)

def deploy_agent_engine_app(
    agent_ref,
    agent_id: str,
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
) -> reasoning_engines.ReasoningEngine:
    """Deploys or updates a Reasoning Engine application."""

    with open(requirements_path, "r") as f:
        requirements = [line.strip() for line in f if line.strip()]

    reasoning_engines.init(project=project, location=location)

    # Prepare arguments for create/update
    eng_kwargs = {
        "reasoning_engine": agent_ref,
        "requirements": requirements,
        "extra_packages": extra_packages,
    }

    # Set Python version for all agents for consistency and compatibility.
    logger.info(f"Setting sys_version='3.11' for agent '{agent_id}'.")
    eng_kwargs["sys_version"] = "3.11"
    eng_kwargs['display_name'] = agent_ref.display_name

    try:
        remote_agent = reasoning_engines.ReasoningEngine(agent_id)
        logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name}. Attempting to update.")

        remote_agent.update(**eng_kwargs)
        logger.info(f"Engine '{remote_agent.display_name}' update operation finished.")

    except exceptions.NotFound:
        logger.info(f"Creating new Reasoning Engine with display name: '{agent_ref.display_name}'")
        remote_agent = reasoning_engines.ReasoningEngine.create(**eng_kwargs)

    return remote_agent
