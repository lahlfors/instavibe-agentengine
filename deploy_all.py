import argparse
import json
import logging
import os
import subprocess
import sys
import time
import re
from typing import Any, Dict, List, Optional, Callable
import tempfile
import yaml # Requires PyYAML: pip install pyyaml

from dotenv import load_dotenv
from google.api_core import exceptions as api_exceptions
from google.cloud import aiplatform as vertexai
from google.cloud.aiplatform_v1.services import \
    reasoning_engine_service
from google.cloud.aiplatform_v1.types import (DeleteReasoningEngineRequest,
                                               ReasoningEngine as ReasoningEngineGAPIC)

# Import agent deployment functions
from agents.orchestrate.deploy import deploy_orchestrate_main_func
from agents.planner.deploy import deploy_planner_main_func
from agents.platform_mcp_client.deploy import \
    deploy_platform_mcp_client_main_func
from agents.social.deploy import deploy_social_main_func


# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
GCLOUD_COMMON_ARGS = [] # Will be populated in setup_environment

class ApiDisabledError(Exception):
    """Custom exception for when a required GCP API is not enabled."""
    pass

class DeploymentError(Exception):
    """Custom exception for deployment failures."""
    pass

# --- Helper Functions ---

def run_command(command: List[str], check: bool = True, capture_output: bool = True, text: bool = True, timeout: Optional[int] = None, input_str: Optional[str] = None) -> subprocess.CompletedProcess:
    """
    Executes a shell command and logs its execution and output.
    Raises CalledProcessError on failure if check is True.
    """
    cmd_str = ' '.join(command)
    logging.info(f"Executing command: {cmd_str}")

    try:
        result = subprocess.run(command, check=check, capture_output=capture_output, text=text, timeout=timeout, input=input_str)
        if result.returncode != 0 and not check:
             logging.warning(f"Command failed with code {result.returncode}: {cmd_str}")
             if capture_output:
                 logging.warning(f"STDERR: {result.stderr.strip()}")
                 logging.warning(f"STDOUT: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}: {' '.join(e.cmd)}")
        if capture_output:
            logging.error(f"STDERR: {e.stderr.strip()}")
            logging.error(f"STDOUT: {e.stdout.strip()}")
        if check:
            raise
        else:
            return subprocess.CompletedProcess(e.args, e.returncode, e.stdout, e.stderr)
    except FileNotFoundError:
        logging.error(f"Command not found: {command[0]}. Ensure gcloud SDK is installed and in your PATH.")
        raise
    except subprocess.TimeoutExpired as e:
        logging.error(f"Command timed out after {timeout} seconds: {cmd_str}")
        if e.stdout: logging.error(f"STDOUT: {e.stdout}")
        if e.stderr: logging.error(f"STDERR: {e.stderr}")
        raise

def sanitize_env_var(value: Optional[str]) -> str:
    """Sanitizes an environment variable value."""
    if value is None:
        return ''
    return value.split('#', 1)[0].strip().strip('"').strip("'")

def setup_environment() -> Dict[str, str]:
    """Loads and validates required environment variables."""
    load_dotenv()
    required_vars = {
        "project_id": "COMMON_GOOGLE_CLOUD_PROJECT",
        "region": "COMMON_GOOGLE_CLOUD_LOCATION",
        "staging_bucket": "COMMON_VERTEX_STAGING_BUCKET",
        "spanner_instance": "COMMON_SPANNER_INSTANCE_ID",
        "spanner_db": "COMMON_SPANNER_DATABASE_ID",
    }
    env_config = {key: sanitize_env_var(os.environ.get(var_name)) for key, var_name in required_vars.items()}

    missing = [var_name for key, var_name in required_vars.items() if not env_config[key]]
    if missing:
        raise ValueError(f"Missing critical environment variables: {', '.join(missing)}")

    global GCLOUD_COMMON_ARGS
    GCLOUD_COMMON_ARGS = ['--project', env_config["project_id"]]

    try:
        vertexai.init(project=env_config["project_id"], location=env_config["region"], staging_bucket=env_config["staging_bucket"])
        logging.info(f"Vertex AI initialized for project '{env_config['project_id']}' in '{env_config['region']}'.")
    except Exception as e:
        raise DeploymentError(f"Failed to initialize Vertex AI: {e}")

    try:
        run_command(['gcloud', 'auth', 'print-access-token'] + GCLOUD_COMMON_ARGS, capture_output=True, text=True, check=True)
        logging.info("gcloud authentication seems fine.")
    except subprocess.CalledProcessError:
        raise DeploymentError("gcloud not authenticated. Please run 'gcloud auth login'.")
    os.environ['GRPC_DNS_RESOLVER'] = 'native'
    logging.info("Set GRPC_DNS_RESOLVER=native")

    return env_config

# --- Spanner Setup ---
def setup_spanner(project_id: str, instance_id: str, db_id: str, region: str):
    """Ensures the Spanner instance and database exist."""
    logging.info("--- Starting Spanner Setup ---")
    instance_check_cmd = ['gcloud', 'spanner', 'instances', 'describe', instance_id] + GCLOUD_COMMON_ARGS
    instance_result = run_command(instance_check_cmd, check=False)
    if instance_result.returncode != 0:
        if "NOT_FOUND" in instance_result.stderr:
            logging.info(f"Spanner instance '{instance_id}' not found. Creating...")
            run_command([
                "gcloud", "spanner", "instances", "create", instance_id,
                f"--config=regional-{region}", f"--description=Spanner for {project_id}",
                "--processing-units=100"
            ] + GCLOUD_COMMON_ARGS, check=True)
            logging.info(f"Spanner instance '{instance_id}' created.")
        else:
            raise DeploymentError(f"Failed to check for Spanner instance '{instance_id}'.")
    db_check_cmd = ['gcloud', 'spanner', 'databases', 'describe', db_id, f'--instance={instance_id}'] + GCLOUD_COMMON_ARGS
    db_result = run_command(db_check_cmd, check=False)
    if db_result.returncode != 0:
        if "NOT_FOUND" in db_result.stderr:
            logging.info(f"Spanner database '{db_id}' not found. Creating...")
            run_command([
                'gcloud', 'spanner', 'databases', 'create', db_id,
                f'--instance={instance_id}'
            ] + GCLOUD_COMMON_ARGS, check=True)
            logging.info(f"Spanner database '{db_id}' created.")
        else:
            raise DeploymentError(f"Failed to check for Spanner database '{db_id}'.")
    original_cwd = os.getcwd()
    try:
        os.chdir("instavibe")
        if os.path.exists("setup.py"):
            run_command([sys.executable, "setup.py"], check=True)
            logging.info("Successfully executed instavibe/setup.py.")
        else:
            logging.warning("instavibe/setup.py not found, skipping schema setup.")
    finally:
        os.chdir(original_cwd)
    logging.info("--- Spanner Setup Complete ---")

# --- Reasoning Engine (Agent) Deployment ---
def get_reasoning_engine(gapic_client, parent_path: str, display_name: str) -> Optional[ReasoningEngineGAPIC]:
    try:
        for engine in gapic_client.list_reasoning_engines(parent=parent_path):
            if engine.display_name == display_name:
                logging.info(f"Found existing Reasoning Engine '{display_name}' ({engine.name}).")
                return engine
        return None
    except api_exceptions.Forbidden as e:
        if "api has not been used" in str(e).lower() or "service is disabled" in str(e).lower():
            raise ApiDisabledError(f"Vertex AI API (aiplatform.googleapis.com) is disabled for project {parent_path.split('/')[1]}. Please enable it in the Cloud Console.") from e
        logging.warning(f"Permission error checking for '{display_name}', assuming it doesn't exist: {e}")
        return None
    except Exception as e:
        logging.warning(f"Error checking for '{display_name}', assuming it doesn't exist: {e}")
        return None

def deploy_agent(project_id: str, region: str, agent_name: str, deploy_func: Callable, deploy_args: Optional[Dict] = None) -> Optional[str]:
    logging.info(f"--- Deploying Agent: {agent_name} ---")
    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    gapic_client = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)
    parent_path = f"projects/{project_id}/locations/{region}"
    try:
        if existing_engine := get_reasoning_engine(gapic_client, parent_path, agent_name):
            logging.info(f"Attempting to delete existing engine '{agent_name}' ({existing_engine.name}) before redeployment.")
            req = DeleteReasoningEngineRequest(name=existing_engine.name, force=True)
            try:
                op = gapic_client.delete_reasoning_engine(request=req)
                op.result(timeout=300)
                logging.info(f"Successfully deleted existing engine '{agent_name}'.")
                time.sleep(20)
            except Exception as e:
                logging.error(f"Failed to delete existing engine '{agent_name}': {e}. Continuing...")
        final_deploy_args = { "project_id": project_id, "region": region, **(deploy_args or {}) }
        resource = deploy_func(**final_deploy_args)
        if resource and hasattr(resource, 'name') and resource.name:
            logging.info(f"Successfully deployed '{agent_name}'. Resource Name: {resource.name}")
            return resource.name
        else:
            logging.error(f"Deployment of '{agent_name}' did not return a valid resource object.")
            return None
    except ApiDisabledError as e:
        logging.error(f"Halting deployment of '{agent_name}': {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to deploy agent '{agent_name}': {e}", exc_info=True)
        return None

# --- Cloud Run Service Deployment ---
def get_build_id(gcloud_stdout: str, gcloud_stderr: str) -> Optional[str]:
    output = gcloud_stdout + "\n" + gcloud_stderr
    patterns = [
        r"cloudbuild.googleapis.com/v1/projects/[^/]+/locations/[^/]+/builds/([a-f0-9-]+)",
        r"\bID:\s*([a-f0-9-]+)",
        r"builds/([a-f0-9-]+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return None

def poll_build_status(build_id: str, project_id: str, region: str) -> Dict[str, Any]:
    logging.info(f"Polling build status for ID: {build_id}")
    for i in range(60):
        describe_cmd = [
            "gcloud", "builds", "describe", build_id,
            "--project", project_id,
            "--region", region,
            "--format=json"
        ]
        try:
            describe_run = run_command(describe_cmd, check=True, timeout=30)
            build_result = json.loads(describe_run.stdout)
            status = build_result.get('status')
            logging.info(f"Build status: {status} (Attempt {i+1})")
            if status not in ['PENDING', 'QUEUED', 'WORKING']:
                return build_result
        except subprocess.CalledProcessError as e:
             logging.warning(f"gcloud builds describe FAILED (will retry): {e}")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse describe output: {describe_run.stdout}")
            raise DeploymentError("Failed to parse build describe JSON") from e
        time.sleep(10)
    raise DeploymentError(f"Build {build_id} did not complete within timeout.")

def extract_image_digest(build_result: Dict[str, Any], image_uri_base: str) -> str:
    """Extracts the image digest from the build result."""
    images = build_result.get('results', {}).get('images', [])
    logging.info(f"DEBUG: Searching for image base '{image_uri_base}'")
    logging.info(f"DEBUG: Images found in build results: {json.dumps(images, indent=2)}")
    if not images:
        logging.error("DEBUG: 'results.images' array is empty or missing in the build result.")
        logging.error(f"DEBUG: Full build result keys: {build_result.keys()}")
        logging.error(f"DEBUG: Build 'results' keys: {build_result.get('results', {}).keys()}")

    for image in images:
        image_name = image.get('name', '')
        if image_name.startswith(image_uri_base):
            digest = image.get('digest')
            if digest:
                image_name_without_tag = image_name.split(':')[0]
                return f"{image_name_without_tag}@{digest}"
            else:
                logging.warning(f"DEBUG: Found image '{image_name}' but it has no digest.")
    raise DeploymentError(f"Could not find digest for image starting with '{image_uri_base}' in build results. Check DEBUG logs.")

def build_and_deploy_cloud_run_service(
    project_id: str,
    region: str,
    service_name: str,
    source_path: str,
    env_vars: Optional[Dict[str, str]] = None,
    allow_unauthenticated: bool = True,
    service_account: Optional[str] = None
) -> Optional[str]:
    """Builds and deploys a Cloud Run service using image digest."""
    logging.info(f"--- Deploying Cloud Run Service: {service_name} ---")
    if not os.path.isdir(source_path):
        raise DeploymentError(f"Source path not found: {source_path}")

    image_uri_base = f"{region}-docker.pkg.dev/{project_id}/instavibe-images/{service_name}"
    image_tag = f"{image_uri_base}:latest"

    # Define the build config to ensure the image is listed in results
    cloudbuild_config = {
        "steps": [{
            "name": "gcr.io/cloud-builders/docker",
             # Corection: Added --no-cache to docker build args
            "args": ["build", "--no-cache", "-t", image_tag, "."],
        }],
        "images": [image_tag]
    }
    cloudbuild_yaml_content = yaml.dump(cloudbuild_config)

    tmp_config_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp_config:
            tmp_config.write(cloudbuild_yaml_content)
            tmp_config_file = tmp_config.name
        logging.info(f"DEBUG: Temporary cloudbuild config at: {tmp_config_file}")

        build_submit_cmd = [
            "gcloud", "builds", "submit", source_path,
            "--config", tmp_config_file,
            "--project", project_id,
            "--region", region
        ]
        logging.info(f"Submitting build for {service_name} from {source_path} using --config {tmp_config_file}")
        completed_build = run_command(build_submit_cmd, timeout=900, check=True)
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Cloud Build submission failed for {service_name}") from e
    finally:
        if tmp_config_file and os.path.exists(tmp_config_file):
            os.remove(tmp_config_file)
            logging.info(f"DEBUG: Removed temporary config file {tmp_config_file}")

    build_id = get_build_id(completed_build.stdout, completed_build.stderr)
    if not build_id:
        raise DeploymentError(f"Failed to extract Build ID for {service_name}.")
    logging.info(f"Cloud Build ID for {service_name}: {build_id}")

    build_result = poll_build_status(build_id, project_id, region)
    if build_result.get('status') != 'SUCCESS':
        log_url = build_result.get('logUrl')
        raise DeploymentError(f"Build {build_id} for {service_name} FAILED. Status: {build_result.get('status')}. Log: {log_url}")
    logging.info(f"Build {build_id} for {service_name} SUCCEEDED.")

    image_name_with_digest = extract_image_digest(build_result, image_uri_base)
    logging.info(f"Using image with digest for {service_name}: {image_name_with_digest}")

    deploy_cmd = [
        "gcloud", "run", "deploy", service_name,
        "--image", image_name_with_digest,
        "--platform", "managed", "--region", region, "--project", project_id,
    ]
    if allow_unauthenticated: deploy_cmd.append("--allow-unauthenticated")
    if service_account: deploy_cmd.extend(["--service-account", service_account])
    if env_vars:
        # Simple escape for commas in env var values: replace , with ^^
        env_vars_string = ",".join([f"{k}={str(v).replace(',', '^^')}" for k, v in env_vars.items()])
        deploy_cmd.extend(["--set-env-vars", env_vars_string])

    logging.info(f"Deploying {service_name} to Cloud Run...")
    try:
        run_command(deploy_cmd, timeout=600, check=True)
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Cloud Run deployment failed for {service_name}") from e

    url_cmd = [
        "gcloud", "run", "services", "describe", service_name,
        "--platform", "managed", "--region", region, "--project", project_id,
        "--format=value(status.url)"
    ]
    result = run_command(url_cmd, check=True)
    service_url = result.stdout.strip()
    if not service_url:
        raise DeploymentError(f"Failed to get URL for Cloud Run service {service_name}")
    logging.info(f"Successfully deployed '{service_name}' to {service_url}")
    return service_url

# --- Main Orchestration ---
def main():
    parser = argparse.ArgumentParser(description="Deploy all components of the InstaVibe system.")
    # ... parser arguments ...
    parser.add_argument("--skip-agents", action="store_true", help="Skip deploying all reasoning engine agents.")
    parser.add_argument("--skip-gateway", action="store_true", help="Skip deploying the Cloud Run gateway.")
    parser.add_argument("--skip-mcp-server", action="store_true", help="Skip deploying the MCP Tool Server.")
    parser.add_argument("--skip-app", action="store_true", help="Skip deploying the main InstaVibe web app.")
    parser.add_argument("--skip-spanner", action="store_true", help="Skip Spanner setup.")
    args = parser.parse_args()

    try:
        config = setup_environment()
        project_id = config["project_id"]
        region = config["region"]

        if not args.skip_spanner:
            setup_spanner(project_id, config["spanner_instance"], config["spanner_db"], region)
        else: logging.info("Skipping Spanner setup.")

        agent_resource_names = {}
        if not args.skip_agents:
            agent_defs = {
                "planner": {"name": "Planner Agent", "func": deploy_planner_main_func},
                "social": {"name": "Social Agent", "func": deploy_social_main_func},
                "mcp_client": {"name": "Platform MCP Client Agent", "func": deploy_platform_mcp_client_main_func},
                 "orchestrate": {"name": "Orchestrate Agent", "func": deploy_orchestrate_main_func, "args": {"base_dir": os.getcwd()}},
            }
            for key, agent in agent_defs.items():
                agent_resource_names[key] = deploy_agent(project_id, region, agent["name"], agent["func"], deploy_args=agent.get("args"))
        else: logging.info("Skipping all agent deployments.")

        mcp_tool_server_url = None
        if not args.skip_mcp_server:
            mcp_tool_server_url = build_and_deploy_cloud_run_service(
                project_id, region, "mcp-tool-server", "./tools/instavibe",
                env_vars={"COMMON_GOOGLE_CLOUD_PROJECT": project_id, "TOOLS_GOOGLE_CLOUD_LOCATION": region}
            )

        gateway_url = None
        if not args.skip_gateway:
            # ... gateway env var setup ...
            gateway_env_vars = {
                "SOCIAL_AGENT_URL": f"https://{region}-aiplatform.googleapis.com/v1beta1/{agent_resource_names.get('social')}:predict" if agent_resource_names.get('social') else "",
                "PLANNER_AGENT_URL": f"https://{region}-aiplatform.googleapis.com/v1beta1/{agent_resource_names.get('planner')}:predict" if agent_resource_names.get('planner') else "",
                "MCP_AGENT_URL": f"https://{region}-aiplatform.googleapis.com/v1beta1/{agent_resource_names.get('mcp_client')}:predict" if agent_resource_names.get('mcp_client') else "",
            }
            valid_gateway_env_vars = {k: v for k, v in gateway_env_vars.items() if v and "None" not in v}
            if valid_gateway_env_vars:
                 gateway_url = build_and_deploy_cloud_run_service(
                     project_id, region, "unified-agent-gateway", "./cloud_run_gateway", valid_gateway_env_vars
                 )
            else:
                logging.warning("Skipping Gateway deployment: no backend agent URLs available.")

        if not args.skip_app:
            # ... app env var setup ...
            app_env_vars = {
                "COMMON_GOOGLE_CLOUD_PROJECT": project_id,
                "COMMON_GOOGLE_CLOUD_LOCATION": region,
                "COMMON_SPANNER_INSTANCE_ID": config["spanner_instance"],
                "COMMON_SPANNER_DATABASE_ID": config["spanner_db"],
                "UNIFIED_AGENT_GATEWAY_URL": gateway_url or "",
            }
            build_and_deploy_cloud_run_service(
                project_id, region, "instavibe-app", "./instavibe",
                env_vars={k:v for k,v in app_env_vars.items() if v}
            )

        logging.info("--- Deployment script finished successfully! ---")
    except (ValueError, subprocess.CalledProcessError, ApiDisabledError, DeploymentError) as e:
        logging.error(f"A critical error occurred: {e}", exc_info=False)
        logging.error("Deployment failed.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        logging.error("Deployment failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
