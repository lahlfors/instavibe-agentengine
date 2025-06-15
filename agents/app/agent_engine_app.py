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
# from google.cloud import logging as google_cloud_logging # Removed, using standard logging
# from opentelemetry import trace # OpenTelemetry tracing removed for simplification
# from opentelemetry.sdk.trace import TracerProvider, export # OpenTelemetry tracing removed
from vertexai import agent_engines
# from vertexai.preview import reasoning_engines # Removed reasoning_engines if not used for non-ADK deployment
from app.utils.gcs import create_bucket_if_not_exists
# from app.utils.tracing import CloudTraceLoggingSpanExporter # OpenTelemetry tracing removed
# from app.utils.typing import Feedback # Feedback class removed
# from vertexai.preview.reasoning_engines import AdkApp # AdkApp removed

# Import the LangGraph app builder
from agents.app.graph_builder import build_graph

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

GOOGLE_CLOUD_PROJECT = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")

# AgentEngineApp class and its methods (set_up, register_feedback, register_operations, clone) are removed
# as they are specific to AdkApp.

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
    # CRITICAL CHANGE: The 'agent_engine' key now needs to point to something
    # compatible with agent_engines.create/update.
    # If LangGraph's compiled app is not directly compatible, this is where
    # a wrapper (e.g., FastAPI app) or a different deployment strategy is needed.

    # For now, we will optimistically pass the langgraph_app.
    # If this fails during actual deployment (which is likely if AgentEngine expects an ADK type),
    # then the deployment part of this function needs to be re-evaluated.
    # The goal of this subtask is to remove ADK from *this* codebase.
    # Actual deployment compatibility is a subsequent concern.

    agent_config: Dict[str, Any] = {
        # "agent_engine": langgraph_app, # This is the optimistic approach
        "display_name": agent_name,
        "description": "Orchestrator agent built with LangGraph", # Updated description
        "extra_packages": extra_packages,
        "requirements": requirements,
        # "env_vars": env_vars, # Handled by Reasoning Engine tool for remote serving if needed, or by container env
    }
    if env_vars: # env_vars are passed to the ReasoningEngine resource
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
    # try:
    #     existing_agents = list(agent_engines.list(filter=f"display_name={agent_name}"))
    #     if existing_agents:
    #         logging.info(f"Attempting to update existing agent: {agent_name}...")
    #         # Ensure agent_config for update includes the 'name' of the existing agent
    #         agent_config_for_update = agent_config.copy()
    #         agent_config_for_update["name"] = existing_agents[0].name
    #         # The 'agent_engine' field must be compatible.
    #         # This is where direct passage of langgraph_app might be an issue.
    #         # For a true update, one might need to create a new ReasoningEngine version
    #         # with the updated langgraph_app and then update the AgentEngine to point to it.
    #         # This is complex and depends on Vertex AI specifics.
    #         # For now, we assume if `create` works, `update` would need similar compatibility.
    #         # remote_agent = existing_agents[0].update(**agent_config) # This line is problematic if langgraph_app isn't directly usable.
    #         logging.warning(f"Update for agent '{agent_name}' is STUBBED. Requires compatible agent_engine type.")
    #         remote_agent = existing_agents[0] # Simulate getting the agent
    #     else:
    #         logging.info(f"Attempting to create new agent: {agent_name}...")
    #         # The `agent_engine` field here is `langgraph_app`. This is the key test.
    #         # If this is not supported, the deployment will fail here.
    #         # remote_agent = agent_engines.create(**agent_config)
    #         logging.warning(f"Create for agent '{agent_name}' is STUBBED. Requires compatible agent_engine type.")
    #         # Simulate a successful creation for metadata purposes if needed by downstream code
    #         # This would require knowing the expected structure of a remote_agent object.
    #
    # except google.api_core.exceptions.InvalidArgument as e:
    #     logging.error(f"!!! InvalidArgument error during (stubbed) agent deployment for '{agent_name}': {e}")
    #     logging.error(f"--- Agent Configuration Summary: {json.dumps(log_config_summary, indent=2, default=str)} ---")
    #     raise
    # except Exception as e:
    #     logging.error(f"An unexpected error occurred during (stubbed) agent deployment for '{agent_name}': {e}", exc_info=True)
    #     raise
    # STUBBED DEPLOYMENT SECTION END

    if remote_agent and hasattr(remote_agent, 'resource_name'): # Check if a simulated or real remote_agent object exists
        config = {
            "remote_agent_engine_id": remote_agent.resource_name,
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

    parser = argparse.ArgumentParser(description="Deploy LangGraph agent engine app to Vertex AI (Deployment calls are STUBBED)")
    # ... (rest of argparse setup remains the same) ...
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
