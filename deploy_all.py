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

def fetch_phase_1_state(context: DeploymentContext) -> DeploymentContext:
    """
    Fetches existing state for Phase 1 services if they are skipped.
    This ensures determinism by verifying resources exist instead of guessing.
    """
    logging.info("🔍 Fetching existing Phase 1 state (Spanner, OTEL, MCP, Specialist Agents)...")
    
    # 1. Fetch Cloud Run URLs (OTEL, MCP)
    # We can re-calculate them deterministically or fetch from Cloud Run API
    # Re-calculating is faster and safe if naming is consistent
    otel_url = get_cloud_run_url("otel-collector", context.project_number, context.location)
    mcp_url = get_cloud_run_url("mcp-tool-server", context.project_number, context.location)
    
    context.update_urls({
        "otel": otel_url,
        "mcp": mcp_url
    })
    logging.info(f"  📍 Found OTEL URL: {otel_url}")
    logging.info(f"  📍 Found MCP URL: {mcp_url}")
    
    # 2. Fetch Specialist Agents
    # We need to find the latest version of each specialist agent
    specialist_agents = ["Planner Agent", "Social Agent", "Platform MCP Client Agent"]
    found_agents = {}
    
    from vertexai.preview import reasoning_engines
    
    try:
        # List all engines once to avoid multiple API calls
        all_engines = reasoning_engines.ReasoningEngine.list(project=context.project_id, location=context.location)
        
        for agent_display_name in specialist_agents:
            # Filter for this agent
            matches = [e for e in all_engines if e.display_name == agent_display_name]
            if not matches:
                raise DeploymentError(f"Required agent '{agent_display_name}' not found. Cannot skip Phase 1.")
            
            # Sort by create time (newest first)
            matches.sort(key=lambda e: e.create_time, reverse=True)
            latest = matches[0]
            
            # Map display name to internal key
            key_map = {
                "Planner Agent": "planner_agent",
                "Social Agent": "social_agent",
                "Platform MCP Client Agent": "platform_mcp_client_agent"
            }
            internal_key = key_map.get(agent_display_name)
            if internal_key:
                found_agents[internal_key] = latest.resource_name
                logging.info(f"  🤖 Found {agent_display_name}: {latest.resource_name}")
                
        context.update_agents(found_agents)
        
    except Exception as e:
        logging.error(f"Failed to fetch existing agents: {e}")
        raise DeploymentError("Failed to fetch existing Phase 1 state. Please run full deployment.")
        
    return context


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

def get_project_number(project_id: str) -> str:
    """Get GCP project number from project ID."""
    # Temporarily hardcoded due to gcloud cffi issue
    if project_id == "laah-genai":
        return "735503743752"
    
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

def deploy_agent_wrapper(agent_conf: Dict, env_config: Dict, gemini_model: str, agent_resource_names: Optional[Dict[str, str]] = None, force_update: bool = False) -> Dict:
    """Thread-safe agent deployment wrapper for parallel execution."""
    display_name = agent_conf["display_name"]
    adk_agent_name = agent_conf["name"]
    
    try:
        logging.info(f"[Parallel] Deploying agent: {display_name}")
        
        # Import and instantiate agent
        module_path = agent_conf["module"]
        agent_var = agent_conf["agent_variable"]
        module = importlib.import_module(module_path)
        agent_class = getattr(module, agent_var)
        
        kwargs = {
            "name": adk_agent_name,
            "model": gemini_model,
            "tools": agent_conf.get("tools", []),
            "display_name": display_name,
            "otel_collector_endpoint": os.getenv("OTEL_COLLECTOR_ENDPOINT")
        }
        
        # Special handling for different agent types
        if agent_var == "PlatformMCPClientAgent":
            kwargs["mcp_server_address"] = os.getenv("MCP_SERVER_ADDRESS", "")
        
        if agent_var == "SocialLoopAgent":
            if "model" in kwargs: del kwargs["model"]
            if "tools" in kwargs: del kwargs["tools"]
        
        # Special handling for Orchestrate Agent - pass agent resource names
        if agent_var == "OrchestrateServiceAgent" and agent_resource_names:
            kwargs["planner_agent_resource_name"] = agent_resource_names.get("planner_agent", "")
            kwargs["social_agent_resource_name"] = agent_resource_names.get("social_agent", "")
            kwargs["platform_mcp_client_agent_resource_name"] = agent_resource_names.get("platform_mcp_client_agent", "")
            logging.info(f"Orchestrate Agent will connect to: planner={kwargs['planner_agent_resource_name']}, social={kwargs['social_agent_resource_name']}, platform={kwargs['platform_mcp_client_agent_resource_name']}")
        
        agent_to_deploy = agent_class(**kwargs)
        
        # Deploy agent
        with open(agent_conf["requirements_file"], "r") as f:
            requirements = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        
        remote_agent = deploy_adk_agent_engine(
            agent_object=agent_to_deploy,
            project=env_config["project_id"],
            location=env_config["region"],
            requirements=requirements,
            extra_packages=agent_conf["extra_packages"],
            display_name=display_name,
            force_update=force_update,
        )
        
        logging.info(f" [Parallel] ✅ {display_name}: {remote_agent.resource_name}")
        return {"success": True, "name": adk_agent_name, "resource_name": remote_agent.resource_name}
        
    except Exception as e:
        logging.error(f"[Parallel] ❌ {display_name}: {e}", exc_info=True)
        return {"success": False, "name": adk_agent_name, "error": str(e)}


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

def build_and_deploy_cloud_run_service(
    project_id: str,
    region: str,
    service_name: str,
    source_path: str,
    env_vars: Optional[Dict[str, str]] = None,
    allow_unauthenticated: bool = True,
    service_account: Optional[str] = None,
    config_path: str = "cloudbuild.yaml"
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
        "_REGION": region,
        "_SERVICE_ACCOUNT": service_account or "",
        "_SERVICE_DIR": source_path,
    }

    if env_vars:
        for k, v in env_vars.items():
            if v is not None:
                substitutions[f"_{k}"] = str(v)

    substitutions_string = ",".join([f"{k}={v}" for k, v in substitutions.items()])

    build_submit_cmd = [
        "gcloud", "builds", "submit", ".",
        "--config", config_path,
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
            config_path=config_path
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
            service_account=env_config.get("service_account")
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
            "module": "agents.planner.agent",
            "agent_variable": "PlannerAgent",
            "requirements_file": "agents/planner/requirements.txt",
            "extra_packages": ["./agents/app", "./agents/common", "./agents/planner"],
            "tools": []
        },
        {
            "name": "orchestrate_agent",
            "gcp_id": "orchestrate-agent",
            "display_name": "Orchestrate Agent",
            "module": "agents.orchestrate.agent",
            "agent_variable": "OrchestrateServiceAgent",
            "requirements_file": "agents/orchestrate/requirements.txt",
            "extra_packages": ["./agents/app", "./agents/common", "./agents/orchestrate", "./agents/_dynamic_tool_agent.py", "./agents/_a2a_helpers.py"],
            "tools": []
        },
        {
            "name": "social_agent",
            "gcp_id": "social-agent",
            "display_name": "Social Agent",
            "module": "agents.social.agent",
            "agent_variable": "SocialLoopAgent",
            "requirements_file": "agents/social/requirements.txt",
            "extra_packages": ["./agents/app", "./agents/common", "./agents/social", "./tools"],
        },
        {
            "name": "platform_mcp_client_agent",
            "gcp_id": "platform-mcp-client-agent",
            "display_name": "Platform MCP Client Agent",
            "module": "agents.platform_mcp_client.agent",
            "agent_variable": "PlatformMCPClientAgent",
            "requirements_file": "agents/platform_mcp_client/requirements.txt",
            "extra_packages": ["./agents/app", "./agents/common", "./agents/platform_mcp_client", "./agents/_dynamic_tool_agent.py"],
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

def setup_cloud_run_urls(env_config: Dict) -> tuple:
    """Pre-calculate deterministic Cloud Run URLs for parallel deployment."""
    logging.info("🔍 Pre-calculating Cloud Run URLs for parallel deployment...")
    project_number = get_project_number(env_config["project_id"])
    region = env_config["region"]
    
    otel_url = get_cloud_run_url("otel-collector", project_number, region)
    mcp_url = get_cloud_run_url("mcp-tool-server", project_number, region)
    app_url = get_cloud_run_url("instavibe-app", project_number, region)
    
    # Set URLs in environment BEFORE deployment
    os.environ["OTEL_COLLECTOR_ENDPOINT"] = f"{otel_url}:4317"
    os.environ["MCP_SERVER_ADDRESS"] = mcp_url
    
    logging.info(f"  📍 OTEL Collector URL: {otel_url}")
    logging.info(f"  📍 MCP Tool Server URL: {mcp_url}")
    logging.info(f"  📍 InstaVibe App URL: {app_url}")
    
    return project_number, {"otel": otel_url, "mcp": mcp_url, "app": app_url}

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



def deploy_phase_1_parallel(args, env_config: Dict, specialist_agents: List[Dict], gemini_model: str, context: DeploymentContext) -> DeploymentContext:
    """PHASE 1: Deploy specialist agents, OTEL, and MCP in parallel."""
    logging.info(f"🚀 PHASE 1: Deploying Specialist Agents, OTEL, and MCP in PARALLEL...")
    
    project_id = env_config["project_id"]
    region = env_config["region"]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(specialist_agents) + 2) as executor:
        futures = {}
        
        # 1. Specialist Agents
        if not args.skip_agents:
            for agent_conf in specialist_agents:
                # Always force update as we assume code changes
                futures[executor.submit(deploy_agent_wrapper, agent_conf, env_config, gemini_model, None, True)] = agent_conf["name"]

        # 2. OTEL Collector
        if not args.skip_collector:
            futures[executor.submit(
                deploy_service_wrapper, 
                "otel-collector", 
                "./otel-collector", 
                env_config, 
                {
                    "GCP_PROJECT_ID": project_id,
                    "GCP_LOCATION": region
                },
                config_path="otel-collector/cloudbuild.yaml"
            )] = "otel-collector"

        # 3. MCP Tool Server
        if not args.skip_mcp_server:
            futures[executor.submit(
                deploy_service_wrapper, 
                "mcp-tool-server", 
                "./tools/instavibe", 
                env_config, 
                {
                    "GCP_PROJECT_ID": project_id,
                    "SPANNER_INSTANCE_ID": env_config["spanner_instance"],
                    "SPANNER_DATABASE_ID": env_config["spanner_db"],
                    "OTEL_COLLECTOR_ENDPOINT": context.urls.get("otel", "") # Use context if available, though likely empty here if deploying
                },
                config_path="tools/instavibe/cloudbuild.yaml"
            )] = "mcp-tool-server"

        # Collect results as they complete
        new_urls = {}
        new_agents = {}
        
        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]
            result = future.result()
            
            if task_name == "otel-collector":
                if result["success"]:
                    new_urls["otel"] = result['url']
                    # Update env var immediately for other threads if needed (though mostly for next phases)
                    os.environ["OTEL_COLLECTOR_ENDPOINT"] = f"{result['url']}:4317"
                    logging.info(f"✅ PHASE 1: OTEL Collector deployed: {result['url']}")
                else:
                    raise DeploymentError(f"OTEL Collector deployment failed: {result.get('error')}")
            
            elif task_name == "mcp-tool-server":
                if result["success"]:
                    new_urls["mcp"] = result['url']
                    os.environ["MCP_SERVER_URL"] = result['url']
                    logging.info(f"✅ PHASE 1: MCP Server deployed: {result['url']}")
                else:
                    raise DeploymentError(f"MCP Server deployment failed: {result.get('error')}")
            
            else:
                # Agent deployment result
                if result["success"]:
                    new_agents[result["name"]] = result["resource_name"]
                else:
                    logging.error(f"❌ PHASE 1 FAILED: {result['name']}: {result.get('error', 'Unknown error')}")
                    raise DeploymentError(f"Phase 1 agent deployment failed: {result['name']}")
        
        # Update Context
        context.update_urls(new_urls)
        context.update_agents(new_agents)
        
        logging.info(f"✅ PHASE 1 COMPLETE: Parallel deployment finished")
    
    return context

def deploy_phase_2_orchestrate(args, env_config: Dict, orchestrate_agent: List[Dict], gemini_model: str, context: DeploymentContext) -> DeploymentContext:
    """PHASE 2: Deploy orchestrate agent (needs specialist agent resource names from context)."""
    if not orchestrate_agent:
        return context
    
    logging.info(f"🔗 PHASE 2: Deploying Orchestrate Agent (depends on Phase 1 agent resource names)...")
    
    # Use resource names from context
    # Always force update
    result = deploy_agent_wrapper(orchestrate_agent[0], env_config, gemini_model, context.agent_resource_names, True)
    
    if result["success"]:
        logging.info(f"✅ PHASE 2 COMPLETE: Orchestrate Agent deployed")
        context.update_agents({result["name"]: result["resource_name"]})
        return context
    else:
        logging.error(f"❌ PHASE 2 FAILED: {result.get('error', 'Unknown error')}")
        raise DeploymentError(f"Phase 2 orchestrate agent deployment failed")



def deploy_phase_3_app(env_config: Dict, context: DeploymentContext):
    """PHASE 3: Deploy InstaVibe App (after orchestrator so it finds the newest one)."""
    logging.info(f"🌐 PHASE 3: Deploying InstaVibe App (after orchestrator deployment)...")
    
    # Construct env vars from context
    otel_endpoint = context.urls.get("otel", "")
    if otel_endpoint and not otel_endpoint.endswith(":4317"):
        otel_endpoint = f"{otel_endpoint}:4317"
        
    app_env_vars = {
        "COMMON_GOOGLE_CLOUD_PROJECT": env_config["project_id"],
        "COMMON_GOOGLE_CLOUD_LOCATION": env_config["region"],
        "COMMON_SPANNER_INSTANCE_ID": env_config["spanner_instance"],
        "COMMON_SPANNER_DATABASE_ID": env_config["spanner_db"],
        "AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL": context.urls.get("mcp", ""),
        "OTEL_COLLECTOR_ENDPOINT": otel_endpoint,
        "ENABLE_TRACING": "True", # Always enable if we are deploying the app
    }
    
    result = deploy_app_wrapper(env_config, app_env_vars)
    if result["success"]:
        logging.info(f"✅ PHASE 3 COMPLETE: InstaVibe App deployed: {result['url']}")
        context.update_urls({"app": result['url']})
    else:
        raise DeploymentError(f"InstaVibe App deployment failed: {result.get('error')}")

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
        context = DeploymentContext(
            project_id=env_config["project_id"],
            location=env_config["region"],
            project_number=get_project_number(env_config["project_id"])
        )

        # Get configurations
        gemini_model = get_gemini_model()
        all_agents = get_agent_configurations()
        
        # Filter agents based on args (e.g. deploy_planner_only)
        # Note: filter_agents_by_args might need adjustment or we just use it as is
        agents_to_deploy = filter_agents_by_args(all_agents, args)
        
        specialist_agents = [a for a in agents_to_deploy if a['name'] != 'orchestrate_agent']
        orchestrate_agent = [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']

        # --- PHASE 1: Foundation & Specialist Agents ---
        # Determine if we should run Phase 1 deployment
        should_deploy_phase_1 = (
            (not args.skip_agents and specialist_agents) or 
            not args.skip_collector or 
            not args.skip_mcp_server
        )
        
        # Override for orchestrate-only (skip Phase 1 deployment)
        if args.deploy_orchestrate_only:
            should_deploy_phase_1 = False

        if should_deploy_phase_1:
            context = deploy_phase_1_parallel(args, env_config, specialist_agents, gemini_model, context)
        else:
            # If skipping Phase 1, we MUST fetch state if we are proceeding to Phase 2 or 3
            # (unless we are doing nothing else, which is unlikely)
            if not args.deploy_planner_only: # If planner only, we stop after Phase 1 anyway
                 context = fetch_phase_1_state(context)

        # --- PHASE 2: Orchestrate Agent ---
        should_deploy_phase_2 = (
            (not args.skip_agents and orchestrate_agent) or
            args.deploy_orchestrate_only
        )
        
        if args.deploy_planner_only:
            should_deploy_phase_2 = False

        if should_deploy_phase_2:
            context = deploy_phase_2_orchestrate(args, env_config, orchestrate_agent, gemini_model, context)
        
        # --- PHASE 3: InstaVibe App ---
        should_deploy_phase_3 = not args.skip_app
        
        if args.deploy_orchestrate_only or args.deploy_planner_only:
            should_deploy_phase_3 = False
            
        if should_deploy_phase_3:
            deploy_phase_3_app(env_config, context)
        else:
            logging.info("--- Skipping InstaVibe App deployment. ---")

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
