import os
import logging
from typing import Optional

from google.cloud import aiplatform as vertexai
from vertexai.preview.reasoning_engines import AdkApp
from vertexai import agent_engines

from agents.orchestrate import agent as orchestrate_agent_module
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__)

def deploy_orchestrate_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Orchestrate Agent to Vertex AI Reasoning Engines using ADK.
    """
    display_name = "Orchestrate Agent"
    description = "This agent orchestrates the decomposition of the user request into tasks that can be performed by the child agents."

    local_agent_instance = orchestrate_agent_module.root_agent
    if local_agent_instance is None:
        raise ValueError("Error: The root_agent in orchestrate.agent is None. Ensure it's initialized.")
    adk_app = AdkApp(agent=local_agent_instance)

    requirements_path = os.path.join(base_dir, "agents/orchestrate/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_path):
        with open(requirements_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    else:
        log.warning(f"Requirements file not found: {requirements_path}. Proceeding with an empty requirements list.")

    extra_packages = [
        os.path.join(base_dir, "agents")
    ]

    for pkg_path in extra_packages:
        if not os.path.exists(pkg_path):
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")

    print(f"Starting deployment of '{display_name}' using ADK...")
    print(f"  Project: {project_id}, Region: {region}")
    print(f"  Requirements file (source): {requirements_path}")
    print(f"  Processed requirements list (for deployment): {requirements_list}")
    print(f"  Extra packages: {extra_packages}")

    env_vars_for_deployment = {
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
    }
    env_vars_for_deployment = {k: v for k, v in env_vars_for_deployment.items() if v}
    print(f"  Environment variables for deployed agent: {env_vars_for_deployment}")

    try:
        remote_agent = agent_engines.create(
            adk_app,
            display_name=display_name,
            description=description,
            requirements=requirements_list,
            extra_packages=extra_packages,
            env_vars=env_vars_for_deployment,
        )
    except Exception as e:
        print(f"ERROR: ADK agent_engines.create() failed for Orchestrate Agent: {e}")
        raise

    print(f"Orchestrate Agent (Reasoning Engine) deployment initiated successfully via ADK.")
    print(f"  Deployed Agent Resource Name: {remote_agent.name if remote_agent else 'Pending...'}")
    print(f"Access the deployed agent in the Vertex AI Console or via its resource name.")

    return remote_agent