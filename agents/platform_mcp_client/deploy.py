import os
# import uuid # No longer needed
# from urllib.parse import urlparse # No longer needed
# import cloudpickle # Handled by ADK
# import tarfile # Handled by ADK
# import tempfile # Handled by ADK
# import shutil # Handled by ADK

from google.cloud import aiplatform as vertexai # Standard alias
# from vertexai.preview import reasoning_engines # ADK for deployment - Old
from vertexai.preview.reasoning_engines import AdkApp # For wrapping
from vertexai import agent_engines # For the new create method
# from google.cloud.aiplatform_v1.services import reasoning_engine_service # GAPIC, removed
# from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC # GAPIC, removed
# from google.cloud.aiplatform_v1.types import ReasoningEngineSpec # GAPIC, removed
# from google.cloud import storage # Handled by ADK or not needed directly
# import google.auth # For google.auth.exceptions

# Import the agent module that contains the `root_agent`
from agents.platform_mcp_client import agent as platform_mcp_client_agent_module
from dotenv import load_dotenv # For loading .env file
import logging # Added

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__) # Added

def deploy_platform_mcp_client_main_func(display_name: str, staging_bucket_uri: str):
    """
    Deploys the Platform MCP Client Agent to Vertex AI Reasoning Engines using ADK.
    Assumes vertexai.init() has been called globally with project, location, and staging_bucket.
    Args:
        display_name: The display name for the Reasoning Engine.
        staging_bucket_uri: The GCS URI for staging (passed for consistency, but global init is primary).
    """
    # project_id and region are picked up from the global vertexai.init()
    # staging_bucket_uri is also primarily from global init, passed here for logging/consistency.
    global_project_id = vertexai.get_project()
    global_location = vertexai.get_location()
    # staging_bucket_uri from param can be used for logging if desired or specific checks.
    log.info(f"Deploying Platform MCP Client Agent with display name: '{display_name}'")
    log.info(f"  Using global Project ID: {global_project_id}, Location: {global_location}")
    log.info(f"  Staging bucket (from global init, confirmed by param): {staging_bucket_uri}")


    description = "An agent that connects to an MCP Tool Server to provide tools for other agents or clients. It can interact with Instavibe services like creating posts and events."

    local_agent_instance = platform_mcp_client_agent_module.root_agent
    if local_agent_instance is None:
        raise ValueError("Error: The root_agent in platform_mcp_client.agent is None. Ensure it's initialized.")
    adk_app = AdkApp(agent=local_agent_instance)

    # Determine base_dir (repository root) dynamically
    # Assumes this script is at <repo_root>/agents/platform_mcp_client/deploy.py
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    log.info(f"  Determined repository base_dir: {base_dir}")

    requirements_path = os.path.join(base_dir, "agents/platform_mcp_client/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_path):
        with open(requirements_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    else:
        log.warning(f"Requirements file not found: {requirements_path}. Proceeding with an empty requirements list initially.")

    nest_asyncio_req_line = "nest_asyncio>=1.5.0,<2.0.0"
    found_nest_asyncio = False
    for i, req in enumerate(requirements_list):
        if req.startswith("nest_asyncio"):
            if req != nest_asyncio_req_line:
                log.info(f"Updating nest_asyncio requirement from '{req}' to '{nest_asyncio_req_line}' in {requirements_path}")
                requirements_list[i] = nest_asyncio_req_line
            found_nest_asyncio = True
            break
    if not found_nest_asyncio:
        log.info(f"Adding '{nest_asyncio_req_line}' to requirements list for {requirements_path}.")
        requirements_list.append(nest_asyncio_req_line)

    extra_packages = [
        os.path.join(base_dir, "agents") # Package the whole 'agents' directory
    ]

    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found relative to {base_dir}.")

    log.info(f"Starting deployment of '{display_name}' using ADK...")
    # Requirements path is still logged for info, but list is used for deployment
    log.info(f"  Requirements file (source): {requirements_path}")
    log.info(f"  Processed requirements list (for deployment): {requirements_list}")
    log.info(f"  Extra packages: {extra_packages}")

    # Prepare environment variables for the deployed agent
    # COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION will be set by Vertex AI based on the deployment region.
    # We should ensure that the other necessary env vars are picked up from the *current* environment where deploy_all.py is run.
    env_vars_for_deployment = {
        # These are usually automatically populated by Vertex AI in the deployed environment
        # "COMMON_GOOGLE_CLOUD_PROJECT": global_project_id,
        # "COMMON_GOOGLE_CLOUD_LOCATION": global_location,
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL": os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL", ""),
        # Add other necessary env vars for Platform MCP Client from the current execution environment
    }
    # Filter out any env vars that weren't set to avoid sending empty strings if not desired
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v is not None and v != ""}
    log.info(f"  Environment variables for deployed agent (from current env): {env_vars_for_deployment}")

    if not env_vars_for_deployment.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL"):
        log.error("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is not set in the environment. Deployment will likely fail or agent will not function.")
        # Potentially raise an error here if it's critical
        # raise ValueError("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL must be set in the environment")


    try:
        remote_agent = agent_engines.create(
            app=adk_app,  # Pass the AdkApp instance, changed param name from adk_app to app
            display_name=display_name, # Use the passed display_name
            description=description,
            requirements=requirements_list,
            extra_packages=extra_packages,
            environment_variables=env_vars_for_deployment, # Changed to environment_variables
            # project, location, staging_bucket are taken from vertexai.init() global config
        )
    except Exception as e:
        log.error(f"ERROR: ADK agent_engines.create() failed for {display_name}: {e}", exc_info=True)
        raise

    print(f"Platform MCP Client Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent
