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

from agents.planner.planner_agent import PlannerAgent

# Load environment variables from the root .env file
# This ensures that any implicit environment variable reads by underlying
# libraries (e.g., Google Cloud clients if project_id isn't explicit everywhere)
# are configured from the root .env.
# Keep load_dotenv for now, as PlannerAgent or other setup might use it.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

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

    local_agent = PlannerAgent()

    requirements_path = os.path.join(base_dir, "agents/planner/requirements.txt")
    if not os.path.exists(requirements_path):
        raise FileNotFoundError(f"Requirements file {requirements_path} not found.")

    # Define paths for extra_packages relative to base_dir
    # base_dir is the repository root.
    # The ADK expects these paths to be directories or .whl files.
    # The 'agents/app' and 'agents/planner' are directories containing package code.
    # The 'agents/a2a_common-0.1.0-py3-none-any.whl' is a wheel file.
    extra_packages = [
        os.path.join(base_dir, "agents/a2a_common-0.1.0-py3-none-any.whl"), # Path to the wheel
        os.path.join(base_dir, "agents/planner") # Path to the 'planner' package directory
    ]

    # Verify extra_packages paths exist
    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}")
    print(f"  Requirements file: {requirements_path}")
    print(f"  Extra packages: {extra_packages}")

    # The ADK's create() function handles packaging and uploading.
    # It uses the globally configured staging bucket from vertexai.init().
    # project and location are also typically set by vertexai.init() but can be overridden.
    try:
        remote_agent = reasoning_engines.ReasoningEngine.create(
            local_agent,  # First positional argument: the agent instance
            display_name=display_name,
            description=description,
            requirements=requirements_path,
            extra_packages=extra_packages,
            # project=project_id, # Optional: ADK uses vertexai.init() global config
            # location=region,    # Optional: ADK uses vertexai.init() global config
            # staging_bucket_uri can be specified to override global, but usually not needed.
            # gcs_dir_name can also be specified if a custom GCS path within the staging bucket is desired.
            # python_version can be specified if needed, e.g., python_version="3.9"
        )
    except Exception as e:
        print(f"ERROR: ADK reasoning_engines.ReasoningEngine.create() failed: {e}")
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
