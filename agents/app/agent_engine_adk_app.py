# agents/app/agent_engine_adk_app.py
import logging
from google.api_core import exceptions
import vertexai
from vertexai import agent_engines
from google.adk.agents import Agent as AdkAgentType
from typing import Optional, List, Any

logger = logging.getLogger(__name__)

def deploy_adk_agent_engine(
    agent_object: AdkAgentType,
    gcp_agent_id: str, # Hyphenated ID for GCP
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
    display_name: str,
) -> Optional[agent_engines.AgentEngine]: # Correct return type
    """Deploys or updates a Reasoning Engine application using ADK's AdkApp."""

    try:
        with open(requirements_path, "r") as f:
            requirements = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Requirements file not found: {requirements_path}")
        raise

    logger.info(f"Wrapping ADK agent '{agent_object.name}' in AdkApp for deployment.")
    app = agent_engines.AdkApp(agent=agent_object)

    full_resource_name = f"projects/{project}/locations/{location}/reasoningEngines/{gcp_agent_id}"

    # Prepare the arguments for create or update
    shared_kwargs = {
        "agent_engine": app,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "display_name": display_name,
        "sys_version": "3.11",
    }

    try:
        logger.info(f"Listing Reasoning Engines in {project}/{location} to find display name: '{display_name}'")
        # *** CORRECTED CALL to list ***
        existing_engines = agent_engines.list(project=project, location=location)

        found_engine = None
        for engine in existing_engines:
            if engine.display_name == display_name:
                found_engine = engine
                break

        if found_engine:
            remote_agent = found_engine
            logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name} with display name '{display_name}'. Deleting to Update.")
            try:
                remote_agent.delete()
                logger.info(f"Successfully deleted existing agent: {remote_agent.resource_name}")
            except Exception as del_e:
                logger.error(f"Failed to delete existing agent {remote_agent.resource_name}: {del_e}", exc_info=True)
                raise

            logger.info(f"Re-creating Reasoning Engine: {gcp_agent_id}")
            remote_agent = agent_engines.create(
                app,
                reasoning_engine_id=gcp_agent_id,
                **shared_kwargs
            )
            logger.info(f"Engine '{display_name}' re-created. Resource Name: {remote_agent.resource_name}")

        else:
            logger.info(f"No existing engine with display name '{display_name}'. Creating new Reasoning Engine: {gcp_agent_id}")
            remote_agent = agent_engines.create(
                app,
                reasoning_engine_id=gcp_agent_id,
                 **shared_kwargs
            )
            logger.info(f"Engine '{display_name}' created. Resource Name: {remote_agent.resource_name}")

    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {display_name}: {e}", exc_info=True)
         raise
    return remote_agent
