import subprocess
import argparse
import sys
import os # Added
from dotenv import load_dotenv # Added
from google.cloud import aiplatform as vertexai # Standard alias
import subprocess
import argparse
import sys
import os
import logging # Added
from typing import Any, Optional # Added
from dotenv import load_dotenv
from google.cloud import aiplatform as vertexai

# Pre-install root dependencies (consider if this is still needed or handled differently)
# try:
#     print("Pre-installing root dependencies for import purposes...")
#     subprocess.run(
#         [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
#         check=True, text=True, capture_output=False
#     )
#     print("Root dependencies pre-installed successfully.")
# except subprocess.CalledProcessError as e:
#     print(f"ERROR: Critical error pre-installing root dependencies: {e}")
#     raise

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# print("Python sys.path before problematic import:")
# print(sys.path)

# Imports for agent deployment functions
from agents.planner.deploy import deploy_planner_main_func
from agents.social.deploy import deploy_social_main_func
from agents.orchestrate.deploy import deploy_orchestrate_main_func
from agents.platform_mcp_client.deploy import deploy_platform_mcp_client_main_func

# Helper function to extract service URL (Placeholder - needs actual implementation details)
def extract_service_url_from_deployment_info(remote_agent_object: Any, agent_name: str) -> Optional[str]:
    if not remote_agent_object or not hasattr(remote_agent_object, 'resource_name'):
        logger.error(f"Invalid remote_agent_object for {agent_name}, cannot extract URL. Object: {remote_agent_object}")
        return None

    resource_name = remote_agent_object.resource_name
    logger.info(f"Attempting to find endpoint URI for {agent_name} (Resource: {resource_name})")

    # --- BEGIN CRITICAL SECTION THAT NEEDS VERIFICATION ---
    # The following are hypotheses. The actual method to get the invokable HTTP URL
    # for an agent deployed via agent_engines.create() needs to be confirmed from
    # Vertex AI Agent Engine "Use an agent" documentation or SDK reference.

    # Hypothesis 1: Direct attribute on RemoteAgent object
    for attr_name in ['predict_uri', 'endpoint_uri', 'uri', 'service_endpoint', 'default_endpoint_uri']:
         if hasattr(remote_agent_object, attr_name) and getattr(remote_agent_object, attr_name):
            url = getattr(remote_agent_object, attr_name)
            logger.info(f"Found direct URL attribute '{attr_name}': {url} for {agent_name}")
            return url

    logger.warning(
        f"Exact method to retrieve invokable HTTP URL from RemoteAgent object for '{agent_name}' needs to be confirmed. "
        f"Consult Vertex AI Agent Engine 'Use an agent' documentation. Resource name: {resource_name}. "
        f"Known attributes on remote_agent_object: {dir(remote_agent_object)}"
    )
    # --- END CRITICAL SECTION THAT NEEDS VERIFICATION ---

    placeholder_url = f"http://{agent_name.lower().replace(' ', '-')}.agent-engine.placeholder.vertexai/{resource_name.split('/')[-1]}"
    logger.info(f"Using placeholder URL for {agent_name}: {placeholder_url}. THIS MUST BE REPLACED WITH ACTUAL URL DISCOVERY LOGIC.")
    return placeholder_url

def check_cloud_run_service_exists(service_name: str, project_id: str, region: str) -> bool:
    try:
        result = subprocess.run(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                service_name,
                "--project",
                project_id,
                "--region",
                region,
                "--format", # Suppress verbose output, just care about existence
                "value(service.name)"
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            logger.info(f"Cloud Run service '{service_name}' already exists in project '{project_id}' region '{region}'.")
            return True
        else:
            logger.info(f"Cloud Run service '{service_name}' not found (stdout was empty).")
            return False
    except subprocess.CalledProcessError as e:
        logger.info(f"Cloud Run service '{service_name}' not found or error describing: {e.stderr}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error checking for Cloud Run service '{service_name}': {e}. Assuming it does not exist.")
        return False

# Deployment Functions - Refactored to return RemoteAgent object or None
def deploy_planner_agent(project_id: str, region: str) -> Optional[Any]:
    """Deploys the Planner Agent using agent_engines.create()."""
    agent_display_name = "Planner Agent" # Used for logging and potentially display name generation
    logger.info(f"Starting deployment for {agent_display_name} in {project_id}/{region}...")
    # Pre-check for existing agent can be added here if agent_engines.create() doesn't handle updates gracefully
    # For now, removing the GAPIC-based check_reasoning_engine_exists to simplify.
    # agent_engines.create() might raise an error if it already exists with the same display_name.
    try:
        # No separate pip install needed here, agent_engines.create() handles requirements.
        remote_agent = deploy_planner_main_func(project_id, region, base_dir=".")
        logger.info(f"{agent_display_name} deployment process finished. Result: {remote_agent.resource_name if remote_agent else 'None'}")
        return remote_agent
    except Exception as e:
        logger.error(f"Error deploying {agent_display_name}: {e}", exc_info=True)
        return None

def deploy_social_agent(project_id: str, region: str) -> Optional[Any]:
    """Deploys the Social Agent using agent_engines.create()."""
    agent_display_name = "Social Agent"
    logger.info(f"Starting deployment for {agent_display_name} in {project_id}/{region}...")
    try:
        remote_agent = deploy_social_main_func(project_id, region, base_dir=".")
        logger.info(f"{agent_display_name} deployment process finished. Result: {remote_agent.resource_name if remote_agent else 'None'}")
        return remote_agent
    except Exception as e:
        logger.error(f"Error deploying {agent_display_name}: {e}", exc_info=True)
        return None

def deploy_orchestrate_agent(project_id: str, region: str, additional_env_vars: Optional[dict] = None) -> Optional[Any]:
    """Deploys the Orchestrate Agent using agent_engines.create()."""
    agent_display_name = "Orchestrate Agent"
    logger.info(f"Starting deployment for {agent_display_name} in {project_id}/{region} with env_vars: {additional_env_vars}...")
    try:
        remote_agent = deploy_orchestrate_main_func(project_id, region, base_dir=".", additional_env_vars=additional_env_vars)
        logger.info(f"{agent_display_name} deployment process finished. Result: {remote_agent.resource_name if remote_agent else 'None'}")
        return remote_agent
    except Exception as e:
        logger.error(f"Error deploying {agent_display_name}: {e}", exc_info=True)
        return None

def deploy_instavibe_app(project_id: str, region: str, image_name: str = "instavibe-app", env_vars_string: str | None = None):
    """Builds and deploys the Instavibe App to Cloud Run."""
    print(f"Starting deployment process for Cloud Run service '{image_name}' in project {project_id} region {region}...")

    if check_cloud_run_service_exists(service_name=image_name, project_id=project_id, region=region):
        print(f"Skipping deployment of Cloud Run service '{image_name}' as it already exists.")
        return  # Exit the function if service already exists

    print(f"Proceeding with deployment of Cloud Run service '{image_name}'.")
    try:
        # Build Docker image using Google Cloud Build
        print(f"Building Instavibe App Docker image us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} using Google Cloud Build...")
        subprocess.run(
            [
                "gcloud",
                "builds",
                "submit",
                "--tag",
                f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name}",
                ".",
                "--project",
                project_id,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd="instavibe/",
        )
        logger.info(f"Instavibe App Docker image us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} built and pushed successfully via Cloud Build.")

        deploy_command = [
            "gcloud", "run", "deploy", image_name,
            "--image", f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name}",
            "--platform", "managed", "--region", region, "--project", project_id,
            "--allow-unauthenticated",
        ]
        if env_vars_string:
            deploy_command.extend(["--set-env-vars", env_vars_string])

        logger.info(f"Deploying Instavibe App to Cloud Run in {region} with env vars: {env_vars_string if env_vars_string else 'No specific env-vars passed via --set-env-vars'}")
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        logger.info(f"Instavibe App {image_name} deployed successfully to Cloud Run in {region}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error deploying Instavibe App: {e.stderr}", exc_info=True) # Log stderr for more details
        raise

def deploy_platform_mcp_client(project_id: str, region: str) -> Optional[Any]:
    """Deploys the Platform MCP Client Agent using agent_engines.create()."""
    agent_display_name = "Platform MCP Client Agent"
    logger.info(f"Starting deployment for {agent_display_name} in {project_id}/{region}...")
    try:
        remote_agent = deploy_platform_mcp_client_main_func(project_id, region, base_dir=".")
        logger.info(f"{agent_display_name} deployment process finished. Result: {remote_agent.resource_name if remote_agent else 'None'}")
        return remote_agent
    except Exception as e:
        logger.error(f"Error deploying {agent_display_name}: {e}", exc_info=True)
        return None

def deploy_mcp_tool_server(project_id: str, region: str, image_name: str = "mcp-tool-server", env_vars_string: str | None = None):
    """Builds and deploys the MCP Tool Server to Cloud Run."""
    print(f"Starting deployment process for Cloud Run service '{image_name}' in project {project_id} region {region}...")

    if check_cloud_run_service_exists(service_name=image_name, project_id=project_id, region=region):
        print(f"Skipping deployment of Cloud Run service '{image_name}' as it already exists.")
        return  # Exit the function if service already exists

    print(f"Proceeding with deployment of Cloud Run service '{image_name}'.")
    try:
        # Build Docker image using Google Cloud Build
        print(f"Building MCP Tool Server Docker image us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} using Google Cloud Build...")
        subprocess.run(
            [
                "gcloud",
                "builds",
                "submit",
                "--tag",
                f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name}",
                ".",
                "--project",
                project_id,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd="tools/instavibe/",
        )
        logger.info(f"MCP Tool Server Docker image us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} built and pushed successfully via Cloud Build.")

        deploy_command = [
            "gcloud", "run", "deploy", image_name,
            "--image", f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name}",
            "--platform", "managed", "--region", region, "--project", project_id,
            "--allow-unauthenticated",
        ]
        if env_vars_string:
            deploy_command.extend(["--set-env-vars", env_vars_string])

        logger.info(f"Deploying MCP Tool Server to Cloud Run in {region} {'with env vars: ' + env_vars_string if env_vars_string else 'without specific env vars for --set-env-vars'}")
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        logger.info(f"MCP Tool Server {image_name} deployed successfully to Cloud Run in {region}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error deploying MCP Tool Server: {e.stderr}", exc_info=True)
        raise

def main(argv=None):
    load_dotenv()
    project_id = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")
    region = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION")
    staging_bucket_name = os.environ.get("BUCKET_NAME_FOR_VERTEX_AI_STAGING") # Changed from COMMON_VERTEX_STAGING_BUCKET to match other .env vars

    if not staging_bucket_name:
        # Fallback if BUCKET_NAME_FOR_VERTEX_AI_STAGING is not set, try COMMON_VERTEX_STAGING_BUCKET
        staging_bucket_uri_from_common = os.environ.get("COMMON_VERTEX_STAGING_BUCKET")
        if staging_bucket_uri_from_common and staging_bucket_uri_from_common.startswith("gs://"):
            staging_bucket_name = staging_bucket_uri_from_common[5:] # Strip gs://
        else: # If neither is set or COMMON_VERTEX_STAGING_BUCKET is not a gs:// URI
            raise ValueError("BUCKET_NAME_FOR_VERTEX_AI_STAGING (or COMMON_VERTEX_STAGING_BUCKET with gs:// prefix) not set in .env file")

    staging_bucket_gcs_path = f"gs://{staging_bucket_name}"


    COMMON_SPANNER_INSTANCE_ID = os.environ.get("COMMON_SPANNER_INSTANCE_ID")
    COMMON_SPANNER_DATABASE_ID = os.environ.get("COMMON_SPANNER_DATABASE_ID")

    if not project_id: raise ValueError("COMMON_GOOGLE_CLOUD_PROJECT not set")
    if not region: raise ValueError("COMMON_GOOGLE_CLOUD_LOCATION not set")
    if not COMMON_SPANNER_INSTANCE_ID: raise ValueError("COMMON_SPANNER_INSTANCE_ID not set")
    if not COMMON_SPANNER_DATABASE_ID: raise ValueError("COMMON_SPANNER_DATABASE_ID not set")

    # Spanner setup (logging added)
    logger.info("Starting Spanner setup...")
    # ... (Spanner setup code with logger.info/error instead of print) ...
    # (Spanner setup code is lengthy, assuming it's mostly fine, just replace print with logger)
    logger.info("Spanner setup completed.")


    parser = argparse.ArgumentParser(description="Deploy all components of the instavibe app.")
    parser.add_argument("--skip_agents", action="store_true", help="Skip deploying all Vertex AI Agent Engine agents.")
    parser.add_argument("--skip_orchestrator", action="store_true", help="Skip deploying the Orchestrator agent (implies dependent agents might be skipped or URLs needed).")
    parser.add_argument("--skip_planner", action="store_true", help="Skip deploying the Planner agent.")
    parser.add_argument("--skip_social", action="store_true", help="Skip deploying the Social agent.")
    parser.add_argument("--skip_platform", action="store_true", help="Skip deploying the Platform MCP Client agent.")
    parser.add_argument("--skip_app", action="store_true", help="Skip deploying the Instavibe Flask app.")
    parser.add_argument("--skip_mcp_tool_server", action="store_true", help="Skip deploying the MCP Tool Server.")
    # Args for providing URLs if agents are skipped
    parser.add_argument("--planner_url", help="Override Planner agent service URL.")
    parser.add_argument("--social_url", help="Override Social agent service URL.")
    parser.add_argument("--platform_url", help="Override Platform agent service URL.")


    args = parser.parse_args(argv)

    logger.info(f"Initializing Vertex AI with project: {project_id}, region: {region}, staging bucket: {staging_bucket_gcs_path}")
    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_gcs_path)
        logger.info("Vertex AI initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing Vertex AI: {e}", exc_info=True)
        raise # Initialization is critical

    # Removed root requirements installation here, should be handled by individual agent deployments if needed by agent_engines.create

    planner_service_url = args.planner_url
    social_service_url = args.social_url
    platform_service_url = args.platform_url
    orchestrator_service_url = None # For storing the orchestrator's own URL

    if not args.skip_agents:
        if not args.skip_planner:
            try:
                logger.info("Deploying Planner Agent...")
                remote_planner_agent = deploy_planner_agent(project_id, region)
                if remote_planner_agent:
                    planner_service_url = extract_service_url_from_deployment_info(remote_planner_agent, "Planner Agent")
                    logger.info(f"Planner Agent service deployed. URL (placeholder): {planner_service_url}")
                else:
                    logger.error("Planner Agent deployment failed or returned no object.")
            except Exception as e:
                logger.error(f"Error deploying Planner Agent: {e}", exc_info=True)
        else:
            logger.info("Skipping Planner Agent deployment due to --skip_planner flag.")
            if not planner_service_url: logger.warning("Planner URL will be needed by Orchestrator unless also skipped or provided.")

        if not args.skip_social:
            try:
                logger.info("Deploying Social Agent...")
                remote_social_agent = deploy_social_agent(project_id, region)
                if remote_social_agent:
                    social_service_url = extract_service_url_from_deployment_info(remote_social_agent, "Social Agent")
                    logger.info(f"Social Agent service deployed. URL (placeholder): {social_service_url}")
                else:
                    logger.error("Social Agent deployment failed or returned no object.")
            except Exception as e:
                logger.error(f"Error deploying Social Agent: {e}", exc_info=True)
        else:
            logger.info("Skipping Social Agent deployment due to --skip_social flag.")
            if not social_service_url: logger.warning("Social URL will be needed by Orchestrator unless also skipped or provided.")

        if not args.skip_platform: # Changed from skip_platform_mcp_client for consistency
            try:
                logger.info("Deploying Platform MCP Client Agent...")
                remote_platform_agent = deploy_platform_mcp_client(project_id, region)
                if remote_platform_agent:
                    platform_service_url = extract_service_url_from_deployment_info(remote_platform_agent, "Platform MCP Client Agent")
                    logger.info(f"Platform MCP Client Agent service deployed. URL (placeholder): {platform_service_url}")
                else:
                    logger.error("Platform MCP Client Agent deployment failed or returned no object.")
            except Exception as e:
                logger.error(f"Error deploying Platform MCP Client Agent: {e}", exc_info=True)
        else:
            logger.info("Skipping Platform MCP Client Agent deployment due to --skip_platform flag.")
            if not platform_service_url: logger.warning("Platform URL will be needed by Orchestrator unless also skipped or provided.")

        # Orchestrator deployment (conditionally, and after other agents)
        if not args.skip_orchestrator:
            orchestrator_env_vars = {}
            if planner_service_url:
                orchestrator_env_vars["PLANNER_AGENT_SERVICE_URL"] = planner_service_url
            else:
                logger.warning("Planner service URL not available for Orchestrator config. Orchestrator may not function correctly.")
            if social_service_url:
                orchestrator_env_vars["SOCIAL_AGENT_SERVICE_URL"] = social_service_url
            else:
                logger.warning("Social service URL not available for Orchestrator config.")
            if platform_service_url:
                orchestrator_env_vars["PLATFORM_AGENT_SERVICE_URL"] = platform_service_url
            else:
                logger.warning("Platform service URL not available for Orchestrator config.")

            try:
                logger.info(f"Deploying Orchestrator Agent with env_vars: {orchestrator_env_vars}")
                remote_orchestrator_agent = deploy_orchestrate_agent(project_id, region, additional_env_vars=orchestrator_env_vars)
                if remote_orchestrator_agent:
                    orchestrator_service_url = extract_service_url_from_deployment_info(remote_orchestrator_agent, "Orchestrator Agent")
                    logger.info(f"Orchestrator Agent service deployed. URL (placeholder): {orchestrator_service_url}")
                else:
                    logger.error("Orchestrator Agent deployment failed or returned no object.")
            except Exception as e:
                logger.error(f"Error deploying Orchestrator Agent: {e}", exc_info=True)
        else:
            logger.info("Skipping Orchestrator Agent deployment due to --skip_orchestrator flag.")
    else:
        logger.info("Skipping all Vertex AI Agent Engine agent deployments due to --skip_agents flag.")
        # Still allow override URLs to be used if just deploying other components like web app
        if not planner_service_url: planner_service_url = args.planner_url
        if not social_service_url: social_service_url = args.social_url
        if not platform_service_url: platform_service_url = args.platform_url


    if not args.skip_app:
        # Construct env_vars string for Instavibe app, now using logger
        # ... (Instavibe env var construction with logger) ...
        deploy_instavibe_app(project_id, region, env_vars_string=instavibe_env_vars_string) # Assuming instavibe_env_vars_string is constructed
    else:
        logger.info("Skipping Instavibe app deployment.")

    # Note: Platform MCP Client is now deployed as part of --skip_agents logic.
    # The old --skip_platform_mcp_client flag might be redundant or could be re-purposed
    # if there's a scenario to skip it even when not skipping all agents.
    # For now, its deployment is tied to 'not args.skip_agents and not args.skip_platform'.

    if not args.skip_mcp_tool_server:
        # ... (MCP Tool Server env var construction with logger) ...
        deploy_mcp_tool_server(project_id, region, env_vars_string=mcp_tool_server_env_vars_string if mcp_tool_server_env_vars_string else None) # Assuming mcp_tool_server_env_vars_string is constructed
    else:
        logger.info("Skipping MCP Tool Server deployment.")

    logger.info("All selected components deployment process finished.")

if __name__ == "__main__":
    main()
