import logging
from google.api_core import exceptions
import vertexai
from vertexai import agent_engines
from google.adk.agents import Agent as AdkAgentType
from typing import Optional, List, Any

logger = logging.getLogger(__name__)

def deploy_adk_agent_engine(
    agent_object: AdkAgentType,
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
) -> Optional[Any]: # Returns an agent_engines client object
    """Deploys or updates a Reasoning Engine application using ADK's AdkApp."""

    display_name = agent_object.display_name
    adk_agent_name = agent_object.name # e.g., planner_agent
    logger.info(f"--- Deploying/Updating Agent: {display_name} (ADK Name: {adk_agent_name}) ---")

    try:
        with open(requirements_path, "r") as f:
            requirements = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Requirements file not found: {requirements_path}")
        raise

    logger.info(f"Wrapping ADK agent '{adk_agent_name}' in AdkApp for deployment.")
    app = agent_engines.AdkApp(agent=agent_object)

    eng_kwargs = {
        "agent_engine": app,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "sys_version": "3.11",
    }

    try:
        logger.info(f"Listing Reasoning Engines in {project}/{location} to find '{display_name}'")
        existing_engines = agent_engines.ReasoningEngine.list(project=project, location=location)

        found_engine = None
        for engine in existing_engines:
            if engine.display_name == display_name:
                found_engine = engine
                break

        if found_engine:
            remote_agent = found_engine
            logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name} with display name '{display_name}'. Attempting to update.")
            agent_engines.update(
                resource_name=remote_agent.resource_name,
                **eng_kwargs
            )
            # Re-fetch to ensure the object is updated, using the known resource_name
            remote_agent = agent_engines.get(remote_agent.resource_name)
            logger.info(f"Engine '{display_name}' update operation finished.")
        else:
            logger.info(f"No existing engine with display name '{display_name}'. Creating new Reasoning Engine.")
            # When creating, we only provide display_name, the ID is generated
            remote_agent = agent_engines.ReasoningEngine.create(
                display_name=display_name,
                 **eng_kwargs
            )
            logger.info(f"Engine '{display_name}' create operation finished. Resource Name: {remote_agent.resource_name}")

    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {display_name}: {e}", exc_info=True)
         raise

    return remote_agent
