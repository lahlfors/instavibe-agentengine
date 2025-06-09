import argparse
import os
from google.cloud import aiplatform
from vertexai import agent_engines

# Import the agent module that contains the `root_agent`
from agents.platform_mcp_client import agent as platform_mcp_client_agent_module

def main(project_id: str, location: str):
    aiplatform.init(project=project_id, location=location)

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

    requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(requirements_path):
        print(f"Error: requirements.txt not found at {requirements_path}")
        # Fallback or error, as requirements are usually needed.
        # For now, let's try deploying without it if not found, though this is not ideal.
        # requirements_path = None
        # Better to fail:
        return


    print(f"Deploying {display_name} to Project: {project_id}, Location: {location}")
    print(f"Using ADK Agent: {adk_agent_to_deploy}")
    print(f"Using requirements: {requirements_path}")

    remote_agent = agent_engines.create(
        app=adk_agent_to_deploy,  # Pass the actual agent instance
        display_name=display_name,
        description=description,
        requirements_path=requirements_path,
        # location=location, # location is implicitly handled by aiplatform.init
        # project_id=project_id # project_id is implicitly handled by aiplatform.init
    )
    print(f"Agent deployed: {remote_agent.name}")
    print(f"View in console: https://console.cloud.google.com/vertex-ai/locations/{location}/agents/{remote_agent.name.split('/')[-1]}/versions?project={project_id}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Platform MCP Client Agent to Vertex AI Agent Engine.")
    parser.add_argument("--project_id", type=str, required=True, help="Google Cloud Project ID.")
    parser.add_argument("--location", type=str, default="us-central1", help="Google Cloud region for deployment.")

    args = parser.parse_args()
    main(project_id=args.project_id, location=args.location)
