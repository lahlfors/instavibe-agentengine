# planner/deploy.py
import os
import asyncio
import threading
import logging

from google.cloud import aiplatform as vertexai # Added this import
from vertexai.preview import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
# Make sure PlannerAgent is correctly imported. Assuming it's the ADK LlmAgent instance or class.
# If PlannerAgent is the class, it needs to be instantiated.
# If planner_adk_module.root_agent is the instance, use that.
from agents.planner.agent import root_agent as planner_core_agent_instance # Adjusted to use the instance
from agents.planner.a2a_server import create_planner_a2a_server, A2A_UVICORN_PORT_PLANNER # Use specific port
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread
from a2a.server import A2AServer # For type hinting run_local_uvicorn

#from google.cloud.aiplatform_v1 import types as aip_types # Not strictly needed for this script version

# Use the specific port constant from a2a_server.py
# A2A_UVICORN_PORT = 8001 # This will be A2A_UVICORN_PORT_PLANNER

logger = logging.getLogger(__name__) # Changed from logging.basicConfig
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())


# Function name changed to match how it's imported in deploy_all.py
def deploy_planner_main_func(project_id: str, region: str, staging_bucket_uri: str, base_dir: str): # Added base_dir back
    """Deploys the Planner agent with integrated A2A server."""
    display_name = "Planner Agent (A2A-Embedded v2)" # Consistent with deploy_all
    logger.info(f"Starting deployment of '{display_name}' to Project: {project_id}, Region: {region}")

    # Initialize ADK (idempotent)
    # The main deploy_all.py should ideally handle this once globally.
    # However, individual deploy scripts often include it for standalone testability.
    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        logger.info(f"Vertex AI SDK initialized/re-initialized for project:{project_id}, location:{region}, staging:{staging_bucket_uri}")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI SDK: {e}", exc_info=True)
        raise

    # planner_core_agent is now planner_core_adk_agent_instance imported from agents.planner.agent
    if planner_core_adk_agent_instance is None:
        logger.error("planner_core_adk_agent_instance (root_agent from agents.planner.agent) is None.")
        raise ValueError("Planner ADK agent instance not found.")

    # Create A2A Server instance
    a2a_server = create_planner_a2a_server(planner_core_adk_agent_instance)
    logger.info("A2AServer instance for Planner created.")

    # Create a temporary requirements file for this deployment
    # Path should be relative to where deploy_all.py runs (repo root) or use absolute path
    # base_dir is expected to be the repo root passed from deploy_all.py
    temp_requirements_file_path = os.path.join(base_dir, "temp_planner_requirements.txt")

    current_vertexai_version = getattr(vertexai, '__version__', '1.88.0') # Fallback if __version__ not found
    with open(temp_requirements_file_path, "w") as f:
        f.write("uvicorn>=0.20.0\n")
        f.write("fastapi>=0.95.0\n")
        f.write("a2a-sdk\n") # Assuming 'a2a-sdk' is the correct PyPI package name for the `a2a` imports
        f.write(f"google-cloud-aiplatform[agent_engines,adk]>={current_vertexai_version}\n")
        f.write("nest_asyncio>=1.5.0,<2.0.0\n")
        # Add other planner-specific requirements from agents/planner/requirements.txt if they exist
        original_req_path = os.path.join(base_dir, "agents/planner/requirements.txt")
        if os.path.exists(original_req_path):
            with open(original_req_path, "r") as orf:
                for line in orf:
                    stripped_line = line.strip()
                    if stripped_line and not stripped_line.startswith("#"):
                        # Avoid duplicating already added core dependencies
                        if not any(core_dep in stripped_line for core_dep in ["uvicorn", "fastapi", "a2a-sdk", "google-cloud-aiplatform", "nest_asyncio"]):
                            f.write(f"{stripped_line}\n")
    logger.info(f"Dynamically created requirements file: {temp_requirements_file_path}")


    # Create the AdkApp
    adk_app = AdkApp(
        agent=planner_core_adk_agent_instance, # Pass the ADK LlmAgent
        setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_PLANNER),
    )
    logger.info(f"AdkApp created. Uvicorn will run on port {A2A_UVICORN_PORT_PLANNER} in container.")

    # Initial Deployment WITHOUT A2A_PUBLIC_BASE_URL
    env_vars_initial = {
        "A2A_UVICORN_PORT_PLANNER": str(A2A_UVICORN_PORT_PLANNER),
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "TOOLS_GOOGLE_API_KEY": os.environ.get("TOOLS_GOOGLE_API_KEY", ""),
    }
    env_vars_initial = {k:v for k,v in env_vars_initial.items() if v is not None}
    logger.info(f"Initial env_vars for create: {env_vars_initial}")

    # Define extra_packages. These are paths relative to the CWD where `deploy_all.py` runs.
    # base_dir is the repo_root.
    extra_packages_for_deployment = [
        os.path.join(base_dir, "agents/app_utils"),
        os.path.join(base_dir, "agents/planner"),
        # Ensure a2a_common or its replacement is installed via requirements if needed by planner's core logic
    ]
    for pkg_path in extra_packages_for_deployment:
        if not os.path.exists(pkg_path):
            logger.error(f"Critical: Extra package path for deployment not found: {pkg_path}")
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")
    logger.info(f"Extra packages for deployment: {extra_packages_for_deployment}")


    remote_app = None
    try:
        logger.info(f"Calling initial agent_engines.create for '{display_name}'")
        remote_app = agent_engines.create(
            agent_engine=adk_app,
            display_name=display_name, # Added display_name
            description=description,   # Added description
            requirements=[temp_requirements_file_path], # Pass path to temp requirements
            extra_packages=extra_packages_for_deployment,
            env_vars=env_vars_initial
        )
        logger.info(f"Initial deployment of '{display_name}' successful. Resource name: {remote_app.name}")

        # Retrieve public endpoint URI
        if not (hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
                hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri):
            logger.error(f"Failed to retrieve public_endpoint_uri for '{display_name}'.")
            raise RuntimeError(f"Could not get public_endpoint_uri for {display_name}.")

        retrieved_a2a_url = remote_app.gca_resource.public_endpoint_uri
        logger.info(f"Retrieved public_endpoint_uri for '{display_name}': {retrieved_a2a_url}")

        # Update the agent with the A2A_PUBLIC_BASE_URL
        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = retrieved_a2a_url

        logger.info(f"Calling agent_engines.update for '{remote_app.name}' to set A2A_PUBLIC_BASE_URL...")
        logger.info(f"Updated env_vars for update: {env_vars_updated}")

        # The agent_engine param for update should be the same AdkApp object
        remote_app_updated = agent_engines.update(
            resource_name=remote_app.name,
            agent_engine=adk_app,
            requirements=[temp_requirements_file_path], # Pass path to temp requirements
            extra_packages=extra_packages_for_deployment,
            env_vars=env_vars_updated
        )
        logger.info(f"'{display_name}' updated successfully with A2A_PUBLIC_BASE_URL. Current resource name: {remote_app_updated.name}")

        # This updates the AgentCard URL for the a2a_server object in *this script's memory*.
        # The running instance inside the container relies on the A2A_PUBLIC_BASE_URL env var.
        if hasattr(a2a_server, 'agent_card') and a2a_server.agent_card:
            a2a_server.agent_card.url = retrieved_a2a_url
            logger.info(f"Locally updated AgentCard URL in a2a_server object to: {retrieved_a2a_url}")

        return remote_app_updated

    except Exception as e:
        logger.error(f"ERROR during deployment process for '{display_name}': {e}", exc_info=True)
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed agent '{remote_app.name}' due to error.")
                agent_engines.delete(remote_app.name, force=True)
                logger.info(f"Successfully deleted partially deployed agent '{remote_app.name}'.")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed agent '{remote_app.name}': {del_e}", exc_info=True)
        raise
    finally:
        # Clean up the temporary requirements file
        if os.path.exists(temp_requirements_file_path):
            try:
                os.remove(temp_requirements_file_path)
                logger.info(f"Removed temporary requirements file: {temp_requirements_file_path}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_requirements_file_path}: {e_rm}")

# Local testing block (optional, can be kept for direct script testing)
async def run_local_uvicorn_for_planner(a2a_server_instance: A2AServer):
  """Runs the Uvicorn server locally for the planner."""
  # Use the port defined in a2a_server.py for consistency
  config = uvicorn.Config(a2a_server_instance.build(), host="0.0.0.0", port=A2A_UVICORN_PORT_PLANNER, log_level="info")
  server = uvicorn.Server(config)
  await server.serve()

if __name__ == "__main__":
    logger.info("Attempting to run Planner A2A server locally for testing...")
    # Set required environment variables for local run if not already set by .env
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "your-local-gcp-project")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
    os.environ.setdefault("GOOGLE_CLOUD_STAGING_BUCKET", "gs://your-local-staging-bucket")
    os.environ.setdefault("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_PLANNER}")
    os.environ.setdefault("A2A_UVICORN_PORT_PLANNER", str(A2A_UVICORN_PORT_PLANNER))


    try:
        # Instantiate the core ADK agent (this might require its own .env loading if not handled globally)
        # Ensure planner_adk_module.root_agent is available
        if planner_core_adk_agent_instance is None:
             # Attempt to load it if module was imported but root_agent not init'd (e.g. if planner.agent needs specific setup)
            from agents.planner.agent import root_agent as planner_agent_main_instance
            if planner_agent_main_instance is None:
                raise ValueError("Planner core ADK agent (root_agent) could not be loaded for local test.")
            current_planner_agent = planner_agent_main_instance
        else:
            current_planner_agent = planner_core_adk_agent_instance

        logger.info(f"Using planner agent for local run: {getattr(current_planner_agent, 'name', 'Unnamed')}")

        local_a2a_server = create_planner_a2a_server(current_planner_agent)
        logger.info(f"Locally created A2AServer for Planner. Card URL: {local_a2a_server.agent_card.url}")
        asyncio.run(run_local_uvicorn_for_planner(local_a2a_server))

    except Exception as e:
        logging.error(f"Failed to run planner agent locally: {e}", exc_info=True)

    # The deployment guard from the example is good practice if this __main__ also tried to deploy.
    # For just local Uvicorn run, it's not strictly needed for cleanup of cloud resources.
    # planner_remote_app = None # Define for finally block
    # try:
    #   planner_remote_app = deploy_planner_agent() # This would call the main function
    # except Exception as e:
    #    logging.error(f"Failed to deploy planner agent: {e}")
    # finally:
    #    if planner_remote_app and hasattr(planner_remote_app, 'name') and planner_remote_app.name:
    #      logging.info(f"Attempting to delete deployed test resource: {planner_remote_app.name}")
    #      agent_engines.delete(planner_remote_app.name, force=True)
    #      logging.info(f"Deleted test resource: {planner_remote_app.name}")
