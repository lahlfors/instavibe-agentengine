import os
import asyncio
import threading
import logging

from google.cloud import aiplatform as vertexai
from vertexai.preview.reasoning_engines import AdkApp
from vertexai import agent_engines

from agents.social import agent as social_adk_module # Contains root_agent
from agents.social.a2a_server import create_social_a2a_server, A2A_UVICORN_PORT_SOCIAL
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

def deploy_social_main_func(project_id: str, region: str, staging_bucket_uri: str):
    """
    Deploys the Social agent with an integrated A2A server to Vertex AI Agent Engines.
    Uses a two-step process (create then update) to set the A2A_PUBLIC_BASE_URL.
    """
    display_name = "Social Agent (A2A-Embedded v2)"
    description = "Social agent with an embedded A2A interface for profile analysis."

    logger.info(f"Starting deployment of '{display_name}' to Project: {project_id}, Region: {region}")

    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        logger.info(f"Vertex AI SDK initialized for Social Agent: project:{project_id}, location:{region}, staging:{staging_bucket_uri}")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI SDK for Social Agent: {e}", exc_info=True)
        raise

    social_core_adk_agent = social_adk_module.root_agent
    if social_core_adk_agent is None:
        logger.error("The root_agent in agents.social.agent is None.")
        raise ValueError("Social ADK agent (root_agent) is not initialized.")
    logger.info(f"Using ADK Social agent: {getattr(social_core_adk_agent, 'name', 'Unnamed')}")

    a2a_starlette_app = create_social_a2a_server(passed_adk_social_agent=social_core_adk_agent)
    logger.info(f"A2AStarletteApplication for Social Agent created: {type(a2a_starlette_app).__name__}")

    temp_requirements_file = "temp_social_requirements.txt"
    current_vertexai_version = vertexai.__version__
    with open(temp_requirements_file, "w") as f:
        f.write("uvicorn>=0.20.0\n")
        f.write("fastapi>=0.95.0\n")
        # Assuming a2a-python (for a2a.server) is included via google-cloud-aiplatform[adk]
        # or a specific common library. If not, add "a2a-python"
        f.write(f"google-cloud-aiplatform[agent_engines,adk]>={current_vertexai_version}\n")
        f.write("nest_asyncio>=1.5.0,<2.0.0\n") # Often needed by ADK
        # Add other specific direct dependencies of social/agent.py or social/a2a_server.py if any
    logger.info(f"Dynamically created requirements file: {temp_requirements_file}")

    adk_app_instance = AdkApp(
        agent=social_core_adk_agent,
        setup_fn=lambda: start_uvicorn_in_thread(a2a_starlette_app, "0.0.0.0", A2A_UVICORN_PORT_SOCIAL)
    )
    logger.info(f"AdkApp instance created for Social Agent. Uvicorn for A2A will start on internal port {A2A_UVICORN_PORT_SOCIAL}.")

    env_vars_initial = {
        "A2A_UVICORN_PORT_SOCIAL": str(A2A_UVICORN_PORT_SOCIAL),
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "ADK_SESSION_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""), # If using Spanner for ADK sessions
        "ADK_SESSION_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""), # If using Spanner for ADK sessions

    }
    env_vars_initial = {k: v for k, v in env_vars_initial.items() if v is not None}
    logger.info(f"Initial environment variables for Social Agent create: {env_vars_initial}")

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    extra_packages_for_deployment = [
        os.path.join(repo_root, "agents/app_utils"),
        os.path.join(repo_root, "agents/social"),
    ]
    for pkg_path in extra_packages_for_deployment:
        if not os.path.exists(pkg_path):
            logger.error(f"Critical: Extra package path for Social Agent deployment not found: {pkg_path}")
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")
    logger.info(f"Extra packages for Social Agent deployment: {extra_packages_for_deployment}")

    remote_app = None
    try:
        logger.info(f"Calling initial agent_engines.create for '{display_name}'...")
        remote_app = agent_engines.create(
            agent_engine=adk_app_instance,
            display_name=display_name,
            description=description,
            requirements=[temp_requirements_file],
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_initial
        )
        logger.info(f"Agent '{display_name}' initial deployment successful. Resource name: {remote_app.name}")

        if not (hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
                hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri):
            logger.error("Failed to retrieve public_endpoint_uri for Social Agent after initial deployment.")
            raise RuntimeError("Could not get public_endpoint_uri for the deployed Social Agent.")

        public_a2a_url = remote_app.gca_resource.public_endpoint_uri
        logger.info(f"Retrieved public_endpoint_uri for Social Agent: {public_a2a_url}")

        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = public_a2a_url

        logger.info(f"Calling agent_engines.update for '{remote_app.name}' to set A2A_PUBLIC_BASE_URL for Social Agent...")
        logger.info(f"Updated environment variables for Social Agent: {env_vars_updated}")

        updated_remote_app = agent_engines.update(
            resource_name=remote_app.name,
            agent_engine=adk_app_instance,
            requirements=[temp_requirements_file],
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_updated
        )
        logger.info(f"Social Agent '{display_name}' updated successfully with A2A_PUBLIC_BASE_URL. New resource state name: {updated_remote_app.name}")

        return updated_remote_app

    except Exception as e:
        logger.error(f"ERROR during Social Agent deployment process for '{display_name}': {e}", exc_info=True)
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed Social Agent '{remote_app.name}' due to error.")
                agent_engines.delete(remote_app.name, force=True)
                logger.info(f"Successfully deleted partially deployed Social Agent '{remote_app.name}'.")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed Social Agent '{remote_app.name}': {del_e}", exc_info=True)
        raise
    finally:
        if os.path.exists(temp_requirements_file):
            try:
                os.remove(temp_requirements_file)
                logger.info(f"Removed temporary requirements file: {temp_requirements_file}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_requirements_file} for Social Agent: {e_rm}")
