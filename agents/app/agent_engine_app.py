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

    agent_id = agent_object.name
    display_name = agent_object.display_name

    # --- DIAGNOSTIC LOGGING ---
    logger.info(f"--- DIAGNOSING RESOURCE NAME ---")
    logger.info(f"Project: {repr(project)}")
    logger.info(f"Location: {repr(location)}")
    logger.info(f"Agent ID: {repr(agent_id)}")
    # --- END DIAGNOSTIC LOGGING ---

    # Construct the full resource name for lookup
    full_resource_name = f"projects/{project}/locations/{location}/reasoningEngines/{agent_id}"
    logger.info(f"Constructed Full Resource Name: {full_resource_name}")

    eng_kwargs = {
        "reasoning_engine": agent_object,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "display_name": display_name,
        "sys_version": "3.11",
    }

    try:
        # Use the full resource name to GET the engine
        remote_agent = reasoning_engines.ReasoningEngine(full_resource_name)
        logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name}. Attempting to update.")
        remote_agent.update(**eng_kwargs)
        logger.info(f"Engine '{display_name}' update operation finished.")

    except exceptions.NotFound:
        logger.info(f"Creating new Reasoning Engine '{agent_id}' with display name: '{display_name}'")
        remote_agent = reasoning_engines.ReasoningEngine.create(**eng_kwargs)
        logger.info(f"Engine '{display_name}' create operation finished.")
    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {agent_id}: {e}", exc_info=True)
         raise

    return remote_agent
