import os
# import uuid # No longer needed for generating unique GCS filenames
# from urllib.parse import urlparse # No longer needed for parsing staging_bucket_uri
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
# import google.auth # For google.auth.exceptions, potentially still needed if vertexai.init() fails early
from dotenv import load_dotenv # For loading .env file

from agents.social.social_agent import SocialAgent

# Load environment variables from the root .env file
# This ensures that any implicit environment variable reads by underlying
# libraries (e.g., Google Cloud clients if project_id isn't explicit everywhere)
# or by the SocialAgent instantiation itself are configured from the root .env.
# Keep load_dotenv for now.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

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

    local_agent = SocialAgent()
    if local_agent is None:
        raise ValueError("SocialAgent instantiation returned None. Check agent initialization.")

    # base_dir is assumed to be the repository root.
    requirements_path = os.path.join(base_dir, "agents/social/requirements.txt")
    if not os.path.exists(requirements_path):
        raise FileNotFoundError(f"Requirements file {requirements_path} not found.")

    extra_packages = [
        os.path.join(base_dir, "agents/a2a_common-0.1.0-py3-none-any.whl"), # Path to the wheel
        os.path.join(base_dir, "agents/app"),  # Path to the 'app' package directory
        os.path.join(base_dir, "agents/social") # Path to the 'social' package directory
    ]

    # Verify extra_packages paths exist
    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}") # project_id and region are for info, ADK uses vertexai.init() config
    print(f"  Requirements file: {requirements_path}")
    print(f"  Extra packages: {extra_packages}")

    try:
        remote_agent = reasoning_engines.ReasoningEngine.create(
            local_agent,  # First positional argument: the agent instance
            display_name=display_name,
            description=description,
            requirements=requirements_path,
            extra_packages=extra_packages,
            # project=project_id, # Optional: ADK uses vertexai.init() global config
            # location=region,    # Optional: ADK uses vertexai.init() global config
        )
    except Exception as e:
        print(f"ERROR: ADK reasoning_engines.ReasoningEngine.create() failed for Social Agent: {e}")
        raise

    print(f"Social Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent
