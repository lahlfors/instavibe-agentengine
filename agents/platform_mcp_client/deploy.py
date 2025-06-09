import argparse
import os
from google.cloud import aiplatform
from vertexai import agent_engines

# Import the agent module that contains the `root_agent`
from agents.platform_mcp_client import agent as platform_mcp_client_agent_module

def deploy_platform_mcp_client_main_func(project_id: str, region: str, base_dir: str):
    """Deploys the Platform MCP Client Agent to Vertex AI Agent Engine."""
    # aiplatform.init() is expected to be called by deploy_all.py
    # aiplatform.init(project=project_id, location=region)

    display_name = "Platform MCP Client Agent"
    description = "An agent that connects to an MCP Tool Server to provide tools for other agents or clients. It can interact with Instavibe services like creating posts and events."

    # The ADK agent to deploy. This should be the `root_agent` instance
    # from the platform_mcp_client_agent_module.
    # We need to ensure `root_agent` is initialized before this script runs,
    # or that accessing it triggers initialization if needed.
    # The agent.py script seems to initialize it at module level.
    adk_agent_to_deploy = platform_mcp_client_agent_module.root_agent

    if adk_agent_to_deploy is None:
        print("Error: The root_agent in platform_mcp_client.agent is None. Ensure it's initialized.")
        return

    requirements_file_path = os.path.join(base_dir, "agents/platform_mcp_client/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_file_path):
        with open(requirements_file_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    else:
        # Fallback for direct execution
        fallback_requirements_path = "./requirements.txt"
        if os.path.exists(fallback_requirements_path):
            print(f"Using fallback requirements path for platform_mcp_client: {fallback_requirements_path}")
            with open(fallback_requirements_path, "r") as f:
                requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        else:
            print(f"Warning: Requirements file not found at {requirements_file_path} or {fallback_requirements_path} for platform_mcp_client. Proceeding with empty requirements.")


    print(f"Deploying {display_name} to Project: {project_id}, Location: {region}")
    print(f"Using ADK Agent: {adk_agent_to_deploy}")
    print(f"Using requirements list from: {requirements_file_path if os.path.exists(requirements_file_path) else (fallback_requirements_path if os.path.exists(fallback_requirements_path) else 'None found')}")

    remote_agent = agent_engines.create(
        app=adk_agent_to_deploy,  # Pass the actual agent instance
        display_name=display_name,
        description=description,
        requirements=requirements_list, # Pass the list
        # location=region, # location is implicitly handled by aiplatform.init()
        # project=project_id # project_id is implicitly handled by aiplatform.init()
    )
    print(f"Platform MCP Client Agent deployed: {remote_agent.name}")
    # The console link relies on the region (location) being correctly passed or inferred.
    # Since deploy_all.py calls aiplatform.init() with project_id and region, this should be fine.
    print(f"View in console: https://console.cloud.google.com/vertex-ai/locations/{region}/agents/{remote_agent.name.split('/')[-1]}/versions?project={project_id}")
    return remote_agent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Platform MCP Client Agent to Vertex AI Agent Engine.")
    parser.add_argument("--project_id", type=str, required=True, help="Google Cloud Project ID.")
    parser.add_argument("--location", type=str, default="us-central1", help="Google Cloud region for deployment.")
    # base_dir is not strictly needed for direct execution if requirements.txt is local,
    # but added for consistency if we want to test the base_dir logic.
    parser.add_argument("--base_dir", type=str, default=".", help="Base directory of the repository.")


    args = parser.parse_args()

    # For direct execution, we need to initialize aiplatform here.
    aiplatform.init(project=args.project_id, location=args.location)

    deploy_platform_mcp_client_main_func(project_id=args.project_id, region=args.location, base_dir=args.base_dir)
