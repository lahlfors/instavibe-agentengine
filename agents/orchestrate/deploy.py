import os
import uuid
import logging # For logging
from typing import Optional # For type hinting

# Import for agent_engines.create()
from vertexai.preview import agent_engines
import vertexai # For vertexai.init()

from dotenv import load_dotenv # For loading .env file
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def deploy_orchestrate_main_func(
    project_id: str,
    region: str,
    base_dir: str,
    additional_env_vars: Optional[dict] = None
):
    """
    Deploys the Orchestrate Agent to Vertex AI Agent Engine using agent_engines.create().
    """
    agent_name = "Orchestrator"
    display_name = f"{agent_name}AgentService-{str(uuid.uuid4())[:8]}" # Unique display name
    description = "Orchestrator Agent: manages tasks and delegates to specialized agents."

    # Ensure Vertex AI is initialized (typically done in deploy_all.py or earlier)
    # vertexai.init(project=project_id, location=region, staging_bucket=os.environ.get("BUCKET_NAME_FOR_VERTEX_AI_STAGING"))

    # 1. Instantiate the agent
    # OrchestrateServiceAgent __init__ should no longer require remote_agent_addresses_str.
    # A2AClient will use environment variables for service discovery.
    local_agent_instance = OrchestrateServiceAgent()
    logger.info(f"Instantiated local {agent_name} agent: {type(local_agent_instance)}")

    # 2. Define requirements for agent_engines.create()
    # These should be core dependencies for OrchestrateServiceAgent, excluding FastAPI/Uvicorn.
    agent_requirements = [
        "google-cloud-aiplatform[agent_engines,langgraph]==1.96.0",
        "python-dotenv==1.0.1",
        "google-adk==1.0.0", # From its requirements.txt
        "deprecated==1.2.18",
        "nest_asyncio==1.6.0",
        "httpx==0.25.0", # Crucial for A2AClient
        # Add other direct dependencies if any.
    ]
    logger.info(f"Agent requirements for {agent_name}: {agent_requirements}")

    # 3. Define extra packages (source code) for agent_engines.create()
    # base_dir is expected to be the repository root.
    # Orchestrator needs its own code, common utilities (A2AClient, OrchestratorState),
    # the graph_builder, and the node execution files it references.
    agent_extra_packages = [
        os.path.join(base_dir, "agents", "orchestrate"),            # Orchestrator's own code
        os.path.join(base_dir, "agents", "app"),                  # For common, graph_builder, utils
        # The following are needed because agents.app.graph_builder directly imports execute_*_node functions
        # which are defined in those specific agent directories.
        os.path.join(base_dir, "agents", "planner"),              # For planner_node.py
        os.path.join(base_dir, "agents", "social"),               # For social_exec_node.py
        os.path.join(base_dir, "agents", "platform_mcp_client"),  # For platform_exec_node.py and mcp_client.py
        os.path.join(base_dir, "agents", "a2a_common-0.1.0-py3-none-any.whl") # Shared library
    ]
    logger.info(f"Extra packages for {agent_name}: {agent_extra_packages}")
    for pkg_path in agent_extra_packages:
        if not os.path.exists(pkg_path):
            logger.warning(f"Path specified in extra_packages does not exist: {pkg_path}")
            # raise FileNotFoundError(f"Required path for extra_packages not found: {pkg_path}")


    # 4. Define environment variables for this agent
    # Merge with additional_env_vars passed from deploy_all.py (containing service URLs)
    final_env_vars = {
        "GOOGLE_CLOUD_PROJECT": project_id,
        "AGENT_NAME": agent_name,
        # Add any other orchestrator-specific static env vars here if any
    }
    if additional_env_vars:
        final_env_vars.update(additional_env_vars)
    logger.info(f"Final environment variables for {agent_name}: {final_env_vars}")

    # 5. Call agent_engines.create()
    logger.info(f"Deploying {display_name} to Vertex AI Agent Engine using agent_engines.create()...")

    try:
        remote_agent = agent_engines.create(
            local_agent_instance,
            requirements=agent_requirements,
            extra_packages=agent_extra_packages,
            environment_variables=final_env_vars,
            display_name=display_name,
            description=description,
        )
        logger.info(f"{display_name} deployed successfully. Resource name: {remote_agent.resource_name}")

        return remote_agent
    except Exception as e:
        logger.error(f"Failed to deploy {agent_name} using agent_engines.create(): {e}", exc_info=True)
        raise

# No __main__ block needed here, as deploy_all.py will be the entry point for deployment.