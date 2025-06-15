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

# --- Custom Container Deployment Workflow ---
# This script deploys a custom Docker container to Vertex AI Agent Engines.
# The overall workflow is:
# 1. Develop your LangGraph application, wrapped in a FastAPI server (e.g., as in `agents/main.py`).
# 2. Create a Dockerfile (e.g., `agents/Dockerfile`) to package this FastAPI application.
#    - Ensure the Dockerfile copies all necessary code (FastAPI app, LangGraph app, common utilities).
#    - Ensure it installs all dependencies from a `requirements.txt`.
#    - Ensure the container exposes the correct port (e.g., 8080) and runs the FastAPI server on 0.0.0.0.
# 3. Build your Docker image:
#    `docker build -t YOUR_IMAGE_NAME:TAG -f agents/Dockerfile .` (assuming context is repo root)
#    or if context is `agents/` directory:
#    `docker build -t YOUR_IMAGE_NAME:TAG -f Dockerfile .`
# 4. Tag your Docker image for Artifact Registry (or another registry):
#    `docker tag YOUR_IMAGE_NAME:TAG YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPO_NAME/YOUR_IMAGE_NAME:TAG`
# 5. Push the image to Artifact Registry:
#    `docker push YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPO_NAME/YOUR_IMAGE_NAME:TAG`
#    (Ensure you have authenticated Docker with gcloud: `gcloud auth configure-docker YOUR_REGION-docker.pkg.dev`)
# 6. Run this script, providing the full image URI obtained in step 5 as the --container-image-uri argument.
#
# Note: This script assumes the container image is already built and pushed to a registry.
# The `container_spec` used in this script for `agent_engines.create()` is based on
# common patterns for custom containers on Vertex AI. Refer to the official
# Vertex AI Agent Engines documentation for the precise schema if available.
# ---

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
# build_graph is no longer called directly in this script when using custom containers.
# from agents.app.graph_builder import build_graph

GOOGLE_CLOUD_PROJECT = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")

# AgentEngineApp class and its methods (set_up, register_feedback, register_operations, clone) are removed
# as they are specific to AdkApp.

def deploy_agent_engine_app(
    project: str,
    location: str,
    container_image_uri: str, # New parameter for the Docker image
    agent_name: str | None = None,
    env_vars: dict[str, str] | None = None,
) -> agent_engines.AgentEngine | None:
    """Deploy the LangGraph agent engine app to Vertex AI using a custom container."""

    staging_bucket = f"gs://{project}-agent-engine"

    create_bucket_if_not_exists(
        bucket_name=staging_bucket, project=project, location=location
    )
    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    # Requirements and extra_packages are now part of the Docker image build process,
    # not directly used in this deployment function.

    # The LangGraph application is assumed to be packaged within the Docker container
    # specified by `container_image_uri`. This script no longer builds it directly.

    # --- Agent Configuration for Custom Container ---
    # This configuration assumes a structure for custom container deployment
    # based on common patterns in Vertex AI (e.g., custom prediction routines).
    # IMPORTANT: Verify this structure against the official documentation for
    # `vertexai.agent_engines` when available for custom container deployment.
    agent_config: Dict[str, Any] = {
        "display_name": agent_name,
        "description": "Orchestrator agent built with LangGraph, served via custom container.",
        # "tool_contract": {
        #     # This section is speculative. If the Agent Engine framework requires
        #     # explicit tool definitions at the engine level (even for custom containers),
        #     # they would be defined here. For a generic FastAPI backend exposing
        #     # LangGraph, this might be minimal or auto-discovered by the framework
        #     # by calling an endpoint on the container.
        # },
        "default_version_config": { # Assuming a versioning system
            "version_display_name": "v1", # Or some other version identifier
            "container_spec": {  # Key part for custom container deployment
                "image_uri": container_image_uri,
                # "command": [],  # Optional: Override Docker CMD
                # "args": [],     # Optional: Override Docker CMD
                "env": [],      # Will be populated from env_vars if provided
                "ports": [
                    {"container_port": int(os.environ.get("CONTAINER_PORT", 8080))} # Port container listens on
                ],
                # These routes are common for Vertex AI custom containers.
                # Ensure your FastAPI application (or other serving framework) in the container
                # exposes these routes accordingly.
                "predict_route": "/invoke_graph", # Route for predictions/invocations (e.g., to your LangGraph)
                "health_route": "/"             # Route for health checks (e.g., FastAPI root)
            }
        }
        # "environment_variables" at the top level might be deprecated if all env vars
        # are now part of container_spec.env. For clarity, we'll populate container_spec.env.
    }

    if env_vars:
        # Format for container_spec.env is typically a list of {"name": "KEY", "value": "VALUE"}
        agent_config["default_version_config"]["container_spec"]["env"] = [
            {"name": k, "value": v} for k, v in env_vars.items()
        ]

    # Logging the configuration for debugging
    # Remove sensitive parts or large structures if necessary for production logs.
    log_config_summary = {
        "display_name": agent_config.get("display_name"),
        "description": agent_config.get("description"),
        "deployment_type": "custom_container",
        "image_uri": container_image_uri,
        "default_version_config": {
            "version_display_name": agent_config.get("default_version_config", {}).get("version_display_name"),
            "container_spec": {
                "image_uri": agent_config.get("default_version_config", {}).get("container_spec", {}).get("image_uri"),
                "ports": agent_config.get("default_version_config", {}).get("container_spec", {}).get("ports"),
                "predict_route": agent_config.get("default_version_config", {}).get("container_spec", {}).get("predict_route"),
                "health_route": agent_config.get("default_version_config", {}).get("container_spec", {}).get("health_route"),
                "env_count": len(agent_config.get("default_version_config", {}).get("container_spec", {}).get("env", [])),
            }
        }
    }
    logging.info(f"Agent config for custom container deployment (summary): {json.dumps(log_config_summary, indent=2, default=str)}")

    logging.info("Attempting to deploy agent engine with custom container...")
    logging.warning("IMPORTANT: Ensure the provided `container_image_uri` is accessible and correctly configured for Vertex AI Agent Engines.")
    logging.warning("The `container_spec` structure used here is based on common Vertex AI patterns and may need verification against official SDK documentation.")

    remote_agent = None
    try:
        existing_agents = list(agent_engines.list(filter=f"display_name='{agent_name}'")) # Ensure agent_name is quoted for filter
        if existing_agents:
            logging.info(f"Attempting to update existing agent: {agent_name} with ID: {existing_agents[0].name}...")
            # For update, the 'name' of the existing agent resource is required.
            # The agent_config should contain the desired state, including the new container_spec.
            # Note: The `update` method might have specific requirements for how versions are handled.
            # This example assumes updating the default version or creating a new one as per `default_version_config`.
            # The SDK might require `agent_config` to be passed to `update_version` or similar.
            # This is a simplified representation.
            # It's also possible that `update` only takes specific fields rather than the whole config.
            # For a robust update, one might need to:
            # 1. Get the existing agent.
            # 2. Create a new version with the new container_spec.
            # 3. Update the agent to point to this new version as default.
            # However, the `update` method on the agent object itself might simplify this.

            # Let's assume `update` can take a modified config. We need the resource name.
            update_payload = agent_config.copy() # Start with the full desired config
            # update_payload["name"] = existing_agents[0].name # The resource name for the update call

            # The update method is on the agent object, not a static method.
            # existing_agents[0].update(???) -> The SDK here is a bit of a guess.
            # Let's assume we pass what can be updated.
            # `display_name`, `description`, `default_version_config` are common.

            # Simplification: Vertex AI Agent Engine's update method might not allow full config pass-through.
            # It might expect specific parameters or a structured update request.
            # For now, this is a placeholder for the correct update logic.
            # A common pattern for updates is to pass only the fields that need changing.
            # However, to update a container, you typically update a "version" of the agent.

            # Given the uncertainty of the `update` method's exact signature for custom containers
            # and versioning, we will focus on `create` and log a warning for `update`.
            # A real implementation would require consulting the SDK for how to properly roll out a new container version.

            logging.warning(f"Update logic for agent '{agent_name}' with a new custom container is complex and SDK-dependent (especially around versioning).")
            logging.warning("This script will attempt a simplified update if the agent exists, but it might not correctly roll out the new container version.")
            logging.warning("Consider manually managing versions or consult SDK for advanced update patterns.")

            # This is a guess: the update method might take the new default_version_config.
            # Or it might require creating a new AgentVersion and then setting it.
            # For now, let's assume the `update` method of an `AgentEngine` instance can refresh its configuration.
            # This is highly speculative.
            remote_agent = existing_agents[0].update(default_version_config=agent_config["default_version_config"])
            logging.info(f"Agent '{agent_name}' update call attempted.")

        else:
            logging.info(f"Attempting to create new agent: {agent_name} with custom container...")
            remote_agent = agent_engines.create(**agent_config)
            logging.info(f"Agent '{agent_name}' create call attempted successfully.")

    except google.api_core.exceptions.InvalidArgument as e:
        logging.error(f"!!! InvalidArgument error during agent deployment for '{agent_name}': {e}")
        logging.error(f"--- Agent Configuration Summary used: {json.dumps(log_config_summary, indent=2, default=str)} ---")
        logging.error("--- Please verify the `agent_config` structure, especially `container_spec`, against Vertex AI Agent Engines documentation for custom containers. ---")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during agent deployment for '{agent_name}': {e}", exc_info=True)
        raise

    if remote_agent and hasattr(remote_agent, 'resource_name'):
        config = {
            "remote_agent_engine_id": remote_agent.resource_name,
            "deployment_timestamp": datetime.datetime.now().isoformat(),
            "status": "ATTEMPTED_DEPLOYMENT_CUSTOM_CONTAINER", # Updated status
            "image_uri": container_image_uri,
            "agent_name": agent_name
        }
        config_file = "deployment_metadata.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        logging.info(f"Deployment metadata written to {config_file}")
    else:
        logging.warning("No remote_agent object returned from deployment call or it lacks 'resource_name'. Skipping metadata file.")

    return remote_agent


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )
    import argparse

    parser = argparse.ArgumentParser(description="Deploy LangGraph agent engine app to Vertex AI using a custom container.")
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
        default="orchestrate-agent-custom-container",
        help="Name for the agent engine",
    )
    # The user must provide the full URI of the pre-built and pushed Docker container image.
    # Example: gcr.io/your-project-id/your-image-name:tag or YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPO_NAME/YOUR_IMAGE_NAME:TAG
    parser.add_argument(
        "--container-image-uri",
        required=True,
        help="URI of the Docker container image for deployment (e.g., gcr.io/your-project/your-agent-image:latest)",
    )
    parser.add_argument(
        "--set-env-vars",
        help="Semicolon-separated list of environment variables in KEY=VALUE format for the agent engine deployment (e.g., 'VAR1=value1;VAR2=value2')",
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
                env_vars_dict[key.strip()] = value.strip() # Also strip value
                logging.info(f"Parsed environment variable for agent engine deployment: {key.strip()}={value.strip()}")
            except ValueError:
                logging.warning(f"Skipping invalid environment variable pair for deployment: '{pair}'")

    effective_project = args.project
    if not effective_project:
        try:
            _, effective_project = google.auth.default()
            logging.info(f"Using default GCP project: {effective_project}")
        except google.auth.exceptions.DefaultCredentialsError:
            logging.error("GCP project not specified and default credentials not found. Please set --project or configure gcloud.")
            exit(1)


    logging.info(f"""
    ╔═════════════════════════════════════════════════════════════════════════════════════════╗
    ║                                                                                         ║
    ║   🚀 ATTEMPTING CUSTOM CONTAINER DEPLOYMENT TO VERTEX AI AGENT ENGINES 🚀                 ║
    ║   Project: {effective_project}                                                               ║
    ║   Location: {args.location}                                                                 ║
    ║   Agent Name: {args.agent_name}                                                             ║
    ║   Container Image URI: {args.container_image_uri}                                           ║
    ║   Environment Variables: {env_vars_dict if env_vars_dict else "None"}                                       ║
    ║                                                                                         ║
    ║   IMPORTANT: Ensure the container image is accessible and the `container_spec` in         ║
    ║   this script aligns with Vertex AI Agent Engines SDK requirements.                       ║
    ║   The SDK calls for `agent_engines.create()` and `update()` are now active.               ║
    ║                                                                                         ║
    ╚═════════════════════════════════════════════════════════════════════════════════════════╝
    """)

    try:
        deploy_agent_engine_app(
            project=effective_project,
            location=args.location,
            agent_name=args.agent_name,
            container_image_uri=args.container_image_uri,
            env_vars=env_vars_dict,
        )
        logging.info("Script finished. Check logs for deployment status.")
    except Exception as e:
        logging.error(f"Deployment script failed: {e}", exc_info=True)
        # Optionally, re-raise or exit with error code
        # exit(1)

# --- Conceptual Testing Strategy ---
# To test this script conceptually (without incurring costs or requiring full GCP setup for automated tests):
#
# 1.  **Unit Test `deploy_agent_engine_app` (Mocked SDK):**
#     *   Write a unit test for the `deploy_agent_engine_app` function.
#     *   Mock the `vertexai.init` and `vertexai.agent_engines` client calls (e.g., `agent_engines.create`, `agent_engines.list`, `agent_engines.update`).
#     *   Verify that the function constructs the `agent_config` (especially the `container_spec`) correctly based on input parameters (project, location, agent_name, container_image_uri, env_vars).
#     *   Check that the correct parameters are passed to the mocked SDK calls.
#     *   Ensure appropriate logging occurs.
#
# 2.  **Command-Line Invocation Test (Dry Run Mindset):**
#     *   Prepare a sample Docker image URI (it doesn't have to be a real, working image for this test, just a correctly formatted URI string).
#     *   Run the script with dummy values for project, location, agent name, and the sample image URI.
#       `python agents/app/agent_engine_app.py --project "test-project" --location "us-central1" --agent-name "test-container-agent" --container-image-uri "us-central1-docker.pkg.dev/test-project/test-repo/test-image:latest" --set-env-vars "MY_VAR=my_value;ANOTHER_VAR=another_value"`
#     *   Observe the log output:
#         *   Verify that the script parses arguments correctly.
#         *   Check that the `agent_config` logged to the console matches expectations (image URI, env vars mapped correctly into `container_spec.env`, etc.).
#         *   Confirm that the script attempts to call `agent_engines.create` or `agent_engines.update`.
#         *   If there are authentication errors (expected if not running with valid gcloud auth), these can be ignored for this conceptual test, as the goal is to see the script's logic flow up to the SDK call.
#
# 3.  **Verify Docker Container Independently (Optional but Recommended):**
#     *   Separately, ensure the Docker container (built from `agents/Dockerfile` and `agents/main.py`) runs correctly locally.
#       `docker run -p 8080:8080 YOUR_IMAGE_NAME:TAG`
#     *   Test that the FastAPI server starts and that the `/` (health) and `/invoke_graph` (predict) endpoints are responsive using `curl` or a tool like Postman.
#     *   This step ensures the artifact being deployed is functional before attempting cloud deployment.
#
# 4.  **Actual Deployment Test (Manual, Staged):**
#     *   Perform a manual deployment using the script against a non-production/test GCP project.
#     *   Use a real, pushed Docker image URI.
#     *   Monitor the Google Cloud Console (Vertex AI > Agent Engines) to see if the agent resource is created or updated.
#     *   Check logs in Cloud Logging for any deployment errors from the Vertex AI platform.
#     *   If successful, attempt to invoke the deployed agent engine (how this is done depends on the Agent Engine's capabilities - it might provide an endpoint or require client code).
#
# Note: Full end-to-end automated testing would require a dedicated test project,
# service accounts, and cleanup routines for created resources.
# The strategy above focuses on testing the script's logic and prerequisites.
# ---
