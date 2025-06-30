import os
import json
import logging
from vertexai import agent_engines # For getting and querying deployed agents
from vertexai.preview import reasoning_engines # For Session type hint if needed, and create_session/delete_session

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstavibeWorkflowAgent:
    """
    Agent logic handler for Instavibe workflows.
    This class contains methods that are called by a tool defined in the
    ADK Agent deployed via `agent_engines.create`.
    It orchestrates calls to other specialized ADK agents.
    """

    def __init__(self):
        """
        Initializes the workflow agent by loading target agent resource names
        from environment variables. These variables must be set in the
        execution environment of the deployed Agent Engine.
        """
        self.planner_agent_resource_name = os.environ.get("AGENTS_PLANNER_RESOURCE_NAME")
        self.orchestrate_agent_resource_name = os.environ.get("AGENTS_ORCHESTRATE_RESOURCE_NAME")

        # These are needed if the agent's main tool itself needs to create sessions for sub-calls
        # (as per the current design of main_workflow_tool in deploy_all.py's plan)
        self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION")
        self.self_agent_engine_id = os.environ.get("SELF_AGENT_ENGINE_ID")


        if not self.planner_agent_resource_name:
            logger.warning("AGENTS_PLANNER_RESOURCE_NAME environment variable not set. Plan generation will fail.")
        if not self.orchestrate_agent_resource_name:
            logger.warning("AGENTS_ORCHESTRATE_RESOURCE_NAME environment variable not set. Event posting will fail.")

        if not all([self.project_id, self.location, self.self_agent_engine_id]):
            logger.warning("One or more of GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION, SELF_AGENT_ENGINE_ID are not set. Session creation for sub-calls by tools might fail.")

        logger.info(f"InstavibeWorkflowAgent logic handler initialized.")
        logger.info(f"  Planner Agent Target: {self.planner_agent_resource_name}")
        logger.info(f"  Orchestrate Agent Target: {self.orchestrate_agent_resource_name}")
        logger.info(f"  Context for sub-call sessions: Project={self.project_id}, Location={self.location}, SelfID={self.self_agent_engine_id}")


    def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session_for_sub_call):
        """
        Generates an event plan by calling the dedicated Planner Agent.
        `adk_session_for_sub_call` is the session object to be used for calling the sub-agent.
        """
        thoughts = []
        if not self.planner_agent_resource_name:
            thoughts.append("Planner Agent resource name not configured.")
            logger.error("Cannot generate plan: Planner Agent resource name not set.")
            return None, thoughts

        if not adk_session_for_sub_call:
            thoughts.append("ADK session for sub-call to Planner Agent not provided.")
            logger.error("Cannot generate plan: ADK session for sub-call missing.")
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
        thoughts.append(f"Delegating plan generation to Planner Agent: {self.planner_agent_resource_name}")
        logger.info(f"Calling Planner Agent ({self.planner_agent_resource_name}) for user '{user_name}' using session {getattr(adk_session_for_sub_call, 'name', 'N/A')}.")

        try:
            planner_client = agent_engines.get(self.planner_agent_resource_name)
            response_struct = planner_client.query(input=planner_input_prompt, session_info=adk_session_for_sub_call)

            if not hasattr(response_struct, 'output'):
                error_msg = f"Planner Agent response structure missing 'output' attribute. Response: {response_struct}"
                thoughts.append(error_msg)
                logger.error(f"{error_msg} for user '{user_name}'.")
                return None, thoughts

            generated_text = response_struct.output
            thoughts.append(f"Planner Agent raw response (from .output): {generated_text[:200]}...")
            if not generated_text or not generated_text.strip():
                thoughts.append("Planner Agent returned an empty response in .output.")
                return None, thoughts

            if "```json" in generated_text:
                json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"):
                json_block = generated_text.strip().strip('`').strip()
            else:
                json_block = generated_text.strip()

            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON from Planner Agent.")
            return plan_json, thoughts

        except json.JSONDecodeError as e:
            err_text = getattr(e, 'doc', generated_text if 'generated_text' in locals() else "unavailable")
            thoughts.append(f"JSONDecodeError from Planner Agent response: {str(e)}. Raw text: {err_text[:200]}")
            logger.error(f"JSONDecodeError from Planner Agent (user '{user_name}'): {str(e)}. Raw text: {err_text}", exc_info=True)
            return None, thoughts
        except Exception as e:
            thoughts.append(f"Error calling Planner Agent: {str(e)}")
            logger.error(f"Error calling Planner Agent (user '{user_name}'): {str(e)}", exc_info=True)
            return None, thoughts

    def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session_for_sub_call):
        thoughts = []
        if not self.orchestrate_agent_resource_name:
            thoughts.append("Orchestrate Agent resource name not configured.")
            logger.error("Cannot process event posting: Orchestrate Agent resource name not set.")
            return False, "Orchestrate Agent not configured.", thoughts

        if not adk_session_for_sub_call:
            thoughts.append("ADK session for sub-call to Orchestrate Agent not provided.")
            logger.error("Cannot post event: ADK session for sub-call missing.")
            return False, "ADK session for sub-call missing.", thoughts

        orchestrator_input_details = {
            "user_name": user_name, "user_id_context": agent_session_user_id,
            "confirmed_plan": confirmed_plan, "invite_message": edited_invite_message,
            "task_summary": f"User '{user_name}' wants to create an event and send an invite."
        }
        orchestrator_input_message = json.dumps(orchestrator_input_details)

        thoughts.append(f"Delegating event posting to Orchestrate Agent: {self.orchestrate_agent_resource_name}")
        logger.info(f"Calling Orchestrate Agent ({self.orchestrate_agent_resource_name}) for user '{user_name}' using session {getattr(adk_session_for_sub_call, 'name', 'N/A')}.")

        try:
            orchestrate_client = agent_engines.get(self.orchestrate_agent_resource_name)
            response_struct = orchestrate_client.query(input=orchestrator_input_message, session_info=adk_session_for_sub_call)

            if not hasattr(response_struct, 'output'):
                error_msg = f"Orchestrate Agent response structure missing 'output' attribute. Response: {response_struct}"
                thoughts.append(error_msg)
                logger.error(f"{error_msg} for user '{user_name}'.")
                return False, "Orchestrate Agent response error.", thoughts

            response_text = response_struct.output
            thoughts.append(f"Orchestrate Agent raw response (from .output): {response_text[:200]}...")
            if response_text and response_text.strip():
                thoughts.append("Successfully delegated to Orchestrate Agent.")
                return True, response_text.strip(), thoughts
            else:
                thoughts.append("Orchestrate Agent returned an empty response in .output.")
                return False, "Orchestrate Agent returned empty response.", thoughts
        except Exception as e:
            thoughts.append(f"Error calling Orchestrate Agent: {str(e)}")
            logger.error(f"Error calling Orchestrate Agent (user '{user_name}'): {str(e)}", exc_info=True)
            return False, str(e), thoughts

    def process_request(self, action: str, payload: dict, adk_session_for_sub_calls=None):
        """
        Main entry point for the agent's logic, called by the ADK Agent tool.
        `adk_session_for_sub_calls` is created by the tool wrapper and passed here.
        """
        logger.info(f"WorkflowAgent logic processing action: '{action}' for user: {payload.get('user_name', payload.get('user_id','Unknown User'))}")

        if not adk_session_for_sub_calls: # This session is now managed by the calling tool
            logger.error("Workflow agent process_request called without an ADK session for sub-calls.")
            return {"success": False, "error": "ADK session for sub-calls is required.", "thoughts": ["ADK session for sub-calls missing."]}

        if action == "generate_plan":
            user_name = payload.get("user_name")
            planned_date = payload.get("planned_date")
            location_n_perference = payload.get("location_n_perference")
            selected_friend_names_list = payload.get("selected_friend_names_list", [])

            if not all([user_name, planned_date, location_n_perference]):
                return {"success": False, "error": "Missing required fields for generate_plan", "thoughts": ["Validation failed for generate_plan payload."]}

            plan_json, thoughts = self._generate_event_plan(
                user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session_for_sub_calls
            )
            if plan_json:
                return {"success": True, "result_type": "plan", "data": plan_json, "thoughts": thoughts}
            else:
                return {"success": False, "error": "Failed to generate plan via Planner Agent.", "thoughts": thoughts}

        elif action == "post_event":
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            agent_session_user_id = payload.get("agent_session_user_id", user_name)

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            success, message, thoughts = self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session_for_sub_calls
            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting via Orchestrate Agent: {message}", "thoughts": thoughts}
        else:
            logger.warning(f"Unknown action received: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}

# Example of how this class might be used by the tool in deploy_all.py:
# instavibe_workflow_logic = InstavibeWorkflowAgent()
# result = instavibe_workflow_logic.process_request(action, payload, session_for_sub_calls)
