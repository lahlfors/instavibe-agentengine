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
) -> Optional[Any]: # Returns an agent_engines client object
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
    logger.info(f"Target Reasoning Engine resource name: {full_resource_name}")

    # Prepare the arguments for create or update
    update_kwargs = {
        "agent_engine": app,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "display_name": display_name,
        "sys_version": "3.11",
    }

    try:
        # Check if the engine exists by trying to get it
        agent_engines.get(full_resource_name)
        logger.info(f"Found existing Reasoning Engine: {full_resource_name}. Attempting to update.")
        # Update the existing engine
        agent_engines.update(
            resource_name=full_resource_name,
            **update_kwargs
        )
        remote_agent = agent_engines.get(full_resource_name) # Fetch the updated instance
        logger.info(f"Engine '{display_name}' update operation finished.")

    except exceptions.NotFound:
        logger.info(f"No existing engine '{gcp_agent_id}'. Creating new Reasoning Engine.")
        # Create a new engine
        create_kwargs = update_kwargs.copy()
        remote_agent = agent_engines.create(
            reasoning_engine_id=gcp_agent_id,
            **create_kwargs
        )
        logger.info(f"Engine '{display_name}' created. Resource Name: {remote_agent.resource_name}")
    except exceptions.InvalidArgument as e:
         logger.error(f"Error (InvalidArgument) during ReasoningEngine operation for {gcp_agent_id}: {e}", exc_info=True)
         logger.error(f"Resource name components: project='{project}', location='{location}', agent_id='{gcp_agent_id}'")
         raise
    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {gcp_agent_id}: {e}", exc_info=True)
         raise

    return remote_agent
