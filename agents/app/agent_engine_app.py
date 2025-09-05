# agents/app/agent_engine_app.py
import logging
from google.api_core import exceptions
from vertexai.preview import reasoning_engines
from typing import Optional

logger = logging.getLogger(__name__)

def deploy_agent_engine_app(
    agent_object,  # This is the instance from ADK
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
) -> Optional[reasoning_engines.ReasoningEngine]:
    """Deploys or updates a Reasoning Engine application."""

    try:
        with open(requirements_path, "r") as f:
            requirements = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Requirements file not found: {requirements_path}")
        raise

    adk_agent_name = agent_object.name  # e.g., planner_agent
    display_name = agent_object.display_name # e.g., "Planner Agent"

    eng_kwargs = {
        "reasoning_engine": agent_object,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "sys_version": "3.11", # Pin Python version
    }

    remote_agent = None
    try:
        logger.info(f"Listing Reasoning Engines in {project}/{location} to find '{display_name}'")
        existing_engines = reasoning_engines.ReasoningEngine.list(project=project, location=location)

        found_engine = None
        for engine in existing_engines:
            if engine.display_name == display_name:
                found_engine = engine
                break

        if found_engine:
            remote_agent = found_engine
            logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name} with display name '{display_name}'. Attempting to update.")
            # Pass display_name to update as well
            eng_kwargs['display_name'] = display_name
            remote_agent.update(**eng_kwargs)
            logger.info(f"Engine '{display_name}' update operation finished.")
        else:
            logger.info(f"No existing engine with display name '{display_name}'. Creating new Reasoning Engine.")
            # Pass display_name for creation
            eng_kwargs['display_name'] = display_name
            remote_agent = reasoning_engines.ReasoningEngine.create(**eng_kwargs)
            logger.info(f"Engine '{display_name}' create operation finished. Resource Name: {remote_agent.resource_name}")

    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {adk_agent_name} ('{display_name}'): {e}", exc_info=True)
         raise

    return remote_agent
