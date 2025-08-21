import os
import logging
from typing import Optional

from google.cloud import aiplatform as vertexai
from agents.app.agent_engine_app import AgentEngineApp
from vertexai import agent_engines

from agents.orchestrate import agent as orchestrate_agent_module
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__)

from typing import List, Optional

def deploy_orchestrate_main_func(project_id: str, region: str, base_dir: str, extra_packages: Optional[List[str]] = None, env_vars: Optional[dict] = None):
    """
    Deploys the Orchestrate Agent to Vertex AI Reasoning Engines using ADK.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository (repo root).
        extra_packages: A list of extra packages to install.
    """
    display_name = "Orchestrate Agent"
    description = "This agent orchestrates the decomposition of the user request into tasks that can be performed by the child agents."

    from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent
    adk_app = AgentEngineApp(agent=OrchestrateServiceAgent)

    requirements_path = os.path.join(base_dir, "agents/orchestrate/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_path):
        with open(requirements_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    else:
        log.warning(f"Requirements file not found: {requirements_path}. Proceeding with an empty requirements list.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}")
    print(f"  Requirements file (source): {requirements_path}")
    print(f"  Processed requirements list (for deployment): {requirements_list}")

    env_vars_for_deployment = {
        "COMMON_GOOGLE_CLOUD_PROJECT": os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT", project_id),
        "COMMON_GOOGLE_CLOUD_LOCATION": os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION", region),
        "ADK_SESSION_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID"),
        "ADK_SESSION_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID"),
    }
    if env_vars:
        env_vars_for_deployment.update(env_vars)
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v}
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")

    try:
        remote_agent = agent_engines.create(
            adk_app,
            display_name=display_name,
            description=description,
            requirements=requirements_list,
            extra_packages=(extra_packages or []) + ["agents/app", "agents/a2a_common-0.1.0-py3-none-any.whl"],
            env_vars=env_vars_for_deployment,
        )
    except Exception as e:
        print(f"ERROR: ADK agent_engines.create() failed for Orchestrate Agent: {e}")
        raise

    print(f"Orchestrate Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent