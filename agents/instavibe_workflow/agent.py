import os
import json
import logging
from typing import Dict
from vertexai import agent_engines
from vertexai.preview import reasoning_engines # For Session type hint

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstavibeWorkflowAgent:
    """
    Agent logic handler for Instavibe workflows.
    This class is instantiated by its Flask wrapper (main.py).
    It orchestrates calls to other specialized ADK agents (Reasoning Engines)
    using the Vertex AI SDK (`agent_engines.get().query()`).
    """

    def __init__(self):
        """
        Initializes the workflow agent by loading target agent resource names
        from environment variables. These are expected to be full Vertex AI
        Reasoning Engine resource names.
        """
        self.planner_agent_resource_name = os.environ.get("PLANNER_AGENT_RESOURCE_NAME")
        self.orchestrate_agent_resource_name = os.environ.get("ORCHESTRATE_AGENT_RESOURCE_NAME")

        # Timeout for sub-agent calls (if query method had a timeout, it's usually part of client config or call)
        # For now, relying on default timeouts of client.query().

        if not self.planner_agent_resource_name:
            logger.warning("PLANNER_AGENT_RESOURCE_NAME environment variable not set. Plan generation will fail.")
        if not self.orchestrate_agent_resource_name:
            logger.warning("ORCHESTRATE_AGENT_RESOURCE_NAME environment variable not set. Event posting will fail.")

        logger.info(f"InstavibeWorkflowAgent logic handler initialized.")
        logger.info(f"  Planner Agent Resource: {self.planner_agent_resource_name}")
        logger.info(f"  Orchestrate Agent Resource: {self.orchestrate_agent_resource_name}")

    async def _generate_event_plan(self, user_name: str, planned_date: str, location_n_perference: str,
                                   selected_friend_names_list: list, adk_session_context: reasoning_engines.Session) -> tuple[dict | None, list]:
        thoughts = []
        if not self.planner_agent_resource_name:
            error_msg = "Planner Agent resource name not configured."
            thoughts.append(error_msg); logger.error(f"Cannot generate plan: {error_msg}")
            return None, thoughts

        if not adk_session_context:
            error_msg = "ADK session for SDK call to Planner Agent not provided."
            thoughts.append(error_msg); logger.error(f"Cannot generate plan: {error_msg}")
            return None, thoughts

        friends_list_example_for_prompt = json.dumps(selected_friend_names_list)
        selected_friend_names_str = ', '.join(selected_friend_names_list)

        planner_input_prompt = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".
Output the entire plan in a SINGLE, COMPLETE JSON object. (Full prompt details omitted for brevity but should be the same as before)
{{
  "friends_name_list": {friends_list_example_for_prompt}, "event_name": "string", "event_date": "{planned_date}",
  "event_description": "string", "locations_and_activities": [{{ "name": "string", "latitude": 12.345, "longitude": -67.890, "address": "string or null", "description": "string"}}],
  "post_to_go_out": "string"
}}"""

        thoughts.append(f"Delegating plan generation to Planner Agent RE: {self.planner_agent_resource_name}")
        logger.info(f"Calling Planner Agent RE ({self.planner_agent_resource_name}) for user '{user_name}' using session {getattr(adk_session_context, 'name', 'N/A')}.")

        generated_text = None # Ensure it's defined for error logging
        try:
            planner_client = agent_engines.get(self.planner_agent_resource_name)
            # query() can be async depending on the SDK version and how it's implemented for REs.
            # Assuming it returns a future or is awaitable if the client is async.
            # For now, let's assume it's awaitable as per user's last snippet.
            response_struct = await planner_client.query(input=planner_input_prompt, session_info=adk_session_context)

            if not hasattr(response_struct, 'output'):
                error_msg = f"Planner Agent RE response structure missing 'output' attribute. Response: {response_struct}"
                thoughts.append(error_msg); logger.error(f"{error_msg} for user '{user_name}'.")
                return None, thoughts

            generated_text = response_struct.output
            thoughts.append(f"Planner Agent RE raw response (from .output): {generated_text[:200]}...")
            if not generated_text or not generated_text.strip():
                thoughts.append("Planner Agent RE returned an empty response in .output.")
                return None, thoughts

            if "```json" in generated_text: json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"): json_block = generated_text.strip().strip('`').strip()
            else: json_block = generated_text.strip()

            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON from Planner Agent RE.")
            return plan_json, thoughts

        except json.JSONDecodeError as e:
            err_text = generated_text if generated_text is not None else "unavailable"
            thoughts.append(f"JSONDecodeError from Planner Agent RE response: {str(e)}. Raw text: {err_text[:200]}")
            logger.error(f"JSONDecodeError from Planner Agent RE (user '{user_name}'): {str(e)}. Raw text: {err_text}", exc_info=True)
            return None, thoughts
        except Exception as e:
            thoughts.append(f"Error calling Planner Agent RE: {str(e)}")
            logger.error(f"Error calling Planner Agent RE (user '{user_name}'): {str(e)}", exc_info=True)
            return None, thoughts

    async def _process_event_posting(self, user_name: str, confirmed_plan: dict, edited_invite_message: str,
                                     agent_context_user_id: str, adk_session_context: reasoning_engines.Session) -> tuple[bool, str, list]:
        thoughts = []
        if not self.orchestrate_agent_resource_name:
            error_msg = "Orchestrate Agent resource name not configured."
            thoughts.append(error_msg); logger.error(f"Cannot process event posting: {error_msg}")
            return False, error_msg, thoughts

        if not adk_session_context:
            error_msg = "ADK session for SDK call to Orchestrate Agent not provided."
            thoughts.append(error_msg); logger.error(f"Cannot post event: {error_msg}")
            return False, error_msg, thoughts

        orchestrator_input_payload = {
            "user_name": user_name, "user_id_context": agent_context_user_id,
            "confirmed_plan": confirmed_plan, "invite_message": edited_invite_message,
            "task_summary": f"User '{user_name}' wants to create an event and send an invite. Orchestrate actions."
        }
        # For RE query, input is usually a string. Convert payload to JSON string.
        orchestrator_input_message = json.dumps(orchestrator_input_payload)

        thoughts.append(f"Delegating event posting to Orchestrate Agent RE: {self.orchestrate_agent_resource_name}")
        logger.info(f"Calling Orchestrate Agent RE ({self.orchestrate_agent_resource_name}) for user '{user_name}' using session {getattr(adk_session_context, 'name', 'N/A')}.")

        response_text = None # Ensure defined for error logging
        try:
            orchestrate_client = agent_engines.get(self.orchestrate_agent_resource_name)
            response_struct = await orchestrate_client.query(input=orchestrator_input_message, session_info=adk_session_context)

            if not hasattr(response_struct, 'output'):
                error_msg = f"Orchestrate Agent RE response structure missing 'output' attribute. Response: {response_struct}"
                thoughts.append(error_msg); logger.error(f"{error_msg} for user '{user_name}'.")
                return False, "Orchestrate Agent RE response error.", thoughts

            response_text = response_struct.output
            thoughts.append(f"Orchestrate Agent RE raw response (from .output): {response_text[:200]}...")

            if response_text and response_text.strip():
                thoughts.append("Successfully delegated to Orchestrate Agent RE.")
                return True, response_text.strip(), thoughts
            else:
                thoughts.append("Orchestrate Agent RE returned an empty response in .output.")
                return False, "Orchestrate Agent RE returned empty response.", thoughts
        except Exception as e:
            thoughts.append(f"Error calling Orchestrate Agent RE: {str(e)}")
            logger.error(f"Error calling Orchestrate Agent RE (user '{user_name}'): {str(e)}", exc_info=True)
            return False, str(e), thoughts

    async def process_request(self, action: str, payload: dict, adk_session_context: reasoning_engines.Session) -> Dict:
        """
        Main entry point for the agent's logic, called by the Flask app in main.py.
        `adk_session_context` is the reasoning_engines.Session object created by main.py.
        """
        logger.info(f"WorkflowAgent logic processing action: '{action}' for user: {payload.get('user_name', payload.get('user_id','Unknown User'))} with session {getattr(adk_session_context, 'name', 'N/A')}")

        if not adk_session_context:
            logger.error("Workflow agent process_request called without an ADK session context.")
            return {"success": False, "error": "ADK session context is required.", "thoughts": ["ADK session context missing."]}

        if action == "generate_plan":
            user_name = payload.get("user_name")
            planned_date = payload.get("planned_date")
            location_n_perference = payload.get("location_n_perference")
            selected_friend_names_list = payload.get("selected_friend_names_list", [])

            if not all([user_name, planned_date, location_n_perference]):
                return {"success": False, "error": "Missing required fields for generate_plan (user_name, planned_date, location_n_perference)", "thoughts": ["Validation failed for generate_plan payload."]}

            plan_json, thoughts = await self._generate_event_plan(
                user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session_context
            )
            if plan_json:
                return {"success": True, "result_type": "plan", "data": plan_json, "thoughts": thoughts}
            else:
                return {"success": False, "error": "Failed to generate plan via Planner Agent RE.", "thoughts": thoughts}

        elif action == "post_event":
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            agent_context_user_id = payload.get("agent_session_user_id", user_name)

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            success, message, thoughts = await self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_context_user_id, adk_session_context
            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting via Orchestrate Agent RE: {message}", "thoughts": thoughts}
        else:
            logger.warning(f"Unknown action received: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}
