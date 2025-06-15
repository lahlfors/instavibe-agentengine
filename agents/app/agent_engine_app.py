# mypy: disable-error-code="attr-defined"
import datetime
import json
import logging # Keep logging import
import os
from dotenv import load_dotenv
from typing import Any, Dict # Mapping, Sequence removed as AgentEngineApp is removed

import google.auth
import vertexai
import google.api_core.exceptions # For specific exception handling
from vertexai import agent_engines
# Removed vertexai.preview.reasoning_engines import
from app.utils.gcs import create_bucket_if_not_exists

# Import the LangGraph app builder
from agents.app.graph_builder import build_graph

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

GOOGLE_CLOUD_PROJECT = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")

# ADK-specific classes like AgentEngineApp and its methods are removed.

def deploy_agent_engine_app(
    project: str,
    location: str,
    agent_name: str | None = None,
    requirements_file: str = "requirements.txt",
    extra_packages: list[str] = ["./agents", "./app", "./common", "./a2a_common-0.1.0-py3-none-any.whl"], # Adjusted paths
    env_vars: dict[str, str] | None = None,
) -> agent_engines.AgentEngine | None: # Return type can be None if deployment is stubbed
    """Deploy the LangGraph agent engine app to Vertex AI."""

    staging_bucket = f"gs://{project}-agent-engine"

    create_bucket_if_not_exists(
        bucket_name=staging_bucket, project=project, location=location
    )
    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    # Read requirements
    with open(requirements_file) as f:
        requirements = f.read().strip().split("\n")

    # Instantiate the LangGraph application
    # This application should be a runnable/callable that Vertex AI Agent Engines can serve.
    # LangGraph's `app.compile()` returns a `CompiledGraph` which is runnable.
    try:
        langgraph_app = build_graph()
        logging.info(f"LangGraph application built successfully: {type(langgraph_app)}")
    except Exception as e:
        logging.error(f"Failed to build the LangGraph application: {e}", exc_info=True)
        # Cannot proceed with deployment if the app itself fails to build.
        return None


    # Common configuration for both create and update operations
    # The 'agent_engine' parameter in agent_engines.create/update is tricky.
    # For this refactoring, we aim to make the script ADK-free.
    # We will pass the langgraph_app directly, acknowledging this might not be
    # directly deployable without a wrapper or future Vertex AI support.
    # The deployment calls themselves are stubbed out.

    agent_config: Dict[str, Any] = {
        # "agent_engine": langgraph_app, # This field is what would pass the app to Vertex AI.
                                        # It's commented out as part of stubbing the deployment.
        "display_name": agent_name,
        "description": "Orchestrator agent built with LangGraph",
        "extra_packages": extra_packages,
        "requirements": requirements,
    }
    if env_vars:
        agent_config["environment_variables"] = env_vars


    # Logging the configuration for debugging
    log_config_summary = {k: v for k, v in agent_config.items() if k != "agent_engine"}
    log_config_summary["agent_engine_type"] = type(langgraph_app).__name__
    logging.info(f"Agent config for deployment (summary): {json.dumps(log_config_summary, indent=2, default=str)}")


    # --- DEPLOYMENT STUB ---
    # The following `agent_engines.create/update` calls will likely fail if `langgraph_app`
    # is not a type that Vertex AI Agent Engines directly supports for the `agent_engine` field
    # (e.g., if it expects an AdkApp or a specific interface for serving).
    #
    # To make this script ADK-free as per the subtask goal, we will comment out
    # the actual deployment calls for now. The script will be runnable without ADK,
    # but deployment will need to be addressed based on how LangGraph apps are
    # hosted on Vertex AI Agent Engines (e.g., custom container, specific serving interface).

    logging.warning("IMPORTANT: The actual deployment calls (`agent_engines.create/update`) are currently STUBBED OUT.")
    logging.warning("The LangGraph application `langgraph_app` needs to be packaged or served in a way that is compatible with Vertex AI Agent Engines.")
    logging.warning("This might involve creating a custom container with a serving layer (e.g., FastAPI) for the LangGraph app, "
                    "or using a future Vertex AI feature that directly supports LangGraph applications.")
    logging.info("To proceed with actual deployment, you would need to replace the stubbed section with a compatible deployment mechanism.")

    # Placeholder for where remote_agent would be defined after successful deployment
    remote_agent = None

    # STUBBED DEPLOYMENT SECTION START
    # The following section demonstrates where the actual calls to Vertex AI Agent Engines would be.
    # These are commented out because direct deployment of a LangGraph `CompiledGraph`
    # via the `agent_engine` parameter is not yet confirmed to be supported without a wrapper.
    #
    # try:
    #     existing_agents = agent_engines.list(filter=f"display_name='{agent_name}'")
    #     if existing_agents:
    #         logging.info(f"Found existing agent(s) with name '{agent_name}'. Attempting update (STUBBED).")
    #         # remote_agent = existing_agents[0].update(agent_engine=langgraph_app, **agent_config_for_update)
    #         # Note: agent_config_for_update would need to be defined, similar to agent_config
    #         # but potentially with minor differences for the update operation.
    #         # For this stub, we assume `agent_config` is largely reusable.
    #         logging.warning(f"Update for agent '{agent_name}' is STUBBED. `agent_engine` field would be `langgraph_app`.")
    #         remote_agent = existing_agents[0] # Simulate getting the agent
    #     else:
    #         logging.info(f"No existing agent found with name '{agent_name}'. Attempting create (STUBBED).")
    #         # remote_agent = agent_engines.create(agent_engine=langgraph_app, **agent_config)
    #         logging.warning(f"Create for agent '{agent_name}' is STUBBED. `agent_engine` field would be `langgraph_app`.")
    #         # To simulate a remote_agent object for metadata, you might need to define a mock object:
    #         # class MockRemoteAgent:
    #         #     def __init__(self, name):
    #         #         self.resource_name = f"projects/{project}/locations/{location}/agentEngines/{name}-simulated"
    #         # remote_agent = MockRemoteAgent(agent_name)
    #
    # except google.api_core.exceptions.InvalidArgument as e:
    #     logging.error(f"!!! InvalidArgument error during (stubbed) agent deployment for '{agent_name}': {e}")
    #     logging.error(f"--- This error would likely occur if `langgraph_app` is not a compatible type for `agent_engine`. ---")
    #     logging.error(f"--- Agent Configuration Summary (excluding agent_engine object): {json.dumps(log_config_summary, indent=2, default=str)} ---")
    #     raise
    # except Exception as e:
    #     logging.error(f"An unexpected error occurred during (stubbed) agent deployment for '{agent_name}': {e}", exc_info=True)
    #     raise
    # STUBBED DEPLOYMENT SECTION END

    # If deployment were real, remote_agent would be the deployed agent_engines.AgentEngine object.
    # For stubbed deployment, we check if remote_agent was assigned (e.g., from a simulated update).
    if remote_agent and hasattr(remote_agent, 'resource_name'):
        config = {
            "remote_agent_engine_id": remote_agent.resource_name, # Example: "projects/.../locations/.../agentEngines/..."
            "deployment_timestamp": datetime.datetime.now().isoformat(),
            "status": "STUBBED_DEPLOYMENT" # Indicate that this was not a live deployment
        }
        config_file = "deployment_metadata.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        logging.info(f"Deployment metadata (stubbed) written to {config_file}")
    else:
        logging.warning("No remote_agent object available (deployment was stubbed). Skipping metadata file.")


    return remote_agent # This will be None if deployment is stubbed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )
    import argparse

    parser = argparse.ArgumentParser(description="Build and prepare LangGraph agent for deployment to Vertex AI (Deployment calls are STUBBED)")
    parser.add_argument(
        "--project",
        default=GOOGLE_CLOUD_PROJECT,
        help="GCP project ID (defaults to COMMON_GOOGLE_CLOUD_PROJECT from .env or application default credentials)",
    )
    parser.add_argument(
        "--location",
        default="us-central1",
        help="GCP region (defaults to us-central1)",
    )
    parser.add_argument(
        "--agent-name",
        default="orchestrate-agent-langgraph", # Modified default name
        help="Name for the agent engine",
    )
    parser.add_argument(
        "--requirements-file",
        default="./requirements.txt",
        help="Path to requirements.txt file",
    )
    parser.add_argument(
        "--extra-packages",
        nargs="+",
        default=["./agents", "./app", "./common", "./a2a_common-0.1.0-py3-none-any.whl"], # Adjusted paths
        help="Additional packages to include",
    )
    parser.add_argument(
        "--set-env-vars",
        help="Semicolon-separated list of environment variables in KEY=VALUE format for the agent engine deployment",
    )
    args = parser.parse_args()

    env_vars_dict = None
    if args.set_env_vars:
        env_vars_dict = {}
        for pair_raw in args.set_env_vars.split(";"):
            pair = pair_raw.strip()
            if not pair: continue
            try:
                key, value = pair.split("=", 1)
                env_vars_dict[key.strip()] = value
                logging.info(f"Parsed environment variable for agent engine deployment: {key.strip()}={value}")
            except ValueError:
                logging.warning(f"Skipping invalid environment variable pair for deployment: '{pair}'")

    effective_project = args.project
    if not effective_project:
        _, effective_project = google.auth.default()
        logging.info(f"Using default GCP project: {effective_project}")


    logging.info("""
    ╔══════════════════════════════════════════════════════════════════════════════════╗
    ║                                                                                      ║
    ║   🔄 REFRAINING FROM ACTUAL DEPLOYMENT - ADK REMOVAL & LANGGRAPH INTEGRATION 🔄     ║
    ║   The script will build the LangGraph app and prepare a configuration,             ║
    ║   but the `agent_engines.create/update` calls are STUBBED OUT.                     ║
    ║   Review logs for compatibility notes for Vertex AI Agent Engines.                 ║
    ║                                                                                      ║
    ╚══════════════════════════════════════════════════════════════════════════════════╝
    """)

    deploy_agent_engine_app(
        project=effective_project,
        location=args.location,
        agent_name=args.agent_name,
        requirements_file=args.requirements_file,
        extra_packages=args.extra_packages,
        env_vars=env_vars_dict,
    )
    logging.info("Script finished. Deployment calls were stubbed.")
