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
import logging # Added

# from agents.planner.planner_agent import PlannerAgent # No longer deploying this wrapper directly
from agents.planner import agent as planner_main_agent_module # Import the module containing root_agent

# Load environment variables from the root .env file
# This ensures that any implicit environment variable reads by underlying
# libraries (e.g., Google Cloud clients if project_id isn't explicit everywhere)
# are configured from the root .env.
# Keep load_dotenv for now, as PlannerAgent or other setup might use it.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__) # Added

def deploy_planner_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Planner Agent as a Vertex AI Reasoning Engine using the ADK,
    packaging the agent's source code and local wheel dependency.
    """
    display_name = "Planner Agent"
    description = """This agent helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions."""

    # Vertex AI Staging bucket is typically set globally via vertexai.init()
    # ADK's create() command will use this global configuration.
    # Ensure vertexai.init(project=project_id, location=region, staging_bucket="gs://your-bucket")
    # has been called, likely in a main deployment script (e.g., deploy_all.py).
    # We remove direct staging_bucket_uri parsing and GCS client instantiation here.

    # local_agent_instance = PlannerAgent() # Old: Deployed the wrapper
    local_agent_instance = planner_main_agent_module.root_agent # New: Deploy the LlmAgent
    if local_agent_instance is None:
        raise ValueError("Error: The root_agent in agents.planner.agent is None. Ensure it's initialized.")
    adk_app = AdkApp(agent=local_agent_instance)

    # base_dir is the repository root.
    requirements_path = os.path.join(base_dir, "agents/planner/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_path):
        with open(requirements_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    else:
        # Log a warning if not found, but proceed with empty list as ADK might allow this
        # or base image might be sufficient for some agents.
        # However, for this agent, requirements are likely crucial.
        log.warning(f"Requirements file not found: {requirements_path}. Proceeding with an empty requirements list.")
        # Consider raising an error if requirements are essential:
        # raise FileNotFoundError(f"Requirements file {requirements_path} not found.")

    # Ensure nest_asyncio is present with the correct version constraint
    # This matches the logic in platform_mcp_client/deploy.py
    nest_asyncio_req_line = "nest_asyncio>=1.5.0,<2.0.0" # ADK often needs this for its async ops
    found_nest_asyncio = False
    for i, req in enumerate(requirements_list):
        if req.startswith("nest_asyncio"):
            # If found, ensure it matches the desired constraint.
            # The planner's requirements.txt already has nest_asyncio==1.6.0, which satisfies this.
            # This logic is more about ensuring a general constraint if it were different or missing.
            # For now, if it's specified as nest_asyncio==1.6.0, this block might not alter it,
            # but if it was, e.g., nest_asyncio==1.4.0, it would update it.
            # To be precise like platform_mcp_client, we could enforce the exact string if different.
            # Let's assume if it starts with "nest_asyncio" and is in requirements.txt, it's the one we want (1.6.0).
            # The logic from platform_mcp_client was more about adding it if missing or updating if version was too old.
            # Given planner's reqs.txt has 1.6.0, this should be fine.
            # For consistency with platform_mcp_client, let's ensure the line matches if found, or add if not.
            if req != nest_asyncio_req_line:
                log.info(f"Updating nest_asyncio requirement from '{req}' to '{nest_asyncio_req_line}' in {requirements_path} (for deployment list)")
                requirements_list[i] = nest_asyncio_req_line
            found_nest_asyncio = True
            break
    if not found_nest_asyncio:
        log.info(f"Adding '{nest_asyncio_req_line}' to requirements list for {display_name} deployment.")
        requirements_list.append(nest_asyncio_req_line)


    # Define paths for extra_packages relative to base_dir
    # base_dir is the repository root.
    # The ADK expects these paths to be directories or .whl files.
    # The 'agents/app' and 'agents/planner' are directories containing package code.
    # The 'agents/a2a_common-0.1.0-py3-none-any.whl' is a wheel file.
    extra_packages = [
        os.path.join(base_dir, "agents")
    ]

    # Verify extra_packages paths exist
    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}")
    print(f"  Requirements file (source): {requirements_path}") # Log original source
    print(f"  Processed requirements list (for deployment): {requirements_list}") # Log processed list
    print(f"  Extra packages: {extra_packages}")

    # Prepare environment variables for the deployed agent
    env_vars_for_deployment = {
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        # AGENTS_PLANNER_AGENT_NAME is set via agent.AGENT_NAME
        # AGENTS_PLANNER_MODEL_NAME is set via agent.MODEL_NAME
        # API keys for tools like google_search should be picked up if root .env is loaded by agent.py
    }
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v}
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")

    # The ADK's create() function handles packaging and uploading.
    # It uses the globally configured staging bucket from vertexai.init().
    # project and location are also typically set by vertexai.init() but can be overridden.
    try:
        remote_agent = agent_engines.create(
            adk_app, # Pass the AdkApp instance
            display_name=display_name,
            description=description,
            requirements=requirements_list, # Pass the processed list
            extra_packages=extra_packages,
            env_vars=env_vars_for_deployment, # Changed to env_vars
            # project=project_id, # Optional: ADK uses vertexai.init() global config
            # location=region,    # Optional: ADK uses vertexai.init() global config
            # staging_bucket_uri can be specified to override global, but usually not needed.
            # gcs_dir_name can also be specified if a custom GCS path within the staging bucket is desired.
            # python_version can be specified if needed, e.g., python_version="3.9"
            # staging_bucket can be set via vertexai.init() globally
        )
    except Exception as e:
        print(f"ERROR: ADK agent_engines.create() failed: {e}")
        # Consider if specific error handling or re-raising is needed.
        # For example, if google.auth.exceptions.DefaultCredentialsError occurs here,
        # it means vertexai.init() might not have been called or failed.
        raise

    print(f"Planner Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name (usually available after operation completion): {remote_agent.name if remote_agent else 'Pending...'}") # .name might not be immediately populated depending on return type.
    # The create() method in ADK is synchronous and should return the deployed resource or raise an error.
    # If it returns a long-running operation, the access to .name might differ.
    # Assuming it returns the completed ReasoningEngine resource as per typical ADK behavior.
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent # Return the ADK representation of the Reasoning Engine


if __name__ == "__main__":
    print("Running Planner Agent deployment script...")
    # This __main__ block is primarily for direct execution of this script,
    # which might be useful for testing the deployment logic in isolation.
    # In a typical setup, deploy_all.py or a similar script would call deploy_planner_main_func.

    # For direct execution, ensure GOOGLE_APPLICATION_CREDENTIALS is set,
    # or you've run `gcloud auth application-default login`.
    # Also, ensure vertexai.init() is called with necessary parameters.

    # Example:
    # try:
    #     # These would typically come from command-line args or a config file
    #     PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
    #     REGION = "us-central1"
    #     STAGING_BUCKET = os.environ.get("VERTEX_AI_STAGING_BUCKET") # e.g., "gs://your-unique-bucket-name"
    #     REPO_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


    #     if not PROJECT_ID:
    #         raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
    #     if not STAGING_BUCKET:
    #         raise ValueError("VERTEX_AI_STAGING_BUCKET environment variable not set (e.g., gs://your-bucket).")

    #     print(f"Initializing Vertex AI for project: {PROJECT_ID}, region: {REGION}, staging: {STAGING_BUCKET}")
    #     vertexai.init(project=PROJECT_ID, location=REGION, staging_bucket=STAGING_BUCKET)

    #     print(f"Using repository base directory: {REPO_BASE_DIR}")

    #     deployed_re = deploy_planner_main_func(
    #         project_id=PROJECT_ID,
    #         region=REGION,
    #         base_dir=REPO_BASE_DIR
    #     )
    #     print(f"Deployment script finished. Deployed Reasoning Engine: {deployed_re.name if deployed_re else 'Failed or not available'}")

    # except Exception as e:
    #     print(f"An error occurred during the __main__ execution: {e}")
    #     import traceback
    #     traceback.print_exc()

    print("Planner deployment script __main__ section is illustrative.")
    print("Actual deployment is typically orchestrated by a higher-level script like deploy_all.py,")
    print("which should handle vertexai.init() and pass appropriate parameters.")
