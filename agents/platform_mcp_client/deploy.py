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

def deploy_platform_mcp_client_main_func(project_id: str, region: str, base_dir: str):
    """Deploys the Platform MCP Client Agent to Vertex AI Reasoning Engines using ADK."""

    display_name = "Platform MCP Client Agent"
    description = "An agent that connects to an MCP Tool Server to provide tools for other agents or clients. It can interact with Instavibe services like creating posts and events."

    # vertexai.init should be called externally, e.g. in deploy_all.py
    # project, region, staging_bucket are picked up from that global config.

    local_agent_instance = platform_mcp_client_agent_module.root_agent
    if local_agent_instance is None:
        raise ValueError("Error: The root_agent in platform_mcp_client.agent is None. Ensure it's initialized.")
    adk_app = AdkApp(agent=local_agent_instance)

    # base_dir is the repository root.
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
        os.path.join(base_dir, "agents")
    ]

    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}") # Informational
    # Requirements path is still logged for info, but list is used for deployment
    print(f"  Requirements file (source): {requirements_path}")
    print(f"  Processed requirements list (for deployment): {requirements_list}")
    print(f"  Extra packages: {extra_packages}")

    # Prepare environment variables for the deployed agent
    env_vars_for_deployment = {
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "TOOLS_INSTAVIBE_MCP_SERVER_BASE_URL": os.environ.get("TOOLS_INSTAVIBE_MCP_SERVER_BASE_URL", "")
        # Add other necessary env vars for Platform MCP Client
    }
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v}
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")

    try:
        remote_agent = agent_engines.create(
            adk_app,  # Pass the AdkApp instance
            display_name=display_name,
            description=description,
            requirements=requirements_list, # Pass the processed list
            extra_packages=extra_packages,
            env_vars=env_vars_for_deployment, # Changed to env_vars
            # project=project_id, # Optional: ADK uses vertexai.init() global config
            # location=region,    # Optional: ADK uses vertexai.init() global config
        )
    except Exception as e:
        print(f"ERROR: ADK agent_engines.create() failed for Platform MCP Client Agent: {e}")
        raise

    print(f"Platform MCP Client Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent
