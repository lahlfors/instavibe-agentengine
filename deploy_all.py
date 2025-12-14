import os
import sys
import logging
import importlib
import argparse
import inspect
import concurrent.futures
from dotenv import load_dotenv
from typing import Dict, List, Optional
import subprocess

# CRITICAL: Add the project root to the path for local module imports
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Add Agents Directory (so agents can find 'common' directly)
# This fixes "ModuleNotFoundError: No module named 'common'"
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)

from agents.app.agent_engine_adk_app import deploy_adk_agent_engine
from agents.common.observability import setup_observability
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

from dataclasses import dataclass, field

@dataclass
class DeploymentContext:
    """Holds the state of the deployment across phases."""
    project_id: str
    location: str
    project_number: str
    urls: Dict[str, str] = field(default_factory=dict)
    agent_resource_names: Dict[str, str] = field(default_factory=dict)
    
    def update_urls(self, new_urls: Dict[str, str]):
        self.urls.update(new_urls)
        
    def update_agents(self, new_agents: Dict[str, str]):
        self.agent_resource_names.update(new_agents)

# --- Helper Functions ---

def fetch_existing_cloud_run_urls(project_id: str, project_number: str, region: str) -> Dict[str, str]:
    """Fetches existing Cloud Run service URLs."""
    urls = {}
    service_names = [
        "otel-collector", "mcp-tool-server", "instavibe-app",
        "planner-agent", "social-agent", "platform-mcp-client-agent", "orchestrate-agent"
    ]
    for name in service_names:
        try:
            service_url = get_cloud_run_url(name, project_number, region)
            urls[name.replace("-", "_")] = service_url
            logger.info(f"  📍 Found existing {name} URL: {service_url}")
        except Exception:
            logger.warning(f"Could not find existing URL for {name}.")
            urls[name.replace("-", "_")] = ""
    return urls


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

    # Temporarily disabled due to enterprise-certificate-proxy cffi issue
    # Application default credentials are already set up via gcloud auth application-default login
    # try:
    #     run_command(['gcloud', 'auth', 'print-access-token'] + GCLOUD_COMMON_ARGS, capture_output=True, text=True, check=True)
    #     logging.info("gcloud authentication seems fine.")
    # except subprocess.CalledProcessError:
    #     raise DeploymentError("gcloud not authenticated. Please run 'gcloud auth login'.")
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

def run_command(command: List[str], check: bool = True, capture_output: bool = True, text: bool = True, timeout: Optional[int] = None, input_str: Optional[str] = None) -> subprocess.CompletedProcess:
    """
    Executes a shell command and logs its execution and output.
    Raises CalledProcessError on Producing a stacktrace if check is True.
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

def get_project_number(project_id: str) -> str:
    """Get GCP project number from project ID."""
    # Temporarily hardcoded due to gcloud cffi issue
    if project_id == "laah-genai": # Replace with your project ID
        return "735503743752" # Replace with your project number
    
    try:
        result = run_command(
            ['gcloud', 'projects', 'describe', project_id, '--format=value(projectNumber)'],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Failed to get project number for {project_id}: {e}")

def get_cloud_run_url(service_name: str, project_number: str, region: str) -> str:
    """Pre-calculate deterministic Cloud Run URL."""
    return f"https://{service_name}-{project_number}.{region}.run.app"

def deploy_adk_agent_cloud_run(agent_conf: Dict, env_config: Dict, gemini_model: str, context: DeploymentContext, force_update: bool = False) -> Dict:
    """Deploys an ADK agent to Cloud Run using its cloudbuild.yaml."""
    display_name = agent_conf["display_name"]
    adk_agent_name = agent_conf["name"]
    service_name = agent_conf["gcp_id"]

    try:
        logging.info(f"[Parallel] Deploying Cloud Run agent: {display_name}")

        # Prepare environment variables for the Cloud Build and Cloud Run service
        agent_env_vars = {
            "GEMINI_MODEL": gemini_model,
            "PLANNER_AGENT_URL": context.urls.get("planner_agent", ""),
            "SOCIAL_AGENT_URL": context.urls.get("social_agent", ""),
            "PLATFORM_MCP_CLIENT_AGENT_URL": context.urls.get("platform_mcp_client_agent", ""),
            "ORCHESTRATE_AGENT_URL": context.urls.get("orchestrate_agent", ""),
            "OTEL_COLLECTOR_ENDPOINT": f"{context.urls.get('otel', '')}" if context.urls.get("otel") else "",
            "MCP_SERVER_ADDRESS": context.urls.get("mcp", ""),
        }
        
        # Add project and region directly as substitutions
        agent_env_vars["GOOGLE_CLOUD_PROJECT"] = env_config["project_id"]
        agent_env_vars["CLOUD_RUN_REGION"] = env_config["region"]

        service_url = build_and_deploy_cloud_run_service(
            env_config["project_id"],
            env_config["region"],
            service_name,
            agent_conf["source_path"],
            env_vars=agent_env_vars, # Pass env_vars to build_and_deploy_cloud_run_service
            allow_unauthenticated=True,
            service_account=env_config.get("service_account"),
            config_path=agent_conf["cloudbuild_file"],
            staging_bucket=env_config.get("staging_bucket")
        )
        logging.info(f" [Parallel] ✅ {display_name}: {service_url}")
        return {"success": True, "name": adk_agent_name, "url": service_url}
    except Exception as e:
        logging.error(f"[Parallel] ❌ {display_name}: {e}", exc_info=True)
        return {"success": False, "name": adk_agent_name, "error": str(e)}


def build_and_deploy_cloud_run_service(
    project_id: str,
    region: str,
    service_name: str,
    source_path: str,
    env_vars: Optional[Dict[str, str]] = None,
    allow_unauthenticated: bool = True,
    service_account: Optional[str] = None,
    config_path: str = "cloudbuild.yaml",
    staging_bucket: Optional[str] = None
) -> Optional[str]:
    """
    Builds and deploys a Cloud Run service using a cloudbuild.yaml that
    accepts individual substitutions for each environment variable.
    """
    logging.info(f"--- Deploying Cloud Run Service: {service_name} from path {source_path} ---")
    if not os.path.isdir(source_path) and source_path != ".":
        raise DeploymentError(f"Source path not found: {source_path}")

    image_path = f"{region}-docker.pkg.dev/{project_id}/instavibe-images/{service_name}:latest"

    # All environment variables passed to the Cloud Run service need to be prefixed with _ for substitution.
    substitutions = {
        "_IMAGE_PATH": image_path,
        "_SERVICE_NAME": service_name,
        "_REGION": region,
    }

    if env_vars:
        for k, v in env_vars.items():
            if v is not None:
                substitutions[f"_{k}"] = str(v)

    substitutions_string = ",".join([f"{k}={v}" for k, v in substitutions.items()])

    build_submit_cmd = [
        "gcloud", "builds", "submit",
        ".",  # Build from the project root
        "--config", os.path.join(source_path, config_path), # Use config path relative to source_path
        f"--substitutions={substitutions_string}",
        "--project", project_id,
    ]
    
    # Add GCS staging directory if bucket is provided
    if staging_bucket:
        # Sanitize bucket name (remove gs:// prefix if present)
        bucket_name = staging_bucket.replace("gs://", "")
        # Use service name as directory for isolation
        staging_dir = f"gs://{bucket_name}/{service_name}/source"
        build_submit_cmd.append(f"--gcs-source-staging-dir={staging_dir}")
        logging.info(f"Using GCS staging directory: {staging_dir}")

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

def deploy_service_wrapper(service_name: str, source_path: str, env_config: Dict, env_vars: Dict, config_path: str = "cloudbuild.yaml") -> Dict:
    """Wrapper for deploying a Cloud Run service in a thread."""
    try:
        logging.info(f"[Parallel] Deploying {service_name} using {config_path}...")
        service_url = build_and_deploy_cloud_run_service(
            env_config["project_id"],
            env_config["region"],
            service_name,
            source_path,
            env_vars=env_vars,
            allow_unauthenticated=True, # Default to unauthenticated for internal services for now, or strictly controlled
            service_account=env_config.get("service_account"),
            config_path=config_path,
            staging_bucket=env_config.get("staging_bucket")
        )
        logging.info(f" [Parallel] ✅ {service_name}: {service_url}")
        return {"success": True, "name": service_name, "url": service_url}
    except Exception as e:
        logging.error(f"[Parallel] ❌ {service_name}: {e}", exc_info=True)
        return {"success": False, "name": service_name, "error": str(e)}

def deploy_app_wrapper(env_config: Dict, app_env_vars: Dict) -> Dict:
    """Wrapper for deploying the InstaVibe App in a thread."""
    try:
        logging.info(f"[Parallel] Deploying InstaVibe App...")
        service_url = build_and_deploy_cloud_run_service(
            env_config["project_id"],
            env_config["region"],
            "instavibe-app",
            "./instavibe",
            env_vars=app_env_vars,
            allow_unauthenticated=True,
            service_account=env_config.get("service_account"),
            config_path="cloudbuild.yaml",
            staging_bucket=env_config.get("staging_bucket")
        )
        logging.info(f" [Parallel] ✅ InstaVibe App: {service_url}")
        return {"success": True, "name": "instavibe-app", "url": service_url}
    except Exception as e:
        logging.error(f"[Parallel] ❌ InstaVibe App: {e}", exc_info=True)
        return {"success": False, "name": "instavibe-app", "error": str(e)}

# --- Configuration Functions ---

def get_agent_configurations() -> List[Dict]:
    """Returns the list of agent configurations for deployment."""
    return [
        {
            "name": "planner_agent",
            "gcp_id": "planner-agent",
            "display_name": "Planner Agent",
            "deployment_type": "cloud_run",
            "source_path": "agents/planner",
            "cloudbuild_file": "cloudbuild.yaml",
            "module": "agents.planner.agent",  # Core agent (wrappers need inline mod)
            "agent_variable": "root_agent",
            "requirements_file": "agents/planner/requirements.txt",
            "extra_packages": ["agents/app", "agents/common", "agents/planner"],
            "tools": []
        },
        {
            "name": "orchestrate_agent",
            "gcp_id": "orchestrate-agent",
            "display_name": "Orchestrate Agent",
            "deployment_type": "cloud_run",
            "source_path": "agents/orchestrate",
            "cloudbuild_file": "cloudbuild.yaml",
            "module": "agents.orchestrate.agent",
            "agent_variable": "root_agent",
            "requirements_file": "agents/orchestrate/requirements.txt",
            "extra_packages": ["agents/app", "agents/common", "agents/orchestrate", "agents/_dynamic_tool_agent.py", "agents/_a2a_helpers.py"],
            "tools": []
        },
        {
            "name": "social_agent",
            "gcp_id": "social-agent",
            "display_name": "Social Agent",
            "deployment_type": "cloud_run",
            "source_path": "agents/social",
            "cloudbuild_file": "cloudbuild.yaml",
            "module": "agents.social.agent",  # Core agent
            "agent_variable": "root_agent",
            "requirements_file": "agents/social/requirements.txt",
            "extra_packages": ["agents/app", "agents/common", "agents/social", "tools"],
        },
        {
            "name": "platform_mcp_client_agent",
            "gcp_id": "platform-mcp-client-agent",
            "display_name": "Platform MCP Client Agent",
            "deployment_type": "cloud_run",
            "source_path": "agents/platform_mcp_client",
            "cloudbuild_file": "cloudbuild.yaml",
            "module": "agents.platform_mcp_client.agent",  # Core agent
            "agent_variable": "root_agent",
            "requirements_file": "agents/platform_mcp_client/requirements.txt",
            "extra_packages": ["agents/app", "agents/common", "agents/platform_mcp_client", "agents/_dynamic_tool_agent.py", "agents/social"],
        },
    ]

def get_gemini_model() -> str:
    """Validate and return GEMINI_MODEL from environment."""
    gemini_model = os.getenv("COMMON_GEMINI_MODEL")
    if not gemini_model:
        logging.error("ERROR: COMMON_GEMINI_MODEL environment variable not set. Please define it in your .env file.")
        exit(1)
    return gemini_model

def filter_agents_by_args(agents_to_deploy: List[Dict], args) -> List[Dict]:
    """Apply deployment filters based on CLI args."""
    if args.deploy_orchestrate_only:
        logging.info("--- Deploying only the Orchestrate Agent ---")
        return [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']
    
    if args.deploy_planner_only:
        logging.info("--- Deploying only the Planner Agent (TESTING) ---")
        return [a for a in agents_to_deploy if a['name'] == 'planner_agent']
    
    return agents_to_deploy

def setup_cloud_run_urls(env_config: Dict, project_number: str) -> Dict[str, str]:
    """Pre-calculate deterministic Cloud Run URLs for parallel deployment."""
    logging.info("🔍 Pre-calculating Cloud Run URLs for parallel deployment...")
    region = env_config["region"]
    
    urls = {
        "otel": get_cloud_run_url("otel-collector", project_number, region),
        "mcp": get_cloud_run_url("mcp-tool-server", project_number, region),
        "app": get_cloud_run_url("instavibe-app", project_number, region),
        "planner_agent": get_cloud_run_url("planner-agent", project_number, region),
        "social_agent": get_cloud_run_url("social-agent", project_number, region),
        "platform_mcp_client_agent": get_cloud_run_url("platform-mcp-client-agent", project_number, region),
        "orchestrate_agent": get_cloud_run_url("orchestrate-agent", project_number, region)
    }

    # Set URLs in environment BEFORE deployment
    os.environ["OTEL_COLLECTOR_ENDPOINT"] = f"{urls.get('otel', '')}" # Removed :4317 as we use standard 443->8080 mapping
    os.environ["MCP_SERVER_ADDRESS"] = urls.get("mcp", "")
    os.environ["PLANNER_AGENT_URL"] = urls.get("planner_agent", "")
    os.environ["SOCIAL_AGENT_URL"] = urls.get("social_agent", "")
    os.environ["PLATFORM_MCP_CLIENT_AGENT_URL"] = urls.get("platform_mcp_client_agent", "")
    os.environ["ORCHESTRATE_AGENT_URL"] = urls.get("orchestrate_agent", "")
    
    logging.info(f"  📍 OTEL Collector URL: {urls.get("otel")}")
    logging.info(f"  📍 MCP Tool Server URL: {urls.get("mcp")}")
    logging.info(f"  📍 InstaVibe App URL: {urls.get("app")}")
    logging.info(f"  📍 Planner Agent URL: {urls.get("planner_agent")}")
    logging.info(f"  📍 Social Agent URL: {urls.get("social_agent")}")
    logging.info(f"  📍 Platform Agent URL: {urls.get("platform_mcp_client_agent")}")
    logging.info(f"  📍 Orchestrate Agent URL: {urls.get("orchestrate_agent")}")
    
    return urls

def shutdown_observability():
    """Shutdown observability providers."""
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

# --- Deployment Phase Functions ---

def deploy_agents_and_services_parallel(args, env_config: Dict, all_agent_confs: List[Dict], gemini_model: str, context: DeploymentContext) -> DeploymentContext:
    """PHASE 1: Deploy ALL agents, OTEL, and MCP in parallel."""
    logging.info(f"🚀 PHASE 1: Deploying ALL Agents, OTEL, and MCP in PARALLEL...")
    
    project_id = env_config["project_id"]
    region = env_config["region"]
    
    # Calculate max_workers based on all deployable items (agents + collector + mcp server)
    # Each agent deployment is now a Cloud Run service via deploy_adk_agent_cloud_run
    max_concurrent_tasks = len(all_agent_confs) # All agents
    if not args.skip_collector: max_concurrent_tasks += 1 # OTEL Collector
    if not args.skip_mcp_server: max_concurrent_tasks += 1 # MCP Tool Server

    # Adjust max_workers to a reasonable minimum/maximum if needed
    max_concurrent_tasks = max(1, min(max_concurrent_tasks, 10)) # Cap at 10 for safety/resource limits

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_tasks) as executor:
        futures = {}
        
        # 1. Agents (All Agents) - using deploy_adk_agent_cloud_run
        if not args.skip_agents:
            for agent_conf in all_agent_confs:
                # This now calls the Cloud Run deployment for all agents
                futures[executor.submit(
                    deploy_adk_agent_cloud_run,
                    agent_conf,
                    env_config,
                    gemini_model,
                    context, # Pass context so it can get URLs if needed
                    True # force_update
                )] = agent_conf["name"]

        # 2. OTEL Collector
        if not args.skip_collector:
            # Env vars for collector deployment
            otel_env_vars = {
                "GCP_PROJECT_ID": project_id,
                "GCP_LOCATION": region
            }
            futures[executor.submit(
                deploy_service_wrapper, 
                "otel-collector", 
                "./otel-collector", 
                env_config, 
                otel_env_vars, # Pass env_vars here
                config_path="cloudbuild.yaml"
            )] = "otel-collector"

        # 3. MCP Tool Server
        if not args.skip_mcp_server:
            # Env vars for MCP server deployment
            mcp_env_vars = {
                "GCP_PROJECT_ID": project_id,
                "SPANNER_INSTANCE_ID": env_config["spanner_instance"],
                "SPANNER_DATABASE_ID": env_config["spanner_db"],
                "OTEL_COLLECTOR_ENDPOINT": f"{context.urls.get('otel', '')}" # Removed :4317
            }
            futures[executor.submit(
                deploy_service_wrapper, 
                "mcp-tool-server", 
                "./tools/instavibe", 
                env_config, 
                mcp_env_vars, # Pass env_vars here
                config_path="cloudbuild.yaml"
            )] = "mcp-tool-server"

        # 4. InstaVibe App (Parallelized)
        if not args.skip_app and not args.deploy_orchestrate_only and not args.deploy_planner_only:
             # Construct env vars from context
            otel_endpoint = context.urls.get("otel", "")
            # No need to append :4317 anymore
                
            app_env_vars = {
                "COMMON_GOOGLE_CLOUD_PROJECT": env_config["project_id"],
                "COMMON_GOOGLE_CLOUD_LOCATION": env_config["region"],
                "COMMON_SPANNER_INSTANCE_ID": env_config["spanner_instance"],
                "COMMON_SPANNER_DATABASE_ID": env_config["spanner_db"],
                "AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL": context.urls.get("mcp", ""),
                "OTEL_COLLECTOR_ENDPOINT": otel_endpoint,
                "ORCHESTRATE_AGENT_URL": context.urls.get("orchestrate_agent", ""),
                "ENABLE_TRACING": "True", # Always enable if we are deploying the app
            }
            
            futures[executor.submit(
                deploy_app_wrapper,
                env_config,
                app_env_vars
            )] = "instavibe-app"

        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]
            result = future.result()

            if not result["success"]:
                raise DeploymentError(f"{task_name} deployment failed: {result.get('error')}")

            if "url" in result:
                # Update context with the new URL
                context.urls[task_name.replace("-", "_")] = result['url']
                # Update global environment variables as well for subsequent steps in the same script
                if task_name == "otel-collector":
                    os.environ["OTEL_COLLECTOR_ENDPOINT"] = f"{result['url']}" # Removed :4317
                elif task_name == "mcp-tool-server":
                    os.environ["MCP_SERVER_ADDRESS"] = result['url']
                elif task_name == "planner-agent": # Ensure specific agent URLs are set
                    os.environ["PLANNER_AGENT_URL"] = result['url']
                elif task_name == "social-agent":
                    os.environ["SOCIAL_AGENT_URL"] = result['url']
                elif task_name == "platform-mcp-client-agent":
                    os.environ["PLATFORM_MCP_CLIENT_AGENT_URL"] = result['url']
                elif task_name == "orchestrate-agent":
                    os.environ["ORCHESTRATE_AGENT_URL"] = result['url']
            else:
                context.agent_resource_names[result["name"]] = result["resource_name"]
        
        logging.info(f"✅ PHASE 1 COMPLETE: Parallel deployment finished")
    
    return context



# --- Main Function ---

def main(args):
    """Main deployment orchestration function."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        # Setup and initialization
        setup_observability(disable_export=True)
        logging.info("Observability setup complete.")
        
        install_dependencies()
        env_config = setup_environment()
        
        if not args.skip_spanner:
            setup_spanner(env_config["project_id"], env_config["spanner_instance"], env_config["spanner_db"], env_config["region"])
        else:
            logging.info("Skipping Spanner setup.")

        # Initialize Context
        project_number = get_project_number(env_config["project_id"])
        initial_urls = setup_cloud_run_urls(env_config, project_number)
        context = DeploymentContext(
            project_id=env_config["project_id"],
            location=env_config["region"],
            project_number=project_number,
            urls=initial_urls
        )

        # Get configurations
        gemini_model = get_gemini_model()
        all_agents = get_agent_configurations()
        
        # Filter agents based on args
        agents_to_deploy = filter_agents_by_args(all_agents, args)
        
        # --- PHASE 1: Foundation & All Agents ---
        should_deploy_phase_1 = (
            (not args.skip_agents and agents_to_deploy) or 
            not args.skip_collector or 
            not args.skip_mcp_server
        )
        
        if should_deploy_phase_1:
            context = deploy_agents_and_services_parallel(args, env_config, agents_to_deploy, gemini_model, context)
        else:
            fetched_urls = fetch_existing_cloud_run_urls(env_config["project_id"], project_number, env_config["region"])
            # Update context with fetched URLs
            context.update_urls(fetched_urls)

        # --- PHASE 3: InstaVibe App (Now Parallelized in Phase 1) ---
        # Logic moved to deploy_agents_and_services_parallel
        pass

        logging.info("--- Deployment script finished successfully! ---")

    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred in deploy_all: {e}", exc_info=True)
        sys.exit(1)
    finally:
        shutdown_observability()

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
    parser.add_argument("--deploy-planner-only", action="store_true", help="Deploy only the planner agent (for testing).")
    args = parser.parse_args()
    main(args)