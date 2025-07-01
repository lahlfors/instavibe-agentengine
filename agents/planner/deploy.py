# agents/planner/deploy.py
import os
import asyncio
import threading # For start_uvicorn_in_thread, though uvicorn.run in thread is simpler
import logging
import tempfile # For NamedTemporaryFile

import vertexai
from vertexai import generative_models # Corrected import path
from vertexai.preview.reasoning_engines import AdkApp # Still using this for AdkApp wrapper

# Agent specific imports
from agents.planner.agent import PlannerAgent # Your PlannerAgent class for the core ADK agent
from agents.planner.a2a_server import create_planner_a2a_server, A2A_UVICORN_PORT_PLANNER
from agents.app_utils.uvicorn_runner import start_uvicorn_in_thread # Assuming this is adapted for A2AServer.build()
from python_a2a.server import A2AServer # For type hinting in run_local_uvicorn

# from google.cloud.aiplatform_v1 import types as aip_types # Not used in this version

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Function name as per user's example in the guide
def deploy_planner_agent(staging_bucket_uri: str, project_id: str = None, location: str = None): # Added project_id, location as optional
    """Deploys the Planner agent with integrated A2A server and MCP."""
    display_name = "Planner Agent (A2A-MCP v0.5.0)"
    logger.info(f"Starting deployment of '{display_name}'...")

    # Initialize ADK
    project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = location or os.environ.get("GOOGLE_CLOUD_LOCATION")
    # staging_bucket_uri is now a required argument for this function

    if not all([project_id, location, staging_bucket_uri]):
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, and staging_bucket_uri must be set."
        )

    logger.info(f"Deployment Config: Project={project_id}, Location={location}, Staging Bucket={staging_bucket_uri}")

    vertexai.init(
        project=project_id, location=location, staging_bucket=staging_bucket_uri
    )

    # 1. Create the core ADK PlannerAgent instance
    # This assumes PlannerAgent() correctly initializes the LlmAgent
    planner_core_agent = PlannerAgent()
    if planner_core_agent is None: # Should not happen if PlannerAgent constructor works
        logger.error("Failed to instantiate PlannerAgent.")
        raise ValueError("PlannerAgent could not be instantiated.")
    logger.info(f"PlannerAgent (core ADK agent) instantiated: {getattr(planner_core_agent, 'name', type(planner_core_agent).__name__)}")

    # 2. Create A2A Server instance (which includes MCP setup internally if any)
    # This A2AServer object itself isn't directly deployed but its components are used.
    a2a_server = create_planner_a2a_server(planner_core_agent)
    logger.info(f"A2AServer instance for Planner created. MCP tools registered: {list(a2a_server.mcp.tools.keys()) if a2a_server.mcp else 'No MCP'}")

    # 3. Create a temporary requirements file for this deployment
    # Using NamedTemporaryFile to handle cleanup automatically via 'delete=True' by default after context exit
    # However, ADK needs the file path for `requirements` list, so manage deletion manually.
    temp_req_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", prefix="planner_req_")
    current_vertexai_version = getattr(vertexai, '__version__', '1.88') # Default if not found

    requirements_content = [
        "uvicorn>=0.20.0",
        "fastapi>=0.95.0",
        "python-a2a==0.5.0", # Explicitly using v0.5.0
        "httpx>=0.20.0", # A2AClient dependency, good to have for server too if it makes calls
        f"google-cloud-aiplatform>={current_vertexai_version}", # Base SDK, AdkApp might need more specific extras
                                                               # The example had "google-cloud-aiplatform"
                                                               # but "google-cloud-aiplatform[agent_engines,adk]" was in previous versions.
                                                               # Let's stick to the guide's "google-cloud-aiplatform" for now.
        "nest_asyncio>=1.5.0,<2.0.0"
    ]
    # Add any agent-specific static requirements if they exist
    # static_req_path = os.path.join(os.path.dirname(__file__), "requirements.txt") # If Planner had its own static file
    # if os.path.exists(static_req_path):
    #     with open(static_req_path, "r") as orf:
    #         for line in orf:
    #             # Add logic to merge carefully, avoiding duplicates of core_deps
    #             pass # For now, keeping it simple as per example

    for req in requirements_content:
        temp_req_file.write(req + "\n")
    temp_req_file.close() # Close it so ADK can read it
    logger.info(f"Dynamically created temporary requirements file: {temp_req_file.name}")

    # 4. Create the AdkApp
    # The agent here is the core ADK LlmAgent, not the A2AServer object.
    adk_app = AdkApp(
        agent=planner_core_agent,
        setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_PLANNER),
    )
    logger.info(f"AdkApp created. Uvicorn (for A2A/MCP) will run on internal port {A2A_UVICORN_PORT_PLANNER}.")

    # 5. Initial Deployment (using vertexai.generative_models)
    # Note: `env_vars` in `generative_models.create` is `environment_variables`
    env_vars_initial = {
        "A2A_UVICORN_PORT_PLANNER": str(A2A_UVICORN_PORT_PLANNER), # For the Uvicorn server inside
        "COMMON_GOOGLE_CLOUD_PROJECT": project_id, # For clients within the agent
        "COMMON_GOOGLE_CLOUD_LOCATION": location,
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        # TOOLS_GOOGLE_API_KEY might be needed if planner_core_agent uses Google Search directly
        "TOOLS_GOOGLE_API_KEY": os.environ.get("TOOLS_GOOGLE_API_KEY", ""),
    }
    env_vars_initial = {k:v for k,v in env_vars_initial.items() if v is not None}
    logger.info(f"Initial env_vars for generative_models.create: {env_vars_initial}")

    # Define extra_packages. These are paths relative to the CWD where `deploy_all.py` runs (repo root).
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    extra_packages_for_deployment = [
        os.path.join(repo_root, "agents/app_utils"),
        os.path.join(repo_root, "agents/planner"),
    ]
    for pkg_path in extra_packages_for_deployment:
        if not os.path.exists(pkg_path): # Should not happen if paths are correct
            logger.error(f"Critical: Extra package path for deployment not found: {pkg_path}")
            os.remove(temp_req_file.name) # Clean up temp file
            raise FileNotFoundError(f"Extra package path {pkg_path} not found.")
    logger.info(f"Extra packages for deployment: {extra_packages_for_deployment}")

    remote_app = None
    try:
        logger.info(f"Calling initial generative_models.create for '{display_name}'")
        # agent_engines.create is now generative_models.ReasoningEngine.create
        # The parameters might differ slightly. The example uses agent_engine=, requirements=, env_vars=.
        # AdkApp is a valid type for agent_engine.
        remote_app = generative_models.ReasoningEngine.create( # Corrected to ReasoningEngine.create
            AdkApp( # Pass AdkApp instance directly to create
                agent=planner_core_agent,
                setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_PLANNER)
            ),
            display_name=display_name,
            description=description,
            requirements=[temp_req_file.name],
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_initial
        )
        logger.info(f"Initial deployment of '{display_name}' successful. Resource name: {remote_app.name}")

        # 6. Retrieve public endpoint URI
        # The example uses remote_app.gca_resource.public_endpoint_uri.
        # For ReasoningEngine, it's typically just remote_app.public_endpoint_uri if available,
        # or needs to be constructed/queried if not directly on the object.
        # Let's assume gca_resource is how it's accessed as per example.
        if not (hasattr(remote_app, 'gca_resource') and remote_app.gca_resource and \
                hasattr(remote_app.gca_resource, 'public_endpoint_uri') and remote_app.gca_resource.public_endpoint_uri):
            logger.error(f"Failed to retrieve public_endpoint_uri for '{display_name}' from remote_app.gca_resource.")
            # Try remote_app.uri or remote_app.name to see if it's there for ReasoningEngine
            logger.debug(f"remote_app attributes: {dir(remote_app)}")
            if hasattr(remote_app, 'uri') and remote_app.uri:
                 retrieved_a2a_public_url = remote_app.uri
                 logger.info(f"Using remote_app.uri as public_endpoint_uri: {retrieved_a2a_public_url}")
            elif hasattr(remote_app, 'name') and remote_app.name: # Fallback to constructing if direct URI not found
                retrieved_a2a_public_url = f"https://{location}-aiplatform.googleapis.com/v1/{remote_app.name}" # This is a guess
                logger.warning(f"public_endpoint_uri not directly found. Constructed a potential URI: {retrieved_a2a_public_url}. This might need verification.")
            else:
                raise RuntimeError(f"Could not get public_endpoint_uri for {display_name}.")
        else:
            retrieved_a2a_public_url = remote_app.gca_resource.public_endpoint_uri

        logger.info(f"Retrieved public_endpoint_uri for '{display_name}': {retrieved_a2a_public_url}")

        # 7. Update Agent with A2A_PUBLIC_BASE_URL (using generative_models.update)
        env_vars_updated = env_vars_initial.copy()
        env_vars_updated["A2A_PUBLIC_BASE_URL"] = retrieved_a2a_public_url

        logger.info(f"Calling generative_models.ReasoningEngine.update for '{remote_app.name}' to set A2A_PUBLIC_BASE_URL...")
        logger.info(f"Updated env_vars for update: {env_vars_updated}")

        # The update method for ReasoningEngine also needs the AdkApp instance.
        remote_app_updated = generative_models.ReasoningEngine.update(
            resource_name=remote_app.name, # Full resource name
            # Pass the AdkApp instance again, or just the fields to update if API allows partial update.
            # The example passes agent_engine (AdkApp), requirements, env_vars.
            agent_engine=AdkApp(
                agent=planner_core_agent,
                setup_fn=lambda: start_uvicorn_in_thread(a2a_server.build(), "0.0.0.0", A2A_UVICORN_PORT_PLANNER)
            ),
            requirements=[temp_req_file.name],
            extra_packages=extra_packages_for_deployment,
            environment_variables=env_vars_updated
        )
        logger.info(f"'{display_name}' updated successfully with A2A_PUBLIC_BASE_URL. Current resource name: {remote_app_updated.name}")

        # Update local A2AServer's card URL (for local testing or if this instance is used further)
        if hasattr(a2a_server, 'agent_card') and a2a_server.agent_card:
            a2a_server.agent_card.url = retrieved_a2a_public_url

        return remote_app_updated

    except Exception as e:
        logger.error(f"ERROR during deployment process for '{display_name}': {e}", exc_info=True)
        if remote_app and hasattr(remote_app, 'name') and remote_app.name:
            try:
                logger.warning(f"Attempting to delete partially deployed agent '{remote_app.name}' due to error.")
                # Use generative_models.ReasoningEngine for delete
                generative_models.ReasoningEngine(remote_app.name).delete(force=True)
                logger.info(f"Successfully deleted partially deployed agent '{remote_app.name}'.")
            except Exception as del_e:
                logger.error(f"Failed to delete partially deployed agent '{remote_app.name}': {del_e}", exc_info=True)
        raise
    finally:
        if os.path.exists(temp_req_file.name):
            try:
                os.remove(temp_req_file.name)
                logger.info(f"Removed temporary requirements file: {temp_req_file.name}")
            except OSError as e_rm:
                logger.warning(f"Could not remove temporary requirements file {temp_req_file.name}: {e_rm}")

async def run_local_uvicorn(a2a_s: A2AServer): # Renamed from a2a_server to a2a_s
    """Runs the Uvicorn server locally."""
    config = uvicorn.Config(a2a_s.build(), host="0.0.0.0", port=A2A_UVICORN_PORT_PLANNER, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    logger.info("Attempting to run Planner A2A server locally for testing...")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id") # Replace with your actual project
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
    os.environ.setdefault("GOOGLE_CLOUD_STAGING_BUCKET", "gs://your-staging-bucket-uri") # Replace

    # For local run, A2A_PUBLIC_BASE_URL should point to localhost and the Uvicorn port
    os.environ.setdefault("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_PLANNER}")
    # A2A_UVICORN_PORT_PLANNER is already defined. Ensure it's string for env if set here.
    # os.environ.setdefault("A2A_UVICORN_PORT_PLANNER", str(A2A_UVICORN_PORT_PLANNER))


    try:
        planner_core_agent_for_local = PlannerAgent()
        logger.info(f"Using planner agent for local run: {getattr(planner_core_agent_for_local, 'name', 'Unnamed')}")

        local_a2a_server = create_planner_a2a_server(planner_core_agent_for_local)
        logger.info(f"Locally created A2AServer for Planner. Card URL: {local_a2a_server.agent_card.url}")

        asyncio.run(run_local_uvicorn(local_a2a_server))

    except Exception as e:
        logging.error(f"Failed to run planner agent locally: {e}", exc_info=True)

    # Example of how one might call the deployment function (usually called from deploy_all.py)
    # deployed_app_for_cleanup = None
    # try:
    #    # Ensure GOOGLE_CLOUD_STAGING_BUCKET is set in env for this to run
    #    # deployed_app_for_cleanup = deploy_planner_agent(staging_bucket_uri=os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET"))
    #    pass # Not deploying from __main__ by default now
    # except Exception as e:
    #    logging.error(f"Failed to deploy planner agent during guarded test: {e}")
    # finally:
    #    if deployed_app_for_cleanup and hasattr(deployed_app_for_cleanup, 'name') and deployed_app_for_cleanup.name:
    #      logging.info(f"Attempting to delete deployed test resource: {deployed_app_for_cleanup.name}")
    #      generative_models.ReasoningEngine(deployed_app_for_cleanup.name).delete(force=True)
    #      logging.info(f"Deleted test resource: {deployed_app_for_cleanup.name}")
