# deploy_all.py
import os
import logging
import subprocess # Added
from agents.planner.deploy import deploy_planner_agent
from agents.social.deploy import deploy_social_agent
from agents.orchestrate.deploy import deploy_orchestrator_agent
from agents.platform_mcp_client.deploy import deploy_platform_mcp_client_main_func # Added
from agents.instavibe_workflow.agent import InstavibeWorkflowAgent # Assuming this is the client
# For instavibe_workflow deployment, we need its deploy function if it's also an RE
# from agents.instavibe_workflow.deploy import deploy_instavibe_workflow_agent # If it's an RE
import asyncio
from typing import Optional, Any
import vertexai # Ensure vertexai is initialized early if not done in individual scripts robustly

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

# Initialize Vertex AI SDK once, centrally.
# Individual deploy scripts also call vertexai.init(), which is idempotent.
try:
    PROJECT_ID = os.environ["COMMON_GOOGLE_CLOUD_PROJECT"]
    LOCATION = os.environ["COMMON_GOOGLE_CLOUD_LOCATION"]
    STAGING_BUCKET = os.environ["COMMON_VERTEX_STAGING_BUCKET"]
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)
    logger.info(f"Vertex AI SDK initialized globally: project:{PROJECT_ID}, location:{LOCATION}, staging:{STAGING_BUCKET}")
except KeyError as e:
    logger.error(f"Critical environment variable missing: {e}. Please set COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, and COMMON_VERTEX_STAGING_BUCKET.")
    raise
except Exception as e:
    logger.error(f"Error initializing Vertex AI SDK globally: {e}", exc_info=True)
    raise


def delete_reasoning_engine_if_exists(display_name_to_delete: str, project_id: str, location: str):
    """Deletes a reasoning engine by its display name if it exists."""
    try:
        # Need to import this for list and delete by display name
        from google.cloud import aiplatform_v1beta1 as aiplatform_preview_client # Use preview for list by display_name

        client_options = {"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        client = aiplatform_preview_client.ReasoningEngineServiceClient(client_options=client_options)

        parent = f"projects/{project_id}/locations/{location}"

        # List engines and find the one with the matching display name
        list_request = aiplatform_preview_client.ListReasoningEnginesRequest(parent=parent)
        engines = client.list_reasoning_engines(request=list_request)

        engine_to_delete_name = None
        for engine in engines:
            if engine.display_name == display_name_to_delete:
                engine_to_delete_name = engine.name
                break

        if engine_to_delete_name:
            logger.info(f"Found existing Reasoning Engine '{display_name_to_delete}' with resource name '{engine_to_delete_name}'. Deleting...")
            delete_request = aiplatform_preview_client.DeleteReasoningEngineRequest(name=engine_to_delete_name)
            operation = client.delete_reasoning_engine(request=delete_request)
            operation.result() # Wait for deletion to complete
            logger.info(f"Successfully deleted Reasoning Engine '{display_name_to_delete}'.")
        else:
            logger.info(f"No existing Reasoning Engine found with display name '{display_name_to_delete}'. Skipping deletion.")

    except ImportError:
        logger.warning("google-cloud-aiplatform preview client (aiplatform_v1beta1) not available. Cannot delete by display name. Skipping pre-deletion.")
    except Exception as e:
        logger.error(f"Error deleting Reasoning Engine '{display_name_to_delete}': {e}", exc_info=True)
        # Decide if this should be a fatal error or just a warning
        logger.warning(f"Proceeding with deployment attempt for '{display_name_to_delete}' despite error during pre-deletion check.")


def deploy_agent_with_forced_update(deploy_func, agent_human_name: str, staging_bucket_uri: str, display_name_for_re: str) -> Optional[Any]:
    """
    Wrapper to deploy an agent. It first attempts to delete any existing
    Reasoning Engine with the target display_name.
    - deploy_func: The actual deployment function for the agent (e.g., deploy_planner_agent).
    - agent_human_name: A human-readable name for logging (e.g., "Planner Agent").
    - staging_bucket_uri: The GCS URI for staging.
    - display_name_for_re: The specific display_name to use for the Reasoning Engine resource.
    """
    logger.info(f"--- Attempting to deploy {agent_human_name} with RE display name: {display_name_for_re} ---")

    # Attempt to delete existing RE by display name first for a "forced update"
    # This uses PROJECT_ID and LOCATION from the global scope (initialized from env vars)
    delete_reasoning_engine_if_exists(display_name_for_re, PROJECT_ID, LOCATION)

    try:
        # Call the specific agent's deployment function
        # It now expects staging_bucket_uri and display_name as arguments
        deployed_agent = deploy_func(staging_bucket_uri=staging_bucket_uri, display_name=display_name_for_re)
        logger.info(f"Successfully deployed {agent_human_name} as '{display_name_for_re}'. Resource: {getattr(deployed_agent, 'name', 'N/A')}")
        return deployed_agent
    except Exception as e:
        logger.error(f"Failed to deploy {agent_human_name} ('{display_name_for_re}'): {e}", exc_info=True)
        return None

async def main():
    # Staging bucket is now read from global STAGING_BUCKET, set during initial vertexai.init()
    # but individual deploy functions expect it as an argument.

    # --- Deploy Core Services First ---
    logger.info("--- Deploying Core Services (Instavibe App & MCP Tool Server) ---")

    # Deploy Instavibe App
    # Note: PROJECT_ID and LOCATION are global variables set from environment variables at the top of the script.
    instavibe_app_url = deploy_instavibe_app(PROJECT_ID, LOCATION, image_name_param="instavibe-app")
    if not instavibe_app_url:
        logger.error("Instavibe App deployment failed or URL not retrieved. Exiting.")
        return
    logger.info(f"Instavibe App Deployed. URL: {instavibe_app_url}")
    os.environ["TOOLS_INSTAVIBE_BASE_URL"] = f"{instavibe_app_url}/api" # Assuming API is at /api
    logger.info(f"Set TOOLS_INSTAVIBE_BASE_URL to: {os.environ['TOOLS_INSTAVIBE_BASE_URL']}")

    # Deploy MCP Tool Server
    mcp_tool_server_url = deploy_mcp_tool_server(PROJECT_ID, LOCATION, image_name_param="mcp-tool-server")
    if not mcp_tool_server_url:
        logger.error("MCP Tool Server deployment failed or URL not retrieved. Exiting.")
        return
    logger.info(f"MCP Tool Server Deployed. URL: {mcp_tool_server_url}")
    # AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL often includes an /sse path
    os.environ["AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL"] = f"{mcp_tool_server_url}/sse" # Assuming /sse endpoint
    logger.info(f"Set AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL to: {os.environ['AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL']}")

    logger.info("--- Core Services Deployed ---")

    # --- Deploy Agents ---
    logger.info("--- Deploying Agents ---")

    # Deploy Planner
    planner_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_planner_agent,
        agent_human_name="Planner Agent",
        staging_bucket_uri=STAGING_BUCKET,
        display_name_for_re="planner_agent_prod"
    )
    planner_a2a_url = None
    if planner_deployed_agent and hasattr(planner_deployed_agent, 'gca_resource') and planner_deployed_agent.gca_resource:
        planner_a2a_url = planner_deployed_agent.gca_resource.public_endpoint_uri
    elif planner_deployed_agent and hasattr(planner_deployed_agent, 'uri'):
        planner_a2a_url = planner_deployed_agent.uri

    if planner_a2a_url:
        logger.info(f"Planner A2A URL: {planner_a2a_url}")
    else:
        logger.error("Planner deployment failed or A2A URL not found, exiting.")
        return

    # Deploy Social
    social_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_social_agent,
        agent_human_name="Social Agent",
        staging_bucket_uri=STAGING_BUCKET,
        display_name_for_re="social_agent_prod"
    )
    social_a2a_url = None
    if social_deployed_agent and hasattr(social_deployed_agent, 'gca_resource') and social_deployed_agent.gca_resource:
        social_a2a_url = social_deployed_agent.gca_resource.public_endpoint_uri
    elif social_deployed_agent and hasattr(social_deployed_agent, 'uri'):
        social_a2a_url = social_deployed_agent.uri

    if social_a2a_url:
        logger.info(f"Social A2A URL: {social_a2a_url}")
    else:
        logger.error("Social deployment failed or A2A URL not found. Orchestrator and Workflow may be impacted.")
        # Allow continuation for now, but Orchestrator might not have all agents.

    # Deploy Orchestrator
    # Construct remote agent addresses for Orchestrator.
    remote_addresses_list = []
    if planner_a2a_url:
        remote_addresses_list.append(planner_a2a_url)
    if social_a2a_url:
        remote_addresses_list.append(social_a2a_url)
    # Platform MCP Client agent will be added to remote_addresses_list if deployed successfully

    # Deploy Platform MCP Client Agent
    # This agent depends on AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL, which should be set by now.
    platform_mcp_client_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_platform_mcp_client_main_func, # Use the main_func directly
        agent_human_name="Platform MCP Client Agent",
        staging_bucket_uri=STAGING_BUCKET, # Pass STAGING_BUCKET
        display_name_for_re="platform_mcp_client_agent_prod" # Specific RE display name
    )
    platform_mcp_client_a2a_url = None
    if platform_mcp_client_deployed_agent and hasattr(platform_mcp_client_deployed_agent, 'gca_resource') and platform_mcp_client_deployed_agent.gca_resource:
        platform_mcp_client_a2a_url = platform_mcp_client_deployed_agent.gca_resource.public_endpoint_uri
    elif platform_mcp_client_deployed_agent and hasattr(platform_mcp_client_deployed_agent, 'uri'):
        platform_mcp_client_a2a_url = platform_mcp_client_deployed_agent.uri

    if platform_mcp_client_a2a_url:
        logger.info(f"Platform MCP Client Agent A2A URL: {platform_mcp_client_a2a_url}")
        remote_addresses_list.append(platform_mcp_client_a2a_url) # Add to list for Orchestrator
    else:
        logger.warning("Platform MCP Client Agent deployment failed or A2A URL not found. Orchestrator might not have this agent.")
        # Continue without it for now.

    # Set/Update AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES for the Orchestrator
    if not remote_addresses_list:
        logger.warning("No agent URLs available for Orchestrator.")
        os.environ["AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES"] = ""
    else:
        os.environ["AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES"] = ",".join(remote_addresses_list)
    logger.info(f"Final AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES for Orchestrator: {os.environ['AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES']}")

    # Deploy Orchestrator (now that all its potential remote agents are known)
    orchestrator_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_orchestrator_agent,
        agent_human_name="Orchestrator Agent",
        staging_bucket_uri=STAGING_BUCKET,
        display_name_for_re="orchestrator_agent_prod"
    )
    orchestrator_a2a_url = None
    if orchestrator_deployed_agent and hasattr(orchestrator_deployed_agent, 'gca_resource') and orchestrator_deployed_agent.gca_resource:
        orchestrator_a2a_url = orchestrator_deployed_agent.gca_resource.public_endpoint_uri
    elif orchestrator_deployed_agent and hasattr(orchestrator_deployed_agent, 'uri'):
        orchestrator_a2a_url = orchestrator_deployed_agent.uri

    if orchestrator_a2a_url:
        logger.info(f"Orchestrator A2A URL: {orchestrator_a2a_url}")
    else:
        logger.error("Orchestrator deployment failed or A2A URL not found. Exiting as workflow agent depends on it.")
        return

    # Set environment variables for the InstavibeWorkflowAgent and other clients
    os.environ["PLANNER_AGENT_A2A_URL"] = planner_a2a_url or ""
    os.environ["ORCHESTRATE_AGENT_A2A_URL"] = orchestrator_a2a_url or ""
    os.environ["SOCIAL_AGENT_A2A_URL"] = social_a2a_url or ""
    os.environ["PLATFORM_MCP_CLIENT_A2A_URL"] = platform_mcp_client_a2a_url or ""


    logger.info(f"Environment variables set/updated for InstavibeWorkflowAgent and other clients:")
    logger.info(f"  TOOLS_INSTAVIBE_BASE_URL={os.environ.get('TOOLS_INSTAVIBE_BASE_URL')}")
    logger.info(f"  AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL={os.environ.get('AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL')}")
    logger.info(f"  PLANNER_AGENT_A2A_URL={os.environ.get('PLANNER_AGENT_A2A_URL')}")
    logger.info(f"  ORCHESTRATE_AGENT_A2A_URL={os.environ.get('ORCHESTRATE_AGENT_A2A_URL')}")
    logger.info(f"  SOCIAL_AGENT_A2A_URL={os.environ.get('SOCIAL_AGENT_A2A_URL')}")
    logger.info(f"  PLATFORM_MCP_CLIENT_A2A_URL={os.environ.get('PLATFORM_MCP_CLIENT_A2A_URL')}")


    # --- Example A2A Calls (Conceptual, for testing if agents are reachable) ---
    # Initialize Workflow Agent for making calls
    workflow_agent = InstavibeWorkflowAgent() # Assumes it picks up URLs from env
    logger.info("InstavibeWorkflowAgent client initialized for example A2A calls.")

    if planner_a2a_url:
        logger.info(f"--- Making example A2A call from Workflow to Planner ({planner_a2a_url}) ---")
        try:
            # The InstavibeWorkflowAgent's query method needs to be defined.
            # Let's assume it's an async method that takes the target agent's A2A URL and a payload.
            # And that it uses httpx.AsyncClient internally.
            # This is a conceptual example; the actual method signature might differ.
            example_payload = {"task": "create a plan for a beach vacation"}
            response = await workflow_agent.a2a_query( # Assuming method is a2a_query
                target_agent_a2a_url=planner_a2a_url,
                payload=example_payload,
                timeout_seconds=60
            )
            if response:
                logger.info(f"Response from Planner via WorkflowAgent: {response}")
            else:
                logger.error(f"Failed to get a valid response from Planner via WorkflowAgent or response was empty.")
        except Exception as e:
            logger.error(f"Error during example A2A call from Workflow to Planner: {e}", exc_info=True)
    else:
        logger.warning("Planner A2A URL not available, skipping example A2A call from Workflow to Planner.")

    # Example of A2A call from WorkflowAgent to Orchestrator
    if orchestrator_a2a_url:
        logger.info(f"--- Making example A2A call from Workflow to Orchestrator ({orchestrator_a2a_url}) ---")
        try:
            example_payload_orchestrator = {"request_type": "execute_plan", "plan_details": "..."}
            response_orc = await workflow_agent.a2a_query(
                target_agent_a2a_url=orchestrator_a2a_url,
                payload=example_payload_orchestrator,
                timeout_seconds=120
            )
            if response_orc:
                logger.info(f"Response from Orchestrator via WorkflowAgent: {response_orc}")
            else:
                logger.error(f"Failed to get a valid response from Orchestrator via WorkflowAgent or response was empty.")
        except Exception as e:
            logger.error(f"Error during example A2A call from Workflow to Orchestrator: {e}", exc_info=True)
    else:
        logger.warning("Orchestrator A2A URL not available, skipping example A2A call from Workflow to Orchestrator.")

    logger.info("--- All Deployments and Example A2A Calls Attempted ---")


if __name__ == "__main__":
    # Ensure COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, COMMON_VERTEX_STAGING_BUCKET are set in environment
    if not all(os.getenv(var) for var in ["COMMON_GOOGLE_CLOUD_PROJECT", "COMMON_GOOGLE_CLOUD_LOCATION", "COMMON_VERTEX_STAGING_BUCKET"]):
        logger.error("One or more required environment variables (COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, COMMON_VERTEX_STAGING_BUCKET) are not set.")
        logger.error("Please set them before running deploy_all.py.")
    else:
        asyncio.run(main())


def deploy_instavibe_app(project_id: str, region: str, image_name_param: str = "instavibe-app", env_vars_string: str | None = None): # Renamed image_name to image_name_param for clarity
    """Deploys the Instavibe app to Cloud Run, attempting to enable Kaniko and using --no-cache."""
    print(f"--- Deploying Instavibe App ({image_name_param}) ---")

    # 1. Set the gcloud configuration to use the Kaniko cache.
    print("Step 1: Attempting to enable Kaniko cache for Google Cloud Build...")
    try:
        subprocess.run(
            ["gcloud", "config", "set", "builds/use_kaniko", "True", "--project", project_id],
            check=True, capture_output=True, text=True
        )
        print("Kaniko cache enabled successfully for project.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not enable Kaniko cache (or it was already set). This is usually fine. Error: {e.stderr}")

    # 2. Build the Docker image with --no-cache
    # Construct the full image tag
    image_tag = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    print(f"\nStep 2: Building Instavibe App Docker image {image_tag} with a clean build...")
    try:
        build_command = [
            "gcloud", "builds", "submit", "instavibe", # Source path from repo root
            "--tag", image_tag,
            "--project", project_id,
            "--no-cache"
        ]
        subprocess.run(
            build_command,
            check=True, capture_output=True, text=True
            # cwd is not needed as "instavibe" is specified as source for gcloud builds submit
        )
        print(f"Successfully built image: {image_tag}")
    except subprocess.CalledProcessError as e:
        print(f"Error building Instavibe App image: {e.stderr}")
        # print full error details
        print(f"Stdout: {e.stdout}")
        raise

    # 3. Deploy the newly built image to Cloud Run
    print(f"\nStep 3: Deploying the new image {image_tag} to Cloud Run service {image_name_param}...")
    try:
        deploy_command = [
            "gcloud", "run", "deploy", image_name_param, # Service name
            "--image", image_tag, # Full image path
            "--platform", "managed",
            "--region", region,
            "--project", project_id,
            "--allow-unauthenticated",
        ]
        if env_vars_string: deploy_command.extend(["--set-env-vars", env_vars_string])

        print(f"Deploying Instavibe App to Cloud Run in {region} with env vars: {env_vars_string if env_vars_string else 'Defaults from Dockerfile/service'}")
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        print(f"Instavibe App {image_name_param} deployed successfully to Cloud Run in {region}.")

        # 4. Get the service URL
        print(f"\nStep 4: Fetching URL for Cloud Run service {image_name_param}...")
        url_command = [
            "gcloud", "run", "services", "describe", image_name_param,
            "--platform", "managed",
            "--region", region,
            "--project", project_id,
            "--format", "value(status.url)"
        ]
        url_result = subprocess.run(url_command, check=True, capture_output=True, text=True)
        service_url = url_result.stdout.strip()
        if not service_url:
            raise Exception(f"Failed to retrieve service URL for {image_name_param}")
        print(f"Successfully fetched URL for {image_name_param}: {service_url}")
        return service_url

    except subprocess.CalledProcessError as e:
        print(f"Error deploying Instavibe App to Cloud Run: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        raise

def deploy_mcp_tool_server(project_id: str, region: str, image_name_param: str = "mcp-tool-server", env_vars_string: str | None = None):
    """Deploys the MCP Tool Server to Cloud Run, attempting to enable Kaniko and using --no-cache."""
    print(f"--- Deploying MCP Tool Server ({image_name_param}) ---")

    # 1. Attempt to set the gcloud configuration to use the Kaniko cache (harmless if already set).
    print("Step 1: Ensuring Kaniko cache is enabled for Google Cloud Build...")
    try:
        subprocess.run(
            ["gcloud", "config", "set", "builds/use_kaniko", "True", "--project", project_id],
            check=True, capture_output=True, text=True
        )
        print("Kaniko cache configuration check/set complete for project.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not set Kaniko cache (or it was already set). This is usually fine. Error: {e.stderr}")

    # 2. Build the Docker image with --no-cache
    image_tag = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    print(f"\nStep 2: Building MCP Tool Server Docker image {image_tag} with a clean build...")
    try:
        build_command = [
            "gcloud", "builds", "submit", "tools/instavibe", # Source path from repo root
            "--tag", image_tag,
            "--project", project_id,
            "--no-cache"
        ]
        subprocess.run(
            build_command,
            check=True, capture_output=True, text=True
            # cwd is not needed as "tools/instavibe" is the source path argument
        )
        print(f"Successfully built image: {image_tag}")
    except subprocess.CalledProcessError as e:
        print(f"Error building MCP Tool Server image: {e.stderr}")
        print(f"Stdout: {e.stdout}") # Also print stdout for more context
        raise

    # 3. Deploy the newly built image to Cloud Run
    print(f"\nStep 3: Deploying the new image {image_tag} to Cloud Run service {image_name_param}...")
    try:
        deploy_command = [
            "gcloud", "run", "deploy", image_name_param,
            "--image", image_tag,
            "--platform", "managed", "--region", region, "--project", project_id, "--allow-unauthenticated",
        ]
        if env_vars_string: deploy_command.extend(["--set-env-vars", env_vars_string])

        print(f"Deploying MCP Tool Server to Cloud Run in {region} {'with env vars: ' + env_vars_string if env_vars_string else 'without specific env vars for --set-env-vars'}")
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        print(f"MCP Tool Server {image_name_param} deployed successfully to Cloud Run in {region}.")

        # 4. Get the service URL
        print(f"\nStep 4: Fetching URL for Cloud Run service {image_name_param}...")
        url_command = [
            "gcloud", "run", "services", "describe", image_name_param,
            "--platform", "managed",
            "--region", region,
            "--project", project_id,
            "--format", "value(status.url)"
        ]
        url_result = subprocess.run(url_command, check=True, capture_output=True, text=True)
        service_url = url_result.stdout.strip()
        if not service_url:
            raise Exception(f"Failed to retrieve service URL for {image_name_param}")
        print(f"Successfully fetched URL for {image_name_param}: {service_url}")
        return service_url

    except subprocess.CalledProcessError as e:
        print(f"Error deploying MCP Tool Server to Cloud Run: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        raise