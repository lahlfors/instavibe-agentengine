import os
import sys
import logging
import importlib
import argparse
from dotenv import load_dotenv
from typing import Dict, List, Optional
import subprocess

# CRITICAL: Add the project root to the path for local module imports
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.app.agent_engine_adk_app import deploy_adk_agent_engine
from common.observability import setup_observability
from google.cloud import aiplatform as vertexai

# --- Logger Initialization ---
logger = logging.getLogger(__name__)

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
GCLOUD_COMMON_ARGS = []

class ApiDisabledError(Exception):
    """Custom exception for when a required GCP API is not enabled."""
    pass

class DeploymentError(Exception):
    """Custom exception for deployment failures."""
    pass

# --- Helper Functions ---

def install_dependencies():
    """Installs dependencies from requirements.txt."""
    logging.info("--- Installing/Updating Dependencies from requirements.txt ---")
    req_path = os.path.join(PROJECT_ROOT, 'requirements.txt')
    if not os.path.exists(req_path):
        logging.warning(f"Root requirements.txt not found at {req_path}. Skipping dependency installation.")
        return
    try:
        run_command([sys.executable, "-m", "pip", "install", "--upgrade", "-r", req_path], check=True, capture_output=False)
        logging.info("--- Dependencies are up to date. ---")
    except subprocess.CalledProcessError as e:
        raise DeploymentError("Failed to install dependencies from requirements.txt.") from e

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
    optional_vars = {
        "service_account": "SERVICE_ACCOUNT_EMAIL",
    }

    env_config = {key: sanitize_env_var(os.environ.get(var_name)) for key, var_name in required_vars.items()}

    for key, var_name in optional_vars.items():
        env_config[key] = sanitize_env_var(os.environ.get(var_name))

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

def build_and_deploy_cloud_run_service(
    project_id: str,
    region: str,
    service_name: str,
    source_path: str,
    env_vars: Optional[Dict[str, str]] = None,
    allow_unauthenticated: bool = True,
    service_account: Optional[str] = None
) -> Optional[str]:
    """
    Builds and deploys a Cloud Run service using a cloudbuild.yaml that
    accepts individual substitutions for each environment variable.
    """
    logging.info(f"--- Deploying Cloud Run Service: {service_name} from path {source_path} ---")
    if not os.path.isdir(source_path):
        raise DeploymentError(f"Source path not found: {source_path}")

    image_path = f"{region}-docker.pkg.dev/{project_id}/instavibe-images/{service_name}:latest"

    substitutions = {
        "_IMAGE_PATH": image_path,
        "_SERVICE_NAME": service_name,
        "_SERVICE_DIR": source_path,
        "_REGION": region,
        "_SERVICE_ACCOUNT": service_account or "",
    }

    if env_vars:
        for k, v in env_vars.items():
            if v is not None:
                substitutions[f"_{k}"] = str(v)

    substitutions_string = ",".join([f"{k}={v}" for k, v in substitutions.items()])

    build_submit_cmd = [
        "gcloud", "builds", "submit", ".",
        "--config", "cloudbuild.yaml",
        f"--substitutions={substitutions_string}",
        "--project", project_id,
    ]

    try:
        logging.info(f"Submitting build and deploy for {service_name}...")
        run_command(build_submit_cmd, timeout=900, check=True)
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Cloud Build submission failed for {service_name}") from e

    url_cmd = [
        "gcloud", "run", "services", "describe", service_name,
        "--platform", "managed", "--region", region, "--project", project_id,
        "--format=value(status.url)"
    ]
    try:
        result = run_command(url_cmd, check=True)
        service_url = result.stdout.strip()
        if not service_url:
            raise DeploymentError(f"Failed to get URL for Cloud Run service {service_name}")
        logging.info(f"Successfully deployed '{service_name}' to {service_url}")
        return service_url
    except (subprocess.CalledProcessError, DeploymentError) as e:
        logging.warning(f"Could not retrieve service URL for {service_name} after deployment. This might be okay. Error: {e}")
        return None

def main(args):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        setup_observability(disable_export=True)
        logging.info("Observability setup complete.")

        install_dependencies()
        env_config = setup_environment()

        if not args.skip_spanner:
            setup_spanner(env_config["project_id"], env_config["spanner_instance"], env_config["spanner_db"], env_config["region"])
        else:
            logging.info("Skipping Spanner setup.")

        if not args.skip_collector:
            otel_collector_url = build_and_deploy_cloud_run_service(
                env_config["project_id"],
                env_config["region"],
                "otel-collector",
                "./otel-collector",
                env_vars={"COMMON_GOOGLE_CLOUD_PROJECT": env_config["project_id"]},
                allow_unauthenticated=False,
                service_account=env_config.get("service_account"),
            )
            if otel_collector_url:
                os.environ["OTEL_COLLECTOR_ENDPOINT"] = f"{otel_collector_url}:4317"
        else:
            logging.info("Skipping OpenTelemetry Collector deployment.")

        mcp_tool_server_url = None
        if not args.skip_mcp_server:
            mcp_tool_server_url = build_and_deploy_cloud_run_service(
                env_config["project_id"],
                env_config["region"],
                "mcp-tool-server",
                "./tools/instavibe",
                env_vars={
                    "COMMON_GOOGLE_CLOUD_PROJECT": env_config["project_id"],
                    "SERVICE_NAME": "mcp-tool-server",
                    "OTEL_COLLECTOR_ENDPOINT": os.environ.get("OTEL_COLLECTOR_ENDPOINT"),
                },
                allow_unauthenticated=False,
            )
            if mcp_tool_server_url:
                logging.info(f"Setting MCP_SERVER_URL for agent deployment: {mcp_tool_server_url}")
                os.environ["MCP_SERVER_URL"] = mcp_tool_server_url
            else:
                logging.warning("MCP Tool Server deployment did not return a URL. Platform MCP Client Agent may fail.")

        agent_resource_names = {}
        if not args.skip_agents:
            agents_to_deploy = [
                {
                    "name": "planner_agent",
                    "display_name": "Planner Agent",
                    "description": "An agent that creates a detailed plan to create a new event.",
                    "module": "agents.planner.agent",
                    "class_name": "PlannerAgent",
                },
                {
                    "name": "orchestrator_agent",
                    "display_name": "Orchestrate Agent",
                    "description": "An agent that orchestrates other agents to create a new event.",
                    "module": "agents.orchestrate.orchestrate_service_agent",
                    "class_name": "OrchestrateServiceAgent",
                },
                {
                    "name": "social_agent",
                    "display_name": "Social Agent",
                    "description": "An agent that generates social media posts.",
                    "module": "agents.social.agent",
                    "class_name": "SocialLoopAgent",
                },
                {
                    "name": "platform_mcp_client_agent",
                    "display_name": "Platform MCP Client Agent",
                    "description": "An agent that interacts with the MCP server.",
                    "module": "agents.platform_mcp_client.agent",
                    "class_name": "PlatformMCPClientAgent",
                },
            ]

            if args.deploy_orchestrate_only:
                logging.info("--- Deploying only the Orchestrate Agent ---")
                agents_to_deploy = [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']

            for agent_config in agents_to_deploy:
                agent_name = agent_config["name"]
                agent_display_name = agent_config["display_name"]
                logging.info(f"--- Deploying/Updating Agent: {agent_display_name} (Name: {agent_name}) ---")

                try:
                    module = importlib.import_module(agent_config["module"])
                    agent_class = getattr(module, agent_config["class_name"])

                    # Dynamically get tools for the agent
                    tools = []
                    if hasattr(agent_class, "get_tools"):
                        tools = agent_class.get_tools()

                    # Create agent instance. This assumes a constructor signature of (model, tools).
                    agent_object = agent_class(model="gemini-1.5-flash-001", tools=tools)

                    # Construct the path to the agent's requirements.txt
                    agent_module_path = agent_config["module"].split('.')
                    agent_dir = agent_module_path[1] if len(agent_module_path) > 1 else agent_module_path[0]
                    requirements_path = os.path.join("agents", agent_dir, "requirements.txt")

                    # Default extra_packages to empty list as it's not in the config
                    extra_packages = agent_config.get("extra_packages", [])

                    remote_agent = deploy_adk_agent_engine(
                        agent_object=agent_object,
                        gcp_agent_id=agent_name,
                        project=env_config["project_id"],
                        location=env_config["region"],
                        requirements_path=requirements_path,
                        extra_packages=extra_packages,
                        display_name=agent_display_name,
                    )
                    if remote_agent and remote_agent.resource_name:
                        agent_resource_names[agent_name] = remote_agent.resource_name
                        logging.info(f"--- Successfully Deployed/Updated: {agent_display_name} to {remote_agent.resource_name} ---")
                    else:
                        logging.error(f"--- FAILED to Deploy/Update: {agent_display_name}. No resource name returned. ---")

                except Exception as e:
                    logging.error(f"--- FAILED to Deploy/Update: {agent_display_name}: {e} ---", exc_info=True)
        else:
            logging.info("--- Skipping all agent deployments. ---")

        if not args.skip_app:
            app_env_vars = {
                "COMMON_GOOGLE_CLOUD_PROJECT": env_config["project_id"],
                "COMMON_GOOGLE_CLOUD_LOCATION": env_config["region"],
                "COMMON_SPANNER_INSTANCE_ID": env_config["spanner_instance"],
                "COMMON_SPANNER_DATABASE_ID": env_config["spanner_db"],
                "AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL": mcp_tool_server_url,
                "OTEL_COLLECTOR_ENDPOINT": os.environ.get("OTEL_COLLECTOR_ENDPOINT"),
                "ENABLE_TRACING": str(not args.deploy_orchestrate_only),
            }
            # Pass all deployed agent resource names to the app
            for agent_name, resource_name in agent_resource_names.items():
                env_key = f"{agent_name.upper()}_RESOURCE_NAME"
                app_env_vars[env_key] = resource_name

            if "orchestrate_agent" not in agent_resource_names:
                 logging.warning("Orchestrate agent resource name not found. InstaVibe app may not function correctly.")

            build_and_deploy_cloud_run_service(
                env_config["project_id"],
                env_config["region"],
                "instavibe-app",
                "./instavibe",
                env_vars=app_env_vars,
                allow_unauthenticated=True,
                service_account=env_config.get("service_account"),
            )
        else:
            logging.info("Skipping InstaVibe App deployment.")

        logging.info("--- Deployment script finished successfully! ---")

    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred in deploy_all: {e}", exc_info=True)
        sys.exit(1)
    finally:
        from opentelemetry import trace, metrics
        logging.info("--- Shutting down observability ---")
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, 'shutdown'):
            try:
                tracer_provider.shutdown()
                logging.info("TracerProvider shutdown complete.")
            except Exception as e:
                logging.error(f"Error shutting down TracerProvider: {e}", exc_info=True)
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, 'shutdown'):
            try:
                meter_provider.shutdown(timeout_millis=10000)
                logging.info("MeterProvider shutdown complete.")
            except Exception as e:
                logging.error(f"Error shutting down MeterProvider: {e}", exc_info=True)
        logging.info("--- Observability shutdown process finished ---")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Deploy all components of the InstaVibe system.")
    parser.add_argument("--skip-agents", action="store_true", help="Skip deploying all reasoning engine agents.")
    parser.add_argument("--skip-gateway", action="store_true", help="Skip deploying the Cloud Run gateway.")
    parser.add_argument("--skip-mcp-server", action="store_true", help="Skip deploying the MCP Tool Server.")
    parser.add_argument("--skip-app", action="store_true", help="Skip deploying the main InstaVibe web app.")
    parser.add_argument("--skip-spanner", action="store_true", help="Skip Spanner setup.")
    parser.add_argument("--skip-collector", action="store_true", help="Skip deploying the OpenTelemetry Collector.")
    parser.add_argument("--deploy-orchestrate-only", action="store_true", help="Deploy only the orchestrate agent.")
    args = parser.parse_args()
    main(args)
