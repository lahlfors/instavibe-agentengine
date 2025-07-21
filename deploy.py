import subprocess
import os
from dotenv import load_dotenv

load_dotenv()

def deploy_service(service_name):
    """Deploys a service to Google Cloud Run."""
    print(f"--- Deploying {service_name} ---")

    # Deploy the container image to Google Cloud Run
    subprocess.run([
        "gcloud", "run", "deploy", service_name,
        "--image", f"gcr.io/{os.environ['PROJECT_ID']}/{service_name}",
        "--platform", "managed",
        "--region", os.environ["REGION"],
        "--allow-unauthenticated",
    ], check=True)

    print(f"--- {service_name} deployment complete ---")

def deploy_orchestrator():
    """Deploys the orchestrator."""
    print("--- Deploying Orchestrator ---")
    subprocess.run(["python", "-c", "from orchestrate import agent; from vertexai import agent_engines; agent_engines.create(agent.root_agent, requirements='./agents/orchestrate/requirements.txt')"], check=True)
    print("--- Orchestrator deployment complete ---")

if __name__ == "__main__":
    # Build the container images using Google Cloud Build
    print("--- Building container images ---")
    subprocess.run(["gcloud", "builds", "submit", "--config", "cloudbuild.yaml", "."], check=True)
    print("--- Container images built successfully ---")

    # Deploy all the services
    deploy_service("a2a_gateway")
    deploy_service("planner")
    deploy_service("platform_mcp_client")
    deploy_service("social")
    deploy_service("instavibe")
    deploy_service("tools")
    deploy_orchestrator()
