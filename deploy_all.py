import subprocess
import argparse
import sys
from google.cloud import aiplatform as vertexai # Standard alias
from google.cloud.aiplatform_v1.services import reasoning_engine_service

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
    except Exception as e:
        print(f"Error checking for Reasoning Engine '{display_name}': {e}. Assuming it does not exist.")
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
    if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
        print(f"Skipping deployment of {agent_display_name} as it already exists.")
        return  # Exit the function if agent already exists

    print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
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
    if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
        print(f"Skipping deployment of {agent_display_name} as it already exists.")
        return

    print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
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
    if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
        print(f"Skipping deployment of {agent_display_name} as it already exists.")
        return

    print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
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

def deploy_instavibe_app(project_id: str, region: str, image_name: str = "instavibe-app"):
    """Builds and deploys the Instavibe App to Cloud Run."""
    print(f"Starting deployment process for Cloud Run service '{image_name}' in project {project_id} region {region}...")

    if check_cloud_run_service_exists(service_name=image_name, project_id=project_id, region=region):
        print(f"Skipping deployment of Cloud Run service '{image_name}' as it already exists.")
        return  # Exit the function if service already exists

    print(f"Proceeding with deployment of Cloud Run service '{image_name}'.")
    try:
        # Build Docker image using Google Cloud Build
        print(f"Building Instavibe App Docker image gcr.io/{project_id}/{image_name} using Google Cloud Build...")
        subprocess.run(
            [
                "gcloud",
                "builds",
                "submit",
                "--tag",
                f"gcr.io/{project_id}/{image_name}",
                ".",
                "--project",
                project_id,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd="instavibe/", # Run this command in the instavibe/ directory
        )
        print(f"Instavibe App Docker image gcr.io/{project_id}/{image_name} built and pushed successfully via Cloud Build.")

        # Deploy to Cloud Run
        print(f"Deploying Instavibe App {image_name} to Cloud Run in {region}...")
        subprocess.run(
            [
                "gcloud",
                "run",
                "deploy",
                image_name,
                "--image",
                f"gcr.io/{project_id}/{image_name}",
                "--platform",
                "managed",
                "--region",
                region,
                "--project",
                project_id,
                "--allow-unauthenticated", # Assuming public access for now
            ],
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
    if check_reasoning_engine_exists(gapic_client_for_check, parent_path, agent_display_name):
        print(f"Skipping deployment of {agent_display_name} as it already exists.")
        return

    print(f"Proceeding with deployment of {agent_display_name} as it does not exist or an error occurred during check.")
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

def deploy_mcp_tool_server(project_id: str, region: str, image_name: str = "mcp-tool-server"):
    """Builds and deploys the MCP Tool Server to Cloud Run."""
    print(f"Starting deployment process for Cloud Run service '{image_name}' in project {project_id} region {region}...")

    if check_cloud_run_service_exists(service_name=image_name, project_id=project_id, region=region):
        print(f"Skipping deployment of Cloud Run service '{image_name}' as it already exists.")
        return  # Exit the function if service already exists

    print(f"Proceeding with deployment of Cloud Run service '{image_name}'.")
    try:
        # Build Docker image using Google Cloud Build
        print(f"Building MCP Tool Server Docker image gcr.io/{project_id}/{image_name} using Google Cloud Build...")
        subprocess.run(
            [
                "gcloud",
                "builds",
                "submit",
                "--tag",
                f"gcr.io/{project_id}/{image_name}",
                ".",
                "--project",
                project_id,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd="tools/instavibe/", # Run this command in the tools/instavibe/ directory
        )
        print(f"MCP Tool Server Docker image gcr.io/{project_id}/{image_name} built and pushed successfully via Cloud Build.")

        # Deploy to Cloud Run
        print(f"Deploying MCP Tool Server {image_name} to Cloud Run in {region}...")
        subprocess.run(
            [
                "gcloud",
                "run",
                "deploy",
                image_name,
                "--image",
                f"gcr.io/{project_id}/{image_name}",
                "--platform",
                "managed",
                "--region",
                region,
                "--project",
                project_id,
                "--allow-unauthenticated", # Assuming public access for now
            ],
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

def main():
    """
    Main function to deploy all components of the instavibe app.
    """
    parser = argparse.ArgumentParser(description="Deploy all components of the instavibe app.")
    parser.add_argument("--project_id", required=True, help="Google Cloud project ID.")
    parser.add_argument("--region", required=True, help="Google Cloud region for deployment.")
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
    parser.add_argument(
        "--staging_bucket",
        type=str,
        required=True,
        help="GCS URI for the Vertex AI staging bucket (e.g., gs://your-bucket-name).",
    )

    args = parser.parse_args()

    print(f"Initializing Vertex AI with project: {args.project_id}, region: {args.region}, staging bucket: {args.staging_bucket}")
    try:
        vertexai.init(
            project=args.project_id,
            location=args.region,
            staging_bucket=args.staging_bucket
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
        deploy_planner_agent(args.project_id, args.region)
        deploy_social_agent(args.project_id, args.region)
        deploy_orchestrate_agent(args.project_id, args.region)
    else:
        print("Skipping agent deployments.")

    if not args.skip_app:
        deploy_instavibe_app(args.project_id, args.region)
    else:
        print("Skipping Instavibe app deployment.")

    if not args.skip_platform_mcp_client:
        deploy_platform_mcp_client(args.project_id, args.region)
    else:
        print("Skipping Platform MCP Client deployment.")

    if not args.skip_mcp_tool_server:
        deploy_mcp_tool_server(args.project_id, args.region)
    else:
        print("Skipping MCP Tool Server deployment.")

    print("All selected components deployed.")


if __name__ == "__main__":
    main()
