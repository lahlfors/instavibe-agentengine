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

def get_project_number(project_id: str) -> str:
    """Get GCP project number from project ID."""
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

        # Pre-calculate deterministic Cloud Run URLs for parallel deployment
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

        # OTEL and MCP will be deployed in Phase 1 (parallel with agents)
        agent_resource_names = {}
        if not args.skip_agents:
            # Get the model name from the environment
            gemini_model = os.getenv("COMMON_GEMINI_MODEL")
            if not gemini_model:
                logging.error("ERROR: COMMON_GEMINI_MODEL environment variable not set. Please define it in your .env file.")
                exit(1)

            agents_to_deploy = [
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
                    "module": "agents.orchestrate.orchestrate_service_agent",
                    "agent_variable": "OrchestrateServiceAgent",
                    "requirements_file": "agents/orchestrate/requirements.txt",
                    "extra_packages": ["./agents/app", "./agents/common", "./agents/orchestrate", "./agents/_dynamic_tool_agent.py", "./agents/_a2a_helpers.py"],
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
                    "tools": []
                }
            ]
            otel_collector_endpoint = os.environ.get("OTEL_COLLECTOR_ENDPOINT")
            mcp_tool_server_url = os.environ.get("MCP_SERVER_ADDRESS")

            if args.deploy_orchestrate_only:
                logging.info("--- Deploying only the Orchestrate Agent ---")
                agents_to_deploy = [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']

            project_id = env_config["project_id"]
            region = env_config["region"]

            # Separate specialist agents from orchestrate agent
            specialist_agents = [a for a in agents_to_deploy if a['name'] != 'orchestrate_agent']
            orchestrate_agent = [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']
            
        # Get the model name from the environment
        gemini_model = os.getenv("COMMON_GEMINI_MODEL")
        if not gemini_model:
            logging.error("ERROR: COMMON_GEMINI_MODEL environment variable not set. Please define it in your .env file.")
            exit(1)

        agents_to_deploy = [
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
        otel_collector_endpoint = os.environ.get("OTEL_COLLECTOR_ENDPOINT")
        mcp_tool_server_url = os.environ.get("MCP_SERVER_ADDRESS")

        if args.deploy_orchestrate_only:
            logging.info("--- Deploying only the Orchestrate Agent ---")
            agents_to_deploy = [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']
        
        if args.deploy_planner_only:
            logging.info("--- Deploying only the Planner Agent (TESTING) ---")
            agents_to_deploy = [a for a in agents_to_deploy if a['name'] == 'planner_agent']

        project_id = env_config["project_id"]
        region = env_config["region"]

        # Separate specialist agents from orchestrate agent
        specialist_agents = [a for a in agents_to_deploy if a['name'] != 'orchestrate_agent']
        orchestrate_agent = [a for a in agents_to_deploy if a['name'] == 'orchestrate_agent']
        
        # PHASE 1: Deploy specialist agents, OTEL, and MCP in parallel (NOT the app yet)
        logging.info(f"🚀 PHASE 1: Deploying Specialist Agents, OTEL, and MCP in PARALLEL...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(specialist_agents) + 2) as executor:
            futures = {}
            
            # 1. Specialist Agents
            if not args.skip_agents:
                for agent_conf in specialist_agents:
                    futures[executor.submit(deploy_agent_wrapper, agent_conf, env_config, gemini_model, None, args.force_update)] = agent_conf["name"]

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
                        "OTEL_COLLECTOR_ENDPOINT": os.environ.get("OTEL_COLLECTOR_ENDPOINT", "")
                    },
                    config_path="tools/instavibe/cloudbuild.yaml"
                )] = "mcp-tool-server"

            # Collect results as they complete
            for future in concurrent.futures.as_completed(futures):
                task_name = futures[future]
                try:
                    result = future.result()
                    
                    if task_name == "otel-collector":
                        if result["success"]:
                            os.environ["OTEL_COLLECTOR_ENDPOINT"] = f"{result['url']}:4317"
                            logging.info(f"✅ PHASE 1: OTEL Collector deployed: {result['url']}")
                        else:
                            raise DeploymentError(f"OTEL Collector deployment failed: {result.get('error')}")
                    
                    elif task_name == "mcp-tool-server":
                        if result["success"]:
                            os.environ["MCP_SERVER_URL"] = result['url']
                            logging.info(f"✅ PHASE 1: MCP Server deployed: {result['url']}")
                        else:
                            raise DeploymentError(f"MCP Server deployment failed: {result.get('error')}")
                    
                    else:
                        # Agent deployment result
                        if result["success"]:
                            agent_resource_names[result["name"]] = result["resource_name"]
                        else:
                            logging.error(f"❌ PHASE 1 FAILED: {result['name']}: {result.get('error', 'Unknown error')}")
                            raise DeploymentError(f"Phase 1 agent deployment failed: {result['name']}")
                            
                except Exception as e:
                    logging.error(f"❌ PHASE 1 FAILED: {task_name}: {e}")
                    raise DeploymentError(f"Phase 1 failed: {task_name}")
            
            logging.info(f"✅ PHASE 1 COMPLETE: Parallel deployment finished")
            
            # PHASE 2: Deploy orchestrate agent (needs specialist agent resource names)
            if orchestrate_agent and not args.deploy_orchestrate_only and not args.skip_agents:
                logging.info(f"🔗 PHASE 2: Deploying Orchestrate Agent (depends on Phase 1 agent resource names)...")
                
                result = deploy_agent_wrapper(orchestrate_agent[0], env_config, gemini_model, agent_resource_names, args.force_update)
                if result["success"]:
                    agent_resource_names[result["name"]] = result["resource_name"]
                    logging.info(f"✅ PHASE 2 COMPLETE: Orchestrate Agent deployed")
                else:
                    logging.error(f"❌ PHASE 2 FAILED: {result.get('error', 'Unknown error')}")
                    raise DeploymentError(f"Phase 2 orchestrate agent deployment failed")
            
            
            # Handle deploy-orchestrate-only flag
            elif args.deploy_orchestrate_only and orchestrate_agent:
                logging.info(f"--- Deploying ONLY Orchestrate Agent (sequential mode) ---")
                
                # Fetch existing deployed agent resource names
                logging.info("Fetching existing specialist agent resource names...")
                existing_agents = {}
                try:
                    from vertexai.preview import reasoning_engines
                    
                    # Fetch Planner Agent (latest version)
                    try:
                        planner_list = reasoning_engines.ReasoningEngine.list(
                            filter='display_name="Planner Agent"'
                        )
                        if planner_list:
                            # Sort by creation time, newest first
                            planner_list = sorted(planner_list, key=lambda x: x.create_time, reverse=True)
                            existing_agents["planner_agent"] = planner_list[0].resource_name
                            logging.info(f"Found Planner Agent (latest): {existing_agents['planner_agent']}")
                        else:
                            logging.error("Planner Agent not found!")
                    except Exception as e:
                        logging.error(f"Could not fetch Planner Agent: {e}")
                        raise
                    
                    # Fetch Social Agent (latest version)
                    try:
                        social_list = reasoning_engines.ReasoningEngine.list(
                            filter='display_name="Social Agent"'
                        )
                        if social_list:
                            # Sort by creation time, newest first
                            social_list = sorted(social_list, key=lambda x: x.create_time, reverse=True)
                            existing_agents["social_agent"] = social_list[0].resource_name
                            logging.info(f"Found Social Agent (latest): {existing_agents['social_agent']}")
                        else:
                            logging.warning("Social Agent not found. Orchestrator will not have social capabilities.")
                    except Exception as e:
                        logging.warning(f"Could not fetch Social Agent: {e}")
                    
                    # Fetch Platform MCP Client Agent (latest version)
                    try:
                        platform_list = reasoning_engines.ReasoningEngine.list(
                            filter='display_name="Platform MCP Client Agent"'
                        )
                        if platform_list:
                            # Sort by creation time, newest first
                            platform_list = sorted(platform_list, key=lambda x: x.create_time, reverse=True)
                            existing_agents["platform_mcp_client_agent"] = platform_list[0].resource_name
                            logging.info(f"Found Platform MCP Client Agent (latest): {existing_agents['platform_mcp_client_agent']}")
                        else:
                            logging.warning("Platform MCP Client Agent not found. Orchestrator will not have platform capabilities.")
                    except Exception as e:
                        logging.warning(f"Could not fetch Platform MCP Client Agent: {e}")
                        
                except Exception as e:
                    logging.error(f"Error fetching existing agents: {e}")
                    raise DeploymentError("Failed to fetch existing specialist agents. Deploy all agents first.")
                
                # Deploy orchestrator with existing agent resource names
                result = deploy_agent_wrapper(orchestrate_agent[0], env_config, gemini_model, existing_agents, args.force_update)
                if result["success"]:
                    agent_resource_names[result["name"]] = result["resource_name"]
                else:
                    raise DeploymentError(f"Orchestrate agent deployment failed: {result.get('error')}")
            
            # Handle deploy-planner-only flag (for testing)
            elif args.deploy_planner_only and agents_to_deploy:
                logging.info(f"--- Deploying ONLY Planner Agent (sequential mode - TESTING) ---")
                result = deploy_agent_wrapper(agents_to_deploy[0], env_config, gemini_model, None, args.force_update)
                if result["success"]:
                    agent_resource_names[result["name"]] = result["resource_name"]
                else:
                    raise DeploymentError(f"Planner agent deployment failed: {result.get('error')}")


        # PHASE 3: Deploy InstaVibe App (AFTER orchestrator so it finds the newest one)
        if not args.skip_app:
            logging.info(f"🌐 PHASE 3: Deploying InstaVibe App (after orchestrator deployment)...")
            
            # Use pre-calculated URLs for App env vars
            app_env_vars = {
                "COMMON_GOOGLE_CLOUD_PROJECT": env_config["project_id"],
                "COMMON_GOOGLE_CLOUD_LOCATION": env_config["region"],
                "COMMON_SPANNER_INSTANCE_ID": env_config["spanner_instance"],
                "COMMON_SPANNER_DATABASE_ID": env_config["spanner_db"],
                "AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL": mcp_tool_server_url,
                "OTEL_COLLECTOR_ENDPOINT": otel_collector_endpoint,
                "ENABLE_TRACING": str(not args.deploy_orchestrate_only),
            }
            
            result = deploy_app_wrapper(env_config, app_env_vars)
            if result["success"]:
                logging.info(f"✅ PHASE 3 COMPLETE: InstaVibe App deployed: {result['url']}")
            else:
                raise DeploymentError(f"InstaVibe App deployment failed: {result.get('error')}")
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
    parser.add_argument("--deploy-planner-only", action="store_true", help="Deploy only the planner agent (for testing).")
    parser.add_argument("--force-update", action="store_true", help="Force update existing agents by deleting them first.")
    args = parser.parse_args()
    main(args)
