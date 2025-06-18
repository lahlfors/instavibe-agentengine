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

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

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
    if not os.path.exists(requirements_path):
        raise FileNotFoundError(f"Requirements file {requirements_path} not found.")

    extra_packages = [
        os.path.join(base_dir, "agents")
    ]

    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}") # Informational
    print(f"  Requirements file: {requirements_path}")
    print(f"  Extra packages: {extra_packages}")

    try:
        remote_agent = agent_engines.create(
            adk_app,  # Pass the AdkApp instance
            display_name=display_name,
            description=description,
            requirements=requirements_path,
            extra_packages=extra_packages,
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
