import os
import asyncio
import threading
import logging
import tempfile # Added tempfile
from typing import Optional

import vertexai # Changed import
from vertexai import generative_models # Changed import
from vertexai.preview.reasoning_engines import AdkApp
# from vertexai import agent_engines # This will be replaced by generative_models

# Import the OrchestrateServiceAgent, A2A server creation function, and Uvicorn port
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent
from agents.orchestrate.a2a_server import create_orchestrator_a2a_server, A2A_UVICORN_PORT_ORCHESTRATE # Assuming this returns A2AServer instance
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread

# Load .env for standalone script execution, though deploy_all.py should handle it.
from dotenv import load_dotenv
if not os.getenv("COMMON_GOOGLE_CLOUD_PROJECT"): # Keep this for standalone runs
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

def deploy_orchestrator_agent(staging_bucket_uri: str, display_name: Optional[str] = None):
    """
    Deploys the Orchestrate Agent with an integrated A2A server to Vertex AI Reasoning Engines.
    Uses a two-step process (create then update) to set the A2A_PUBLIC_BASE_URL.
    """
    effective_display_name = display_name or "Orchestrator Agent (A2A-Embedded)"
    description = f"Orchestrator agent: {effective_display_name}. Manages tasks for other agents via A2A."

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION")

    logger.info(f"Starting deployment of '{effective_display_name}' to Project: {project_id}, Location: {location}")

    if not all([project_id, location, staging_bucket_uri]):
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, and staging_bucket_uri must be set."
        )

    try:
        vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket_uri)
        logger.info(f"Vertex AI SDK initialized for Orchestrator Agent: project:{project_id}, location:{location}, staging:{staging_bucket_uri}")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI SDK for Orchestrator Agent: {e}", exc_info=True)
        raise

    # dynamic_remote_agent_addresses is now sourced from env var directly
    remote_agent_addresses_str = os.getenv("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES", "")
    if not remote_agent_addresses_str:
        logger.warning("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES is not set. Orchestrator may not connect to remote agents effectively.")

    orchestrate_core_adk_agent_service = OrchestrateServiceAgent(remote_agent_addresses_str=remote_agent_addresses_str)
    if orchestrate_core_adk_agent_service.host_agent_logic.root_agent is None:
         logger.error("The root_agent within HostAgent for Orchestrator is None.")
         raise ValueError("Orchestrator's core ADK agent (HostAgent.root_agent) is not initialized.")
    logger.info(f"Using ADK Orchestrate agent service: {type(orchestrate_core_adk_agent_service).__name__}")

    a2a_server_instance = create_orchestrator_a2a_server(passed_orchestrate_service_agent=orchestrate_core_adk_agent_service)
    logger.info(f"A2A Server instance for Orchestrator created: {type(a2a_server_instance).__name__}")

    temp_req_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", prefix="orchestrate_req_")
    current_vertexai_version = getattr(vertexai, '__version__', '1.88')

    # Core dependencies
    core_deps = [
        "uvicorn>=0.20.0",
        "fastapi>=0.95.0",
        "python-a2a==0.5.0", # Using python-a2a
        f"google-cloud-aiplatform>={current_vertexai_version}", # Base, not with [extras] for generative_models
        "nest_asyncio>=1.5.0,<2.0.0"
    ]

    # Read static requirements
    static_requirements_list = []
    # Assumes requirements.txt is in the same directory as this deploy.py
    static_req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if os.path.exists(static_req_path):
        with open(static_req_path, "r") as orf:
            for line in orf:
                stripped_line = line.strip()
                if stripped_line and not stripped_line.startswith("#"):
                    static_requirements_list.append(stripped_line)

    # Combine and de-duplicate:
    final_req_dict = {req.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip(): req for req in core_deps}
    for req in static_requirements_list:
        req_name = req.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
        if req_name not in final_req_dict:
            final_req_dict[req_name] = req

    final_requirements_content = sorted(list(final_req_dict.values()))

    for req_line in final_requirements_content:
        temp_req_file.write(req_line + "\n")
    temp_req_file.close() # Close file for ADK to read
    logger.info(f"Dynamically created temporary requirements file: {temp_req_file.name} with contents: {final_requirements_content}")

    adk_llm_agent_for_orchestrator = orchestrate_core_adk_agent_service.host_agent_logic.root_agent
    adk_app_instance = AdkApp(
        agent=adk_llm_agent_for_orchestrator,
        setup_fn=lambda: start_uvicorn_in_thread(a2a_server_instance.build(), "0.0.0.0", A2A_UVICORN_PORT_ORCHESTRATE) # Use .build()
    )
    logger.info(f"AdkApp instance created for Orchestrator. Uvicorn for A2A will start on internal port {A2A_UVICORN_PORT_ORCHESTRATE}.")

    env_vars_initial = {
        "A2A_UVICORN_PORT_ORCHESTRATE": str(A2A_UVICORN_PORT_ORCHESTRATE),
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id, # Already defined from env
        "COMMON_GOOGLE_CLOUD_LOCATION": location, # Already defined from env
        "AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES": remote_agent_addresses_str,
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "COMMON_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "COMMON_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
        "ADK_SESSION_SPANNER_INSTANCE_ID": os.environ.get("COMMON_SPANNER_INSTANCE_ID", ""),
        "ADK_SESSION_SPANNER_DATABASE_ID": os.environ.get("COMMON_SPANNER_DATABASE_ID", ""),
    }
    env_vars_initial = {k: v for k, v in env_vars_initial.items() if v is not None} # Filter out None
    logger.info(f"Initial environment variables for Orchestrator create: {env_vars_initial}")

    # Define extra_packages relative to the repository root
    extra_packages_for_deployment = [
        "agents/app_utils",
        "agents/orchestrate",
        # Add others if Orchestrator directly imports their code and they are not covered by A2A calls
        # "agents/planner",
        # "agents/social",
    ]
    # Basic check, assuming CWD is repo root when deploy_all.py runs.
    # for pkg_path in extra_packages_for_deployment:
    #     if not os.path.exists(pkg_path): # This check might be too strict if CWD isn't guaranteed
    #         logger.warning(f"Extra package path for deployment might not be found from current CWD: {pkg_path}")
    logger.info(f"Extra packages for Orchestrator deployment: {extra_packages_for_deployment}")

    remote_app = None
    try:
        logger.info(f"Calling initial generative_models.ReasoningEngine.create for '{effective_display_name}'...")
        # Use generative_models.ReasoningEngine instead of agent_engines
        remote_app = generative_models.ReasoningEngine.create(
            agent_engine=adk_app_instance, # This is the AdkApp instance
            display_name=effective_display_name,
            description=description,
            requirements=[temp_req_file.name], # Use .name of the temp file
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_initial
        )
        logger.info(f"Agent '{effective_display_name}' initial deployment successful. Resource name: {remote_app.name}")

        public_a2a_url = None
        if hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
           hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri:
            public_a2a_url = remote_app.gca_resource.public_endpoint_uri
        elif hasattr(remote_app, 'uri') and remote_app.uri: # Fallback for ReasoningEngine object
             public_a2a_url = remote_app.uri

        if not public_a2a_url:
            logger.error(f"Failed to retrieve public_endpoint_uri for '{effective_display_name}' after initial deployment.")
            raise RuntimeError(f"Could not get public_endpoint_uri for the deployed Orchestrator Agent: {effective_display_name}.")

        logger.info(f"Retrieved public_endpoint_uri for Orchestrator ('{effective_display_name}'): {public_a2a_url}")

        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = public_a2a_url

        logger.info(f"Calling generative_models.ReasoningEngine.update for '{remote_app.name}' (Display Name: {effective_display_name}) to set A2A_PUBLIC_BASE_URL...")
        logger.info(f"Updated environment variables for Orchestrator: {env_vars_updated}")

        # Use generative_models.ReasoningEngine.update
        updated_remote_app = generative_models.ReasoningEngine.update(
            resource_name=remote_app.name,
            agent_engine=adk_app_instance, # Pass AdkApp instance again
            requirements=[temp_req_file.name], # Use .name of the temp file
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_updated
        )
        logger.info(f"Orchestrator Agent '{effective_display_name}' updated successfully. New resource state name: {updated_remote_app.name}")

        return updated_remote_app

    except Exception as e:
        logger.error(f"ERROR during Orchestrator Agent deployment process for '{effective_display_name}': {e}", exc_info=True)
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed Orchestrator Agent '{remote_app.name}' (Display Name: {effective_display_name}) due to error.")
                # Use generative_models.ReasoningEngine(resource_name).delete()
                generative_models.ReasoningEngine(remote_app.name).delete(force=True)
                logger.info(f"Successfully deleted partially deployed Orchestrator Agent '{remote_app.name}' (Display Name: {effective_display_name}).")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed Orchestrator Agent '{remote_app.name}' (Display Name: {effective_display_name}): {del_e}", exc_info=True)
        raise
    finally:
        # Clean up the temporary requirements file
        if hasattr(temp_req_file, 'name') and os.path.exists(temp_req_file.name): # Check if temp_req_file was defined and file exists
            try:
                os.remove(temp_req_file.name)
                logger.info(f"Removed temporary requirements file: {temp_req_file.name}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_req_file.name} for Orchestrator: {e_rm}")