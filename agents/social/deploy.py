import os
import uuid
import logging # For logging

# Import for agent_engines.create()
from vertexai.preview import agent_engines
import vertexai # For vertexai.init()

from dotenv import load_dotenv # For loading .env file
from agents.social.social_agent import SocialAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def deploy_social_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Social Agent to Vertex AI Agent Engine using agent_engines.create().
    """
    agent_name = "Social"
    display_name = f"{agent_name}AgentService-{str(uuid.uuid4())[:8]}" # Unique display name
    description = """This agent analyzes social profiles, including posts, friend networks, and event participation, to generate comprehensive summaries and identify common ground between individuals."""

    # Ensure Vertex AI is initialized (typically done in deploy_all.py or earlier)
    # vertexai.init(project=project_id, location=region, staging_bucket=os.environ.get("BUCKET_NAME_FOR_VERTEX_AI_STAGING"))

    # 1. Instantiate the agent
    local_agent_instance = SocialAgent()
    logger.info(f"Instantiated local {agent_name} agent: {type(local_agent_instance)}")

    # 2. Define requirements for agent_engines.create()
    # These should be core dependencies for SocialAgent, excluding FastAPI/Uvicorn.
    # Refer to agents/social/requirements.txt and strip out service-related packages.
    agent_requirements = [
        "google-cloud-aiplatform[agent_engines,langgraph]==1.96.0", # Make sure version is correct
        "google-adk==1.0.0", # From its specific requirements
        "python-dotenv==1.0.1",
        "deprecated==1.2.18",
        "google-cloud-spanner==3.54.0", # Specific to SocialAgent's tools/instavibe.py
        "google-genai==1.14.0",         # Specific to SocialAgent's tools/instavibe.py
        # "urllib3==2.4.0", # Often a sub-dependency, consider if direct import is used.
                           # For now, assume it's pulled in if needed by spanner/genai.
        # Add other direct dependencies of SocialAgent if any.
    ]
    logger.info(f"Agent requirements for {agent_name}: {agent_requirements}")

    # 3. Define extra packages (source code) for agent_engines.create()
    # base_dir is expected to be the repository root.
    agent_extra_packages = [
        os.path.join(base_dir, "agents", "social"),  # Social agent's own code (including instavibe.py)
        os.path.join(base_dir, "agents", "app", "common"), # For OrchestratorState, shared types, etc.
        os.path.join(base_dir, "agents", "a2a_common-0.1.0-py3-none-any.whl") # Shared library
    ]
    logger.info(f"Extra packages for {agent_name}: {agent_extra_packages}")
    # Verify paths exist
    for pkg_path in agent_extra_packages:
        if not os.path.exists(pkg_path):
            logger.warning(f"Path specified in extra_packages does not exist: {pkg_path}")
            # raise FileNotFoundError(f"Required path for extra_packages not found: {pkg_path}")

    # 4. Define environment variables for this agent
    agent_env_vars = {
        "GOOGLE_CLOUD_PROJECT": project_id,
        "AGENT_NAME": agent_name,
        # SocialAgent currently doesn't seem to require specific additional env vars for its own operation.
    }
    logger.info(f"Environment variables for {agent_name}: {agent_env_vars}")

    # 5. Call agent_engines.create()
    logger.info(f"Deploying {display_name} to Vertex AI Agent Engine using agent_engines.create()...")

    try:
        remote_agent = agent_engines.create(
            local_agent_instance,
            requirements=agent_requirements,
            extra_packages=agent_extra_packages,
            environment_variables=agent_env_vars,
            display_name=display_name,
            description=description,
            # project and location are typically picked from vertexai.init()
            # gcs_dir_name can be specified if you want to control the staging GCS path
        )
        logger.info(f"{display_name} deployed successfully. Resource name: {remote_agent.resource_name}")

        return remote_agent
    except Exception as e:
        logger.error(f"Failed to deploy {agent_name} using agent_engines.create(): {e}", exc_info=True)
        raise

# Main block for direct testing of this script (optional, as deploy_all.py is the primary entry point)
# if __name__ == "__main__":
#     logger.info("Running Social Agent deployment script directly (for testing)...")
#     PROJECT_ID = os.environ.get("PROJECT_ID")
#     REGION = os.environ.get("REGION")
#     BUCKET_NAME = os.environ.get("BUCKET_NAME_FOR_VERTEX_AI_STAGING")

#     if not all([PROJECT_ID, REGION, BUCKET_NAME]):
#         logger.error("Error: PROJECT_ID, REGION, and BUCKET_NAME_FOR_VERTEX_AI_STAGING must be set for local testing.")
#     else:
#         current_script_path = os.path.dirname(os.path.abspath(__file__))
#         repo_base_dir = os.path.abspath(os.path.join(current_script_path, '..', '..'))

#         try:
#             vertexai.init(project=PROJECT_ID, location=REGION, staging_bucket=f"gs://{BUCKET_NAME}")
#             logger.info("Vertex AI SDK initialized successfully for local test.")
#             deployed_remote_agent = deploy_social_main_func(
#                 project_id=PROJECT_ID,
#                 region=REGION,
#                 base_dir=repo_base_dir
#             )
#             logger.info(f"Test deployment successful. Deployed Social Agent resource: {deployed_remote_agent.resource_name}")
#         except Exception as e:
#             logger.error(f"Error during local test of deploy_social_main_func: {e}", exc_info=True)
#     logger.info("Social Agent deployment script direct execution test finished.")
