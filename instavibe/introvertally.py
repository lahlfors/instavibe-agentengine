import os
import pprint # Retained for potential debugging if needed
import json
import logging
import requests # For calling the workflow agent
from google.oauth2 import service_account # For service account credentials
from google.auth import default as default_credentials # For default credentials
from google.auth.transport.requests import Request as GoogleAuthRequest # For refreshing credentials

# Initialize logger
logger = logging.getLogger(__name__)

logger.critical("DIAGNOSTIC_LOG: Running REFACTORED introvertally.py - V2_HTTP_CLIENT_VERSION")

# Global variable for workflow agent URL
WORKFLOW_AGENT_URL = os.getenv("WORKFLOW_AGENT_URL")
if not WORKFLOW_AGENT_URL:
    logger.error("WORKFLOW_AGENT_URL environment variable not set. Calls to workflow agent will fail.")

# --- ADK related global initialization removed ---
# global adk_app (removed)
# init_agent_engine function (removed)
# COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION based init (removed)


def get_id_token(audience_url):
    """
    Generates an OIDC ID token for calling a Cloud Run service (or other GCP service requiring ID token).
    Uses Application Default Credentials.
    """
    try:
        creds, project = default_credentials()

        # If running with a service account, it might already be the right identity.
        # For Cloud Run to Cloud Run, or local to Cloud Run (with gcloud auth),
        # an ID token is usually needed.

        # Check if credentials need refreshing
        if hasattr(creds, 'token') and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            logger.info("Credentials refreshed.")

        # For generating an ID token for a specific audience (the target service URL)
        # This is the standard way to authenticate to Cloud Run services.
        auth_req = GoogleAuthRequest()
        creds.refresh(auth_req) # Ensure credentials are fresh before requesting ID token

        # The google.oauth2.id_token.fetch_id_token method is simpler if available with creds
        # but google-auth's id_token module is often used.
        # Let's try a robust way:
        from google.oauth2 import id_token as id_token_utils

        # If creds already have service_account_email, it indicates it might be a service account.
        # For user accounts (local dev), this might not be present, but ADC should handle it.
        id_token = id_token_utils.fetch_id_token(auth_req, audience_url)
        logger.info(f"Successfully fetched ID token for audience: {audience_url}")
        return id_token
    except Exception as e:
        logger.error(f"Failed to get ID token for audience {audience_url}: {e}", exc_info=True)
        raise Exception(f"Error getting ID token: {e}")


def call_workflow_agent(user_id, action, payload):
    """
    Calls the external workflow agent via HTTP.
    Handles authentication using ID tokens.
    """
    if not WORKFLOW_AGENT_URL:
        logger.error("WORKFLOW_AGENT_URL is not set. Cannot call workflow agent.")
        # Yield an error structure compatible with the original streaming logic
        yield {"type": "error", "data": {"message": "Workflow agent URL not configured.", "raw_output": ""}}
        return

    full_target_url = f"{WORKFLOW_AGENT_URL.rstrip('/')}/execute"

    thoughts_for_caller = [] # To somewhat mimic the old thought streaming

    try:
        id_token = get_id_token(WORKFLOW_AGENT_URL) # Audience is the base URL of the workflow agent
    except Exception as e_token:
        logger.error(f"Failed to obtain ID token: {e_token}")
        thoughts_for_caller.append(f"Authentication error: Failed to get ID token: {str(e_token)}")
        yield {"type": "error", "data": {"message": f"Authentication error: {str(e_token)}", "raw_output": ""}}
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {id_token}",
    }
    request_body = {
        "user_id": str(user_id), # Ensure user_id is a string
        "action": action,
        "payload": payload,
    }

    thoughts_for_caller.append(f"Calling workflow agent at {full_target_url} with action '{action}' for user '{user_id}'.")
    logger.info(f"Calling workflow agent: URL='{full_target_url}', User='{user_id}', Action='{action}'")
    logger.debug(f"Request body for workflow agent: {json.dumps(request_body, indent=2)}")

    try:
        response = requests.post(
            full_target_url,
            headers=headers,
            json=request_body, # Using json parameter for requests library
            timeout=120 # Increased timeout for potentially long agent calls (e.g., 2 minutes)
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        agent_response = response.json()
        logger.info(f"Received response from workflow agent for action '{action}', user '{user_id}'. Success: {agent_response.get('success')}")
        logger.debug(f"Workflow agent raw response: {json.dumps(agent_response, indent=2)}")

        # Stream back thoughts from the workflow agent if any
        if "thoughts" in agent_response and isinstance(agent_response["thoughts"], list):
            for thought in agent_response["thoughts"]:
                yield {"type": "thought", "data": f"WorkflowAgent: {thought}"}

        if agent_response.get("success"):
            yield {"type": "workflow_success", "action": action, "data": agent_response}
        else:
            error_message = agent_response.get("error", "Unknown error from workflow agent.")
            thoughts_for_caller.append(f"Workflow agent reported failure for action '{action}': {error_message}")
            yield {"type": "error", "data": {"message": error_message, "raw_output": json.dumps(agent_response)}}

    except requests.exceptions.HTTPError as http_err:
        error_content = http_err.response.text
        logger.error(f"HTTP error calling workflow agent: {http_err}. Response: {error_content}", exc_info=True)
        thoughts_for_caller.append(f"HTTP error calling workflow agent: {str(http_err)}. Response: {error_content}")
        yield {"type": "error", "data": {"message": f"HTTP error: {str(http_err)}", "raw_output": error_content}}
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request exception calling workflow agent: {req_err}", exc_info=True)
        thoughts_for_caller.append(f"Request exception: {str(req_err)}")
        yield {"type": "error", "data": {"message": f"Request exception: {str(req_err)}", "raw_output": ""}}
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to decode JSON response from workflow agent: {json_err}. Response text: {response.text if 'response' in locals() else 'N/A'}", exc_info=True)
        thoughts_for_caller.append(f"JSON decode error from workflow agent: {str(json_err)}")
        yield {"type": "error", "data": {"message": f"JSON decode error: {str(json_err)}", "raw_output": response.text if 'response' in locals() else 'N/A'}}

    # Yield any accumulated thoughts from this calling function
    for thought in thoughts_for_caller:
        # Check if this thought was already yielded by error cases
        if not any(err_item['data']['message'] in thought for err_item in previous_yields_if_error(inspect.currentframe())): # pseudo-code
             yield {"type": "thought", "data": thought}


def previous_yields_if_error(frame): # Helper for thought de-duplication (conceptual)
    # This is a placeholder for a more complex logic if needed to avoid duplicate thoughts on errors.
    # In a real scenario, you'd manage yielded messages' state.
    return []


def call_agent_for_plan(user_name, planned_date, location_n_perference, selected_friend_names_list):
    user_id = str(user_name) # Consistent user_id handling

    yield {"type": "thought", "data": f"--- IntrovertAlly Agent Call Initiated (via Workflow Agent) ---"}
    yield {"type": "thought", "data": f"User ID for this run: {user_id}"}
    yield {"type": "thought", "data": f"User: {user_name}"}
    yield {"type": "thought", "data": f"Planned Date: {planned_date}"}
    yield {"type": "thought", "data": f"Location/Preference: {location_n_perference}"}
    yield {"type": "thought", "data": f"Selected Friends: {', '.join(selected_friend_names_list)}"}

    payload = {
        "user_name": user_name,
        "planned_date": planned_date,
        "location_n_perference": location_n_perference,
        "selected_friend_names_list": selected_friend_names_list,
    }

    final_result_json = None
    has_errored = False

    for event in call_workflow_agent(user_id, "generate_plan", payload):
        yield event # Stream thoughts and errors directly from the workflow call
        if event["type"] == "workflow_success" and event["action"] == "generate_plan":
            if event["data"].get("success"):
                final_result_json = event["data"].get("data") # The plan JSON is in "data.data"
                if not final_result_json: # Check if plan_json itself is None/empty
                    yield {"type": "thought", "data": "Workflow agent succeeded but returned no plan data."}
                    yield {"type": "error", "data": {"message": "Workflow agent returned no plan data.", "raw_output": json.dumps(event["data"])}}
                    has_errored = True
                # else: # Plan data is present
                #    yield {"type": "thought", "data": f"Plan data received: {json.dumps(final_result_json)[:100]}..."}

            else: # workflow_success was true, but data.success was false
                error_msg = event["data"].get("error", "Plan generation failed in workflow.")
                yield {"type": "thought", "data": f"Plan generation failed: {error_msg}"}
                yield {"type": "error", "data": {"message": error_msg, "raw_output": json.dumps(event["data"])}}
                has_errored = True
            break # Stop processing events for this call once we get workflow_success
        elif event["type"] == "error":
            has_errored = True
            # Error already yielded by call_workflow_agent
            break


    if not has_errored and final_result_json:
        yield {"type": "plan_complete", "data": final_result_json}
    elif not has_errored and not final_result_json: # Succeeded but no plan
        # This case should ideally be caught by the 'no plan data' check above
        if not any(item['type'] == 'error' for item in previous_yields_if_error(None)): # Avoid double error if already sent
            yield {"type": "error", "data": {"message": "Plan generation completed but no plan was returned.", "raw_output": ""}}
    # If has_errored, the error was already yielded.


def post_plan_event(user_name, confirmed_plan, edited_invite_message, agent_session_user_id):
    adk_user_id = str(agent_session_user_id if agent_session_user_id else user_name)

    yield {"type": "thought", "data": f"--- Post Plan Event Agent Call Initiated (via Workflow Agent) ---"}
    yield {"type": "thought", "data": f"Agent Session User ID for this run: {adk_user_id}"}
    yield {"type": "thought", "data": f"User performing action: {user_name}"}
    yield {"type": "thought", "data": f"Received Confirmed Plan (event_name): {confirmed_plan.get('event_name', 'N/A')}"}
    yield {"type": "thought", "data": f"Received Invite Message: {edited_invite_message[:100]}..."}

    payload = {
        "user_name": user_name,
        "confirmed_plan": confirmed_plan,
        "edited_invite_message": edited_invite_message,
        "agent_session_user_id": adk_user_id, # Pass this for context within the workflow if needed
    }

    posting_finished_successfully = False
    has_errored = False

    for event in call_workflow_agent(adk_user_id, "post_event", payload):
        yield event # Stream thoughts and errors
        if event["type"] == "workflow_success" and event["action"] == "post_event":
            if event["data"].get("success"):
                posting_finished_successfully = True
                # The message from the workflow can be logged as a thought or part of the success
                workflow_message = event["data"].get("message", "Event posting instructions processed by workflow agent.")
                yield {"type": "thought", "data": f"Workflow Agent Confirmation: {workflow_message}"}
            else:
                error_msg = event["data"].get("error", "Event posting failed in workflow.")
                yield {"type": "thought", "data": f"Event posting failed: {error_msg}"}
                yield {"type": "error", "data": {"message": error_msg, "raw_output": json.dumps(event["data"])}}
                has_errored = True
            break # Stop processing events for this call
        elif event["type"] == "error":
            has_errored = True
            # Error already yielded
            break

    if not has_errored and posting_finished_successfully:
        yield {"type": "posting_finished", "data": {"success": True, "message": "Workflow agent has processed the event and post creation instructions."}}
    elif not has_errored and not posting_finished_successfully: # Succeeded but no confirmation
        if not any(item['type'] == 'error' for item in previous_yields_if_error(None)):
             yield {"type": "error", "data": {"message": "Event posting completed but no confirmation was received.", "raw_output": ""}}
    # If has_errored, error already yielded.
