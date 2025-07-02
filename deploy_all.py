# deploy_all.py
import os
import logging
from agents.planner.deploy import deploy_planner_agent
from agents.social.deploy import deploy_social_agent
from agents.orchestrate.deploy import deploy_orchestrator_agent
from agents.instavibe_workflow.agent import InstavibeWorkflowAgent # Assuming this is the client
# For instavibe_workflow deployment, we need its deploy function if it's also an RE
# from agents.instavibe_workflow.deploy import deploy_instavibe_workflow_agent # If it's an RE
import asyncio
from typing import Optional, Any
import vertexai # Ensure vertexai is initialized early if not done in individual scripts robustly

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

# Initialize Vertex AI SDK once, centrally.
# Individual deploy scripts also call vertexai.init(), which is idempotent.
try:
    PROJECT_ID = os.environ["COMMON_GOOGLE_CLOUD_PROJECT"]
    LOCATION = os.environ["COMMON_GOOGLE_CLOUD_LOCATION"]
    STAGING_BUCKET = os.environ["COMMON_VERTEX_STAGING_BUCKET"]
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)
    logger.info(f"Vertex AI SDK initialized globally: project:{PROJECT_ID}, location:{LOCATION}, staging:{STAGING_BUCKET}")
except KeyError as e:
    logger.error(f"Critical environment variable missing: {e}. Please set COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, and COMMON_VERTEX_STAGING_BUCKET.")
    raise
except Exception as e:
    logger.error(f"Error initializing Vertex AI SDK globally: {e}", exc_info=True)
    raise


def delete_reasoning_engine_if_exists(display_name_to_delete: str, project_id: str, location: str):
    """Deletes a reasoning engine by its display name if it exists."""
    try:
        # Need to import this for list and delete by display name
        from google.cloud import aiplatform_v1beta1 as aiplatform_preview_client # Use preview for list by display_name

        client_options = {"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        client = aiplatform_preview_client.ReasoningEngineServiceClient(client_options=client_options)

        parent = f"projects/{project_id}/locations/{location}"

        # List engines and find the one with the matching display name
        list_request = aiplatform_preview_client.ListReasoningEnginesRequest(parent=parent)
        engines = client.list_reasoning_engines(request=list_request)

        engine_to_delete_name = None
        for engine in engines:
            if engine.display_name == display_name_to_delete:
                engine_to_delete_name = engine.name
                break

        if engine_to_delete_name:
            logger.info(f"Found existing Reasoning Engine '{display_name_to_delete}' with resource name '{engine_to_delete_name}'. Deleting...")
            delete_request = aiplatform_preview_client.DeleteReasoningEngineRequest(name=engine_to_delete_name)
            operation = client.delete_reasoning_engine(request=delete_request)
            operation.result() # Wait for deletion to complete
            logger.info(f"Successfully deleted Reasoning Engine '{display_name_to_delete}'.")
        else:
            logger.info(f"No existing Reasoning Engine found with display name '{display_name_to_delete}'. Skipping deletion.")

    except ImportError:
        logger.warning("google-cloud-aiplatform preview client (aiplatform_v1beta1) not available. Cannot delete by display name. Skipping pre-deletion.")
    except Exception as e:
        logger.error(f"Error deleting Reasoning Engine '{display_name_to_delete}': {e}", exc_info=True)
        # Decide if this should be a fatal error or just a warning
        logger.warning(f"Proceeding with deployment attempt for '{display_name_to_delete}' despite error during pre-deletion check.")


def deploy_agent_with_forced_update(deploy_func, agent_human_name: str, staging_bucket_uri: str, display_name_for_re: str) -> Optional[Any]:
    """
    Wrapper to deploy an agent. It first attempts to delete any existing
    Reasoning Engine with the target display_name.
    - deploy_func: The actual deployment function for the agent (e.g., deploy_planner_agent).
    - agent_human_name: A human-readable name for logging (e.g., "Planner Agent").
    - staging_bucket_uri: The GCS URI for staging.
    - display_name_for_re: The specific display_name to use for the Reasoning Engine resource.
    """
    logger.info(f"--- Attempting to deploy {agent_human_name} with RE display name: {display_name_for_re} ---")

    # Attempt to delete existing RE by display name first for a "forced update"
    # This uses PROJECT_ID and LOCATION from the global scope (initialized from env vars)
    delete_reasoning_engine_if_exists(display_name_for_re, PROJECT_ID, LOCATION)

    try:
        # Call the specific agent's deployment function
        # It now expects staging_bucket_uri and display_name as arguments
        deployed_agent = deploy_func(staging_bucket_uri=staging_bucket_uri, display_name=display_name_for_re)
        logger.info(f"Successfully deployed {agent_human_name} as '{display_name_for_re}'. Resource: {getattr(deployed_agent, 'name', 'N/A')}")
        return deployed_agent
    except Exception as e:
        logger.error(f"Failed to deploy {agent_human_name} ('{display_name_for_re}'): {e}", exc_info=True)
        return None

async def main():
    # Staging bucket is now read from global STAGING_BUCKET, set during initial vertexai.init()
    # but individual deploy functions expect it as an argument.

    # Deploy Planner
    # The display_name passed here ("planner_agent_prod") will be used by deploy_planner_agent
    # for the ReasoningEngine's display_name.
    planner_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_planner_agent,
        agent_human_name="Planner Agent",
        staging_bucket_uri=STAGING_BUCKET,
        display_name_for_re="planner_agent_prod" # Specific RE display name
    )
    planner_a2a_url = None
    if planner_deployed_agent and hasattr(planner_deployed_agent, 'gca_resource') and planner_deployed_agent.gca_resource:
        planner_a2a_url = planner_deployed_agent.gca_resource.public_endpoint_uri
    elif planner_deployed_agent and hasattr(planner_deployed_agent, 'uri'): # Fallback for RE direct attribute
        planner_a2a_url = planner_deployed_agent.uri

    if planner_a2a_url:
        logger.info(f"Planner A2A URL: {planner_a2a_url}")
    else:
        logger.error("Planner deployment failed or A2A URL not found, exiting.")
        return

    # Deploy Social
    social_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_social_agent,
        agent_human_name="Social Agent",
        staging_bucket_uri=STAGING_BUCKET,
        display_name_for_re="social_agent_prod" # Specific RE display name
    )
    social_a2a_url = None
    if social_deployed_agent and hasattr(social_deployed_agent, 'gca_resource') and social_deployed_agent.gca_resource:
        social_a2a_url = social_deployed_agent.gca_resource.public_endpoint_uri
    elif social_deployed_agent and hasattr(social_deployed_agent, 'uri'):
        social_a2a_url = social_deployed_agent.uri

    if social_a2a_url:
        logger.info(f"Social A2A URL: {social_a2a_url}")
    else:
        logger.error("Social deployment failed or A2A URL not found. Continuing with Orchestrator if possible, but workflow may be impacted.")
        # Decide if this is fatal. For now, let's try to deploy orchestrator.

    # Deploy Orchestrator
    # Orchestrator's deploy_orchestrator_agent will internally get AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES from env.
    # We need to set that env var if it's not already. For this example, assume it's set.
    # Example: os.environ["AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES"] = f"{planner_a2a_url},{social_a2a_url}"
    # This should be done *before* calling deploy_orchestrator_agent if it reads it on init.
    # The OrchestratorServiceAgent reads it at construction time.
    
    # Construct remote agent addresses for Orchestrator. Filter out None URLs.
    remote_addresses_list = []
    if planner_a2a_url:
        remote_addresses_list.append(planner_a2a_url)
    if social_a2a_url: # Only add if social deployment was successful
        remote_addresses_list.append(social_a2a_url)

    if not remote_addresses_list:
        logger.warning("No planner or social agent URLs available for Orchestrator. Orchestrator may not function correctly.")
        # Set to empty string or handle as error depending on requirements
        os.environ["AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES"] = ""
    else:
        os.environ["AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES"] = ",".join(remote_addresses_list)
    logger.info(f"Setting AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES to: {os.environ['AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES']}")

    orchestrator_deployed_agent = deploy_agent_with_forced_update(
        deploy_func=deploy_orchestrator_agent,
        agent_human_name="Orchestrator Agent",
        staging_bucket_uri=STAGING_BUCKET,
        display_name_for_re="orchestrator_agent_prod" # Specific RE display name
    )
    orchestrator_a2a_url = None
    if orchestrator_deployed_agent and hasattr(orchestrator_deployed_agent, 'gca_resource') and orchestrator_deployed_agent.gca_resource:
        orchestrator_a2a_url = orchestrator_deployed_agent.gca_resource.public_endpoint_uri
    elif orchestrator_deployed_agent and hasattr(orchestrator_deployed_agent, 'uri'):
        orchestrator_a2a_url = orchestrator_deployed_agent.uri

    if orchestrator_a2a_url:
        logger.info(f"Orchestrator A2A URL: {orchestrator_a2a_url}")
    else:
        logger.error("Orchestrator deployment failed or A2A URL not found, exiting as workflow agent depends on it.")
        return

    # Initialize Workflow Agent (Client-side)
    # This assumes InstavibeWorkflowAgent is a client and doesn't need its own RE deployment here.
    # If it *was* an RE, its deploy function would be called similarly to others,
    # and its A2A URL might be configured via env vars for other agents if needed.
    # For now, it's a client that will use the obtained URLs.

    # Configure InstavibeWorkflowAgent with the deployed A2A URLs
    # This could be done by setting environment variables before InstavibeWorkflowAgent is initialized,
    # if it reads them from os.environ. Or by passing them to its constructor.
    # The example workflow_agent.query below suggests it takes the URL per call.

    os.environ["PLANNER_AGENT_A2A_URL"] = planner_a2a_url or "" # Ensure empty string if None
    os.environ["ORCHESTRATE_AGENT_A2A_URL"] = orchestrator_a2a_url or "" # Ensure empty string if None
    # Social URL might also be needed by workflow or orchestrator directly
    os.environ["SOCIAL_AGENT_A2A_URL"] = social_a2a_url or ""

    logger.info(f"Environment variables for InstavibeWorkflowAgent:")
    logger.info(f"  PLANNER_AGENT_A2A_URL={os.environ['PLANNER_AGENT_A2A_URL']}")
    logger.info(f"  ORCHESTRATE_AGENT_A2A_URL={os.environ['ORCHESTRATE_AGENT_A2A_URL']}")
    logger.info(f"  SOCIAL_AGENT_A2A_URL={os.environ['SOCIAL_AGENT_A2A_URL']}")

    # Assuming InstavibeWorkflowAgent picks these up from env vars upon instantiation
    workflow_agent = InstavibeWorkflowAgent()
    logger.info("InstavibeWorkflowAgent client initialized.")

    # Example of A2A call from WorkflowAgent to Planner (if planner_a2a_url is available)
    if planner_a2a_url:
        logger.info(f"--- Making example A2A call from Workflow to Planner ({planner_a2a_url}) ---")
        try:
            # The InstavibeWorkflowAgent's query method needs to be defined.
            # Let's assume it's an async method that takes the target agent's A2A URL and a payload.
            # And that it uses httpx.AsyncClient internally.
            # This is a conceptual example; the actual method signature might differ.
            example_payload = {"task": "create a plan for a beach vacation"}
            response = await workflow_agent.a2a_query( # Assuming method is a2a_query
                target_agent_a2a_url=planner_a2a_url,
                payload=example_payload,
                timeout_seconds=60
            )
            if response:
                logger.info(f"Response from Planner via WorkflowAgent: {response}")
            else:
                logger.error(f"Failed to get a valid response from Planner via WorkflowAgent or response was empty.")
        except Exception as e:
            logger.error(f"Error during example A2A call from Workflow to Planner: {e}", exc_info=True)
    else:
        logger.warning("Planner A2A URL not available, skipping example A2A call from Workflow to Planner.")

    # Example of A2A call from WorkflowAgent to Orchestrator
    if orchestrator_a2a_url:
        logger.info(f"--- Making example A2A call from Workflow to Orchestrator ({orchestrator_a2a_url}) ---")
        try:
            example_payload_orchestrator = {"request_type": "execute_plan", "plan_details": "..."}
            response_orc = await workflow_agent.a2a_query(
                target_agent_a2a_url=orchestrator_a2a_url,
                payload=example_payload_orchestrator,
                timeout_seconds=120
            )
            if response_orc:
                logger.info(f"Response from Orchestrator via WorkflowAgent: {response_orc}")
            else:
                logger.error(f"Failed to get a valid response from Orchestrator via WorkflowAgent or response was empty.")
        except Exception as e:
            logger.error(f"Error during example A2A call from Workflow to Orchestrator: {e}", exc_info=True)
    else:
        logger.warning("Orchestrator A2A URL not available, skipping example A2A call from Workflow to Orchestrator.")

    logger.info("--- All Deployments and Example A2A Calls Attempted ---")


if __name__ == "__main__":
    # Ensure COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, COMMON_VERTEX_STAGING_BUCKET are set in environment
    if not all(os.getenv(var) for var in ["COMMON_GOOGLE_CLOUD_PROJECT", "COMMON_GOOGLE_CLOUD_LOCATION", "COMMON_VERTEX_STAGING_BUCKET"]):
        logger.error("One or more required environment variables (COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, COMMON_VERTEX_STAGING_BUCKET) are not set.")
        logger.error("Please set them before running deploy_all.py.")
    else:
        asyncio.run(main())