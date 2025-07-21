import subprocess
import os

def deploy_service(service_name, dockerfile_path):
    """Deploys a service to Google Cloud Run."""
    print(f"--- Deploying {service_name} ---")

    # Build the container image
    image_name = f"gcr.io/{os.environ['PROJECT_ID']}/{service_name}"
    subprocess.run(["docker", "build", "-t", image_name, "-f", dockerfile_path, "."], check=True, cwd=os.path.dirname(dockerfile_path))

    # Push the container image to Google Container Registry
    subprocess.run(["docker", "push", image_name], check=True)

    # Deploy the container image to Google Cloud Run
    subprocess.run([
        "gcloud", "run", "deploy", service_name,
        "--image", image_name,
        "--platform", "managed",
        "--region", os.environ["REGION"],
        "--allow-unauthenticated",
    ], check=True)

    print(f"--- {service_name} deployment complete ---")

def deploy_orchestrator():
    """Deploys the orchestrator."""
    print("--- Deploying Orchestrator ---")
    subprocess.run(["python", "agents/orchestrate/deploy.py"], check=True)
    print("--- Orchestrator deployment complete ---")

if __name__ == "__main__":
    # Deploy all the services
    deploy_service("a2a_gateway", "agents/a2a_gateway/Dockerfile")
    deploy_service("planner", "agents/planner/Dockerfile")
    deploy_service("platform_mcp_client", "agents/platform_mcp_client/Dockerfile")
    deploy_service("social", "agents/social/Dockerfile")
    deploy_service("instavibe", "instavibe/Dockerfile")
    deploy_service("tools", "tools/instavibe/Dockerfile")
    deploy_orchestrator()
