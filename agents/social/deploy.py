import os
from agents.social import agent as social_adk_agent_module
from agents.social.social_agent import SocialAgent # Used for AdkApp local execution
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp # For local execution

def deploy_social_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Social Agent to Vertex AI Agent Engines.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository.
    """
    # aiplatform.init() is expected to be called by the main deployment script (deploy_all.py)

    display_name = "Social Agent"
    description = """This agent analyzes social profiles, including posts, friend networks, and event participation, to generate comprehensive summaries and identify common ground between individuals."""

    requirements_file_path = os.path.join(base_dir, "agents/social/requirements.txt")
    if not os.path.exists(requirements_file_path):
        # Fallback for cases where base_dir might be agents/social itself (e.g. direct execution)
        requirements_file_path = "./requirements.txt"
        if not os.path.exists(requirements_file_path):
             print(f"Warning: Requirements file not found at {os.path.join(base_dir, 'agents/social/requirements.txt')} or ./requirements.txt. Proceeding with empty requirements for deployment.")
             requirements_list = []
        else:
            with open(requirements_file_path, "r") as f:
                requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    else:
        with open(requirements_file_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]


    print(f"Deploying Social Agent as Reasoning Engine to project {project_id} in {region} with requirements from {requirements_file_path}...")

    # Note: agent_engines.create uses 'app' to refer to the ADK agent module.
    # The ReasoningEngine (SocialAgent) is used for local AdkApp execution.
    deployed_agent = agent_engines.create(
        app=social_adk_agent_module,  # This should be the module containing the ADK agent
        display_name=display_name,
        description=description,
        requirements=requirements_list,
        # project and location are typically inferred from aiplatform.init()
    )
    print(f"Social Agent (Reasoning Engine) deployed successfully: {deployed_agent.name}")
    print(f"Deployed Reasoning Engine Name: {deployed_agent.name}")
    # Assuming resource_id is an attribute, if not, adjust as needed or remove.
    # print(f"Resource ID: {deployed_agent.resource_id}")
    return deployed_agent

if __name__ == "__main__":
    # This block is for local execution or testing of the AdkApp.
    # It's not directly used by deploy_all.py for cloud deployment.
    print("Running Social Agent locally using AdkApp...")

    # For local execution, AdkApp typically needs an instance of the agent.
    # SocialAgent itself is a ReasoningEngine.
    social_reasoning_engine_instance = SocialAgent()

    # It's good practice to initialize aiplatform here for local runs if project/location are needed
    # import google.cloud.aiplatform as aiplatform
    # aiplatform.init(project="your-local-project", location="us-central1")


    app = AdkApp(
        agent=social_reasoning_engine_instance,
        enable_tracing=True,
    )

    print("AdkApp configured for Social Agent. To run locally, you might need to use 'adk run' or 'adk serve'.")
    # Or, to test the cloud deployment function directly (requires auth and project/region):
    # deploy_social_main_func(project_id="your-gcp-project", region="us-central1", base_dir=".")
    # app.serve() # This would typically be `adk serve` or `python -m adk serve` from CLI
