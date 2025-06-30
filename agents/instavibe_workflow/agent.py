import os
import json
import logging
import requests # For making HTTP A2A calls
from vertexai.preview import reasoning_engines # For Session type hint, create_session, delete_session

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstavibeWorkflowAgent:
    """
    Agent logic handler for Instavibe workflows.
    This class orchestrates calls to other specialized agents via their A2A HTTP endpoints.
    It's designed to be used as a tool within an ADK Agent deployed via `agent_engines.create(agent=...)`.
    """

    def __init__(self):
        self.planner_a2a_url = os.environ.get("PLANNER_A2A_ENDPOINT_URL")
        self.orchestrate_a2a_url = os.environ.get("ORCHESTRATE_A2A_ENDPOINT_URL")

        # Timeout for A2A HTTP calls in seconds
        self.a2a_timeout = 120

        if not self.planner_a2a_url:
            logger.warning("PLANNER_A2A_ENDPOINT_URL environment variable not set. Plan generation will fail.")
        if not self.orchestrate_a2a_url:
            logger.warning("ORCHESTRATE_A2A_ENDPOINT_URL environment variable not set. Event posting will fail.")

        logger.info(f"InstavibeWorkflowAgent logic handler initialized.")
        logger.info(f"  Planner A2A URL: {self.planner_a2a_url}")
        logger.info(f"  Orchestrate A2A URL: {self.orchestrate_a2a_url}")

    def _make_a2a_call(self, target_url: str, input_payload: dict, adk_session_context, operation_name: str):
        """
        Helper function to make an A2A HTTP call.
        `adk_session_context` is the reasoning_engines.Session object.
        """
        thoughts = []
        if not target_url:
            error_msg = f"{operation_name}: Target A2A URL is not configured."
            thoughts.append(error_msg)
            logger.error(error_msg)
            return None, thoughts

        headers = {"Content-Type": "application/json"}

        # Construct A2A payload. This is a common pattern; actual structure might vary.
        # Assuming sub-agents expect an 'input' field and session details.
        a2a_request_body = {
            "input": input_payload, # The specific input for the target agent
            "session_info": { # Pass session context if sub-agents are session-aware
                "session_id": getattr(adk_session_context, 'name', None), # Full session resource name
                "user_id": getattr(adk_session_context, 'user_id', None) # User ID from the session
            }
            # Add other A2A protocol specific fields if necessary
        }

        session_id_for_log = getattr(adk_session_context, 'name', 'N/A')
        thoughts.append(f"{operation_name}: Sending A2A request to {target_url} with session {session_id_for_log}.")
        logger.info(f"{operation_name}: Calling A2A endpoint {target_url} with session {session_id_for_log}.")
        logger.debug(f"A2A request body for {target_url}: {json.dumps(a2a_request_body, indent=2)}")

        try:
            response = requests.post(target_url, headers=headers, json=a2a_request_body, timeout=self.a2a_timeout)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            response_json = response.json()
            thoughts.append(f"{operation_name}: Received A2A response. Status: {response.status_code}.")
            logger.info(f"{operation_name}: A2A call to {target_url} successful. Status: {response.status_code}.")
            logger.debug(f"A2A response JSON from {target_url}: {json.dumps(response_json, indent=2)}")

            # Assuming the sub-agent's actual output is in a field like 'output' or 'result'
            # This needs to match the actual A2A response schema of Planner/Orchestrator.
            # If the entire JSON is the output, then just `return response_json, thoughts`.
            agent_output = response_json.get("output", response_json.get("result", response_json))
            if agent_output is None:
                 thoughts.append(f"{operation_name}: A2A response JSON missing 'output' or 'result' field. Full response: {response_json}")

            return agent_output, thoughts

        except requests.exceptions.HTTPError as http_err:
            error_content = http_err.response.text if http_err.response else str(http_err)
            thoughts.append(f"{operation_name}: HTTP error calling A2A endpoint {target_url}: {str(http_err)}. Response: {error_content[:200]}")
            logger.error(f"{operation_name}: HTTP error for {target_url}: {http_err}. Response: {error_content}", exc_info=True)
            return None, thoughts
        except requests.exceptions.RequestException as req_err:
            thoughts.append(f"{operation_name}: Request exception calling A2A endpoint {target_url}: {str(req_err)}")
            logger.error(f"{operation_name}: Request exception for {target_url}: {req_err}", exc_info=True)
            return None, thoughts
        except json.JSONDecodeError as json_err:
            raw_text = response.text if 'response' in locals() else "N/A"
            thoughts.append(f"{operation_name}: JSON decode error from A2A endpoint {target_url}: {str(json_err)}. Response text: {raw_text[:200]}")
            logger.error(f"{operation_name}: JSON decode error for {target_url}: {json_err}. Raw text: {raw_text}", exc_info=True)
            return None, thoughts
        except Exception as e:
            thoughts.append(f"{operation_name}: Unexpected error during A2A call to {target_url}: {str(e)}")
            logger.error(f"{operation_name}: Unexpected error for {target_url}: {e}", exc_info=True)
            return None, thoughts


    def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session_context):
        thoughts = []
        if not self.planner_a2a_url:
            error_msg = "Planner Agent A2A URL not configured."
            thoughts.append(error_msg)
            logger.error(f"Cannot generate plan: {error_msg}")
            return None, thoughts

        if not adk_session_context:
            error_msg = "ADK session for A2A call to Planner Agent not provided."
            thoughts.append(error_msg)
            logger.error(f"Cannot generate plan: {error_msg}")
            return None, thoughts

        friends_list_example_for_prompt = json.dumps(selected_friend_names_list)
        selected_friend_names_str = ', '.join(selected_friend_names_list)

        # This is the input specific to the Planner agent
        planner_input_payload = {
            "user_name": user_name, # Assuming Planner needs these fields directly
            "planned_date": planned_date,
            "location_n_perference": location_n_perference,
            "selected_friend_names_list": selected_friend_names_list,
            "prompt_override": f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".
Output the entire plan in a SINGLE, COMPLETE JSON object. (Full prompt details omitted for brevity but should be the same as before)
{{
  "friends_name_list": {friends_list_example_for_prompt}, "event_name": "string", "event_date": "{planned_date}",
  "event_description": "string", "locations_and_activities": [{{ "name": "string", "latitude": 12.345, "longitude": -67.890, "address": "string or null", "description": "string"}}],
  "post_to_go_out": "string"
}}"""
        }

        generated_text, a2a_thoughts = self._make_a2a_call(self.planner_a2a_url, planner_input_payload, adk_session_context, "PlannerCall")
        thoughts.extend(a2a_thoughts)

        if generated_text is None: # Error occurred during A2A call
            return None, thoughts

        # If the A2A call returns the direct text output (JSON string)
        if not isinstance(generated_text, str) or not generated_text.strip():
            thoughts.append(f"Planner Agent (A2A) returned empty or non-string response: {generated_text}")
            return None, thoughts

        try:
            if "```json" in generated_text:
                json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"):
                json_block = generated_text.strip().strip('`').strip()
            else:
                json_block = generated_text.strip()

            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON from Planner Agent (A2A).")
            return plan_json, thoughts
        except json.JSONDecodeError as e:
            thoughts.append(f"JSONDecodeError from Planner Agent A2A response: {str(e)}. Raw text: {generated_text[:200]}")
            logger.error(f"JSONDecodeError from Planner Agent A2A (user '{user_name}'): {str(e)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts
        except Exception as e_parse: # Catch other errors during parsing
            thoughts.append(f"Error parsing Planner Agent A2A response: {str(e_parse)}. Raw text: {generated_text[:200]}")
            logger.error(f"Error parsing Planner Agent A2A response (user '{user_name}'): {str(e_parse)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts


    def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session_context):
        thoughts = []
        if not self.orchestrate_a2a_url:
            error_msg = "Orchestrate Agent A2A URL not configured."
            thoughts.append(error_msg)
            logger.error(f"Cannot process event posting: {error_msg}")
            return False, error_msg, thoughts

        if not adk_session_context:
            error_msg = "ADK session for A2A call to Orchestrate Agent not provided."
            thoughts.append(error_msg)
            logger.error(f"Cannot post event: {error_msg}")
            return False, error_msg, thoughts

        # This is the input specific to the Orchestrate agent
        orchestrator_input_payload = {
            "user_name": user_name,
            "user_id_context": agent_session_user_id,
            "confirmed_plan": confirmed_plan,
            "invite_message": edited_invite_message,
            "task_summary": f"User '{user_name}' wants to create an event based on the confirmed plan and send an invite. Orchestrate the necessary actions."
            # The Orchestrate agent would then internally decide to call Social, Platform MCP, etc.
        }

        response_content, a2a_thoughts = self._make_a2a_call(self.orchestrate_a2a_url, orchestrator_input_payload, adk_session_context, "OrchestratorCall")
        thoughts.extend(a2a_thoughts)

        if response_content is None: # Error occurred during A2A call
            return False, "Failed to communicate with Orchestrate Agent.", thoughts

        # Assuming response_content from orchestrator is a string confirmation/narration
        # or a JSON dict with a status/message. For now, treat string as success message.
        if isinstance(response_content, str) and response_content.strip():
            thoughts.append("Successfully delegated to Orchestrate Agent (A2A).")
            return True, response_content.strip(), thoughts
        elif isinstance(response_content, dict) and response_content.get("message"): # If it returns a structured message
            thoughts.append(f"Orchestrate Agent (A2A) response: {response_content.get('message')}")
            return response_content.get("success", True), response_content.get("message"), thoughts
        else:
            thoughts.append(f"Orchestrate Agent (A2A) returned an empty or unexpected response: {response_content}")
            return False, "Orchestrate Agent (A2A) returned an unexpected response.", thoughts


    def process_request(self, action: str, payload: dict, adk_session_context=None):
        """
        Main entry point for the agent's logic, called by the ADK Agent tool.
        `adk_session_context` is the reasoning_engines.Session object obtained from ToolContext
        by the tool wrapper in deploy_all.py.
        """
        logger.info(f"WorkflowAgent logic processing action: '{action}' for user: {payload.get('user_name', payload.get('user_id','Unknown User'))}")

        if not adk_session_context:
            logger.error("Workflow agent process_request called without an ADK session context.")
            return {"success": False, "error": "ADK session context is required for workflow agent execution.", "thoughts": ["ADK session context missing."]}

        if action == "generate_plan": # Matches the action string from introvertally.py
            user_name = payload.get("user_name")
            planned_date = payload.get("planned_date")
            location_n_perference = payload.get("location_n_perference")
            selected_friend_names_list = payload.get("selected_friend_names_list", [])

            if not all([user_name, planned_date, location_n_perference]): # selected_friend_names_list can be empty
                return {"success": False, "error": "Missing required fields for generate_plan (user_name, planned_date, location_n_perference)", "thoughts": ["Validation failed for generate_plan payload."]}

            plan_json, thoughts = self._generate_event_plan(
                user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session_context
            )
            if plan_json:
                return {"success": True, "result_type": "plan", "data": plan_json, "thoughts": thoughts}
            else:
                return {"success": False, "error": "Failed to generate plan via Planner Agent (A2A).", "thoughts": thoughts}

        elif action == "post_event": # Matches the action string from introvertally.py
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            # 'agent_session_user_id' from payload is the user_id for context, used for logging or if sub-agents need it
            agent_context_user_id = payload.get("agent_session_user_id", user_name)

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            success, message, thoughts = self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_context_user_id, adk_session_context
            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting via Orchestrate Agent (A2A): {message}", "thoughts": thoughts}
        else:
            logger.warning(f"Unknown action received: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}
