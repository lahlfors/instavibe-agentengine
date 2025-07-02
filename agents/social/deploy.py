# agents/social/deploy.py
import os
import asyncio
import threading
import logging
import tempfile

import vertexai
from vertexai import generative_models
from vertexai.preview.reasoning_engines import AdkApp

from agents.social.agent import root_agent as social_core_adk_agent_instance # Assuming root_agent is the LlmAgent instance
from agents.social.a2a_server import create_social_a2a_server, A2A_UVICORN_PORT_SOCIAL
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread
from python_a2a.server import A2AServer # For type hinting in run_local_uvicorn

logger = logging.getLogger(__name__)
from typing import Optional # Add Optional for the new display_name parameter

if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

def deploy_social_agent(staging_bucket_uri: str, display_name: Optional[str] = None):
    """
    Deploys the Social agent with an integrated A2A server to Vertex AI Agent Engines
    (using generative_models for deployment).
    Uses a two-step process (create then update) to set the A2A_PUBLIC_BASE_URL.
    """
    effective_display_name = display_name or "Social Agent (A2A-Embedded)"
    description = f"Social agent: {effective_display_name}. Provides profile analysis and summarization via A2A (python-a2a v0.5.0)."

    project_id = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION")

    logger.info(f"Starting deployment of '{effective_display_name}' to Project: {project_id}, Location: {location}")

    if not all([project_id, location, staging_bucket_uri]):
        raise ValueError(
            "COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, and staging_bucket_uri must be set."
        )

    try:
        vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket_uri)
        logger.info(f"Vertex AI SDK initialized for Social Agent: project:{project_id}, location:{location}, staging:{staging_bucket_uri}")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI SDK for Social Agent: {e}", exc_info=True)
        raise

    if social_core_adk_agent_instance is None:
        logger.error("The root_agent in agents.social.agent is None.")
        raise ValueError("Social ADK agent instance not found.")
    logger.info(f"Using ADK Social agent: {getattr(social_core_adk_agent_instance, 'name', 'Unnamed')}")

    a2a_server = create_social_a2a_server(social_core_adk_agent_instance)
    logger.info("A2AServer instance for Social Agent created.")

    # Use NamedTemporaryFile for requirements, similar to planner
    temp_req_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", prefix="social_req_")
    current_vertexai_version = getattr(vertexai, '__version__', '1.88')

    requirements_content = [
        "uvicorn>=0.20.0",
        "fastapi>=0.95.0",
        "python-a2a==0.5.0",
        "httpx>=0.20.0",
        f"google-cloud-aiplatform>={current_vertexai_version}",
        "nest_asyncio>=1.5.0,<2.0.0"
    ]
    # Merge with static requirements from agents/social/requirements.txt
    # Assumes requirements.txt is in the same directory as this deploy.py script
    static_req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if os.path.exists(static_req_path):
        with open(static_req_path, "r") as orf:
            for line in orf:
                stripped_line = line.strip()
                if stripped_line and not stripped_line.startswith("#"):
                    is_core_dep = any(stripped_line.startswith(core_dep_base) for core_dep_base in
                                      ["uvicorn", "fastapi", "python-a2a", "google-cloud-aiplatform", "nest_asyncio", "httpx"])
                    if not is_core_dep:
                        requirements_content.append(stripped_line)

    requirements_content = sorted(list(set(requirements_content)))

    for req_line in requirements_content:
        temp_req_file.write(req_line + "\n")
    temp_req_file.close() # Close the file so ADK can read it
    logger.info(f"Dynamically created temporary requirements file: {temp_req_file.name}")

    adk_app = AdkApp(
        agent=social_core_adk_agent_instance,
        setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_SOCIAL),
    )
    logger.info(f"AdkApp created for Social Agent. Uvicorn will run on port {A2A_UVICORN_PORT_SOCIAL}.")

    env_vars_initial = {
        "A2A_UVICORN_PORT_SOCIAL": str(A2A_UVICORN_PORT_SOCIAL),
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id, # project_id is already defined from env
        "COMMON_GOOGLE_CLOUD_LOCATION": location, # location is already defined from env
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "ADK_SESSION_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "ADK_SESSION_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
    }
    env_vars_initial = {k:v for k,v in env_vars_initial.items() if v is not None} # Filter out None values
    logger.info(f"Initial env_vars for Social Agent create: {env_vars_initial}")

    # Define extra_packages relative to the repository root (where deploy_all.py runs)
    # This script (agents/social/deploy.py) is one level down.
    # To make them relative to repo root: "agents/app_utils", "agents/social"
    repo_root_relative_app_utils = "agents/app_utils"
    repo_root_relative_social_agent = "agents/social"

    extra_packages_for_deployment = [
        repo_root_relative_app_utils,
        repo_root_relative_social_agent,
    ]
    # Verification of paths should ideally be done by the caller (deploy_all.py) or paths constructed carefully.
    # For robustness, could add a check here if needed, assuming a certain CWD.
    logger.info(f"Extra packages for Social Agent deployment: {extra_packages_for_deployment}")

    remote_app = None
    try:
        logger.info(f"Calling initial generative_models.ReasoningEngine.create for '{effective_display_name}'")
        remote_app = generative_models.ReasoningEngine.create(
            AdkApp( # Pass AdkApp instance directly
                agent=social_core_adk_agent_instance,
                setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_SOCIAL)
            ),
            display_name=effective_display_name, # Use effective_display_name
            description=description, # Use updated description
            requirements=[temp_req_file.name], # Use .name of the temp file
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_initial
        )
        logger.info(f"Initial deployment of '{effective_display_name}' successful. Resource name: {remote_app.name}")

        retrieved_a2a_public_url = None
        if hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
           hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri:
            retrieved_a2a_public_url = remote_app.gca_resource.public_endpoint_uri
        elif hasattr(remote_app, 'uri') and remote_app.uri:
             retrieved_a2a_public_url = remote_app.uri

        if not retrieved_a2a_public_url:
            logger.error(f"Failed to retrieve public_endpoint_uri for '{effective_display_name}'.")
            raise RuntimeError(f"Could not get public_endpoint_uri for {effective_display_name}.")
        logger.info(f"Retrieved public_endpoint_uri for '{effective_display_name}': {retrieved_a2a_public_url}")

        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = retrieved_a2a_public_url

        logger.info(f"Calling generative_models.ReasoningEngine.update for '{remote_app.name}' (Display Name: {effective_display_name}) to set A2A_PUBLIC_BASE_URL...")

        remote_app_updated = generative_models.ReasoningEngine.update(
            resource_name=remote_app.name,
            agent_engine=AdkApp(
                agent=social_core_adk_agent_instance,
                setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_SOCIAL)
            ),
            requirements=[temp_req_file.name], # Use .name of the temp file
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_updated
        )
        logger.info(f"'{effective_display_name}' updated successfully. Current resource name: {remote_app_updated.name}")

        if hasattr(a2a_server, 'agent_card') and a2a_server.agent_card:
            a2a_server.agent_card.url = retrieved_a2a_public_url

        return remote_app_updated
    except Exception as e:
        logger.error(f"ERROR during deployment process for '{effective_display_name}': {e}", exc_info=True)
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed agent '{remote_app.name}' (Display Name: {effective_display_name}) due to error.")
                generative_models.ReasoningEngine(remote_app.name).delete(force=True)
                logger.info(f"Successfully deleted partially deployed agent '{remote_app.name}' (Display Name: {effective_display_name}).")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed agent '{remote_app.name}' (Display Name: {effective_display_name}): {del_e}", exc_info=True)
        raise
    finally:
        # Clean up the temporary requirements file
        if os.path.exists(temp_req_file.name):
            try:
                os.remove(temp_req_file.name)
                logger.info(f"Removed temporary requirements file: {temp_req_file.name}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_req_file.name}: {e_rm}")

# Local testing block (optional)
async def run_local_uvicorn_for_social(a2a_s: A2AServer):
  config = uvicorn.Config(a2a_s.build(), host="0.0.0.0", port=A2A_UVICORN_PORT_SOCIAL, log_level="info")
  server = uvicorn.Server(config)
  await server.serve()

if __name__ == "__main__":
    logger.info("Attempting to run Social A2A server locally for testing...")
    os.environ.setdefault("COMMON_GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
    os.environ.setdefault("COMMON_GOOGLE_CLOUD_LOCATION", "us-central1")
    os.environ.setdefault("COMMON_VERTEX_STAGING_BUCKET", "gs://your-local-staging-bucket")
    os.environ.setdefault("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_SOCIAL}")

    try:
        if social_core_adk_agent_instance is None: # Should be imported from agents.social.agent
            raise ValueError("Social core ADK agent (root_agent) could not be loaded for local test.")

        local_a2a_server = create_social_a2a_server(social_core_adk_agent_instance)
        logger.info(f"Locally created A2AServer for Social Agent. Card URL: {local_a2a_server.agent_card.url}")
        asyncio.run(run_local_uvicorn_for_social(local_a2a_server))
    except Exception as e:
        logging.error(f"Failed to run Social agent locally: {e}", exc_info=True)
