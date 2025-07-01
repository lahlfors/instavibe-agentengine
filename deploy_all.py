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
# AdkApp import REMOVED as it's no longer used for workflow agent deployment
from google.adk.agents import Agent as GoogleAdkAgentDef # For defining the agent structure
from vertexai.preview import reasoning_engines # For create_session, delete_session by the tool
from google.cloud.aiplatform_v1.services import reasoning_engine_service
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC, DeleteReasoningEngineRequest
from google.api_core import exceptions as api_exceptions
import time
import logging # Added for tool logging
import traceback # ADDED for enhanced error logging

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
        name_to_return = None

        if not deployed_agent_resource:
            print(f"{agent_display_name} deployment function returned None or empty. Cannot determine resource name.")
        elif isinstance(deployed_agent_resource, str):
            # Case 1: The function returned a string (either full resource name or just ID)
            raw_name_from_sdk = deployed_agent_resource
            if raw_name_from_sdk.startswith("projects/"):
                print(f"{agent_display_name} deployment returned full resource name string: {raw_name_from_sdk}")
                name_to_return = raw_name_from_sdk
            elif raw_name_from_sdk.isdigit():
                print(f"{agent_display_name} deployment returned ID string: {raw_name_from_sdk}. Constructing full resource name.")
                name_to_return = f"projects/{project_id}/locations/{region}/reasoningEngines/{raw_name_from_sdk}"
                print(f"{agent_display_name} - Constructed full resource name: {name_to_return}")
            else:
                print(f"ERROR: {agent_display_name} - deployment returned a string in an unexpected format: '{raw_name_from_sdk}'. Cannot determine full resource name.")
        elif hasattr(deployed_agent_resource, 'name') and deployed_agent_resource.name:
            # Case 2: The function returned an object with a .name attribute
            raw_name_from_sdk = deployed_agent_resource.name
            if callable(raw_name_from_sdk): # Should not happen for .name attribute but defensive
                print(f"WARNING: {agent_display_name} - deployed_agent_resource.name is callable. Calling it.")
                raw_name_from_sdk = raw_name_from_sdk()

            if not isinstance(raw_name_from_sdk, str):
                print(f"ERROR: {agent_display_name} - deployed_agent_resource.name is not a string (type: {type(raw_name_from_sdk)}). Value: {raw_name_from_sdk}")
            elif raw_name_from_sdk.startswith("projects/"):
                print(f"{agent_display_name} deployment returned full resource name via attribute: {raw_name_from_sdk}")
                name_to_return = raw_name_from_sdk
            elif raw_name_from_sdk.isdigit(): # It's likely just the ID
                print(f"{agent_display_name} deployment returned ID via attribute: {raw_name_from_sdk}. Constructing full resource name.")
                name_to_return = f"projects/{project_id}/locations/{region}/reasoningEngines/{raw_name_from_sdk}"
                print(f"{agent_display_name} - Constructed full resource name: {name_to_return}")
            else: # Unexpected format
                print(f"ERROR: {agent_display_name} - deployed_agent_resource.name is in an unexpected format: '{raw_name_from_sdk}'. Cannot determine full resource name.")
        else:
            # Case 3: Returned object is not a string and doesn't have a valid .name attribute
            print(f"ERROR: {agent_display_name} - deployment returned an object of type {type(deployed_agent_resource)} without a valid '.name' attribute.")
            print(f"DIAGNOSTIC_TRACE: {agent_display_name} - deployed_agent_resource attributes: {dir(deployed_agent_resource)}")

        if name_to_return:
            print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} IS RETURNING: '{name_to_return}' (type: {type(name_to_return)})")
            return name_to_return
        else:
            print(f"{agent_display_name} deployment process resulted in an invalid or unhandled resource identifier. See previous ERRORs.")
            print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} - Original deployed_agent_resource: {deployed_agent_resource}")
            print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} IS RETURNING: None")
            return None

    except Exception as e:
        print(f"Error deploying {agent_display_name}: {e}")
        print(f"DIAGNOSTIC_TRACE: deploy_agent_with_forced_update for {agent_display_name} re-raising exception, WILL RETURN None implicitly if not caught by caller.")
        # Re-raise to indicate failure to the main script
        raise
    # This final return None should be unreachable if the try/except logic is exhaustive.
    # If it's reached, it means an unexpected control flow.
    print(f"DEBUG: deploy_agent_with_forced_update for {agent_display_name} reached unexpected final return None.") # DIAGNOSTIC
    return None

# Specific deployment functions using the generic helper
def deploy_planner_agent(project_id: str, region: str):
    # This agent might become obsolete if all planning goes through the workflow agent
    print("Note: Planner Agent deployment might be obsolete if all planning is via Workflow Agent.")
    return deploy_agent_with_forced_update(project_id, region, "Planner Agent", deploy_planner_main_func)

def deploy_social_agent(project_id: str, region: str):
    return deploy_agent_with_forced_update(project_id, region, "Social Agent", deploy_social_main_func)

def deploy_orchestrate_agent(project_id: str, region: str, remote_addresses_str: str):
    additional_args = {"dynamic_remote_agent_addresses": remote_addresses_str}
    return deploy_agent_with_forced_update(project_id, region, "Orchestrate Agent", deploy_orchestrate_main_func, additional_deploy_args=additional_args)

def deploy_platform_mcp_client(project_id: str, region: str):
    return deploy_agent_with_forced_update(project_id, region, "Platform MCP Client Agent", deploy_platform_mcp_client_main_func)


# New function to deploy the Instavibe Workflow Agent using ADK SDK
def deploy_instavibe_workflow_agent(project_id: str, location: str, staging_bucket_uri: str,
                                    reasoning_engine_id: str = "instavibe_workflow_agent", # USE UNDERSCORES
                                    agent_display_name: str = "Instavibe Workflow Agent", # Display name can have spaces/hyphens
                                    planner_target_name: str | None = None,
                                    orchestrate_target_name: str | None = None):
    """
    Deploys the Instavibe Workflow Agent using ADK SDK (agent_engines.create/update).
    Returns the endpoint URI of the deployed agent.
    Passes planner_target_name and orchestrate_target_name as env vars to the workflow agent.
    """
    print(f"--- Deploying Instavibe Workflow Agent ({agent_display_name}) ---")
    print(f"Project: {project_id}, Location: {location}, Staging Bucket: {staging_bucket_uri}")
    print(f"Reasoning Engine ID for deployment: {reasoning_engine_id}, Display Name: {agent_display_name}")
    tool_logger = logging.getLogger("deploy_all.workflow_tool") # Specific logger for the tool

    # Ensure vertexai is initialized (idempotent for project/location, staging bucket is important for create)
    try:
        vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket_uri)
        print(f"Vertex AI SDK initialized for Workflow Agent deployment (Project: {project_id}, Location: {location}, Staging: {staging_bucket_uri}).")
    except Exception as e:
        print(f"ERROR: Failed to initialize Vertex AI for Workflow Agent deployment: {e}")
        return None # Cannot proceed

    try:
        from agents.instavibe_workflow.agent import InstavibeWorkflowAgent
        # This InstavibeWorkflowAgent class is now a logic handler, not a deployable ADK agent itself.
        # It will be instantiated and used by the tool defined below.
    except ImportError as e:
        print(f"ERROR: Could not import InstavibeWorkflowAgent from agents.instavibe_workflow.agent: {e}")
        return None

    # This object holds the logic. It reads env vars (planner/orchestrator names) upon init.
    # These env vars must be set in the *Agent Engine's runtime environment*.
    # We pass them via agent_engines.create(..., package_env_vars=...)
    # Note: The InstavibeWorkflowAgent itself also reads GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, SELF_AGENT_ENGINE_ID
    # for its sub-call session creation logic. These also need to be in package_env_vars.
    # Instantiation here is only for defining the tool. The deployed agent will instantiate it in its own env.

    # Define the tool that will be executed by the deployed ADK Agent.
    # This tool will instantiate and run our workflow logic.
    def main_instavibe_workflow_tool(action: str, payload: dict) -> dict:
        """
        Tool entrypoint for the Instavibe Workflow Agent.
        It instantiates the logic handler and processes the request.
        It creates and manages ADK sessions for calls to sub-agents.
        """
        tool_logger.info(f"Tool: main_instavibe_workflow_tool called with action='{action}', payload_user='{payload.get('user_name', payload.get('user_id'))}'")

        # Instantiating the logic handler here ensures it picks up env vars set for the Agent Engine runtime
        workflow_logic_handler = InstavibeWorkflowAgent()

        # The tool needs to create a session for the sub-agent calls.
        # It uses the environment variables configured for the Agent Engine.
        session_for_sub_calls = None
        user_id_for_session = str(payload.get("user_id", "workflow-tool-user")) # Ensure string

        if not (workflow_logic_handler.project_id and workflow_logic_handler.location and workflow_logic_handler.self_agent_engine_id):
            tool_logger.error("Tool: Missing project/location/self_id for creating sub-call session. Check agent env vars.")
            return {"success": False, "error": "Tool: Workflow agent internal configuration error for session creation."}

        session_resource_name = f"projects/{workflow_logic_handler.project_id}/locations/{workflow_logic_handler.location}/reasoningEngines/{workflow_logic_handler.self_agent_engine_id}"

        try:
            tool_logger.info(f"Tool: Attempting to create ADK session for sub-calls. User: {user_id_for_session}, RE: {session_resource_name}")
            session_for_sub_calls = reasoning_engines.create_session(
                reasoning_engine=session_resource_name, # This workflow agent itself
                user_id=user_id_for_session
            )
            tool_logger.info(f"Tool: Created ADK session for sub-calls: {getattr(session_for_sub_calls, 'name', 'N/A')}")
        except Exception as e_sess_tool:
            tool_logger.error(f"Tool: Failed to create ADK session for sub-calls: {e_sess_tool}", exc_info=True)
            return {"success": False, "error": f"Tool: Failed to create session for sub-calls: {str(e_sess_tool)}"}

        try:
            result = workflow_logic_handler.process_request(
                action=action,
                payload=payload,
                adk_session_for_sub_calls=session_for_sub_calls
            )
        except Exception as e_process:
            tool_logger.error(f"Tool: Error during workflow_logic_handler.process_request: {e_process}", exc_info=True)
            result = {"success": False, "error": f"Tool: Error processing request: {str(e_process)}"}
        finally:
            if session_for_sub_calls and hasattr(session_for_sub_calls, 'name'):
                try:
                    tool_logger.info(f"Tool: Attempting to delete ADK session for sub-calls: {session_for_sub_calls.name}")
                    reasoning_engines.delete_session(name=session_for_sub_calls.name)
                    tool_logger.info(f"Tool: Deleted ADK session for sub-calls: {session_for_sub_calls.name}")
                except Exception as e_del_sess_tool:
                    tool_logger.warning(f"Tool: Failed to delete ADK session {session_for_sub_calls.name}: {e_del_sess_tool}", exc_info=True)
        return result

    # Define the ADK Agent structure that will be deployed
    agent_definition = GoogleAdkAgentDef(
        name=reasoning_engine_id, # This is the short ID, ensure it uses underscores
        model="gemini-1.0-pro", # Model for the agent's own potential reasoning (if any beyond tool use)
        tools=[main_instavibe_workflow_tool],
        description=f"{agent_display_name} - Main workflow processing tool.",
        instruction="You are the primary router for Instavibe operations. Use the 'main_instavibe_workflow_tool' to handle requests for 'generate_plan' or 'post_event'."
    )

    # Environment variables to be set for the deployed Reasoning Engine's runtime
    # These are crucial for InstavibeWorkflowAgent to find sub-agents and for session creation in the tool
    package_env_vars = {
        "GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": location,
        "SELF_AGENT_ENGINE_ID": reasoning_engine_id, # For the tool to create sessions for this workflow agent
        "PLANNER_A2A_ENDPOINT_URL": planner_target_name if planner_target_name else "", # planner_target_name is assumed to be the A2A HTTP URL
        "ORCHESTRATE_A2A_ENDPOINT_URL": orchestrate_target_name if orchestrate_target_name else "", # orchestrate_target_name is assumed to be the A2A HTTP URL
        # Any other env vars your InstavibeWorkflowAgent or its tool might need
    }

    # Requirements for the Agent Engine runtime.
    # These should include dependencies for InstavibeWorkflowAgent and its tool.
    requirements_path = os.path.join("agents", "instavibe_workflow", "requirements.txt")
    if not os.path.exists(requirements_path):
        print(f"ERROR: requirements.txt not found at {requirements_path} for workflow agent.")
        return None
    with open(requirements_path, 'r') as f:
        agent_requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    print(f"Workflow Agent runtime requirements: {agent_requirements}")


    deployed_reasoning_engine = None
    deployed_agent_endpoint_uri = None

    try:
        print(f"Checking for existing workflow agent (ReasoningEngine): {agent_display_name} in {location}")
        existing_engines = list(vertexai.agent_engines.list(filter=f'display_name="{agent_display_name}" AND location="{location}"'))

        if existing_engines:
            print(f"Found existing ReasoningEngine: {existing_engines[0].name}. Agent Engine does not support update via agent_engines.update() for this type of agent. Please delete and redeploy if changes are needed, or use a new reasoning_engine_id.")
            # For simplicity, we'll just use the existing one if found.
            # A more robust script might delete and recreate, or require a version change.
            deployed_reasoning_engine = existing_engines[0]
            print(f"Using existing ReasoningEngine: {deployed_reasoning_engine.name}")
        else:
            print("No existing workflow agent found. Creating new ReasoningEngine.")
            # extra_packages should list Python files needed by the agent_definition (InstavibeWorkflowAgent and its tool)
            # The paths are relative to the root of the `extra_packages_gcs_path` after upload.
            # `agent_engines.create` handles packaging. We need to point to the module containing InstavibeWorkflowAgent
            # and the module containing main_instavibe_workflow_tool (if it were separate).
            # Since main_instavibe_workflow_tool is defined here, it's part of this script's context.
            # InstavibeWorkflowAgent is in agents.instavibe_workflow.agent.
            # The ADK packaging will need to find 'agents/instavibe_workflow/agent.py'.
            # This is usually handled by specifying `packages_to_install` or `extra_packages` that point to local paths.
            # The `agent` parameter takes an `Agent` object. Its tools and code need to be resolvable.

            # For code defined outside the deployment script (like InstavibeWorkflowAgent):
            # vertexai.init(project=.., location=.., staging_bucket=..) is key.
            # The SDK will try to pickle the agent_definition and its dependencies (including the tool and the
            # InstavibeWorkflowAgent class instance if it's part of the tool's closure, or the class itself).
            # It uploads these to the staging bucket.
            # The `extra_packages` argument in some ADK deployment methods is for local Python files/dirs.
            # `agent_engines.create(agent=...)` is higher level.
            # We must ensure `agents.instavibe_workflow.agent` is findable by the Python environment running `deploy_all.py`.
            # `sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))` at the top of deploy_all.py helps.

            deployed_reasoning_engine = vertexai.agent_engines.create(
                reasoning_engine_id=reasoning_engine_id, # This is the "short name"
                agent=agent_definition,
                display_name=agent_display_name,
                description="Instavibe Workflow Agent - orchestrates planning and posting.",
                requirements=agent_requirements, # Pass runtime requirements
                # `packages_to_install` can point to local paths like './agents/instavibe_workflow' if needed.
                # For now, rely on pickling and sys.path for InstavibeWorkflowAgent.
                # extra_packages is also an option for specific files/dirs.
                # Ensure the `agents` dir is in python path for the deploy script.
                # The current `sys.path.insert` at the top of deploy_all.py should make `agents.instavibe_workflow.agent` importable.
                environment_variables=package_env_vars # Set env vars for the Agent Engine runtime
            )
            print(f"ReasoningEngine created successfully: {deployed_reasoning_engine.name}")

        if deployed_reasoning_engine and hasattr(deployed_reasoning_engine, 'name'):
            # Wait a bit for the endpoint to be provisioned and ready after creation
            print(f"Waiting for agent engine {deployed_reasoning_engine.name} to be ready...")
            time.sleep(30) # Increased wait time

            # Re-fetch the agent to get potentially updated info, including endpoint_uri
            try:
                refetched_engine = vertexai.agent_engines.get(deployed_reasoning_engine.name)
                if refetched_engine and hasattr(refetched_engine, 'endpoint_uri') and refetched_engine.endpoint_uri:
                    deployed_agent_endpoint_uri = refetched_engine.endpoint_uri
                    print(f"Instavibe Workflow Agent Endpoint URI: {deployed_agent_endpoint_uri}")
                else:
                    print(f"WARNING: Workflow agent deployed/found ({refetched_engine.name if refetched_engine else 'N/A'}), but endpoint_uri is not available. Check console.")
                    print(f"Refetched engine details: {refetched_engine}")
            except Exception as e_fetch:
                 print(f"WARNING: Failed to re-fetch agent engine {deployed_reasoning_engine.name} to get endpoint_uri: {e_fetch}")
                 print("Consider using the resource name directly or fetching URI from console if needed by instavibe-app for HTTP calls.")
                 # If instavibe-app needs to call this agent via HTTP, endpoint_uri is essential.
                 # If it were to call via SDK using resource_name, then name is sufficient.
                 # Current introvertally.py uses WORKFLOW_AGENT_URL (HTTP endpoint).

        else:
            print("ERROR: Workflow agent deployment/retrieval failed, or resource name not obtained.")
            return None

    except api_exceptions.Forbidden as e:
        # ... (error handling as before) ...
        return None
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = f"ERROR: Failed to deploy Instavibe Workflow Agent. Exception: {e}\nTraceback:\n{tb_str}"
        print(error_message)
        # If a global logger is configured for deploy_all.py, you could also use:
        # logger.error(error_message)
        return None

    return deployed_agent_endpoint_uri # Return the HTTP endpoint URI for instavibe-app


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

    # --- Pre-build step for copying 'agents' directory REMOVED ---
    # After refactoring, instavibe-app should not have direct dependencies on the 'agents/' common code.
    # Its dependencies should be managed via its own requirements.txt and it communicates
    # with agentic functionalities via the HTTP an WORKFLOW_AGENT_URL.

    # 2. Build the Docker image
    image_tag = f"us-central1-docker.pkg.dev/{project_id}/instavibe-images/{image_name_param}"
    print(f"\nStep 2: Building Instavibe App Docker image {image_tag}...")
    try:
        substitutions_arg = f"_IMAGE_TAG={image_tag}"

        build_command = [
            "gcloud", "builds", "submit", "instavibe", # Source for the build is the 'instavibe' directory
            f"--config=instavibe/cloudbuild.yaml",    # Config file path relative to CWD of deploy_all.py
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
    # --- Post-build cleanup for 'temp_agents_for_build' REMOVED ---

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

    parser = argparse.ArgumentParser(description="Deploy all components of the instavibe app.")
    parser.add_argument("--skip_agents", action="store_true", help="Skip deploying the agents.")
    parser.add_argument("--skip_app", action="store_true", help="Skip deploying the Instavibe app.")
    parser.add_argument("--skip_platform_mcp_client", action="store_true", help="Skip deploying the Platform MCP Client.")
    parser.add_argument("--skip_mcp_tool_server", action="store_true", help="Skip deploying the MCP Tool Server.")
    parser.add_argument("--skip_workflow_agent", action="store_true", help="Skip deploying the Instavibe Workflow Agent.") # New arg
    args = parser.parse_args(argv)

    # General Vertex AI SDK initialization (for multiple agent deployments)
    # Specific init with staging_bucket for AdkApp based deployment will be in its function
    print(f"Initializing Vertex AI SDK globally (Project: {project_id}, Location: {region}, Staging Bucket: {staging_bucket_uri})")
    try:
        vertexai.init(project=project_id, location=region, staging_bucket=staging_bucket_uri)
        print("Global Vertex AI SDK initialized successfully (with staging bucket).")
    except Exception as e:
        print(f"Error initializing Vertex AI SDK globally: {e}")
        raise

    planner_resource_name, social_resource_name, platform_mcp_client_resource_name, orchestrate_resource_name = None, None, None, None
    workflow_agent_url = None # Variable to hold the workflow agent's URL

    # Deploy individual agents first, as their resource names might be needed by others.
    if not args.skip_agents:
        print("--- Deploying Individual Agents (Planner, Social) ---")
        planner_resource_name = deploy_planner_agent(project_id, region)
        print(f"DIAGNOSTIC_TRACE: main() - planner_resource_name: '{planner_resource_name}' (type: {type(planner_resource_name)})")
        social_resource_name = deploy_social_agent(project_id, region)
        print(f"DIAGNOSTIC_TRACE: main() - social_resource_name: '{social_resource_name}' (type: {type(social_resource_name)})")
    else:
        print("Skipping Planner and Social agent deployments due to --skip_agents flag.")
        # Try to get from env if skipped, in case only workflow agent is being deployed but needs them
        planner_resource_name = sanitize_env_var_value(os.environ.get("AGENTS_PLANNER_RESOURCE_NAME"))
        social_resource_name = sanitize_env_var_value(os.environ.get("AGENTS_SOCIAL_RESOURCE_NAME"))


    if not args.skip_platform_mcp_client:
        print("--- Deploying Platform MCP Client Agent ---")
        platform_mcp_client_resource_name = deploy_platform_mcp_client(project_id, region)
        print(f"DIAGNOSTIC_TRACE: main() - platform_mcp_client_resource_name: '{platform_mcp_client_resource_name}' (type: {type(platform_mcp_client_resource_name)})")
    else:
        print("Skipping Platform MCP Client agent deployment due to --skip_platform_mcp_client flag.")
        platform_mcp_client_resource_name = sanitize_env_var_value(os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_RESOURCE_NAME"))

    # Prepare dynamic addresses for Orchestrate Agent
    temp_remote_names_for_orchestrator = [planner_resource_name, social_resource_name, platform_mcp_client_resource_name]
    valid_remote_names_for_orchestrator = [name for name in temp_remote_names_for_orchestrator if name]
    orchestrator_dynamic_addresses = ",".join(valid_remote_names_for_orchestrator)
    print(f"DIAGNOSTIC_TRACE: main() - orchestrator_dynamic_addresses for Orchestrate Agent: '{orchestrator_dynamic_addresses}'")

    if not args.skip_agents: # Orchestrator is skipped if other agents are skipped (by --skip_agents)
        print("--- Deploying Orchestrate Agent ---")
        orchestrate_resource_name = deploy_orchestrate_agent(project_id, region, remote_addresses_str=orchestrator_dynamic_addresses)
        print(f"DIAGNOSTIC_TRACE: main() - orchestrate_resource_name: '{orchestrate_resource_name}' (type: {type(orchestrate_resource_name)})")
    else:
        print("Skipping Orchestrate agent deployment (as other agents were skipped by --skip_agents).")
        orchestrate_resource_name = sanitize_env_var_value(os.environ.get("AGENTS_ORCHESTRATE_RESOURCE_NAME"))


    # Deploy Instavibe Workflow Agent - it needs planner_resource_name and orchestrate_resource_name
    if not args.skip_workflow_agent:
        print("--- Deploying Instavibe Workflow Agent ---")
        if not staging_bucket_uri:
            print("ERROR: COMMON_VERTEX_STAGING_BUCKET must be set in .env for deploying the Workflow Agent.")
            sys.exit(1)

        # Ensure workflow_agent_id uses underscores for Pydantic validation compatibility
        workflow_agent_id = sanitize_env_var_value(os.environ.get("WORKFLOW_AGENT_ENGINE_ID", "instavibe_workflow_agent"))
        if "-" in workflow_agent_id:
            print(f"Warning: WORKFLOW_AGENT_ENGINE_ID ('{workflow_agent_id}') contains hyphens. Forcing to underscores ('{workflow_agent_id.replace('-', '_')}') for deployment ID.")
            workflow_agent_id = workflow_agent_id.replace('-', '_')

        workflow_agent_display_name = sanitize_env_var_value(os.environ.get("WORKFLOW_AGENT_DISPLAY_NAME", "Instavibe Workflow Agent")) # Display name can have hyphens

        # Call the integrated function: deploy_instavibe_workflow_agent
        # This replaces the call to deploy_new_workflow_agent() which seemed to call an external script.
        workflow_agent_url = deploy_instavibe_workflow_agent(
            project_id=project_id,
            location=region, # Correctly maps to 'location' param of deploy_instavibe_workflow_agent
            staging_bucket_uri=staging_bucket_uri,
            reasoning_engine_id=workflow_agent_id,
            agent_display_name=workflow_agent_display_name,
            planner_target_name=planner_resource_name,
            orchestrate_target_name=orchestrate_resource_name
        )
        if not workflow_agent_url:
            print("ERROR: Instavibe Workflow Agent deployment failed using integrated method. Halting.")
            sys.exit(1)
        print(f"Instavibe Workflow Agent deployed (integrated method). Endpoint URL: {workflow_agent_url}")
    else:
        print("Skipping Instavibe Workflow Agent deployment due to --skip_workflow_agent flag.")
        workflow_agent_url = sanitize_env_var_value(os.environ.get("WORKFLOW_AGENT_URL"))
        if not workflow_agent_url:
            print("Warning: Workflow agent deployment skipped and WORKFLOW_AGENT_URL not found in environment. Dependent apps might fail if not skipped.")

    # Deploy Instavibe App - it needs workflow_agent_url
    if not args.skip_app:
        instavibe_env_vars_list = [
            f"COMMON_GOOGLE_CLOUD_PROJECT={project_id}",
            f"COMMON_SPANNER_INSTANCE_ID={spanner_instance_id}",
            f"COMMON_SPANNER_DATABASE_ID={spanner_database_id}",
            f"INSTAVIBE_FLASK_SECRET_KEY={sanitize_env_var_value(os.environ.get('INSTAVIBE_FLASK_SECRET_KEY', 'defaultSecretKey'))}",
            f"INSTAVIBE_APP_HOST={sanitize_env_var_value(os.environ.get('INSTAVIBE_APP_HOST', '0.0.0.0'))}",
            f"INSTAVIBE_APP_PORT={sanitize_env_var_value(os.environ.get('INSTAVIBE_APP_PORT', '8080'))}",
            f"INSTAVIBE_GOOGLE_MAPS_API_KEY={sanitize_env_var_value(os.environ.get('INSTAVIBE_GOOGLE_MAPS_API_KEY', ''))}",
            f"INSTAVIBE_GOOGLE_MAPS_MAP_ID={sanitize_env_var_value(os.environ.get('INSTAVIBE_GOOGLE_MAPS_MAP_ID', ''))}",
            f"COMMON_GOOGLE_CLOUD_LOCATION={region}" # Changed from 'location' to 'region' to match other uses
        ]
        # Add WORKFLOW_AGENT_URL if available
        if workflow_agent_url:
            instavibe_env_vars_list.append(f"WORKFLOW_AGENT_URL={workflow_agent_url}")
        else:
            print("WARNING: WORKFLOW_AGENT_URL is not available for instavibe-app deployment. App might not function correctly.")

        # Removed AGENTS_PLANNER_RESOURCE_NAME and other direct agent links for instavibe-app
        # as it now goes through the workflow agent.
        # If OrchestrateAgent is still used directly by instavibe-app for some reason (unlikely now), it would be added here.
        # For now, assuming all agent interactions from instavibe-app are via WORKFLOW_AGENT_URL.
        if orchestrate_resource_name: # Example if it were still needed directly
             # instavibe_env_vars_list.append(f"AGENTS_ORCHESTRATE_RESOURCE_NAME={orchestrate_resource_name}")
             pass


        instavibe_env_vars_string = ",".join(var for var in instavibe_env_vars_list if var.split('=', 1)[1] or var.split('=',1)[0] == "INSTAVIBE_GOOGLE_MAPS_API_KEY" or var.split('=',1)[0] == "INSTAVIBE_GOOGLE_MAPS_MAP_ID") # Allow empty API keys
        print(f"DEBUG: instavibe_env_vars_string for instavibe-app: '{instavibe_env_vars_string}'")
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
        print(f"DEBUG: mcp_tool_server_env_vars_string for mcp-tool-server: '{mcp_tool_server_env_vars_string}'") # ADDED FOR DEBUGGING
        deploy_mcp_tool_server(project_id, region, env_vars_string=mcp_tool_server_env_vars_string if mcp_tool_server_env_vars_string else None)
    else:
        print("Skipping MCP Tool Server deployment.")

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