import os
import asyncio
import threading
import logging

from google.cloud import aiplatform as vertexai
from vertexai.preview.reasoning_engines import AdkApp
from vertexai import agent_engines

# Import the ADK agent class/instance and the A2A server creation function
from agents.planner import agent as planner_adk_module # Contains root_agent (LlmAgent)
from agents.planner.a2a_server import create_planner_a2a_server, A2A_UVICORN_PORT_PLANNER
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread

# For type hinting if needed for a2a_app, though not strictly necessary for runtime
# from a2a.server import A2AStarletteApplication

# Setup logging
# Load dotenv might be needed if running standalone and not via deploy_all.py which handles it.
# from dotenv import load_dotenv
# load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

def deploy_planner_main_func(project_id: str, region: str, staging_bucket_uri: str):
    """
    Deploys the Planner agent with an integrated A2A server to Vertex AI Agent Engines.
    Uses a two-step process (create then update) to set the A2A_PUBLIC_BASE_URL.

    Args:
        project_id: GCP project ID.
        region: GCP region.
        staging_bucket_uri: GCS URI for staging ADK artifacts.

    Returns:
        The deployed and updated remote_app object from Vertex AI Agent Engines.
    """
    display_name = "Planner Agent (A2A-Embedded v2)"
    description = "Planner agent with an embedded A2A interface, updated deployment."

    logger.info(f"Starting deployment of '{display_name}' to Project: {project_id}, Region: {region}")

    # 1. Initialize Vertex AI SDK (idempotent if already called by deploy_all.py)
    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        logger.info(f"Vertex AI SDK initialized/re-initialized for project:{project_id}, location:{region}, staging:{staging_bucket_uri}")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI SDK: {e}", exc_info=True)
        raise

    # 2. Get/Create the core ADK Agent instance
    # Assuming planner_adk_module.root_agent is the LlmAgent instance
    planner_core_adk_agent = planner_adk_module.root_agent
    if planner_core_adk_agent is None:
        logger.error("The root_agent in agents.planner.agent is None.")
        raise ValueError("Planner ADK agent (root_agent) is not initialized.")
    logger.info(f"Using ADK Planner agent: {getattr(planner_core_adk_agent, 'name', 'Unnamed')}")

    # 3. Create the A2AStarletteApplication instance
    # This function expects the instantiated ADK agent
    a2a_starlette_app = create_planner_a2a_server(passed_adk_planner_agent=planner_core_adk_agent)
    logger.info(f"A2AStarletteApplication for Planner created: {type(a2a_starlette_app).__name__}")

    # 4. Dynamically create a requirements.txt for this deployment
    # This file will be in the CWD of where deploy.py is executed (likely repo root if called by deploy_all.py)
    # ADK's `agent_engines.create` will pick it up if `requirements=["requirements.txt"]` is used.
    # Ensure this path is correct or adjust as needed if deploy_all.py changes CWD.
    # For simplicity, assuming CWD is repo root.
    temp_requirements_file = "temp_planner_requirements.txt"
    with open(temp_requirements_file, "w") as f:
        f.write("uvicorn>=0.20.0 # Specify a version if needed\n")
        f.write("fastapi>=0.95.0 # Specify a version if needed\n")
        # a2a-sdk/a2a-python should be included via google-cloud-aiplatform[adk] or a direct common lib
        # If not, add "a2a-python" or specific "a2a-sdk" package name here
        f.write(f"google-cloud-aiplatform[agent_engines,adk]>={vertexai.__version__}\n") # Use current SDK version
        # Add other specific direct dependencies of planner/agent.py or planner/a2a_server.py if any
        # For example, if planner uses a specific library not in a2a_common:
        # f.write("some-planner-specific-dependency==1.2.3\n")
    logger.info(f"Dynamically created requirements file: {temp_requirements_file}")

    # 5. Define the AdkApp
    adk_app_instance = AdkApp(
        agent=planner_core_adk_agent,
        setup_fn=lambda: start_uvicorn_in_thread(a2a_starlette_app, "0.0.0.0", A2A_UVICORN_PORT_PLANNER)
    )
    logger.info(f"AdkApp instance created. Uvicorn for A2A will start on internal port {A2A_UVICORN_PORT_PLANNER} via setup_fn.")

    # 6. Initial Deployment (without A2A_PUBLIC_BASE_URL)
    env_vars_initial = {
        "A2A_UVICORN_PORT_PLANNER": str(A2A_UVICORN_PORT_PLANNER),
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "TOOLS_GOOGLE_API_KEY": os.environ.get("TOOLS_GOOGLE_API_KEY", ""),
        # Do NOT set A2A_PUBLIC_BASE_URL here yet
    }
    env_vars_initial = {k: v for k, v in env_vars_initial.items() if v is not None}
    logger.info(f"Initial environment variables for agent_engines.create: {env_vars_initial}")

    # Define extra_packages. These are paths relative to the CWD where `deploy.py` (or `deploy_all.py`) runs.
    # Usually, this is the repository root.
    # ADK needs these to find your custom modules (agent code, a2a_server, utils).
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    extra_packages_for_deployment = [
        os.path.join(repo_root, "agents/app_utils"),  # For uvicorn_runner
        os.path.join(repo_root, "agents/planner"),    # The planner agent's own code
        # Ensure a2a_common (or its replacement instavibe_common_lib) is in the dynamic requirements.txt
        # or installed in the environment running this script if it's a prerequisite for pickling.
    ]
    for pkg_path in extra_packages_for_deployment:
        if not os.path.exists(pkg_path):
            logger.error(f"Critical: Extra package path for deployment not found: {pkg_path}")
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")
    logger.info(f"Extra packages for deployment: {extra_packages_for_deployment}")

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

        # 7. Retrieve public endpoint URI
        if not (hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
                hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri):
            logger.error("Failed to retrieve public_endpoint_uri after initial deployment.")
            raise RuntimeError("Could not get public_endpoint_uri for the deployed agent.")

        public_a2a_url = remote_app.gca_resource.public_endpoint_uri
        logger.info(f"Retrieved public_endpoint_uri: {public_a2a_url}")

        # 8. Update Agent with A2A_PUBLIC_BASE_URL
        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = public_a2a_url

        logger.info(f"Calling agent_engines.update for '{remote_app.name}' to set A2A_PUBLIC_BASE_URL...")
        logger.info(f"Updated environment variables: {env_vars_updated}")

        # For update, we pass the same AdkApp definition and requirements.
        # The `agent_engine` parameter in `update` expects the AdkApp object.
        updated_remote_app = agent_engines.update(
            resource_name=remote_app.name, # Use full resource name
            agent_engine=adk_app_instance,
            requirements=[temp_requirements_file],
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_updated
        )
        logger.info(f"Agent '{display_name}' updated successfully with A2A_PUBLIC_BASE_URL. New resource state name: {updated_remote_app.name}")

        # The agent_card.url in the a2a_starlette_app object is for local reference if needed,
        # the running instance inside the container will use the A2A_PUBLIC_BASE_URL from its env.
        # a2a_starlette_app.agent_card.url = public_a2a_url
        # logger.info(f"Locally updated AgentCard URL in a2a_app object to: {public_a2a_url}")

        return updated_remote_app

    except Exception as e:
        logger.error(f"ERROR during deployment process for '{display_name}': {e}", exc_info=True)
        # Clean up remote_app if initial create succeeded but update failed, or if any other error.
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed agent '{remote_app.name}' due to error.")
                agent_engines.delete(remote_app.name, force=True)
                logger.info(f"Successfully deleted partially deployed agent '{remote_app.name}'.")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed agent '{remote_app.name}': {del_e}", exc_info=True)
        raise # Re-raise the original error
    finally:
        # Clean up the temporary requirements file
        if os.path.exists(temp_requirements_file):
            try:
                os.remove(temp_requirements_file)
                logger.info(f"Removed temporary requirements file: {temp_requirements_file}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_requirements_file}: {e_rm}")

# Note: The __main__ block for standalone testing of this script would be complex
# as it needs GOOGLE_CLOUD_PROJECT, LOCATION, STAGING_BUCKET to be set correctly.
# It's better to test this via deploy_all.py.
