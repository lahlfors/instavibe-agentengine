import subprocess
import argparse

def deploy_planner_agent(project_id: str, region: str):
    """Deploys the Planner Agent."""
    print("Deploying Planner Agent...")
    try:
        print("Installing Planner Agent dependencies...")
        subprocess.run(
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/planner",
        )
        subprocess.run(
            ["python", "deploy.py", "--project_id", project_id, "--region", region],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/planner",
        )
        print("Planner Agent deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Planner Agent: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_social_agent(project_id: str, region: str):
    """Deploys the Social Agent."""
    print("Deploying Social Agent...")
    try:
        print("Installing Social Agent dependencies...")
        subprocess.run(
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/social",
        )
        subprocess.run(
            ["python", "deploy.py", "--project_id", project_id, "--region", region],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/social",
        )
        print("Social Agent deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Social Agent: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_orchestrate_agent(project_id: str, region: str):
    """Deploys the Orchestrate Agent."""
    print("Deploying Orchestrate Agent...")
    try:
        print("Installing Orchestrate Agent dependencies...")
        subprocess.run(
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/orchestrate",
        )
        subprocess.run(
            ["python", "deploy.py", "--project_id", project_id, "--region", region],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/orchestrate",
        )
        print("Orchestrate Agent deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Orchestrate Agent: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_instavibe_app(project_id: str, region: str, image_name: str = "instavibe-app"):
    """Builds and deploys the Instavibe App to Cloud Run."""
    print("Deploying Instavibe App...")
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
    print("Deploying Platform MCP Client Agent to Vertex AI Agent Engine...")
    try:
        print("Installing Platform MCP Client Agent dependencies...")
        subprocess.run(
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/platform_mcp_client",
        )
        subprocess.run(
            [
                "python",
                "deploy.py", # Now relative to cwd
                "--project_id",
                project_id,
                "--location",
                region,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd="agents/platform_mcp_client",
        )
        print(f"Platform MCP Client Agent deployed successfully to Project: {project_id}, Region: {region}.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Platform MCP Client Agent: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise

def deploy_mcp_tool_server(project_id: str, region: str, image_name: str = "mcp-tool-server"):
    """Builds and deploys the MCP Tool Server to Cloud Run."""
    print("Deploying MCP Tool Server...")
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

    args = parser.parse_args()

    print("Installing root dependencies...")
    try:
        subprocess.run(
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Root dependencies installed successfully.")
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
