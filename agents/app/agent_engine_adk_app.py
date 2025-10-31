# agents/app/agent_engine_adk_app.py
import logging
import time
from google.api_core import exceptions
import vertexai
from vertexai.preview import reasoning_engines # Import the module
from google.adk.agents import Agent as AdkAgentType
from typing import Optional, List, Any
import os

logger = logging.getLogger(__name__)

# Access classes from the imported reasoning_engines module
ReasoningEngine = reasoning_engines.ReasoningEngine
AdkApp = reasoning_engines.AdkApp
# The ReasoningEngineSpec class has been removed from the SDK.
# The ReasoningEngine class is now used for this purpose.
# try:
#     ReasoningEngineSpec = reasoning_engines.ReasoningEngineSpec
#     logger.info("Using reasoning_engines.ReasoningEngineSpec")
# except AttributeError:
#     logger.critical("CRITICAL: reasoning_engines.ReasoningEngineSpec not found!")
#     raise

def find_existing_reasoning_engine(display_name: str, project: str, location: str) -> Optional[ReasoningEngine]:
    """Finds an existing Reasoning Engine by display name."""
    try:
        filters = f'display_name="{display_name}"'
        engines = ReasoningEngine.list(filter=filters, project=project, location=location)
        return engines[0] if engines else None
    except Exception as e:
        logger.error(f"Error listing Reasoning Engines: {e}", exc_info=True)
        return None

def deploy_adk_agent_engine(
    agent_object: AdkAgentType,
    gcp_agent_id: str, # For logging
    project: str,
    location: str,
    requirements_path: str,
    extra_packages: list[str],
    display_name: str,
) -> Optional[ReasoningEngine]:
    """Deploys or updates a Reasoning Engine application using ADK's AdkApp."""

    try:
        with open(requirements_path, "r") as f:
            requirements = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        logger.info(f"Cleaned requirements: {requirements}")
    except FileNotFoundError:
        logger.error(f"Requirements file not found: {requirements_path}")
        raise

    logger.info(f"Wrapping ADK agent '{agent_object.name}' in AdkApp for deployment.")
    try:
        app = AdkApp(agent=agent_object)
    except Exception as e:
        logger.error(f"Failed to create AdkApp: {e}", exc_info=True)
        raise

    # --- CORRECTED Spec ---
    spec = reasoning_engines.ReasoningEngine(
        agent=app,
        requirements=requirements,
        extra_packages=extra_packages,
        display_name=display_name,
        # --- REMOVED service_account ---
    )

    existing_agent = find_existing_reasoning_engine(display_name, project, location)

    if existing_agent:
        logger.info(f"Found existing Reasoning Engine: {existing_agent.resource_name}. Deleting to update...")
        try:
            delete_operation = existing_agent.delete() # Removed force=True
            logger.info(f"Deletion initiated for {existing_agent.resource_name}. Waiting for completion...")
            try:
                delete_operation.result(timeout=180)
                logger.info(f"Successfully deleted existing agent: {existing_agent.resource_name}")
            except TimeoutError:
                logger.warning(f"Deletion of {existing_agent.resource_name} timed out after 180s.")
            except Exception as e:
                 logger.error(f"Error during delete operation for {existing_agent.resource_name}: {e}", exc_info=True)
                 raise
        except exceptions.NotFound:
            logger.info(f"Agent {existing_agent.resource_name} not found for deletion.")
        except Exception as e:
            logger.error(f"Failed to initiate deletion for {existing_agent.resource_name}: {e}", exc_info=True)
            raise

    logger.info(f"Creating Reasoning Engine for {display_name}...")
    try:
        remote_agent = ReasoningEngine.create(spec)
        logger.info(f"Creation initiated for {display_name}. Waiting for LRO to complete...")
        remote_agent = remote_agent._wait_for_creation()
        logger.info(f"Successfully created or updated: {remote_agent.resource_name}")
        return remote_agent
    except Exception as e:
        logger.error(f"Failed to create new Reasoning Engine {display_name}: {e}", exc_info=True)
        raise
