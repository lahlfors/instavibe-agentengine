import os
import asyncio
import threading
import logging
from typing import Optional

from google.cloud import aiplatform as vertexai
from vertexai.preview.reasoning_engines import AdkApp
from vertexai import agent_engines

# Import the OrchestrateServiceAgent, A2A server creation function, and Uvicorn port
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent
# This next import assumes agents/orchestrate/a2a_server.py will be created in the next step
from agents.orchestrate.a2a_server import create_orchestrator_a2a_server, A2A_UVICORN_PORT_ORCHESTRATE
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread

# Load .env for standalone script execution, though deploy_all.py should handle it.
from dotenv import load_dotenv
if not os.getenv("COMMON_GOOGLE_CLOUD_PROJECT"):
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

def deploy_orchestrate_main_func(project_id: str, region: str, staging_bucket_uri: str, dynamic_remote_agent_addresses: Optional[str] = None):
    """
    Deploys the Orchestrate Agent with an integrated A2A server to Vertex AI Agent Engines.
    Uses a two-step process (create then update) to set the A2A_PUBLIC_BASE_URL.
    """
    display_name = "Orchestrate Agent (A2A-Embedded v2)"
    description = "Orchestrator agent with an embedded A2A interface, managing tasks for other agents."

    logger.info(f"Starting deployment of '{display_name}' to Project: {project_id}, Region: {region}")

    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        logger.info(f"Vertex AI SDK initialized for Orchestrate Agent: project:{project_id}, location:{region}, staging:{staging_bucket_uri}")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI SDK for Orchestrate Agent: {e}", exc_info=True)
        raise

    remote_agent_addresses_str = dynamic_remote_agent_addresses if dynamic_remote_agent_addresses \
        else os.getenv("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES", "")
    if not remote_agent_addresses_str:
        logger.warning("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES is not set. Orchestrator may not connect to remote agents effectively.")

    orchestrate_core_adk_agent_service = OrchestrateServiceAgent(remote_agent_addresses_str=remote_agent_addresses_str)
    if orchestrate_core_adk_agent_service.host_agent_logic.root_agent is None:
         logger.error("The root_agent within HostAgent for Orchestrator is None.")
         raise ValueError("Orchestrator's core ADK agent (HostAgent.root_agent) is not initialized.")
    logger.info(f"Using ADK Orchestrate agent service: {type(orchestrate_core_adk_agent_service).__name__}")

    a2a_starlette_app = create_orchestrator_a2a_server(passed_orchestrate_service_agent=orchestrate_core_adk_agent_service)
    logger.info(f"A2AStarletteApplication for Orchestrator created: {type(a2a_starlette_app).__name__}")

    temp_requirements_file = "temp_orchestrate_requirements.txt"
    current_vertexai_version = vertexai.__version__
    # Use the orchestrator's own requirements.txt as a base, then add uvicorn etc.
    base_requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    requirements_list = []
    if os.path.exists(base_requirements_path):
        with open(base_requirements_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not any("uvicorn" in req for req in requirements_list):
        requirements_list.append("uvicorn>=0.20.0")
    if not any("fastapi" in req for req in requirements_list): # a2a-python needs it
        requirements_list.append("fastapi>=0.95.0")
    # Ensure google-cloud-aiplatform is present with adk,agent_engines extras
    # Remove any existing line and add the correct one to avoid conflicts
    requirements_list = [req for req in requirements_list if not req.startswith("google-cloud-aiplatform")]
    requirements_list.append(f"google-cloud-aiplatform[agent_engines,adk]>={current_vertexai_version}")
    if not any("nest_asyncio" in req for req in requirements_list):
        requirements_list.append("nest_asyncio>=1.5.0,<2.0.0")

    with open(temp_requirements_file, "w") as f:
        for req_line in requirements_list:
            f.write(f"{req_line}\n")
    logger.info(f"Dynamically created requirements file: {temp_requirements_file} with contents: {requirements_list}")

    adk_llm_agent_for_orchestrator = orchestrate_core_adk_agent_service.host_agent_logic.root_agent
    adk_app_instance = AdkApp(
        agent=adk_llm_agent_for_orchestrator,
        setup_fn=lambda: start_uvicorn_in_thread(a2a_starlette_app, "0.0.0.0", A2A_UVICORN_PORT_ORCHESTRATE)
    )
    logger.info(f"AdkApp instance created for Orchestrator. Uvicorn for A2A will start on internal port {A2A_UVICORN_PORT_ORCHESTRATE}.")

    env_vars_initial = {
        "A2A_UVICORN_PORT_ORCHESTRATE": str(A2A_UVICORN_PORT_ORCHESTRATE),
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES": remote_agent_addresses_str,
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "ADK_SESSION_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "ADK_SESSION_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
    }
    env_vars_initial = {k: v for k, v in env_vars_initial.items() if v is not None}
    logger.info(f"Initial environment variables for Orchestrator create: {env_vars_initial}")

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    extra_packages_for_deployment = [
        os.path.join(repo_root, "agents/app_utils"),
        os.path.join(repo_root, "agents/orchestrate"),
        # Add other agent directories if HostAgent tools have direct local dependencies
        # os.path.join(repo_root, "agents/planner"),
        # os.path.join(repo_root, "agents/social"),
        # os.path.join(repo_root, "agents/platform_mcp_client"),
    ]
    extra_packages_for_deployment = [pkg for pkg in extra_packages_for_deployment if os.path.exists(pkg)]
    logger.info(f"Extra packages for Orchestrator deployment: {extra_packages_for_deployment}")

    remote_app = None
    try:
        logger.info(f"Calling initial agent_engines.create for '{display_name}'...")
        remote_app = agent_engines.create(
            agent_engine=adk_app_instance,
            display_name=display_name,
            description=description,
            requirements=[temp_requirements_file], # Use the dynamically generated file
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_initial
        )
        logger.info(f"Agent '{display_name}' initial deployment successful. Resource name: {remote_app.name}")

        if not (hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
                hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri):
            logger.error("Failed to retrieve public_endpoint_uri for Orchestrator after initial deployment.")
            raise RuntimeError("Could not get public_endpoint_uri for the deployed Orchestrator Agent.")

        public_a2a_url = remote_app.gca_resource.public_endpoint_uri
        logger.info(f"Retrieved public_endpoint_uri for Orchestrator: {public_a2a_url}")

        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = public_a2a_url

        logger.info(f"Calling agent_engines.update for '{remote_app.name}' to set A2A_PUBLIC_BASE_URL for Orchestrator...")
        logger.info(f"Updated environment variables for Orchestrator: {env_vars_updated}")

        updated_remote_app = agent_engines.update(
            resource_name=remote_app.name,
            agent_engine=adk_app_instance,
            requirements=[temp_requirements_file],
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_updated
        )
        logger.info(f"Orchestrator Agent '{display_name}' updated successfully. New resource state name: {updated_remote_app.name}")

        return updated_remote_app

    except Exception as e:
        logger.error(f"ERROR during Orchestrator Agent deployment process for '{display_name}': {e}", exc_info=True)
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed Orchestrator Agent '{remote_app.name}' due to error.")
                agent_engines.delete(remote_app.name, force=True)
                logger.info(f"Successfully deleted partially deployed Orchestrator Agent '{remote_app.name}'.")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed Orchestrator Agent '{remote_app.name}': {del_e}", exc_info=True)
        raise
    finally:
        if os.path.exists(temp_requirements_file):
            try:
                os.remove(temp_requirements_file)
                logger.info(f"Removed temporary requirements file: {temp_requirements_file}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_requirements_file} for Orchestrator: {e_rm}")