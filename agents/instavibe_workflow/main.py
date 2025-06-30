# Instavibe Workflow Agent - main.py
import os
import json
import logging
from flask import Flask, request, jsonify
from google.cloud import aiplatform as vertexai # For ADK session service
from vertexai.preview import reasoning_engines # For ADK session service & init

from .agent import InstavibeWorkflowAgent # Import the agent logic

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global instances for the agent and session service
# These will be initialized once when the Flask app starts (or on first request if using app context)
workflow_agent_instance = None
session_service_instance = None
project_id_global = None
location_global = None
agent_engine_id_global = None # This is the ID of THIS deployed agent engine

def init_globals():
    global workflow_agent_instance, session_service_instance
    global project_id_global, location_global, agent_engine_id_global

    if workflow_agent_instance and session_service_instance:
        logger.info("Globals already initialized.")
        return True

    try:
        project_id_global = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location_global = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION") # Matching env var
        # This is the ID of the Agent Engine where *this* workflow agent is deployed.
        # It's needed for creating ADK sessions for this agent's own operations.
        agent_engine_id_global = os.environ.get("SELF_AGENT_ENGINE_ID") # Or a more suitable name like WORKFLOW_AGENT_ENGINE_ID

        if not all([project_id_global, location_global, agent_engine_id_global]):
            logger.error("Missing critical environment variables: GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, SELF_AGENT_ENGINE_ID")
            return False

        # Initialize Vertex AI SDK for ADK components (like SessionService)
        # The agent.py also initializes, but this is for the session service specifically.
        # Ensure this doesn't conflict if agent.py's init is slightly different.
        # ADK's reasoning_engines.init is generally idempotent or handles re-init.
        reasoning_engines.init(project=project_id_global, location=location_global)
        logger.info(f"Vertex AI SDK initialized by main.py for project {project_id_global} in {location_global}")

        # Initialize the workflow agent (which internally initializes its own LLM model)
        workflow_agent_instance = InstavibeWorkflowAgent() # Model name is defaulted in agent.py
        if not workflow_agent_instance.model: # Check if model init failed in agent
             logger.error("Failed to initialize model within InstavibeWorkflowAgent. Agent will not function.")
             workflow_agent_instance = None # Prevent use
             return False


        # Initialize the ADK Session Service
        # This service is used by this workflow agent to create sessions for its own execution.
        session_service_instance = reasoning_engines.SessionServiceClient() # Correct way to get client for session ops

        logger.info("Workflow agent and session service initialized successfully.")
        return True

    except Exception as e:
        logger.error(f"Error during global initialization: {e}", exc_info=True)
        workflow_agent_instance = None # Ensure it's None on failure
        session_service_instance = None
        return False

# Call init_globals() when the application starts.
# For Gunicorn, this will run in each worker process.
if not init_globals():
    logger.critical("Application failed to initialize global components. It may not function correctly.")

@app.route("/", methods=["GET"])
def health_check():
    if workflow_agent_instance and session_service_instance:
        return jsonify({"status": "healthy", "message": "InstavibeWorkflowAgent is running."}), 200
    else:
        return jsonify({"status": "unhealthy", "message": "InstavibeWorkflowAgent failed to initialize."}), 500

@app.route("/execute", methods=["POST"])
def execute_workflow():
    if not workflow_agent_instance or not session_service_instance:
        logger.error("Agent or session service not initialized. Cannot execute workflow.")
        return jsonify({"success": False, "error": "Workflow agent service not properly initialized."}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided in request."}), 400

        user_id = data.get("user_id")
        action = data.get("action")
        payload = data.get("payload")

        if not all([user_id, action, payload]):
            return jsonify({"success": False, "error": "Missing 'user_id', 'action', or 'payload' in request."}), 400

        logger.info(f"Received /execute request for user_id: {user_id}, action: {action}")

        # Create an ADK session for this specific workflow execution
        # The `app_name` here refers to the resource name of THIS deployed reasoning engine.
        # This is crucial for ADK session management.
        session_resource_name = f"projects/{project_id_global}/locations/{location_global}/reasoningEngines/{agent_engine_id_global}"

        # Correctly creating a session using the client
        # The ADK's `reasoning_engines.create_session` is a higher-level utility.
        # If using SessionServiceClient directly, the call is different.
        # Let's use the higher-level `reasoning_engines.create_session` for simplicity if available,
        # otherwise, we'd need to construct the request for `session_service_instance.create_reasoning_engine_session`.
        # For ADK >1.0, `reasoning_engines.create_session` is the way.

        created_session = None
        try:
            # This creates a session for the current reasoning engine specified by agent_engine_id_global
            created_session = reasoning_engines.create_session(
                reasoning_engine=session_resource_name, # Resource name of this agent
                user_id=str(user_id) # Ensure user_id is a string
            )
            # `created_session` is an object, typically `reasoning_engines.Session`
            # which has attributes like `name` (the full session resource name)
            session_id_for_agent_run = created_session.name # The full session resource name
            logger.info(f"ADK session created for user '{user_id}': {session_id_for_agent_run}")
        except Exception as e_sess:
            logger.error(f"Failed to create ADK session for user '{user_id}': {e_sess}", exc_info=True)
            return jsonify({"success": False, "error": f"Failed to create ADK session: {str(e_sess)}"}), 500

        # Run the workflow agent's logic, passing the created session's resource name
        # The `InstavibeWorkflowAgent.run` method expects the session object or its name
        # For now, our agent.py doesn't deeply use the session object with direct model calls,
        # but it's good practice to pass it.
        result = workflow_agent_instance.run(action=action, payload=payload, adk_session=created_session)

        # Session deletion: For stateless HTTP calls, sessions might be short-lived.
        # ADK Agent Engine might handle cleanup, or you might need explicit deletion
        # if sessions are long-lived or resource-intensive.
        # For now, we assume default ADK behavior or short-lived sessions.
        # If explicit deletion is needed:
        # try:
        #     reasoning_engines.delete_session(name=session_id_for_agent_run)
        #     logger.info(f"ADK session deleted: {session_id_for_agent_run}")
        # except Exception as e_del_sess:
        #     logger.warning(f"Failed to delete ADK session {session_id_for_agent_run}: {e_del_sess}", exc_info=True)


        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error during /execute: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == "__main__":
    # This is for local development.
    # In Cloud Run (or similar), Gunicorn will be used as specified in Dockerfile.
    # Ensure required environment variables are set for local testing:
    # GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, SELF_AGENT_ENGINE_ID
    logger.info("Starting Flask app for local development.")
    if not os.environ.get("SELF_AGENT_ENGINE_ID"):
        logger.warning("Warning: SELF_AGENT_ENGINE_ID not set. Session creation might fail if this agent is called by itself.")
        # Set a dummy one for local tests if needed, but real calls require a deployed ID.
        os.environ["SELF_AGENT_ENGINE_ID"] = "local-dev-workflow-agent"

    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
