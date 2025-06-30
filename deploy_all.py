import subprocess
import argparse
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__))) # Add repo root to path

# --- BEGIN OpenTelemetry API Version Diagnostic (using importlib.metadata) ---
import opentelemetry
# Attempt to prime the opentelemetry namespace by importing key submodules early
try:
    import opentelemetry.sdk
    import opentelemetry.sdk.trace
    import opentelemetry.propagate
    import opentelemetry.instrumentation # Base for instrumentation submodules
    import opentelemetry.instrumentation.logging
    print("DEBUG: Successfully performed early priming imports for opentelemetry.sdk, .trace, .propagate, .instrumentation, .instrumentation.logging")
except ImportError as e_prime:
    print(f"DEBUG: Error during early OTel priming imports: {e_prime}. This might be okay if the namespace populates correctly anyway.")

try:
    from importlib import metadata as importlib_metadata # Python 3.8+
except ImportError:
    import importlib_metadata # Fallback for Python < 3.10 where it might be a backport
    print("DEBUG: importlib.metadata not found, using importlib_metadata backport (ensure it's in requirements.txt if Python < 3.8).")

try:
    otel_api_version = importlib_metadata.version('opentelemetry-api')
    print(f"DEBUG: opentelemetry-api version (importlib.metadata): {otel_api_version}")
except importlib_metadata.PackageNotFoundError:
    print("DEBUG: opentelemetry-api version not found via importlib.metadata.")
except Exception as e_meta:
    print(f"DEBUG: Error getting opentelemetry-api version via importlib.metadata: {e_meta}")

# Re-check after priming imports
print(f"DEBUG: opentelemetry module location (after priming): {opentelemetry.__file__}")
print(f"DEBUG: opentelemetry version attribute (after priming): {opentelemetry.__version__ if hasattr(opentelemetry, '__version__') else 'N/A'}")
if hasattr(opentelemetry, 'sdk') and hasattr(opentelemetry.sdk, '__file__'):
    print(f"DEBUG: opentelemetry.sdk location (after priming): {opentelemetry.sdk.__file__}")
if hasattr(opentelemetry, 'propagate') and hasattr(opentelemetry.propagate, '__file__'):
    print(f"DEBUG: opentelemetry.propagate location (after priming): {opentelemetry.propagate.__file__}")
if hasattr(opentelemetry, 'instrumentation') and hasattr(opentelemetry.instrumentation, 'logging') and hasattr(opentelemetry.instrumentation.logging, '__file__'):
    print(f"DEBUG: opentelemetry.instrumentation.logging location (after priming): {opentelemetry.instrumentation.logging.__file__}")

# --- Explicitly initialize and set TracerProvider ---
try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry import trace as global_trace
    # Basic resource, can be enhanced later if deploy_all.py itself needs to emit traces
    # from opentelemetry.sdk.resources import Resource
    # resource = Resource(attributes={"service.name": "deploy_all_script"})
    # tracer_provider = TracerProvider(resource=resource)
    tracer_provider = TracerProvider() # Minimal provider
    global_trace.set_tracer_provider(tracer_provider)
    print("DEBUG: TracerProvider initialized and set globally in deploy_all.py.")
    # Re-check opentelemetry module status after setting provider
    print(f"DEBUG: opentelemetry module location (after set_tracer_provider): {opentelemetry.__file__}")
    print(f"DEBUG: opentelemetry version attribute (after set_tracer_provider): {opentelemetry.__version__ if hasattr(opentelemetry, '__version__') else 'N/A'}")
except ImportError as e_tp_import:
    print(f"DEBUG: Failed to import for TracerProvider setup: {e_tp_import}")
except Exception as e_tp_set:
    print(f"DEBUG: Error during TracerProvider setup: {e_tp_set}")
# --- END SDK Activation ---

# --- END OpenTelemetry API Version Diagnostic ---

from dotenv import load_dotenv
from google.cloud import aiplatform as vertexai
from google.cloud.aiplatform_v1.services import reasoning_engine_service
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC, DeleteReasoningEngineRequest # MODIFIED: Added DeleteReasoningEngineRequest
from google.api_core import exceptions as api_exceptions
import time

# Pre-install root dependencies
print(f"DEBUG: deploy_all.py sys.executable (before pip): {sys.executable}")
print(f"DEBUG: deploy_all.py VIRTUAL_ENV (before pip): {os.environ.get('VIRTUAL_ENV', 'Not set')}")
print(f"DEBUG: deploy_all.py sys.path (before pip): {sys.path}")
try:
    print("Pre-installing root dependencies for import purposes (with --no-cache-dir)...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--break-system-packages", "-r", "requirements.txt"],
        check=True, text=True, capture_output=False # Set capture_output to False to see pip's output directly
    )
    print("Root dependencies pre-installed successfully (with --no-cache-dir).")
except subprocess.CalledProcessError as e:
    print(f"ERROR: Critical error pre-installing root dependencies: {e}")
    if e.stdout: print(f"Stdout: {e.stdout}") # Will be None if capture_output=False
    if e.stderr: print(f"Stderr: {e.stderr}") # Will be None if capture_output=False
    raise

# The extensive diagnostic block previously here (after internal pip install) has been removed.
# The primary diagnostics are now at the top of the script, enhanced with early priming imports.

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
        print(f"Attempting to delete existing Reasoning Engine '{display_name}' ({existing_engine.name}) with force=True...")
        try:
            # MODIFIED: Use DeleteReasoningEngineRequest to pass force=True
            request = DeleteReasoningEngineRequest(name=existing_engine.name, force=True)
            delete_operation = gapic_client.delete_reasoning_engine(request=request)
            print(f"Force deletion initiated for {existing_engine.name}. Waiting up to 180s for completion...")
            delete_operation.result(timeout=180)
            print(f"Successfully force-deleted existing Reasoning Engine '{existing_engine.name}'.")
            # Add a small delay to allow backend to fully process deletion
            time.sleep(10)
        except Exception as del_e:
            print(f"ERROR: Failed to force-delete existing Reasoning Engine '{existing_engine.name}': {del_e}. Manual deletion might be required.")
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

        if deployed_agent_resource and hasattr(deployed_agent_resource, 'name') and deployed_agent_resource.name:
            raw_name_from_sdk = deployed_agent_resource.name
            if callable(raw_name_from_sdk): # Should not happen for .name attribute but defensive
                print(f"WARNING: {agent_display_name} - deployed_agent_resource.name is callable. Calling it.")
                raw_name_from_sdk = raw_name_from_sdk()

            # Ensure raw_name_from_sdk is a string before doing string operations
            if not isinstance(raw_name_from_sdk, str):
                print(f"ERROR: {agent_display_name} - deployed_agent_resource.name is not a string (type: {type(raw_name_from_sdk)}). Value: {raw_name_from_sdk}")
                name_to_return = None # Cannot form full name
            elif raw_name_from_sdk.startswith("projects/"):
                print(f"{agent_display_name} deployment returned full resource name: {raw_name_from_sdk}")
                name_to_return = raw_name_from_sdk
            elif raw_name_from_sdk.isdigit(): # It's likely just the ID
                print(f"{agent_display_name} deployment returned ID: {raw_name_from_sdk}. Constructing full resource name.")
                name_to_return = f"projects/{project_id}/locations/{region}/reasoningEngines/{raw_name_from_sdk}"
                print(f"{agent_display_name} - Constructed full resource name: {name_to_return}")
            else: # Unexpected format
                print(f"ERROR: {agent_display_name} - deployed_agent_resource.name is in an unexpected format: '{raw_name_from_sdk}'. Cannot determine full resource name.")
                name_to_return = None # Cannot form full name

            if name_to_return:
                print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} IS RETURNING: '{name_to_return}' (type: {type(name_to_return)})")
                return name_to_return
            else: # Fall through if name_to_return ended up being None due to errors above
                print(f"{agent_display_name} deployment process resulted in an invalid name. See previous ERRORs.")
                # No change needed for the DIAGNOSTIC_TRACE lines below as they will explain the None return
        # This else block handles cases where deployed_agent_resource is None or .name is missing/empty initially
        print(f"{agent_display_name} deployment process completed, but resource or its '.name' attribute is invalid/empty initially.")
        print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} - deployed_agent_resource: {deployed_agent_resource}") # DIAGNOSTIC_TRACE
        if deployed_agent_resource:
            print(f"DIAGNOSTIC_TRACE: {agent_display_name} - deployed_agent_resource attributes: {dir(deployed_agent_resource)}") # DIAGNOSTIC_TRACE
            if not hasattr(deployed_agent_resource, 'name'):
                print(f"DIAGNOSTIC_TRACE: {agent_display_name} - deployed_agent_resource exists but has no 'name' attribute.") # DIAGNOSTIC_TRACE
            elif not deployed_agent_resource.name: # Check if .name is empty or None
                print(f"DIAGNOSTIC_TRACE: {agent_display_name} - deployed_agent_resource has an empty or None 'name' attribute: '{deployed_agent_resource.name}'") # DIAGNOSTIC_TRACE
        print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} IS RETURNING: None") # DIAGNOSTIC_TRACE
        return None # Explicitly returning None
    except Exception as e:
        print(f"Error deploying {agent_display_name}: {e}")
        print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} re-raising exception, WILL RETURN None implicitly if not caught by caller.") # DIAGNOSTIC_TRACE
        # Re-raise to indicate failure to the main script
        raise
    # This final return None should be unreachable if the try/except logic is exhaustive.
    # If it's reached, it means an unexpected control flow.
    print(f"DEBUG: deploy_agent_with_forced_update for {agent_display_name} reached unexpected final return None.") # DIAGNOSTIC
    return None

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

    # --- Pre-build step: Copy the entire 'agents' directory into the 'instavibe' build context ---
    # This replaces the need for the a2a_common.whl for instavibe-app's direct dependencies on agents/app code.
    source_agents_dir_name = "agents"
    temp_agents_dir_in_context = "temp_agents_for_build" # Name of the dir when copied into instavibe/

    # Assuming deploy_all.py is at the project root, so 'agents' is 'project_root/agents'
    source_agents_path = source_agents_dir_name
    dest_agents_path_in_build_context = os.path.join("instavibe", temp_agents_dir_in_context)

    print(f"Preparing build context for instavibe-app: Copying '{source_agents_path}' to '{dest_agents_path_in_build_context}'...")
    import shutil
    try:
        if not os.path.isdir(source_agents_path):
            raise FileNotFoundError(f"Critical: Source agents directory '{source_agents_path}' not found relative to {os.getcwd()}.")
        
        if os.path.exists(dest_agents_path_in_build_context):
            shutil.rmtree(dest_agents_path_in_build_context)
            print(f"Removed existing '{dest_agents_path_in_build_context}'.")

        shutil.copytree(source_agents_path, dest_agents_path_in_build_context)
        print(f"Successfully copied '{source_agents_path}' to '{dest_agents_path_in_build_context}'.")
    except Exception as copy_e:
        print(f"ERROR: Could not copy '{source_agents_path}' to '{dest_agents_path_in_build_context}': {copy_e}")
        if os.path.exists(dest_agents_path_in_build_context): # Attempt cleanup on error
            shutil.rmtree(dest_agents_path_in_build_context)
        raise

    # 2. Build the Docker image
    image_tag = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    print(f"\nStep 2: Building Instavibe App Docker image {image_tag}...")
    try:
        # _A2A_WHL_FILE substitution is removed as the wheel is no longer used for these common utils.
        substitutions_arg = f"_IMAGE_TAG={image_tag}"

        build_command = [
            "gcloud", "builds", "submit", "instavibe",
            f"--config=instavibe/cloudbuild.yaml",
            f"--substitutions={substitutions_arg}",
            "--project", project_id
        ]
        print(f"Executing build command: {' '.join(build_command)}")
        subprocess.run(
            build_command,
            check=True, capture_output=True, text=True
        )
        print(f"Successfully built image: {image_tag}")
    except subprocess.CalledProcessError as e:
        print(f"Error building Instavibe App image: {e.stderr}")
        print(f"Stdout: {e.stdout}")
        raise
    finally:
        # --- Post-build cleanup: Remove the copied 'agents' directory ---
        if os.path.exists(dest_agents_path_in_build_context):
            print(f"Cleaning up: Removing '{dest_agents_path_in_build_context}'...")
            try:
                shutil.rmtree(dest_agents_path_in_build_context)
                print(f"Successfully removed '{dest_agents_path_in_build_context}'.")
            except OSError as rm_e:
                print(f"Warning: Could not remove temporary agents directory '{dest_agents_path_in_build_context}': {rm_e}")
        else:
            print(f"Cleanup: Temporary agents directory '{dest_agents_path_in_build_context}' not found, no removal needed.")

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
    import uuid
    cache_buster_value = uuid.uuid4().hex[:6]
    
    base_image_name = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    image_tag_with_buster = f"{base_image_name}:latest-cb{cache_buster_value}" # Append to tag part or use as tag
    # Using a fixed tag like 'latest' and appending a cache buster to it, or making the whole tag unique.
    # For Cloud Run, it's often better to have a unique tag rather than always 'latest'.
    # Let's make the tag itself unique for this build.
    image_tag_for_build = f"{base_image_name}-cb{cache_buster_value}"


    print(f"\nStep 2: Building MCP Tool Server Docker image {image_tag_for_build} with a clean build (cache buster: {cache_buster_value})...")
    try:
        substitutions = f"_AGENT_DIR=tools/instavibe,_DOCKERFILE_NAME=Dockerfile.v2,_IMAGE_PATH={image_tag_for_build}"
        build_command = [
            "gcloud", "builds", "submit", ".",  # Context is repo root
            "--config", "agents/cloudbuild.yaml",
            "--project", project_id,
            # "--no-cache", # Removed as it's not allowed with --config and GCB handles caching with --config
            f"--substitutions={substitutions}"
        ]
        # Assuming deploy_all.py is run from the repository root
        # If not, an absolute path to "." or a correct relative path from where deploy_all.py is run to repo root would be needed.
        # For now, assuming it's run from repo root, so "." is correct.
        subprocess.run(
            build_command,
            check=True, capture_output=True, text=True
        )
        print(f"Successfully submitted build for image: {image_tag_for_build} using agents/cloudbuild.yaml")
    except subprocess.CalledProcessError as e:
        print(f"Error building MCP Tool Server image using agents/cloudbuild.yaml: {e.stderr}")
        print(f"Stdout: {e.stdout}") # Also print stdout for more context
        raise

    # 3. Deploy the newly built image to Cloud Run
    print(f"\nStep 3: Deploying the new image {image_tag_for_build} to Cloud Run service {image_name_param}...")
    try:
        deploy_command = [
            "gcloud", "run", "deploy", image_name_param,
            "--image", image_tag_for_build, # Use the cache-busted image tag
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

    parser = argparse.ArgumentParser(description="Deploy components of the instavibe app. If no specific component flags are provided, all components will be deployed.")
    parser.add_argument("--deploy_instavibe", action="store_true", help="Deploy the Instavibe app.")
    parser.add_argument("--deploy_mcp_tool_server", action="store_true", help="Deploy the MCP Tool Server.")
    parser.add_argument("--deploy_agents", action="store_true", help="Deploy all agents (Planner, Social, Orchestrate, Platform MCP Client).")
    # Add individual agent deployment flags if needed in future, e.g.:
    # parser.add_argument("--deploy_planner_agent", action="store_true", help="Deploy the Planner agent.")
    # parser.add_argument("--deploy_social_agent", action="store_true", help="Deploy the Social agent.")
    # parser.add_argument("--deploy_orchestrate_agent", action="store_true", help="Deploy the Orchestrate agent.")
    # parser.add_argument("--deploy_platform_mcp_client_agent", action="store_true", help="Deploy the Platform MCP Client agent.")

    args = parser.parse_args(argv)

    # Determine if any specific deployment flag was passed
    specific_deployment_requested = any([
        args.deploy_instavibe,
        args.deploy_mcp_tool_server,
        args.deploy_agents
    ])

    # If no specific deployment flag is set, default to deploying all
    deploy_all_components = not specific_deployment_requested

    print(f"Initializing Vertex AI with project: {project_id}, region: {region}, staging bucket: {staging_bucket_uri}")
    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        print("Vertex AI initialized successfully.")
    except Exception as e:
        print(f"Error initializing Vertex AI: {e}")
        raise

    planner_resource_name, social_resource_name, platform_mcp_client_resource_name, orchestrate_resource_name = None, None, None, None

    # Deploy Agents if requested or if deploying all
    if deploy_all_components or args.deploy_agents:
        print("--- Deploying Agents ---")
        print("--- Deploying Individual Agents (Planner, Social) ---")
        planner_resource_name = deploy_planner_agent(project_id, region)
        print(f"DIAGNOSTIC_TRACE: main() - planner_resource_name: '{planner_resource_name}' (type: {type(planner_resource_name)})")
        social_resource_name = deploy_social_agent(project_id, region)
        print(f"DIAGNOSTIC_TRACE: main() - social_resource_name: '{social_resource_name}' (type: {type(social_resource_name)})")

        print("--- Deploying Platform MCP Client Agent ---")
        platform_mcp_client_resource_name = deploy_platform_mcp_client(project_id, region)
        print(f"DIAGNOSTIC_TRACE: main() - platform_mcp_client_resource_name: '{platform_mcp_client_resource_name}' (type: {type(platform_mcp_client_resource_name)})")

        # DIAGNOSTIC_TRACE: Log contents of valid_remote_agent_names before join
        temp_remote_names_for_debug = [planner_resource_name, social_resource_name, platform_mcp_client_resource_name]
        print(f"DIAGNOSTIC_TRACE: main() - Names for orchestrator_dynamic_addresses before filtering: {temp_remote_names_for_debug}")
        valid_remote_agent_names = [name for name in temp_remote_names_for_debug if name]
        print(f"DIAGNOSTIC_TRACE: main() - Valid names for orchestrator_dynamic_addresses after filtering: {valid_remote_agent_names}")
        orchestrator_dynamic_addresses = ",".join(valid_remote_agent_names)
        print(f"DIAGNOSTIC_TRACE: main() - orchestrator_dynamic_addresses: '{orchestrator_dynamic_addresses}'")

        print("--- Deploying Orchestrate Agent ---")
        orchestrate_resource_name = deploy_orchestrate_agent(project_id, region, remote_addresses_str=orchestrator_dynamic_addresses)
        print(f"DIAGNOSTIC_TRACE: main() - orchestrate_resource_name: '{orchestrate_resource_name}' (type: {type(orchestrate_resource_name)})")
    else:
        print("Skipping agent deployments as neither --deploy_agents nor default all deployment was specified.")

    # Deploy Instavibe App if requested or if deploying all
    if deploy_all_components or args.deploy_instavibe:
        print("--- Deploying Instavibe App ---")
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
        print(f"DEBUG: instavibe_env_vars_string for instavibe-app: '{instavibe_env_vars_string}'")
        deploy_instavibe_app(project_id, region, env_vars_string=instavibe_env_vars_string)
    else:
        print("Skipping Instavibe app deployment as --deploy_instavibe was not specified and not deploying all.")

    # Deploy MCP Tool Server if requested or if deploying all
    if deploy_all_components or args.deploy_mcp_tool_server:
        print("--- Deploying MCP Tool Server ---")
        mcp_tool_server_env_vars_list = [
            f"COMMON_GOOGLE_CLOUD_PROJECT={project_id}",
            f"TOOLS_INSTAVIBE_BASE_URL={sanitize_env_var_value(os.environ.get('TOOLS_INSTAVIBE_BASE_URL', ''))}",
            f"TOOLS_GOOGLE_GENAI_USE_VERTEXAI={sanitize_env_var_value(os.environ.get('TOOLS_GOOGLE_GENAI_USE_VERTEXAI', 'True'))}", # Default to True
            f"TOOLS_GOOGLE_CLOUD_LOCATION={region}",
            f"TOOLS_GOOGLE_API_KEY={sanitize_env_var_value(os.environ.get('TOOLS_GOOGLE_API_KEY', ''))}"
        ]
        mcp_tool_server_env_vars_string = ",".join(var for var in mcp_tool_server_env_vars_list if var.split('=', 1)[1])
        print(f"DEBUG: mcp_tool_server_env_vars_string for mcp-tool-server: '{mcp_tool_server_env_vars_string}'")
        deploy_mcp_tool_server(project_id, region, env_vars_string=mcp_tool_server_env_vars_string if mcp_tool_server_env_vars_string else None)
    else:
        print("Skipping MCP Tool Server deployment as --deploy_mcp_tool_server was not specified and not deploying all.")

    print("All selected components deployed.")

if __name__ == "__main__":
    main()

def build_a2a_common_wheel():
    """Builds the a2a_common wheel from agents/app directory."""
    print("\n--- Building a2a_common wheel ---")
    a2a_source_dir = os.path.join("agents", "app")
    if not os.path.isdir(a2a_source_dir):
        raise FileNotFoundError(f"Critical: a2a_common source directory '{a2a_source_dir}' not found.")

    # Clean up old build artifacts
    print(f"Cleaning up old build artifacts in {a2a_source_dir}...")
    import shutil
    import glob

    dist_dir = os.path.join(a2a_source_dir, "dist")
    build_dir = os.path.join(a2a_source_dir, "build")
    egg_info_dirs = glob.glob(os.path.join(a2a_source_dir, "*.egg-info"))

    if os.path.isdir(dist_dir):
        shutil.rmtree(dist_dir)
        print(f"Removed old {dist_dir}")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
        print(f"Removed old {build_dir}")
    for egg_dir in egg_info_dirs:
        shutil.rmtree(egg_dir)
        print(f"Removed old {egg_dir}")

    # Build the wheel
    print(f"Running 'python -m build' in {a2a_source_dir}...")
    try:
        # Ensure build and its dependencies are installed (might be good to add 'build' to root requirements.txt)
        # For now, assume they are present or handle error if 'build' module is not found by python.
        subprocess.run(
            [sys.executable, "-m", "build"],
            cwd=a2a_source_dir, # Run command in this directory
            check=True, text=True, capture_output=True # Capture output to show in case of error
        )
        print("a2a_common wheel built successfully.")
    except FileNotFoundError as e: # Specific for python executable not found, though sys.executable should be valid
        print(f"ERROR: Python executable not found? This should not happen. {e}")
        raise
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to build a2a_common wheel in {a2a_source_dir}.")
        if e.stdout: print(f"Build Stdout:\n{e.stdout}")
        if e.stderr: print(f"Build Stderr:\n{e.stderr}")
        raise
    except Exception as e: # Catch any other unexpected error during build
        print(f"ERROR: An unexpected error occurred during a2a_common wheel build: {e}")
        raise
    print("--- a2a_common wheel build process finished ---")

# Modify main to call the build function
def main(argv=None):
    load_dotenv()

    # Build the a2a_common wheel first
    build_a2a_common_wheel()

    project_id = sanitize_env_var_value(os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT"))
    region = sanitize_env_var_value(os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION"))