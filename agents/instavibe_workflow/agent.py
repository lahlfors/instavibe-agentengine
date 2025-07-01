import os
import json
import logging
import requests # For making HTTP A2A calls
from typing import Dict
from google.adk.tools import ToolContext # For type hinting
from vertexai.preview import reasoning_engines # For Session type hint

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstavibeWorkflowAgent:
    """
    Agent logic handler for Instavibe workflows.
    This class is instantiated by the deployment script (deploy_all.py) and wrapped in a FunctionTool.
    It orchestrates calls to other specialized agents via their A2A HTTP endpoints.
    """

    def __init__(self,
                 planner_a2a_endpoint_uri: str,
                 event_posting_a2a_endpoint_uri: str,
                 project_id: str, # For context if needed, not directly used by this class now
                 location: str,   # For context if needed
                 gcs_bucket_name: str # For context if needed
                ):
        """
        Initializes the workflow agent with necessary A2A endpoint URLs and context.
        """
        self.planner_a2a_url = planner_a2a_endpoint_uri
        self.orchestrate_a2a_url = event_posting_a2a_endpoint_uri
        self.project_id = project_id
        self.location = location
        self.gcs_bucket_name = gcs_bucket_name # Example, not used in current A2A calls

        self.a2a_timeout = 120

        if not self.planner_a2a_url:
            logger.warning("Planner A2A Endpoint URI not provided during initialization. Plan generation will fail.")
        if not self.orchestrate_a2a_url:
            logger.warning("Orchestrate A2A Endpoint URI not provided during initialization. Event posting will fail.")

        logger.info(f"InstavibeWorkflowAgent logic handler initialized.")
        logger.info(f"  Planner A2A URL: {self.planner_a2a_url}")
        logger.info(f"  Orchestrate A2A URL: {self.orchestrate_a2a_url}")
        logger.info(f"  Project ID: {self.project_id}, Location: {self.location}, GCS: {self.gcs_bucket_name}")


    def _make_a2a_call(self, target_url: str, input_payload: dict, adk_session: reasoning_engines.Session, operation_name: str):
        """
        Helper function to make an A2A HTTP call.
        `adk_session` is the reasoning_engines.Session object from the ToolContext.
        """
        thoughts = []
        if not target_url:
            error_msg = f"{operation_name}: Target A2A URL is not configured."
            thoughts.append(error_msg)
            logger.error(error_msg)
            return None, thoughts

        if not adk_session or not hasattr(adk_session, 'name') or not hasattr(adk_session, 'user_id'):
            error_msg = f"{operation_name}: Invalid or incomplete ADK session object provided for A2A call."
            thoughts.append(error_msg)
            logger.error(error_msg)
            return None, thoughts

        headers = {"Content-Type": "application/json"}

        a2a_request_body = {
            "input": input_payload,
            "session_info": {
                "session_id": adk_session.name,
                "user_id": adk_session.user_id
            }
        }

        thoughts.append(f"{operation_name}: Sending A2A request to {target_url} with session {adk_session.name}.")
        logger.info(f"{operation_name}: Calling A2A endpoint {target_url} with session {adk_session.name}.")
        logger.debug(f"A2A request body for {target_url}: {json.dumps(a2a_request_body, indent=2)}")

        try:
            response = requests.post(target_url, headers=headers, json=a2a_request_body, timeout=self.a2a_timeout)
            response.raise_for_status()
            response_json = response.json()
            thoughts.append(f"{operation_name}: Received A2A response. Status: {response.status_code}.")
            logger.info(f"{operation_name}: A2A call to {target_url} successful. Status: {response.status_code}.")
            agent_output = response_json.get("output", response_json.get("result", response_json))
            if agent_output is None:
                 thoughts.append(f"{operation_name}: A2A response JSON missing 'output' or 'result' field. Full response: {response_json}")
            return agent_output, thoughts
        except requests.exceptions.HTTPError as http_err:
            # ... (error handling as before) ...
            error_content = http_err.response.text if http_err.response else str(http_err)
            thoughts.append(f"{operation_name}: HTTP error calling A2A endpoint {target_url}: {str(http_err)}. Response: {error_content[:200]}")
            logger.error(f"{operation_name}: HTTP error for {target_url}: {http_err}. Response: {error_content}", exc_info=True)
            return None, thoughts
        except Exception as e: # Broader catch for other request issues or JSON issues
            thoughts.append(f"{operation_name}: Error during A2A call to {target_url}: {str(e)}")
            logger.error(f"{operation_name}: Error for {target_url}: {e}", exc_info=True)
            return None, thoughts


    def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session: reasoning_engines.Session):
        thoughts = []
        if not self.planner_a2a_url: # Check if URL was initialized
            error_msg = "Planner Agent A2A URL not configured."
            thoughts.append(error_msg); logger.error(f"Cannot generate plan: {error_msg}")
            return None, thoughts

        friends_list_example_for_prompt = json.dumps(selected_friend_names_list)
        selected_friend_names_str = ', '.join(selected_friend_names_list)

        planner_input_payload = { # This is the "input" for the _make_a2a_call
            "user_name": user_name,
            "planned_date": planned_date,
            "location_n_perference": location_n_perference,
            "selected_friend_names_list": selected_friend_names_list,
            # The detailed prompt is now part of the payload sent to the planner agent
            "prompt_override": f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".
Output the entire plan in a SINGLE, COMPLETE JSON object. (Full prompt details omitted for brevity but should be the same as before)
{{
  "friends_name_list": {friends_list_example_for_prompt}, "event_name": "string", "event_date": "{planned_date}",
  "event_description": "string", "locations_and_activities": [{{ "name": "string", "latitude": 12.345, "longitude": -67.890, "address": "string or null", "description": "string"}}],
  "post_to_go_out": "string"
}}"""
        }

        generated_text, a2a_thoughts = self._make_a2a_call(self.planner_a2a_url, planner_input_payload, adk_session, "PlannerCall")
        thoughts.extend(a2a_thoughts)

        if generated_text is None: return None, thoughts
        if not isinstance(generated_text, str) or not generated_text.strip():
            thoughts.append(f"Planner Agent (A2A) returned empty or non-string response: {generated_text}")
            return None, thoughts
        try:
            # ... (JSON parsing logic as before) ...
            if "```json" in generated_text: json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"): json_block = generated_text.strip().strip('`').strip()
            else: json_block = generated_text.strip()
            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON from Planner Agent (A2A).")
            return plan_json, thoughts
        except Exception as e_parse:
            thoughts.append(f"Error parsing Planner Agent A2A response: {str(e_parse)}. Raw text: {generated_text[:200]}")
            logger.error(f"Error parsing Planner Agent A2A response (user '{user_name}'): {str(e_parse)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts

    def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_context_user_id, adk_session: reasoning_engines.Session):
        thoughts = []
        if not self.orchestrate_a2a_url: # Check if URL was initialized
            error_msg = "Orchestrate Agent A2A URL not configured."
            thoughts.append(error_msg); logger.error(f"Cannot process event posting: {error_msg}")
            return False, error_msg, thoughts

        orchestrator_input_payload = { # This is the "input" for the _make_a2a_call
            "user_name": user_name, "user_id_context": agent_context_user_id,
            "confirmed_plan": confirmed_plan, "invite_message": edited_invite_message,
            "task_summary": f"User '{user_name}' wants to create an event and send an invite. Orchestrate actions."
        }
        response_content, a2a_thoughts = self._make_a2a_call(self.orchestrate_a2a_url, orchestrator_input_payload, adk_session, "OrchestratorCall")
        thoughts.extend(a2a_thoughts)

        if response_content is None: return False, "Failed to communicate with Orchestrate Agent.", thoughts

        if isinstance(response_content, str) and response_content.strip():
            thoughts.append("Successfully delegated to Orchestrate Agent (A2A).")
            return True, response_content.strip(), thoughts
        elif isinstance(response_content, dict) and response_content.get("message"):
            thoughts.append(f"Orchestrate Agent (A2A) response: {response_content.get('message')}")
            return response_content.get("success", True), response_content.get("message"), thoughts
        else:
            thoughts.append(f"Orchestrate Agent (A2A) returned an empty or unexpected response: {response_content}")
            return False, "Orchestrate Agent (A2A) returned an unexpected response.", thoughts

    def __call__(self, action: str, payload: Dict, adk_session: reasoning_engines.Session, tool_context: ToolContext) -> Dict:
        """
        Main entry point for the InstavibeWorkflowAgent when called as a tool.
        `adk_session` and `tool_context` are provided by the ADK Runner.
        We primarily use `adk_session` to pass to sub-agent A2A calls.
        """
        logger.info(f"InstavibeWorkflowAgent Tool __call__ invoked. Action: '{action}', User (from payload): {payload.get('user_name', payload.get('user_id'))}, ADK Session: {getattr(adk_session, 'name', 'N/A')}")

        # Log details from tool_context if useful for debugging
        # logger.debug(f"ToolContext session_id: {tool_context.session_id()}, user_id: {tool_context.user_id()}")

        if not adk_session: # Should be provided by ADK runner when tool is called
            logger.error("Tool __call__ error: ADK session not provided via ToolContext or arguments.")
            return {"success": False, "error": "ADK session context is required.", "thoughts": ["ADK session missing in tool call."]}

        if action == "generate_plan": # This should match "generate_plan" from introvertally.py
            user_name = payload.get("user_name")
            planned_date = payload.get("planned_date")
            location_n_perference = payload.get("location_n_perference")
            selected_friend_names_list = payload.get("selected_friend_names_list", [])

            if not all([user_name, planned_date, location_n_perference]):
                return {"success": False, "error": "Missing required fields for generate_plan", "thoughts": ["Validation failed for generate_plan payload."]}

            plan_json, thoughts = self._generate_event_plan(
                user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session
            )
            if plan_json:
                return {"success": True, "result_type": "plan", "data": plan_json, "thoughts": thoughts}
            else:
                return {"success": False, "error": "Failed to generate plan via Planner Agent (A2A).", "thoughts": thoughts}

        elif action == "post_event": # This should match "post_event" from introvertally.py
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            agent_context_user_id = payload.get("agent_session_user_id", user_name)

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            success, message, thoughts = self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_context_user_id, adk_session
            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting via Orchestrate Agent (A2A): {message}", "thoughts": thoughts}
        else:
            logger.warning(f"Unknown action received in __call__: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}
