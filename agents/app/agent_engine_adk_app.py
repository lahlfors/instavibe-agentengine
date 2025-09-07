import logging
from google.api_core import exceptions
from vertexai import agent_engines
from typing import Optional, List, Any, Type

logger = logging.getLogger(__name__)

def deploy_adk_agent_engine(
    project_id: str,
    location: str,
    display_name: str,
    agent_class: Type,
    agent_description: Optional[str] = None,
    staging_bucket: Optional[str] = None,
    tools_for_agent: Optional[List] = None,
) -> Any:
    """Deploys or updates a Reasoning Engine application."""

    logger.info(f"--- Deploying/Updating Agent: {display_name} ---")

    # This is a simplified approach to get requirements.
    # A more robust solution would inspect the agent's dependencies.
    requirements = ["google-cloud-aiplatform[reasoningengine]"]

    app = agent_engines.AdkApp(
        agent=agent_class(
            model="gemini-1.5-flash-001",
            tools=tools_for_agent or [],
        ),
        description=agent_description,
    )

    eng_kwargs = {
        "agent_engine": app,
        "requirements": requirements,
        "staging_bucket": staging_bucket,
    }

    try:
        logger.info(f"Listing Reasoning Engines in {project_id}/{location} to find '{display_name}'")
        existing_engines = agent_engines.list(project=project_id, location=location)

        found_engine = None
        for engine in existing_engines:
            if engine.display_name == display_name:
                found_engine = engine
                break

        if found_engine:
            remote_agent = found_engine
            logger.info(f"Found existing Reasoning Engine: {remote_agent.resource_name} with display name '{display_name}'. Attempting to update.")
            remote_agent.update(**eng_kwargs)
            logger.info(f"Engine '{display_name}' update operation finished.")
        else:
            logger.info(f"No existing engine with display name '{display_name}'. Creating new Reasoning Engine.")
            remote_agent = agent_engines.create(
                project=project_id,
                location=location,
                display_name=display_name,
                **eng_kwargs
            )
            logger.info(f"Engine '{display_name}' create operation finished. Resource Name: {remote_agent.resource_name}")

    except Exception as e:
         logger.error(f"Error during ReasoningEngine operation for {display_name}: {e}", exc_info=True)
         raise

    return remote_agent
