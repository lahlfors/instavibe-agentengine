import os
import json
import logging
from flask import Flask, request, jsonify
from vertexai.preview import reasoning_engines

# Import the agent logic class
from .agent import InstavibeWorkflowAgent

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize the workflow agent logic handler
# This instance will be shared across requests in the same worker.
# It reads its own config (like sub-agent resource names) from env vars at init.
try:
    # These env vars are expected to be set in the deployed container environment
    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
    LOCATION = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION")
    # SELF_AGENT_ENGINE_ID is the ID of this deployed workflow agent itself
    SELF_AGENT_ENGINE_ID = os.environ.get("SELF_AGENT_ENGINE_ID")

    if not all([PROJECT_ID, LOCATION, SELF_AGENT_ENGINE_ID]):
        logger.error("Critical environment variables (GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, SELF_AGENT_ENGINE_ID) not set for workflow agent main.py.")
        # Allow app to start but agent calls might fail if session creation relies on these.
        # InstavibeWorkflowAgent __init__ also reads its specific needs.

    # Initialize Vertex AI SDK for ADK session service within this Flask app.
    # The global init in deploy_all.py is for the deployment script's context.
    # The deployed agent needs its own init if it uses SDK features like session creation.
    reasoning_engines.init(project=PROJECT_ID, location=LOCATION)
    logger.info(f"Workflow Agent (main.py): Vertex AI SDK initialized for project {PROJECT_ID} in {LOCATION}")

    workflow_agent_logic_handler = InstavibeWorkflowAgent()
except Exception as e:
    logger.error(f"Failed to initialize InstavibeWorkflowAgent handler: {e}", exc_info=True)
    workflow_agent_logic_handler = None

@app.route("/", methods=["GET"])
def health_check():
    if workflow_agent_logic_handler:
        return jsonify({"status": "healthy", "message": "InstavibeWorkflowAgent (Flask) is running."}), 200
    else:
        return jsonify({"status": "unhealthy", "message": "InstavibeWorkflowAgent (Flask) failed to initialize."}), 500

@app.route("/execute", methods=["POST"])
async def execute_workflow(): # Made async to align with agent logic
    if not workflow_agent_logic_handler:
        logger.error("Workflow agent logic handler not initialized. Cannot execute workflow.")
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

        logger.info(f"Flask: Received /execute request for user_id: {user_id}, action: {action}")

        # Create an ADK session for this specific workflow execution.
        # The SELF_AGENT_ENGINE_ID environment variable should be set to this agent's own deployed ID.
        current_session = None
        if not SELF_AGENT_ENGINE_ID:
            logger.error("SELF_AGENT_ENGINE_ID not set, cannot create ADK session for request.")
            return jsonify({"success": False, "error": "Workflow agent internal configuration error (missing self ID)."}), 500

        session_resource_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{SELF_AGENT_ENGINE_ID}"

        try:
            logger.info(f"Flask: Attempting to create ADK session. User: {user_id}, RE: {session_resource_name}")
            current_session = reasoning_engines.create_session(
                reasoning_engine=session_resource_name,
                user_id=str(user_id)
            )
            logger.info(f"Flask: ADK session created: {getattr(current_session, 'name', 'N/A')}")
        except Exception as e_sess:
            logger.error(f"Flask: Failed to create ADK session for user '{user_id}': {e_sess}", exc_info=True)
            return jsonify({"success": False, "error": f"Failed to create ADK session: {str(e_sess)}"}), 500

        # Call the agent's logic, passing the created session
        # The InstavibeWorkflowAgent.process_request is now async
        result = await workflow_agent_logic_handler.process_request(
            action=action,
            payload=payload,
            adk_session_context=current_session # Pass the session object
        )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error during /execute: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if current_session and hasattr(current_session, 'name'):
            try:
                logger.info(f"Flask: Attempting to delete ADK session: {current_session.name}")
                reasoning_engines.delete_session(name=current_session.name)
                logger.info(f"Flask: Deleted ADK session: {current_session.name}")
            except Exception as e_del_sess:
                logger.warning(f"Flask: Failed to delete ADK session {current_session.name}: {e_del_sess}", exc_info=True)

if __name__ == "__main__":
    # For local development. Gunicorn is used in Dockerfile for deployment.
    # Ensure necessary environment variables are set locally for testing.
    # GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, SELF_AGENT_ENGINE_ID,
    # PLANNER_AGENT_RESOURCE_NAME, ORCHESTRATE_AGENT_RESOURCE_NAME
    if not workflow_agent_logic_handler:
        print("CRITICAL: InstavibeWorkflowAgent handler failed to initialize. Flask app cannot run effectively.")
    else:
        print("Starting Flask app for local development (InstavibeWorkflowAgent)...")
        app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8081))) # Use a different port for local dev
