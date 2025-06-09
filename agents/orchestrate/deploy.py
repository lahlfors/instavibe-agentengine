import os
from agents.orchestrate import agent as orchestrate_adk_agent_module
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp # For local execution

def deploy_orchestrate_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Orchestrate Agent to Vertex AI Agent Engines.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository.
    """
    # aiplatform.init() is expected to be called by the main deployment script (deploy_all.py)

    display_name = "Orchestrate Agent"
    description = """
  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work on helping user to get social 
"""

    requirements_file_path = os.path.join(base_dir, "agents/orchestrate/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_file_path):
        with open(requirements_file_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    else:
        # Fallback for cases where base_dir might be agents/orchestrate itself (e.g. direct execution)
        fallback_requirements_path = "./requirements.txt"
        if os.path.exists(fallback_requirements_path):
            print(f"Using fallback requirements path: {fallback_requirements_path}")
            with open(fallback_requirements_path, "r") as f:
                requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        else:
             print(f"Warning: Requirements file not found at {requirements_file_path} or {fallback_requirements_path}. Proceeding with empty requirements for deployment.")

    print(f"Deploying Orchestrate Agent from module: {orchestrate_adk_agent_module.__name__} to project {project_id} in {region} with requirements from {requirements_file_path}...")

    deployed_agent = agent_engines.create(
        app=orchestrate_adk_agent_module,
        display_name=display_name,
        description=description,
        requirements=requirements_list,
        # project and location are typically inferred from aiplatform.init()
    )
    print(f"Orchestrate Agent deployed successfully: {deployed_agent.name}")
    # print(f"Deployed Reasoning Engine Name: {deployed_agent.name}") # Duplicates previous line
    # print(f"Resource ID: {deployed_agent.resource_id}") # Assuming resource_id is available
    return deployed_agent

if __name__ == "__main__":
    # This block is for local execution or testing of the AdkApp.
    print("Configuring Orchestrate Agent for local AdkApp execution...")

    # The root_agent is defined in orchestrate_adk_agent_module (agents/orchestrate/agent.py)
    # Ensure aiplatform is initialized if any ADK components require project/location for local run
    # import google.cloud.aiplatform as aiplatform
    # aiplatform.init(project="your-local-project", location="us-central1") # Example for local run

    app = AdkApp(
        agent=orchestrate_adk_agent_module.root_agent,
        enable_tracing=True,
    )

    print("AdkApp for Orchestrate Agent is configured. To run locally, use 'adk run' or 'adk serve'.")
    # Example for testing the cloud deployment function (requires auth, project, region):
    # deploy_orchestrate_main_func(project_id="your-gcp-project", region="us-central1", base_dir=".")
    # To run the AdkApp server (example):
    # app.serve(host="0.0.0.0", port=8080)