import subprocess
import argparse
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__))) # Add repo root to path
from dotenv import load_dotenv
from google.cloud import aiplatform as vertexai
from google.cloud.aiplatform_v1.services import reasoning_engine_service
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC # For type hint
from google.api_core import exceptions as api_exceptions
import time

# Pre-install root dependencies
try:
    print("Pre-installing root dependencies for import purposes...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
        check=True, text=True, capture_output=False
    )
    print("Root dependencies pre-installed successfully.")
except subprocess.CalledProcessError as e:
    print(f"ERROR: Critical error pre-installing root dependencies: {e}")
    if e.stdout: print(f"Stdout: {e.stdout}")
    if e.stderr: print(f"Stderr: {e.stderr}")
    raise

from agents.planner.deploy import deploy_planner_main_func
from agents.social.deploy import deploy_social_main_func
from agents.orchestrate.deploy import deploy_orchestrate_main_func
from agents.platform_mcp_client.deploy import deploy_platform_mcp_client_main_func

class ApiDisabledError(Exception): pass

def sanitize_env_var_value(value: str | None) -> str:
    if value is None:
        return ''
    return value.split('#', 1)[0].strip().strip('"').strip("'")

def check_reasoning_engine_exists(gapic_client: reasoning_engine_service.ReasoningEngineServiceClient, parent_path: str, display_name: str) -> ReasoningEngineGAPIC | None:
    """Checks if a reasoning engine with the given display name exists. Returns the engine object if found, else None."""
    try:
        engines = gapic_client.list_reasoning_engines(parent=parent_path)
        for engine in engines:
            if engine.display_name == display_name:
                print(f"Reasoning Engine '{display_name}' already exists with resource name: {engine.name}")
                return engine
        print(f"Reasoning Engine '{display_name}' not found.")
        return None
    except api_exceptions.Forbidden as e:
        error_message = str(e).lower()
        if ("api has not been used" in error_message or
            "service is disabled" in error_message or
            "enable it by visiting" in error_message or
            'reason: "service_disabled"' in error_message):
            print(f"ERROR: Vertex AI API is disabled for project {parent_path.split('/')[1]}. Full error: {e}")
            raise ApiDisabledError(f"Vertex AI API disabled for {parent_path.split('/')[1]}")
        else:
            print(f"Warning: Received a Forbidden error while checking for Reasoning Engine '{display_name}': {e}. Assuming it does not exist.")
            return None
    except Exception as e:
        print(f"Warning: Error checking for Reasoning Engine '{display_name}': {e}. Assuming it does not exist.")
        return None

def delete_reasoning_engine_if_exists(gapic_client: reasoning_engine_service.ReasoningEngineServiceClient, parent_path: str, display_name: str):
    """Deletes the reasoning engine if it exists."""
    existing_engine = check_reasoning_engine_exists(gapic_client, parent_path, display_name)
    if existing_engine:
        print(f"Attempting to delete existing Reasoning Engine '{display_name}' ({existing_engine.name})...")
        try:
            delete_operation = gapic_client.delete_reasoning_engine(name=existing_engine.name)
            print(f"Deletion initiated for {existing_engine.name}. Waiting up to 180s for completion...")
            delete_operation.result(timeout=180)
            print(f"Successfully deleted existing Reasoning Engine '{existing_engine.name}'.")
            # Add a small delay to allow backend to fully process deletion
            time.sleep(10)
        except Exception as del_e:
            print(f"ERROR: Failed to delete existing Reasoning Engine '{existing_engine.name}': {del_e}. Manual deletion might be required.")
            raise # Re-raise to halt further deployment of this specific agent

def check_cloud_run_service_exists(service_name: str, project_id: str, region: str) -> bool:
    try:
        result = subprocess.run(
            ["gcloud", "run", "services", "describe", service_name, "--project", project_id, "--region", region, "--format", "value(service.name)"],
            check=True, capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(f"Cloud Run service '{service_name}' already exists in project '{project_id}' region '{region}'.")
            return True
        return False
    except subprocess.CalledProcessError:
        print(f"Cloud Run service '{service_name}' not found or error describing.")
        return False
    except Exception as e:
        print(f"Unexpected error checking for Cloud Run service '{service_name}': {e}. Assuming it does not exist.")
        return False

def deploy_agent_with_forced_update(
    project_id: str, region: str, agent_display_name: str,
    deploy_main_func, # The specific deploy_xxx_main_func from agent's deploy.py
    base_dir_for_deploy_func: str = ".",
    additional_deploy_args=None # Dictionary for extra args like dynamic_remote_agent_addresses
):
    """Generic function to deploy an agent, forcing deletion if it already exists."""
    print(f"Starting deployment process for {agent_display_name} in project {project_id} region {region}...")
    if additional_deploy_args and "dynamic_remote_agent_addresses" in additional_deploy_args:
        print(f"  with remote agent addresses: {additional_deploy_args['dynamic_remote_agent_addresses'] if additional_deploy_args['dynamic_remote_agent_addresses'] else 'NONE'}")

    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    try:
        gapic_client = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)
    except Exception as e:
        print(f"ERROR: Failed to create GAPIC client: {e}. Skipping deployment of {agent_display_name}.")
        return None # Return None to indicate failure

    parent_path = f"projects/{project_id}/locations/{region}"
    try:
        delete_reasoning_engine_if_exists(gapic_client, parent_path, agent_display_name)
        print(f"Proceeding with fresh deployment of {agent_display_name}.")
    except ApiDisabledError:
        print(f"Halting deployment of {agent_display_name} due to Vertex AI API being disabled.")
        return None
    except Exception as e:
        print(f"Failed during pre-deployment delete for {agent_display_name} due to an error: {e}. Skipping deployment.")
        return None

    try:
        deploy_args = {
            "project_id": project_id,
            "region": region,
            "base_dir": base_dir_for_deploy_func
        }
        if additional_deploy_args:
            deploy_args.update(additional_deploy_args)

        deployed_agent_resource = deploy_main_func(**deploy_args)

        if deployed_agent_resource and deployed_agent_resource.name:
            print(f"{agent_display_name} deployment process completed. Resource name: {deployed_agent_resource.name}")
            return deployed_agent_resource.name
        else:
            print(f"{agent_display_name} deployment process completed, but resource or name is invalid.")
            return None
    except Exception as e:
        print(f"Error deploying {agent_display_name}: {e}")
        # Re-raise to indicate failure to the main script
        raise
    return None # Should be unreachable if an error occurs and is re-raised.

# Specific deployment functions using the generic helper
def deploy_planner_agent(project_id: str, region: str):
    return deploy_agent_with_forced_update(project_id, region, "Planner Agent", deploy_planner_main_func)

def deploy_social_agent(project_id: str, region: str):
    return deploy_agent_with_forced_update(project_id, region, "Social Agent", deploy_social_main_func)

def deploy_orchestrate_agent(project_id: str, region: str, remote_addresses_str: str):
    additional_args = {"dynamic_remote_agent_addresses": remote_addresses_str}
    return deploy_agent_with_forced_update(project_id, region, "Orchestrate Agent", deploy_orchestrate_main_func, additional_deploy_args=additional_args)

def deploy_platform_mcp_client(project_id: str, region: str):
    return deploy_agent_with_forced_update(project_id, region, "Platform MCP Client Agent", deploy_platform_mcp_client_main_func)


def deploy_instavibe_app(project_id: str, region: str, image_name_param: str = "instavibe-app", env_vars_string: str | None = None): # Renamed image_name to image_name_param for clarity
    """Deploys the Instavibe app to Cloud Run, attempting to enable Kaniko and using --no-cache."""
    print(f"--- Deploying Instavibe App ({image_name_param}) ---")

    # 1. Set the gcloud configuration to use the Kaniko cache.
    print("Step 1: Attempting to enable Kaniko cache for Google Cloud Build...")
    try:
        subprocess.run(
            ["gcloud", "config", "set", "builds/use_kaniko", "True", "--project", project_id],
            check=True, capture_output=True, text=True
        )
        print("Kaniko cache enabled successfully for project.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not enable Kaniko cache (or it was already set). This is usually fine. Error: {e.stderr}")

    # 2. Build the Docker image with --no-cache
    # Construct the full image tag
    image_tag = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    print(f"\nStep 2: Building Instavibe App Docker image {image_tag} with a clean build...")
    try:
        build_command = [
            "gcloud", "builds", "submit", "instavibe", # Source path from repo root
            "--tag", image_tag,
            "--project", project_id,
            "--no-cache"
        ]
        subprocess.run(
            build_command,
            check=True, capture_output=True, text=True
            # cwd is not needed as "instavibe" is specified as source for gcloud builds submit
        )
        print(f"Successfully built image: {image_tag}")
    except subprocess.CalledProcessError as e:
        print(f"Error building Instavibe App image: {e.stderr}")
        # print full error details
        print(f"Stdout: {e.stdout}")
        raise

    # 3. Deploy the newly built image to Cloud Run
    print(f"\nStep 3: Deploying the new image {image_tag} to Cloud Run service {image_name_param}...")
    try:
        deploy_command = [
            "gcloud", "run", "deploy", image_name_param, # Service name
            "--image", image_tag, # Full image path
            "--platform", "managed",
            "--region", region,
            "--project", project_id,
            "--allow-unauthenticated",
        ]
        if env_vars_string: deploy_command.extend(["--set-env-vars", env_vars_string])

        print(f"Deploying Instavibe App to Cloud Run in {region} with env vars: {env_vars_string if env_vars_string else 'Defaults from Dockerfile/service'}")
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        print(f"Instavibe App {image_name_param} deployed successfully to Cloud Run in {region}.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Instavibe App to Cloud Run: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        raise

def deploy_mcp_tool_server(project_id: str, region: str, image_name_param: str = "mcp-tool-server", env_vars_string: str | None = None):
    """Deploys the MCP Tool Server to Cloud Run, attempting to enable Kaniko and using --no-cache."""
    print(f"--- Deploying MCP Tool Server ({image_name_param}) ---")

    # 1. Attempt to set the gcloud configuration to use the Kaniko cache (harmless if already set).
    print("Step 1: Ensuring Kaniko cache is enabled for Google Cloud Build...")
    try:
        subprocess.run(
            ["gcloud", "config", "set", "builds/use_kaniko", "True", "--project", project_id],
            check=True, capture_output=True, text=True
        )
        print("Kaniko cache configuration check/set complete for project.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not set Kaniko cache (or it was already set). This is usually fine. Error: {e.stderr}")

    # 2. Build the Docker image with --no-cache
    image_tag = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    print(f"\nStep 2: Building MCP Tool Server Docker image {image_tag} with a clean build...")
    try:
        build_command = [
            "gcloud", "builds", "submit", "tools/instavibe", # Source path from repo root
            "--tag", image_tag,
            "--project", project_id,
            "--no-cache"
        ]
        subprocess.run(
            build_command,
            check=True, capture_output=True, text=True
            # cwd is not needed as "tools/instavibe" is the source path argument
        )
        print(f"Successfully built image: {image_tag}")
    except subprocess.CalledProcessError as e:
        print(f"Error building MCP Tool Server image: {e.stderr}")
        print(f"Stdout: {e.stdout}") # Also print stdout for more context
        raise

    # 3. Deploy the newly built image to Cloud Run
    print(f"\nStep 3: Deploying the new image {image_tag} to Cloud Run service {image_name_param}...")
    try:
        deploy_command = [
            "gcloud", "run", "deploy", image_name_param,
            "--image", image_tag,
            "--platform", "managed", "--region", region, "--project", project_id, "--allow-unauthenticated",
        ]
        if env_vars_string: deploy_command.extend(["--set-env-vars", env_vars_string])

        print(f"Deploying MCP Tool Server to Cloud Run in {region} {'with env vars: ' + env_vars_string if env_vars_string else 'without specific env vars for --set-env-vars'}")
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        print(f"MCP Tool Server {image_name_param} deployed successfully to Cloud Run in {region}.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying MCP Tool Server to Cloud Run: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        raise

def main(argv=None):
    load_dotenv()
    project_id = sanitize_env_var_value(os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT"))
    region = sanitize_env_var_value(os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION"))
    staging_bucket_uri = sanitize_env_var_value(os.environ.get("COMMON_VERTEX_STAGING_BUCKET"))
    spanner_instance_id = sanitize_env_var_value(os.environ.get("COMMON_SPANNER_INSTANCE_ID"))
    spanner_database_id = sanitize_env_var_value(os.environ.get("COMMON_SPANNER_DATABASE_ID"))

    if not all([project_id, region, staging_bucket_uri, spanner_instance_id, spanner_database_id]):
        missing_vars = [var for var, val in {
            "COMMON_GOOGLE_CLOUD_PROJECT": project_id, "COMMON_GOOGLE_CLOUD_LOCATION": region,
            "COMMON_VERTEX_STAGING_BUCKET": staging_bucket_uri, "COMMON_SPANNER_INSTANCE_ID": spanner_instance_id,
            "COMMON_SPANNER_DATABASE_ID": spanner_database_id
        }.items() if not val]
        raise ValueError(f"Missing critical environment variables in .env file: {', '.join(missing_vars)}")

    print("Starting Spanner setup...")
    instance_exists = False
    try:
        print(f"Checking if Spanner instance '{spanner_instance_id}' exists in project '{project_id}'...")
        describe_command = ['gcloud', 'spanner', 'instances', 'describe', spanner_instance_id, '--project', project_id]
        result = subprocess.run(describe_command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print(f"Spanner instance '{spanner_instance_id}' already exists.")
            instance_exists = True
        elif "NOT_FOUND" in result.stderr or "failed to find" in result.stderr.lower():
            print(f"Spanner instance '{spanner_instance_id}' does not exist. Will attempt to create it.")
            instance_exists = False
        else:
            print(f"Error describing Spanner instance '{spanner_instance_id}': {result.stderr}\nStdout: {result.stdout}")
            raise subprocess.CalledProcessError(result.returncode, describe_command, output=result.stdout, stderr=result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Halting Spanner setup due to an issue checking instance existence: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error while checking Spanner instance: {e}. Halting setup.")
        raise

    if not instance_exists:
        try:
            print(f"Creating Spanner instance '{spanner_instance_id}'...")
            subprocess.run(
                ["gcloud", "spanner", "instances", "create", spanner_instance_id, "--config=regional-us-central1",
                 "--description=GraphDB Instance InstaVibe", "--processing-units=100", "--edition=ENTERPRISE", "--project", project_id],
                check=True, capture_output=True, text=True
            )
            print(f"Spanner instance '{spanner_instance_id}' created successfully.")
        except subprocess.CalledProcessError as e:
            if "ALREADY_EXISTS" in e.stderr:
                print(f"Spanner instance '{spanner_instance_id}' already exists (detected during create attempt).")
            else:
                print(f"Error creating Spanner instance: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
                raise

    try:
        subprocess.run(
            ["gcloud", "spanner", "databases", "create", spanner_database_id, f"--instance={spanner_instance_id}",
             "--database-dialect=GOOGLE_STANDARD_SQL", "--project", project_id],
            check=True, capture_output=True, text=True
        )
        print(f"Spanner database {spanner_database_id} created successfully or already exists.")
    except subprocess.CalledProcessError as e:
        if "ALREADY_EXISTS" in e.stderr:
            print(f"Spanner database {spanner_database_id} on instance {spanner_instance_id} already exists.")
        else:
            print(f"Error creating Spanner database: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
            raise

    original_cwd = os.getcwd()
    try:
        print("Changing directory to 'instavibe' to run setup.py...")
        os.chdir("instavibe")
        subprocess.run([sys.executable, "setup.py"], check=True, capture_output=True, text=True)
        print("instavibe/setup.py executed successfully.")
    except FileNotFoundError:
        print("Error: 'instavibe' directory not found or setup.py not in it.")
        os.chdir(original_cwd)
        raise
    except subprocess.CalledProcessError as e:
        print(f"Error running instavibe/setup.py: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        os.chdir(original_cwd)
        raise
    finally:
        os.chdir(original_cwd)
        print(f"Changed directory back to {original_cwd}.")
    print("Spanner setup completed.")

    parser = argparse.ArgumentParser(description="Deploy all components of the instavibe app.")
    parser.add_argument("--skip_agents", action="store_true", help="Skip deploying the agents.")
    parser.add_argument("--skip_app", action="store_true", help="Skip deploying the Instavibe app.")
    parser.add_argument("--skip_platform_mcp_client", action="store_true", help="Skip deploying the Platform MCP Client.")
    parser.add_argument("--skip_mcp_tool_server", action="store_true", help="Skip deploying the MCP Tool Server.")
    args = parser.parse_args(argv)

    print(f"Initializing Vertex AI with project: {project_id}, region: {region}, staging bucket: {staging_bucket_uri}")
    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        print("Vertex AI initialized successfully.")
    except Exception as e:
        print(f"Error initializing Vertex AI: {e}")
        raise

    planner_resource_name, social_resource_name, platform_mcp_client_resource_name, orchestrate_resource_name = None, None, None, None

    if not args.skip_agents:
        print("--- Deploying Individual Agents (Planner, Social) ---")
        planner_resource_name = deploy_planner_agent(project_id, region)
        social_resource_name = deploy_social_agent(project_id, region)
    else:
        print("Skipping Planner and Social agent deployments due to --skip_agents flag.")

    if not args.skip_platform_mcp_client: # Not skipped by --skip_agents, has its own flag
        print("--- Deploying Platform MCP Client Agent ---")
        platform_mcp_client_resource_name = deploy_platform_mcp_client(project_id, region)
    else:
        print("Skipping Platform MCP Client agent deployment due to --skip_platform_mcp_client flag.")

    valid_remote_agent_names = [name for name in [planner_resource_name, social_resource_name, platform_mcp_client_resource_name] if name]
    orchestrator_dynamic_addresses = ",".join(valid_remote_agent_names)

    if not args.skip_agents: # Orchestrator is skipped if all agents are skipped
        print("--- Deploying Orchestrate Agent ---")
        orchestrate_resource_name = deploy_orchestrate_agent(project_id, region, remote_addresses_str=orchestrator_dynamic_addresses)
    else:
        print("Skipping Orchestrate agent deployment due to --skip_agents flag.")

    if not args.skip_app:
        instavibe_env_vars_list = [
            f"COMMON_GOOGLE_CLOUD_PROJECT={project_id}",
            f"COMMON_SPANNER_INSTANCE_ID={spanner_instance_id}",
            f"COMMON_SPANNER_DATABASE_ID={spanner_database_id}",
            f"INSTAVIBE_FLASK_SECRET_KEY={sanitize_env_var_value(os.environ.get('INSTAVIBE_FLASK_SECRET_KEY', 'defaultSecretKey'))}", # Added default
            f"INSTAVIBE_APP_HOST={sanitize_env_var_value(os.environ.get('INSTAVIBE_APP_HOST', '0.0.0.0'))}",
            f"INSTAVIBE_APP_PORT={sanitize_env_var_value(os.environ.get('INSTAVIBE_APP_PORT', '8080'))}",
            f"INSTAVIBE_GOOGLE_MAPS_API_KEY={sanitize_env_var_value(os.environ.get('INSTAVIBE_GOOGLE_MAPS_API_KEY', ''))}",
            f"INSTAVIBE_GOOGLE_MAPS_MAP_ID={sanitize_env_var_value(os.environ.get('INSTAVIBE_GOOGLE_MAPS_MAP_ID', ''))}",
            f"COMMON_GOOGLE_CLOUD_LOCATION={region}"
        ]
        if planner_resource_name: instavibe_env_vars_list.append(f"AGENTS_PLANNER_RESOURCE_NAME={planner_resource_name}")
        if social_resource_name: instavibe_env_vars_list.append(f"AGENTS_SOCIAL_RESOURCE_NAME={social_resource_name}")
        if platform_mcp_client_resource_name: instavibe_env_vars_list.append(f"AGENTS_PLATFORM_MCP_CLIENT_RESOURCE_NAME={platform_mcp_client_resource_name}")
        if orchestrate_resource_name: instavibe_env_vars_list.append(f"AGENTS_ORCHESTRATE_RESOURCE_NAME={orchestrate_resource_name}")

        instavibe_env_vars_string = ",".join(var for var in instavibe_env_vars_list if var.split('=', 1)[1]) # Ensure value is not empty
        deploy_instavibe_app(project_id, region, env_vars_string=instavibe_env_vars_string)
    else:
        print("Skipping Instavibe app deployment.")

    if not args.skip_mcp_tool_server:
        mcp_tool_server_env_vars_list = [
            f"COMMON_GOOGLE_CLOUD_PROJECT={project_id}",
            f"TOOLS_INSTAVIBE_BASE_URL={sanitize_env_var_value(os.environ.get('TOOLS_INSTAVIBE_BASE_URL', ''))}",
            f"TOOLS_GOOGLE_GENAI_USE_VERTEXAI={sanitize_env_var_value(os.environ.get('TOOLS_GOOGLE_GENAI_USE_VERTEXAI', 'True'))}", # Default to True
            f"TOOLS_GOOGLE_CLOUD_LOCATION={region}",
            f"TOOLS_GOOGLE_API_KEY={sanitize_env_var_value(os.environ.get('TOOLS_GOOGLE_API_KEY', ''))}"
        ]
        mcp_tool_server_env_vars_string = ",".join(var for var in mcp_tool_server_env_vars_list if var.split('=', 1)[1])
        deploy_mcp_tool_server(project_id, region, env_vars_string=mcp_tool_server_env_vars_string if mcp_tool_server_env_vars_string else None)
    else:
        print("Skipping MCP Tool Server deployment.")

    print("All selected components deployed.")

if __name__ == "__main__":
    main()
