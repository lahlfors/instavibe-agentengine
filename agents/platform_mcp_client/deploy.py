import os
# import uuid # No longer needed
# from urllib.parse import urlparse # No longer needed
# import cloudpickle # Handled by ADK
# import tarfile # Handled by ADK
# import tempfile # Handled by ADK
# import shutil # Handled by ADK

from google.cloud import aiplatform as vertexai # Standard alias
# from vertexai.preview import reasoning_engines # ADK for deployment - Old
from agents.app.agent_engine_app import AgentEngineApp # For wrapping
from vertexai import agent_engines # For the new create method
# from google.cloud.aiplatform_v1.services import reasoning_engine_service # GAPIC, removed
# from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC # GAPIC, removed
# from google.cloud.aiplatform_v1.types import ReasoningEngineSpec # GAPIC, removed
# from google.cloud import storage # Handled by ADK or not needed directly
# import google.auth # For google.auth.exceptions

from agents.platform_mcp_client.agent import PlatformMCPClientAgent
from dotenv import load_dotenv # For loading .env file
import logging # Added

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__) # Added

from typing import List, Optional

def deploy_platform_mcp_client_main_func(project_id: str, region: str, base_dir: str, extra_packages: Optional[List[str]] = None, env_vars: Optional[dict[str, str]] = None):
    """
    Deploys the Platform MCP Client Agent to Vertex AI Reasoning Engines using ADK.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository (repo root).
        extra_packages: A list of extra packages to install.
        env_vars: A dictionary of environment variables to pass to the agent.
    """

    display_name = "Platform MCP Client Agent"
    description = "An agent that connects to an MCP Tool Server to provide tools for other agents or clients. It can interact with Instavibe services like creating posts and events."

    # Get required config from environment variables.
    env_vars = env_vars or {}
    mcp_server_url = env_vars.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL") or os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL")
    if not mcp_server_url:
        raise ValueError("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL not found in provided env_vars or environment.")

    # This secret name is a placeholder, adjust if a real secret is used.
    api_key_secret_name = os.environ.get("MCP_API_KEY_SECRET", "default-mcp-api-key-secret")

    # Instantiate the agent directly, passing serializable config.
    local_agent_instance = PlatformMCPClientAgent(
        name="platform_mcp_client_agent",
    model="gemini-1.5-flash",
        mcp_server_address=mcp_server_url,
        api_key_secret=api_key_secret_name
    )

    adk_app = AgentEngineApp(agent=local_agent_instance)

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

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}") # Informational
    # Requirements path is still logged for info, but list is used for deployment
    print(f"  Requirements file (source): {requirements_path}")
    print(f"  Processed requirements list (for deployment): {requirements_list}")

    # Prepare environment variables for the deployed agent
    env_vars_for_deployment = {
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "TOOLS_INSTAVIBE_MCP_SERVER_BASE_URL": os.environ.get("TOOLS_INSTAVIBE_MCP_SERVER_BASE_URL", ""),
        "INSTAVIBE_GOOGLE_MAPS_API_KEY": os.getenv("INSTAVIBE_GOOGLE_MAPS_API_KEY")
    }
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v}
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")

    try:
        remote_agent = agent_engines.create(
            adk_app,  # Pass the AdkApp instance
            display_name=display_name,
            description=description,
            requirements=requirements_list, # Pass the processed list
            extra_packages=(extra_packages or []) + ["agents/app", "./common", "agents/a2a_common-0.1.0-py3-none-any.whl"],
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
