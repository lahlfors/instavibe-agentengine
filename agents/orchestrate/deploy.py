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
#
# from google.cloud import storage # Handled by ADK or not needed directly
# import google.auth # For google.auth.exceptions
import logging # For logging
from typing import Optional # For Optional type hint

from dotenv import load_dotenv # For loading .env file
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

# Load environment variables from the root .env file
# This is crucial for capturing AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES at deployment time.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__)

def deploy_orchestrate_main_func(project_id: str, region: str, base_dir: str, dynamic_remote_agent_addresses: Optional[str] = None):
    """
    Deploys the Orchestrate Agent to Vertex AI Reasoning Engines using ADK.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository (repo root).
        dynamic_remote_agent_addresses: Optional string of comma-separated remote agent addresses.
    """
    display_name = "Orchestrate Agent"
    description = """
  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work on helping user to get social 
"""

    # vertexai.init() should be called externally (e.g., in deploy_all.py)
    # project, region, staging_bucket are picked up from that global config.

    # Instantiate the agent. The ADK will pickle this instance.
    # The OrchestrateServiceAgent constructor requires remote_agent_addresses_str.

    remote_agent_addresses_str_from_env = os.getenv("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES", "")
    if dynamic_remote_agent_addresses:
        remote_agent_addresses_str = dynamic_remote_agent_addresses
        log.info(f"Using dynamically provided remote agent addresses for OrchestrateServiceAgent: {remote_agent_addresses_str}")
    else:
        remote_agent_addresses_str = remote_agent_addresses_str_from_env
        log.info(f"Using environment variable AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES for OrchestrateServiceAgent: {remote_agent_addresses_str}")

    if not remote_agent_addresses_str:
        log.warning("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES is not set from dynamic input or environment. Orchestrator may not connect to remote agents.")
        # Consider if this should be an error or just a warning. For now, warning.

    local_agent_instance = OrchestrateServiceAgent(remote_agent_addresses_str=remote_agent_addresses_str)
    adk_app = AdkApp(agent=local_agent_instance)

    # env_vars_for_deployment has been removed.
    # The agent constructor now receives the necessary configuration directly.
    # The print statement below now uses the final remote_agent_addresses_str
    print(f"OrchestrateServiceAgent initialized with remote agent addresses: '{remote_agent_addresses_str}'")


    # base_dir is the repository root.
    requirements_path = os.path.join(base_dir, "agents/orchestrate/requirements.txt")
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
    # print(f"  Environment variables for deployed agent: {env_vars_for_deployment}") # Removed


    try:
        remote_agent = agent_engines.create(
            adk_app,  # Pass the AdkApp instance
            display_name=display_name,
            description=description,
            requirements=requirements_path,
            extra_packages=extra_packages,
            # env_vars parameter removed as agent takes config via constructor
            # project=project_id, # Optional: ADK uses vertexai.init() global config
            # location=region,    # Optional: ADK uses vertexai.init() global config
        )
    except Exception as e:
        print(f"ERROR: ADK agent_engines.create() failed for Orchestrate Agent: {e}")
        raise

    print(f"Orchestrate Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent