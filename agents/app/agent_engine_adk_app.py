# agents/app/agent_engine_adk_app.py
import logging
from google.api_core import exceptions
# import vertexai # Not strictly needed here if already init'd in deploy_all
from vertexai import agent_engines
from google.adk.agents import Agent as AdkAgentType
from typing import Optional, List, Any

logger = logging.getLogger(__name__)

def deploy_adk_agent_engine(
    agent_object: AdkAgentType,
    gcp_agent_id: str, # For logging
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
    display_name: str,
) -> Optional[agent_engines.AgentEngine]:
    """Deploys or updates a Reasoning Engine application using ADK's AdkApp."""

    try:
        with open(requirements_path, "r") as f:
            requirements = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Requirements file not found: {requirements_path}")
        raise

    logger.info(f"Wrapping ADK agent '{agent_object.name}' in AdkApp for deployment.")
    try:
        # AdkApp only wraps the agent object
        app = agent_engines.AdkApp(agent=agent_object)
    except Exception as e:
        logger.error(f"Failed to create AdkApp: {e}", exc_info=True)
        raise

    # Arguments for the create/update operations
    spec_kwargs = {
        "requirements": requirements,
        "extra_packages": extra_packages,
        "python_version": "3.11",
    }

    remote_agent = None
    try:
        logger.info(f"Listing Reasoning Engines in {project}/{location} to find display name: '{display_name}'")
        existing_engines = agent_engines.list()

        found_engine = None
        for engine in existing_engines:
            if engine.display_name == display_name:
                found_engine = engine
                break

        if found_engine:
            remote_agent = found_engine
            logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name} with display name '{display_name}'. Attempting to update.")
            try:
                # Update the existing engine with the new app definition and specs
                remote_agent.update(
                    reasoning_engine=app,
                    **spec_kwargs
                )
                logger.info(f"Successfully updated existing agent: {remote_agent.resource_name}")
            except Exception as up_e:
                logger.error(f"Failed to update existing agent {remote_agent.resource_name}: {up_e}", exc_info=True)
                raise
        else:
            logger.info(f"No existing engine with display name '{display_name}'. Creating new Reasoning Engine.")
            try:
                remote_agent = agent_engines.create(
                    reasoning_engine=app, # Pass the AdkApp object
                    display_name=display_name,
                    **spec_kwargs
                )
                logger.info(f"Engine '{display_name}' created. Resource Name: {remote_agent.resource_name}")
            except Exception as c_e:
                 logger.error(f"Failed to create new Reasoning Engine {display_name}: {c_e}", exc_info=True)
                 raise

    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {display_name}: {e}", exc_info=True)
         raise
    return remote_agent
