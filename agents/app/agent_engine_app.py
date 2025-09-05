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

    display_name = agent_ref.display_name

    logger.info(f"--- PRE-LOOKUP DIAGNOSTICS ---")
    logger.info(f"Component REPRs: project={repr(project)}, location={repr(location)}, agent_id={repr(agent_id)}")
    full_resource_name = f"projects/{project}/locations/{location}/reasoningEngines/{agent_id}"
    logger.info(f"Constructed full_resource_name: '{full_resource_name}'")

    # ... eng_kwargs setup ...
    eng_kwargs = {
        "reasoning_engine": agent_ref,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "display_name": display_name,
        "sys_version": "3.11",
    }
    try:
        remote_agent = reasoning_engines.ReasoningEngine(full_resource_name)
        # ... update ...
        logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name}. Attempting to update.")
        remote_agent.update(**eng_kwargs)
        logger.info(f"Engine '{display_name}' update operation finished.")
    except exceptions.NotFound:
        # ... create ...
        logger.info(f"Creating new Reasoning Engine '{agent_id}' with display name: '{display_name}'")
        remote_agent = reasoning_engines.ReasoningEngine.create(**eng_kwargs)
        logger.info(f"Engine '{display_name}' create operation finished.")
    except exceptions.InvalidArgument as e:
         logger.error(f"Error (InvalidArgument) during ReasoningEngine operation for {agent_id}: {e}", exc_info=True)
         # Re-raise to stop this agent's deployment
         raise
    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {agent_id}: {e}", exc_info=True)
         raise

    return remote_agent
