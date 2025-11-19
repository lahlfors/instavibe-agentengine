# In agents/app/agent_engine_adk_app.py
import logging
import time
import vertexai
from vertexai.preview import reasoning_engines
from google.adk.agents import Agent as AdkAgentType
from typing import Optional, List
from google.api_core import exceptions

logger = logging.getLogger(__name__)

ReasoningEngine = reasoning_engines.ReasoningEngine
AdkApp = reasoning_engines.AdkApp

def find_existing_reasoning_engine(
    display_name: str, project: str, location: str
) -> Optional[ReasoningEngine]:
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
    display_name: str,
    project: str,
    location: str,
    requirements: List[str],
    extra_packages: List[str],
) -> Optional[ReasoningEngine]:
    """ Deploys or updates a Reasoning Engine by DELETING and RE-CREATING it. """

    vertexai.init(project=project, location=location)

    logger.info(f"Wrapping ADK agent '{agent_object.name}' in AdkApp for deployment.")
    try:
        app = AdkApp(agent=agent_object)
    except Exception as e:
        logger.error(f"Failed to create AdkApp: {e}", exc_info=True)
        raise

    logger.info(f"Checking for existing Reasoning Engine: '{display_name}'")
    existing_agent = find_existing_reasoning_engine(
        display_name=display_name, project=project, location=location
    )

    if existing_agent:
        logger.warning(f"Found existing engine: {existing_agent.resource_name}. Deleting it now...")
        try:
            existing_agent.delete()
            logger.info(f"Successfully deleted old agent: {display_name}")
            time.sleep(10) 
        except exceptions.NotFound:
            logger.warning(f"Agent {display_name} was already deleted.")
        except Exception as e:
            logger.error(f"Failed to delete existing Reasoning Engine {display_name}: {e}", exc_info=True)
            raise

    logger.info(f"Creating new Reasoning Engine for {display_name}...")
    try:
        remote_agent = ReasoningEngine.create(
            app,
            requirements=requirements,
            extra_packages=extra_packages,
            display_name=display_name,
        )
        
        logger.info(f"Successfully created: {remote_agent.resource_name}")
        return remote_agent
        
    except Exception as e:
        logger.error(f"Failed to create new Reasoning Engine {display_name}: {e}", exc_info=True)
        raise
