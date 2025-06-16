import os
import uuid
import logging # For logging

# Import for agent_engines.create()
from vertexai.preview import agent_engines
import vertexai # For vertexai.init()

from dotenv import load_dotenv # For loading .env file
from agents.planner.planner_agent import PlannerAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def deploy_planner_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Planner Agent to Vertex AI Agent Engine using agent_engines.create().
    """
    agent_name = "Planner"
    display_name = f"{agent_name}AgentService-{str(uuid.uuid4())[:8]}" # Unique display name
    description = """This agent helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions."""

    # Ensure Vertex AI is initialized (typically done in deploy_all.py or earlier)
    # If not, it might be necessary to call it here:
    # try:
    #     vertexai.init(project=project_id, location=region, staging_bucket=os.environ.get("BUCKET_NAME_FOR_VERTEX_AI_STAGING"))
    # except Exception as e:
    #     logger.warning(f"vertexai.init may have already been called or failed: {e}")


    # 1. Instantiate the agent
    local_agent_instance = PlannerAgent()
    logger.info(f"Instantiated local {agent_name} agent: {type(local_agent_instance)}")

    # 2. Define requirements for agent_engines.create()
    # These should be core dependencies for PlannerAgent, excluding FastAPI/Uvicorn.
    # Refer to agents/planner/requirements.txt and strip out service-related packages.
    agent_requirements = [
        "google-cloud-aiplatform[agent_engines,langgraph]==1.96.0", # Make sure version is correct
        "python-dotenv==1.0.1",
        "deprecated==1.2.18",
        # Add other direct dependencies of PlannerAgent if any, e.g.,
        # "langchain_google_genai", "langchain_core", etc.
        # For PlannerAgent, it seems to be mostly covered by ADK's dependencies.
    ]
    logger.info(f"Agent requirements for {agent_name}: {agent_requirements}")

    # 3. Define extra packages (source code) for agent_engines.create()
    # Paths should be relative to the execution root of deploy_all.py, or use base_dir correctly.
    # base_dir is expected to be the repository root.
    agent_extra_packages = [
        os.path.join(base_dir, "agents", "planner"),  # Planner agent's own code
        os.path.join(base_dir, "agents", "app", "common"), # For OrchestratorState, shared types, etc.
                                                          # A2AClient itself is not used by PlannerAgent.
        os.path.join(base_dir, "agents", "a2a_common-0.1.0-py3-none-any.whl") # Shared library
    ]
    logger.info(f"Extra packages for {agent_name}: {agent_extra_packages}")
    # Verify paths exist to prevent silent errors during agent_engines.create() packaging
    for pkg_path in agent_extra_packages:
        if not os.path.exists(pkg_path):
            logger.warning(f"Path specified in extra_packages does not exist: {pkg_path}")
            # Depending on severity, you might raise an error:
            # raise FileNotFoundError(f"Required path for extra_packages not found: {pkg_path}")


    # 4. Define environment variables for this agent
    agent_env_vars = {
        "GOOGLE_CLOUD_PROJECT": project_id, # Example: Pass project_id if agent needs it explicitly
        "AGENT_NAME": agent_name, # Example: If the agent logic uses this
        # PlannerAgent currently doesn't seem to require specific additional env vars for its own operation.
        # Service URLs for A2A calls are handled by the Orchestrator.
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
            # gcs_dir_name can be specified if you want to control the staging GCS path, e.g.:
            # gcs_dir_name=f"gs://{os.environ['BUCKET_NAME_FOR_VERTEX_AI_STAGING']}/{agent_name.lower()}_staging_{str(uuid.uuid4())[:8]}"
        )
        logger.info(f"{display_name} deployed successfully. Resource name: {remote_agent.resource_name}")

        # The remote_agent object itself contains deployment information.
        # This will be used by deploy_all.py to extract the invokable URL.
        return remote_agent
    except Exception as e:
        logger.error(f"Failed to deploy {agent_name} using agent_engines.create(): {e}", exc_info=True)
        raise # Re-raise the exception to be caught by deploy_all.py if necessary


if __name__ == "__main__":
    # This block is for testing this specific deployment script.
    # In the actual flow, deploy_all.py will call deploy_planner_main_func.

    logger.info("Running Planner Agent deployment script directly (for testing)...")

    # Example: Load environment variables for local testing of this script
    PROJECT_ID = os.environ.get("PROJECT_ID")
    REGION = os.environ.get("REGION")
    BUCKET_NAME = os.environ.get("BUCKET_NAME_FOR_VERTEX_AI_STAGING") # Ensure this is set in .env for local test

    if not all([PROJECT_ID, REGION, BUCKET_NAME]):
        logger.error("Error: PROJECT_ID, REGION, and BUCKET_NAME_FOR_VERTEX_AI_STAGING must be set in .env for local testing.")
    else:
        logger.info(f"Using PROJECT_ID: {PROJECT_ID}, REGION: {REGION}, BUCKET_NAME: {BUCKET_NAME}")

        # Determine base_dir (repository root)
        # Assuming this script is in agents/planner/deploy.py, base_dir is ../../
        current_script_path = os.path.dirname(os.path.abspath(__file__))
        repo_base_dir = os.path.abspath(os.path.join(current_script_path, '..', '..'))
        logger.info(f"Repository base directory (for extra_packages): {repo_base_dir}")

        try:
            # Initialize Vertex AI SDK for this test run
            vertexai.init(project=PROJECT_ID, location=REGION, staging_bucket=f"gs://{BUCKET_NAME}")
            logger.info("Vertex AI SDK initialized successfully for local test.")

            # Call the main deployment function
            deployed_remote_agent = deploy_planner_main_func(
                project_id=PROJECT_ID,
                region=REGION,
                base_dir=repo_base_dir
            )
            logger.info(f"Test deployment successful. Deployed Planner Agent resource: {deployed_remote_agent.resource_name}")

            # In a real scenario, you might want to try interacting with the deployed agent here
            # or output its invokable URL if discoverable from remote_agent object.
            # For now, just logging the resource name.
            # url = remote_agent.predict_http_uri # Example hypothetical attribute
            # logger.info(f"Hypothetical invokable URL: {url}")


        except Exception as e:
            logger.error(f"Error during local test of deploy_planner_main_func: {e}", exc_info=True)

    logger.info("Planner Agent deployment script direct execution test finished.")
