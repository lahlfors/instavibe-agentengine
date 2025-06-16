import os
# import uuid # No longer needed
# from urllib.parse import urlparse # No longer needed
# import cloudpickle # Handled by ADK
# import tarfile # Handled by ADK
# import tempfile # Handled by ADK
# import shutil # Handled by ADK

from google.cloud import aiplatform as vertexai # Standard alias
from vertexai.preview import reasoning_engines # ADK for deployment
# from google.cloud.aiplatform_v1.services import reasoning_engine_service # GAPIC, removed
# from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC # GAPIC, removed
# from google.cloud.aiplatform_v1.types import ReasoningEngineSpec # GAPIC, removed
# from google.cloud import storage # Handled by ADK or not needed directly
# import google.auth # For google.auth.exceptions

from dotenv import load_dotenv # For loading .env file
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

# Load environment variables from the root .env file
# This is crucial for capturing AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES at deployment time.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


def deploy_orchestrate_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Orchestrate Agent to Vertex AI Reasoning Engines using ADK.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository (repo root).
    """
    display_name = "Orchestrate Agent"
    description = """
  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work on helping user to get social 
"""

    # vertexai.init() should be called externally (e.g., in deploy_all.py)
    # project, region, staging_bucket are picked up from that global config.

    # Instantiate the agent. The ADK will pickle this instance.
    # If OrchestrateServiceAgent reads AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES from os.environ in its __init__,
    # it will do so in the *deployed* environment, which will be set by `env_vars` below.
    local_agent = OrchestrateServiceAgent()

    # Define environment variables for the deployed Reasoning Engine
    # These are read from the deployment environment (where this script runs)
    # and passed to the remote environment where the agent executes.
    remote_agent_addresses_str = os.getenv("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES", "")
    env_vars_for_deployment = {
        "AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES": remote_agent_addresses_str
    }
    print(f"Deployment-time AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES: '{remote_agent_addresses_str}' will be set for the deployed agent.")


    # base_dir is the repository root.
    requirements_path = os.path.join(base_dir, "agents/orchestrate/requirements.txt")
    if not os.path.exists(requirements_path):
        raise FileNotFoundError(f"Requirements file {requirements_path} not found.")

    extra_packages = [
        os.path.join(base_dir, "agents/a2a_common-0.1.0-py3-none-any.whl"),
        os.path.join(base_dir, "agents/app"),
        os.path.join(base_dir, "agents/orchestrate")
    ]

    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}") # Informational
    print(f"  Requirements file: {requirements_path}")
    print(f"  Extra packages: {extra_packages}")
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")


    try:
        remote_agent = reasoning_engines.deploy(
            local_agent,
            requirements=requirements_path,
            extra_packages=extra_packages,
            display_name=display_name,
            description=description,
            env_vars=env_vars_for_deployment, # Pass environment variables here
            # project=project_id, # Optional, from vertexai.init()
            # location=region,    # Optional, from vertexai.init()
        )
    except Exception as e:
        print(f"ERROR: ADK reasoning_engines.create() failed for Orchestrate Agent: {e}")
        raise

    print(f"Orchestrate Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent