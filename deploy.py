import subprocess
import os
import json
from dotenv import load_dotenv

load_dotenv()

def deploy_service(service_name, env_vars=None):
    """Deploys a service to Google Cloud Run and returns its URL."""
    print(f"--- Deploying {service_name} ---")

    # Always include the GOOGLE_CLOUD_PROJECT environment variable
    if env_vars is None:
        env_vars = {}
    env_vars["GOOGLE_CLOUD_PROJECT"] = os.environ["PROJECT_ID"]

    env_vars_list = []
    for key, value in env_vars.items():
        env_vars_list.append(f"{key}={value}")

    command = [
        "gcloud", "run", "deploy", service_name,
        "--image", f"us-central1-docker.pkg.dev/{os.environ['PROJECT_ID']}/instavibe-images/{service_name}",
        "--platform", "managed",
        "--region", os.environ["REGION"],
        "--allow-unauthenticated",
        "--format=json"
    ]

    if env_vars_list:
        command.extend(["--set-env-vars", ",".join(env_vars_list)])

    result = subprocess.run(command, check=True, capture_output=True, text=True)

    service_url = json.loads(result.stdout)["status"]["url"]
    print(f"--- {service_name} deployment complete ---")
    return service_url

def deploy_orchestrator(remote_agent_addresses):
    """Deploys the orchestrator."""
    print("--- Deploying Orchestrator ---")
    env = os.environ.copy()
    env["REMOTE_AGENT_ADDRESSES"] = remote_agent_addresses
    subprocess.run(["python", "-c", "from orchestrate import agent; from vertexai import agent_engines; agent_engines.create(agent.root_agent, requirements='./agents/orchestrate/requirements.txt')"], check=True, env=env)
    print("--- Orchestrator deployment complete ---")

if __name__ == "__main__":
    # Build the container images using Google Cloud Build
    print("--- Building container images ---")
    subprocess.run(["gcloud", "builds", "submit", "--config", "cloudbuild.yaml", "."], check=True)
    print("--- Container images built successfully ---")

    # Deploy all the services and capture their URLs
    service_urls = {}
    service_urls["instavibe"] = deploy_service("instavibe")
    service_urls["tools"] = deploy_service("tools", env_vars={"INSTAVIBE_BASE_URL": service_urls["instavibe"]})
    service_urls["a2a_gateway"] = deploy_service("a2a_gateway")
    service_urls["social"] = deploy_service("social")
    service_urls["planner"] = deploy_service("planner")
    service_urls["platform_mcp_client"] = deploy_service("platform_mcp_client", env_vars={"MCP_SERVER_URL": os.environ["MCP_SERVER_URL"]})

    remote_agent_addresses = ",".join([
        service_urls["a2a_gateway"],
        service_urls["social"],
        service_urls["planner"],
        service_urls["platform_mcp_client"],
    ])
    deploy_orchestrator(remote_agent_addresses)

    # Print the URLs of the deployed services
    print("\n--- Deployed Service URLs ---")
    for service, url in service_urls.items():
        print(f"{service}: {url}")
