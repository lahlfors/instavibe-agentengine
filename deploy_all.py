import subprocess
import argparse
import sys
import os # Added
from dotenv import load_dotenv # Added
from google.cloud import aiplatform as vertexai # Standard alias
from google.cloud.aiplatform_v1.services import reasoning_engine_service
from google.api_core import exceptions as api_exceptions

# Pre-install root dependencies to ensure imports work
try:
    print("Pre-installing root dependencies for import purposes...")
    # Temporarily disable capture_output to see pip's full output
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
        check=True,  # Still check for errors
        text=True,   # Decode stdout/stderr as text
        capture_output=False # Print directly to console
    )
    print("Root dependencies pre-installed successfully (based on exit code).")
except subprocess.CalledProcessError as e:
    print(f"ERROR: Critical error pre-installing root dependencies: {e}")
    if e.stdout: # Access stdout via result object if needed, but with capture_output=False, it's on console
        print(f"Stdout: {e.stdout}")
    if e.stderr:
        print(f"Stderr: {e.stderr}")
    # It's critical, so perhaps exit or raise
    raise # Re-raise the exception to halt execution if pre-installation fails critically

print("Python sys.path before problematic import:")
print(sys.path)

from google.cloud import aiplatform
# Removed duplicate import of reasoning_engine_service_client
# from google.cloud.aiplatform_v1.types import ReasoningEngine # Not strictly needed by the provided functions

class ApiDisabledError(Exception): pass

from agents.planner.deploy import deploy_planner_main_func
from agents.social.deploy import deploy_social_main_func
from agents.orchestrate.deploy import deploy_orchestrate_main_func
from agents.platform_mcp_client.deploy import deploy_platform_mcp_client_main_func

# Helper Functions
def check_reasoning_engine_exists(gapic_client: reasoning_engine_service.ReasoningEngineServiceClient, parent_path: str, display_name: str) -> bool:
    try:
        engines = gapic_client.list_reasoning_engines(parent=parent_path)
        for engine in engines:
            if engine.display_name == display_name:
                print(f"Reasoning Engine '{display_name}' already exists.")
                return True
        print(f"Reasoning Engine '{display_name}' not found.")
        return False
    except api_exceptions.Forbidden as e:
        error_message = str(e).lower()
        if ("api has not been used" in error_message or
            "service is disabled" in error_message or
            "enable it by visiting" in error_message or
            'reason: "service_disabled"' in error_message):
            print(f"ERROR: Vertex AI API is disabled for project {parent_path.split('/')[1]}. "
                  f"Please enable it by visiting the URL mentioned in the error below. Full error: {e}")
            raise ApiDisabledError(f"Vertex AI API disabled for {parent_path.split('/')[1]}")
        else:
            print(f"Warning: Received a Forbidden error while checking for Reasoning Engine '{display_name}', but not the typical API disabled message: {e}. Assuming it does not exist.")
            return False
    except Exception as e:
        print(f"Warning: Error checking for Reasoning Engine '{display_name}': {e}. Assuming it does not exist.")
        return False

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
        if result.stdout.strip(): # If stdout is not empty, service exists
            print(f"Cloud Run service '{service_name}' already exists in project '{project_id}' region '{region}'.")
            return True
        else: # Should not happen if check=True and service exists, but as a fallback
            print(f"Cloud Run service '{service_name}' not found (stdout was empty).")
            return False
    except subprocess.CalledProcessError as e:
        # Non-zero exit code usually means service not found or other gcloud error
        print(f"Cloud Run service '{service_name}' not found or error describing: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error checking for Cloud Run service '{service_name}': {e}. Assuming it does not exist.")
        return False

# Deployment Functions
def deploy_planner_agent(project_id: str, region: str):
    """Deploys the Planner Agent."""
    agent_display_name = "Planner Agent"
    print(f"Starting deployment process for {agent_display_name} in project {project_id} region {region}...")

    # Initialize GAPIC client for checking
    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    try:
        gapic_client_for_check = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)
    except Exception as e:
        print(f"ERROR: Failed to create GAPIC client for pre-check: {e}. Skipping deployment of {agent_display_name}.")
        return

    parent_path = f"projects/{project_id}/locations/{region}"
    try:
        if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
            print(f"Skipping deployment of {agent_display_name} as it already exists.")
            return  # Exit the function if agent already exists
        print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
    except ApiDisabledError:
        print(f"Halting deployment of {agent_display_name} due to Vertex AI API being disabled.")
        return
    except Exception as e: # Catch any other unexpected error from the check
        print(f"Failed to check for existing {agent_display_name} due to an unexpected error: {e}. Skipping deployment.")
        return

    # The original print("Deploying Planner Agent...") is now covered by the more specific print above.
    try:
        print(f"Uninstalling existing {agent_display_name} dependencies...")
        # Uninstall doesn't need --break-system-packages
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "google-cloud-aiplatform", "google-adk", "-y"], capture_output=True, text=True, cwd="agents/planner")
        print("Installing Planner Agent dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/planner",
        )
        deploy_planner_main_func(project_id, region, base_dir=".")
        print("Planner Agent deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Planner Agent: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_social_agent(project_id: str, region: str):
    """Deploys the Social Agent."""
    agent_display_name = "Social Agent"
    print(f"Starting deployment process for {agent_display_name} in project {project_id} region {region}...")

    # Initialize GAPIC client for checking
    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    try:
        gapic_client_for_check = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)
    except Exception as e:
        print(f"ERROR: Failed to create GAPIC client for pre-check: {e}. Skipping deployment of {agent_display_name}.")
        return

    parent_path = f"projects/{project_id}/locations/{region}"
    try:
        if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
            print(f"Skipping deployment of {agent_display_name} as it already exists.")
            return
        print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
    except ApiDisabledError:
        print(f"Halting deployment of {agent_display_name} due to Vertex AI API being disabled.")
        return
    except Exception as e: # Catch any other unexpected error from the check
        print(f"Failed to check for existing {agent_display_name} due to an unexpected error: {e}. Skipping deployment.")
        return

    try:
        print(f"Installing {agent_display_name} dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/social",
        )
        deploy_social_main_func(project_id, region, base_dir=".")
        print(f"{agent_display_name} deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying {agent_display_name}: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_orchestrate_agent(project_id: str, region: str):
    """Deploys the Orchestrate Agent."""
    agent_display_name = "Orchestrate Agent"
    print(f"Starting deployment process for {agent_display_name} in project {project_id} region {region}...")

    # Initialize GAPIC client for checking
    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    try:
        gapic_client_for_check = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)
    except Exception as e:
        print(f"ERROR: Failed to create GAPIC client for pre-check: {e}. Skipping deployment of {agent_display_name}.")
        return

    parent_path = f"projects/{project_id}/locations/{region}"
    try:
        if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
            print(f"Skipping deployment of {agent_display_name} as it already exists.")
            return
        print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
    except ApiDisabledError:
        print(f"Halting deployment of {agent_display_name} due to Vertex AI API being disabled.")
        return
    except Exception as e: # Catch any other unexpected error from the check
        print(f"Failed to check for existing {agent_display_name} due to an unexpected error: {e}. Skipping deployment.")
        return

    try:
        print(f"Installing {agent_display_name} dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/orchestrate",
        )
        deploy_orchestrate_main_func(project_id, region, base_dir=".")
        print(f"{agent_display_name} deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying {agent_display_name}: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

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
            cwd="instavibe/", # Run this command in the instavibe/ directory
        )
        print(f"Instavibe App Docker image us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} built and pushed successfully via Cloud Build.")

        # Deploy to Cloud Run
        deploy_command = [
            "gcloud", "run", "deploy", image_name,
            "--image", f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name}",
            "--platform", "managed",
            "--region", region,
            "--project", project_id,
            "--allow-unauthenticated", # Assuming public access for now
        ]
        if env_vars_string:
            deploy_command.extend(["--set-env-vars", env_vars_string])
        # If no env_vars_string, the --set-env-vars flag is omitted.
        # The app should be prepared to handle missing optional env vars if not baked into the image,
        # or rely on defaults set in its Dockerfile or app code.

        print(f"Deploying Instavibe App us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} to Cloud Run in {region} with env vars: {env_vars_string if env_vars_string else 'No specific env-vars passed via --set-env-vars'}")
        subprocess.run(
            deploy_command,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"Instavibe App {image_name} deployed successfully to Cloud Run in {region}.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Instavibe App: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_platform_mcp_client(project_id: str, region: str):
    """Deploys the Platform MCP Client Agent to Vertex AI Agent Engine."""
    agent_display_name = "Platform MCP Client Agent"
    print(f"Starting deployment process for {agent_display_name} in project {project_id} region {region}...")

    # Initialize GAPIC client for checking
    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    try:
        gapic_client_for_check = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)
    except Exception as e:
        print(f"ERROR: Failed to create GAPIC client for pre-check: {e}. Skipping deployment of {agent_display_name}.")
        return

    parent_path = f"projects/{project_id}/locations/{region}"
    try:
        if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
            print(f"Skipping deployment of {agent_display_name} as it already exists.")
            return
        print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
    except ApiDisabledError:
        print(f"Halting deployment of {agent_display_name} due to Vertex AI API being disabled.")
        return
    except Exception as e: # Catch any other unexpected error from the check
        print(f"Failed to check for existing {agent_display_name} due to an unexpected error: {e}. Skipping deployment.")
        return

    try:
        print(f"Installing {agent_display_name} dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/platform_mcp_client",
        )
        deploy_platform_mcp_client_main_func(project_id, region, base_dir=".")
        print(f"{agent_display_name} deployed successfully to Project: {project_id}, Region: {region}.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying {agent_display_name}: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

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
            cwd="tools/instavibe/", # Run this command in the tools/instavibe/ directory
        )
        print(f"MCP Tool Server Docker image us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} built and pushed successfully via Cloud Build.")

        # Deploy to Cloud Run
        deploy_command = [
            "gcloud", "run", "deploy", image_name,
            "--image", f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name}",
            "--platform", "managed",
            "--region", region,
            "--project", project_id,
            "--allow-unauthenticated", # Assuming public access for now
        ]
        if env_vars_string: # Add env vars if provided
            deploy_command.extend(["--set-env-vars", env_vars_string])

        print(f"Deploying MCP Tool Server us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name} to Cloud Run in {region} {'with env vars: ' + env_vars_string if env_vars_string else 'without specific env vars for --set-env-vars'}")
        subprocess.run(
            deploy_command,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"MCP Tool Server {image_name} deployed successfully to Cloud Run in {region}.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying MCP Tool Server: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def main(argv=None):
    """
    Main function to deploy all components of the instavibe app.
    """
    load_dotenv() # Load .env file from project root

    project_id = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")
    # Using COMMON_GOOGLE_CLOUD_LOCATION as the common region for all deployments in this script.
    region = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION")
    staging_bucket_uri = os.environ.get("COMMON_VERTEX_STAGING_BUCKET")

    if not project_id:
        raise ValueError("COMMON_GOOGLE_CLOUD_PROJECT not set in .env file")
    if not region:
        raise ValueError("COMMON_GOOGLE_CLOUD_LOCATION (used as common deploy region) not set in .env file")
    if not staging_bucket_uri:
        raise ValueError("COMMON_VERTEX_STAGING_BUCKET not set in .env file")

    parser = argparse.ArgumentParser(description="Deploy all components of the instavibe app.")
    # Removed --project_id, --region, --staging_bucket arguments
    parser.add_argument(
        "--skip_agents", action="store_true", help="Skip deploying the agents."
    )
    parser.add_argument(
        "--skip_app", action="store_true", help="Skip deploying the Instavibe app."
    )
    parser.add_argument(
        "--skip_platform_mcp_client", action="store_true", help="Skip deploying the Platform MCP Client."
    )
    parser.add_argument(
        "--skip_mcp_tool_server", action="store_true", help="Skip deploying the MCP Tool Server."
    )
    # Removed --staging_bucket argument

    args = parser.parse_args(argv)

    print(f"Initializing Vertex AI with project: {project_id}, region: {region}, staging bucket: {staging_bucket_uri}")
    try:
        vertexai.init(
            project=project_id,
            location=region,
            staging_bucket=staging_bucket_uri
        )
        print("Vertex AI initialized successfully.")
    except Exception as e:
        print(f"Error initializing Vertex AI: {e}")
        # Depending on the desired behavior, you might want to raise the exception or exit.
        # For now, just print and continue to see if other parts fail.
        # Consider exiting if init is critical for all subsequent steps.

    print("Ensuring root dependencies are installed (main check)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Root dependencies verified/installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error installing root dependencies: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

    if not args.skip_agents:
        deploy_planner_agent(project_id, region) # Use variables from env
        deploy_social_agent(project_id, region) # Use variables from env
        deploy_orchestrate_agent(project_id, region) # Use variables from env
    else:
        print("Skipping agent deployments.")

    if not args.skip_app:
        # Construct env_vars string for Instavibe app
        instavibe_env_vars_list = [
            f"COMMON_GOOGLE_CLOUD_PROJECT={os.environ.get('COMMON_GOOGLE_CLOUD_PROJECT', '')}",
            f"COMMON_SPANNER_INSTANCE_ID={os.environ.get('COMMON_SPANNER_INSTANCE_ID', '')}",
            f"COMMON_SPANNER_DATABASE_ID={os.environ.get('COMMON_SPANNER_DATABASE_ID', '')}",
            f"INSTAVIBE_FLASK_SECRET_KEY={os.environ.get('INSTAVIBE_FLASK_SECRET_KEY', '')}",
            f"INSTAVIBE_APP_HOST={os.environ.get('INSTAVIBE_APP_HOST', '0.0.0.0')}",
            f"INSTAVIBE_APP_PORT={os.environ.get('INSTAVIBE_APP_PORT', '8080')}",
            f"INSTAVIBE_GOOGLE_MAPS_API_KEY={os.environ.get('INSTAVIBE_GOOGLE_MAPS_API_KEY', '')}",
            f"INSTAVIBE_GOOGLE_MAPS_MAP_ID={os.environ.get('INSTAVIBE_GOOGLE_MAPS_MAP_ID', '')}",
        ]
        # Filter out vars that were not set in .env to avoid "VARNAME=" or "VARNAME=None"
        instavibe_env_vars_string = ",".join(
            var for var in instavibe_env_vars_list if var.split('=', 1)[1] not in ['None', '']
        )
        deploy_instavibe_app(project_id, region, env_vars_string=instavibe_env_vars_string)
    else:
        print("Skipping Instavibe app deployment.")

    if not args.skip_platform_mcp_client:
        deploy_platform_mcp_client(project_id, region) # Use variables from env
    else:
        print("Skipping Platform MCP Client deployment.")

    if not args.skip_mcp_tool_server:
        # For mcp_tool_server, construct env_vars_string if needed.
        # These are examples; the mcp_server.py itself doesn't use many of these directly,
        # but its dependencies or underlying ADK/cloud libraries might.
        mcp_tool_server_env_vars_list = [
            f"COMMON_GOOGLE_CLOUD_PROJECT={os.environ.get('COMMON_GOOGLE_CLOUD_PROJECT', '')}",
            f"TOOLS_INSTAVIBE_BASE_URL={os.environ.get('TOOLS_INSTAVIBE_BASE_URL', '')}",
            f"TOOLS_GOOGLE_GENAI_USE_VERTEXAI={os.environ.get('TOOLS_GOOGLE_GENAI_USE_VERTEXAI', '')}",
            f"TOOLS_GOOGLE_CLOUD_LOCATION={os.environ.get('COMMON_GOOGLE_CLOUD_LOCATION', '')}",
            f"TOOLS_GOOGLE_API_KEY={os.environ.get('TOOLS_GOOGLE_API_KEY', '')}",
            # Add other TOOLS_ prefixed vars if the mcp_server uses them (e.g., APP_HOST, APP_PORT if they were prefixed)
        ]
        mcp_tool_server_env_vars_string = ",".join(
            var for var in mcp_tool_server_env_vars_list if var.split('=', 1)[1] not in ['None', '']
        )
        # Pass the env_vars_string. If it's empty, no --set-env-vars will be added by the deploy function.
        deploy_mcp_tool_server(project_id, region, env_vars_string=mcp_tool_server_env_vars_string if mcp_tool_server_env_vars_string else None)
    else:
        print("Skipping MCP Tool Server deployment.")

    print("All selected components deployed.")


if __name__ == "__main__":
    main()
