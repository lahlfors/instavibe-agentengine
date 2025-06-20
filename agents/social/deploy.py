import os
# import uuid # No longer needed for generating unique GCS filenames
# from urllib.parse import urlparse # No longer needed for parsing staging_bucket_uri
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
# import google.auth # For google.auth.exceptions, potentially still needed if vertexai.init() fails early
from dotenv import load_dotenv # For loading .env file

from agents.social.social_agent import SocialAgent

# Load environment variables from the root .env file
# This ensures that any implicit environment variable reads by underlying
# libraries (e.g., Google Cloud clients if project_id isn't explicit everywhere)
# or by the SocialAgent instantiation itself are configured from the root .env.
# Keep load_dotenv for now.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

import logging # Added
log = logging.getLogger(__name__) # Added

def deploy_social_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Social Agent as a Vertex AI Reasoning Engine using the ADK.

    Args:
        project_id: The Google Cloud project ID. (Used by vertexai.init if not already set)
        region: The Google Cloud region for deployment. (Used by vertexai.init if not already set)
        base_dir: The base directory of the repository (repo root).
    """
    display_name = "Social Agent"
    description = """This agent analyzes social profiles, including posts, friend networks, and event participation, to generate comprehensive summaries and identify common ground between individuals."""

    # Vertex AI Staging bucket is typically set globally via vertexai.init()
    # ADK's create() command will use this global configuration.
    # Ensure vertexai.init(project=project_id, location=region, staging_bucket="gs://your-bucket")
    # has been called, likely in a main deployment script (e.g., deploy_all.py).

    local_agent_instance = SocialAgent()
    if local_agent_instance is None: # Check updated variable name
        raise ValueError("SocialAgent instantiation returned None. Check agent initialization.")
    adk_app = AdkApp(agent=local_agent_instance)

    # base_dir is assumed to be the repository root.
    requirements_path = os.path.join(base_dir, "agents/social/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_path):
        with open(requirements_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    else:
        log.warning(f"Requirements file not found: {requirements_path}. Proceeding with an empty requirements list.")

    nest_asyncio_req_line = "nest_asyncio>=1.5.0,<2.0.0"
    found_nest_asyncio = False
    # Check if nest_asyncio is in agents/social/requirements.txt (it's not currently, so this will add it)
    for i, req in enumerate(requirements_list):
        if req.startswith("nest_asyncio"):
            if req != nest_asyncio_req_line:
                log.info(f"Updating nest_asyncio requirement from '{req}' to '{nest_asyncio_req_line}' in {requirements_path} (for deployment list)")
                requirements_list[i] = nest_asyncio_req_line
            found_nest_asyncio = True
            break
    if not found_nest_asyncio:
        log.info(f"Adding '{nest_asyncio_req_line}' to requirements list for {display_name} deployment.")
        requirements_list.append(nest_asyncio_req_line)

    extra_packages = [
        os.path.join(base_dir, "agents")
    ]

    # Verify extra_packages paths exist
    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}")
    print(f"  Requirements file (source): {requirements_path}")
    print(f"  Processed requirements list (for deployment): {requirements_list}")
    print(f"  Extra packages: {extra_packages}")

    # Prepare environment variables for the deployed agent
    env_vars_for_deployment = {
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id, # Use the project_id passed to the function
        "COMMON_GOOGLE_CLOUD_LOCATION": region,   # Use the region passed to the function
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        # Add any other essential env vars the agent might need at runtime
    }
    # Filter out any empty values to avoid passing VAR=""
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v}
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")

    try:
        remote_agent = agent_engines.create(
            adk_app, # Pass the AdkApp instance
            display_name=display_name,
            description=description,
            requirements=requirements_list, # Pass the processed list
            extra_packages=extra_packages,
            environment_variables=env_vars_for_deployment, # Pass the env vars
            # project=project_id, # Optional: ADK uses vertexai.init() global config
            # location=region,    # Optional: ADK uses vertexai.init() global config
        )
    except Exception as e:
        print(f"ERROR: ADK agent_engines.create() failed for Social Agent: {e}")
        raise

    print(f"Social Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent
