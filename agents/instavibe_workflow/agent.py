# Instavibe Workflow Agent - agent.py
import os
import json
import logging
from vertexai.preview import reasoning_engines
from vertexai.preview.reasoning_engines import Agent as AdkAgentExecutor # To execute other ADK Agents

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Vertex AI SDK initialization (project, location) should be done by main.py
# before this class is instantiated, or ensure environment variables are set for it.

class InstavibeWorkflowAgent:
    """
    Agent to handle Instavibe workflows like plan generation and event posting
    by orchestrating other specialized ADK agents.
    """

    def __init__(self):
        self.planner_agent_resource_name = os.environ.get("AGENTS_PLANNER_RESOURCE_NAME")
        self.orchestrate_agent_resource_name = os.environ.get("AGENTS_ORCHESTRATE_RESOURCE_NAME")
        # Add other target agent resource names here if needed

        if not self.planner_agent_resource_name:
            logger.warning("AGENTS_PLANNER_RESOURCE_NAME environment variable not set. Plan generation will fail.")
        if not self.orchestrate_agent_resource_name:
            logger.warning("AGENTS_ORCHESTRATE_RESOURCE_NAME environment variable not set. Event posting will fail.")

        logger.info(f"InstavibeWorkflowAgent initialized.")
        logger.info(f"  Planner Agent Target: {self.planner_agent_resource_name}")
        logger.info(f"  Orchestrate Agent Target: {self.orchestrate_agent_resource_name}")


    def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session):
        """
        Generates an event plan by calling the dedicated Planner Agent.
        `adk_session` is the session object for the current workflow agent's execution.
        """
        thoughts = []
        if not self.planner_agent_resource_name:
            thoughts.append("Planner Agent resource name not configured.")
            logger.error("Cannot generate plan: Planner Agent resource name not set.")
            return None, thoughts

        # Prepare input for the Planner Agent
        # This needs to match what the target Planner Agent expects.
        # Assuming it takes a structured input or a detailed prompt.
        # For this example, let's create a detailed prompt similar to the original direct LLM call.
        friends_list_example_for_prompt = json.dumps(selected_friend_names_list)
        selected_friend_names_str = ', '.join(selected_friend_names_list)

        planner_input_prompt = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".

Analyze friend interests (if possible, use Instavibe profiles or summarized interests) to create a tailored plan. Ensure the plan includes the date {planned_date}.

Output the entire plan in a SINGLE, COMPLETE JSON object with the following structure. **CRITICAL: The FINAL RESPONSE MUST BE ONLY THIS JSON. If any fields are missing or unavailable, INVENT them appropriately to complete the JSON structure. Do not return any conversational text or explanations. Just the raw, valid JSON.**

{{
  "friends_name_list": {friends_list_example_for_prompt},
  "event_name": "string",
  "event_date": "{planned_date}",
  "event_description": "string",
  "locations_and_activities": [
    {{
      "name": "string",
      "latitude": 12.345,
      "longitude": -67.890,
      "address": "string or null",
      "description": "string"
    }}
  ],
  "post_to_go_out": "string"
}}
"""
        thoughts.append(f"Delegating plan generation to Planner Agent: {self.planner_agent_resource_name}")
        logger.info(f"Calling Planner Agent ({self.planner_agent_resource_name}) for user '{user_name}'.")

        try:
            # Create an executor for the target Planner Agent
            planner_executor = AdkAgentExecutor(agent=self.planner_agent_resource_name)

            # Call the Planner Agent.
            # The `input` parameter name might vary based on how the target agent is defined.
            # Common names are 'input', 'message', 'prompt', 'query'. Assuming 'message' or 'input'.
            # ADK Agent.run() typically expects `input` or specific args defined by the agent.
            # Let's assume the target agent takes a generic 'input' string.
            response = planner_executor.run(input=planner_input_prompt, session=adk_session)

            # The response from an ADK agent's run() method is typically the final string output.
            # If it's structured (JSON), it should be returned as a string to be parsed.
            generated_text = response # Assuming response is the direct string output.

            thoughts.append(f"Planner Agent raw response: {generated_text[:200]}...")
            logger.info(f"Planner Agent raw response (user '{user_name}'): {generated_text[:200]}...")

            if not generated_text or not generated_text.strip():
                thoughts.append("Planner Agent returned an empty response.")
                return None, thoughts

            # Attempt to parse the JSON from the response
            if "```json" in generated_text:
                json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                thoughts.append("Extracted JSON from markdown block (Planner Agent).")
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"):
                json_block = generated_text.strip().strip('`').strip()
                thoughts.append("Extracted JSON from simple backticks (Planner Agent).")
            else:
                json_block = generated_text.strip()

            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON from Planner Agent.")
            return plan_json, thoughts

        except json.JSONDecodeError as e:
            thoughts.append(f"JSONDecodeError from Planner Agent response: {str(e)}. Raw text: {generated_text}")
            logger.error(f"JSONDecodeError from Planner Agent (user '{user_name}'): {str(e)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts
        except Exception as e:
            thoughts.append(f"Error calling Planner Agent: {str(e)}")
            logger.error(f"Error calling Planner Agent (user '{user_name}'): {str(e)}", exc_info=True)
            return None, thoughts

    def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session):
        """
        Processes event posting by calling the dedicated Orchestrate Agent.
        `adk_session` is the session object for the current workflow agent's execution.
        """
        thoughts = []
        if not self.orchestrate_agent_resource_name:
            thoughts.append("Orchestrate Agent resource name not configured.")
            logger.error("Cannot process event posting: Orchestrate Agent resource name not set.")
            return False, "Orchestrate Agent not configured.", thoughts

        # Prepare input for the Orchestrate Agent.
        # This needs to match what the target Orchestrate Agent expects.
        # The original prompt for the LLM was quite detailed.
        # We might pass this as a structured input or a natural language instruction.
        orchestrator_input_details = {
            "user_name": user_name,
            "user_id_context": agent_session_user_id,
            "confirmed_plan": confirmed_plan,
            "invite_message": edited_invite_message,
            "task_summary": f"User '{user_name}' wants to create an event based on the confirmed plan and send an invite."
            # The Orchestrate Agent would then use its own logic/LLM to break this down
            # and call other agents like Social Agent or Platform MCP tools.
        }
        # For simplicity, let's convert this to a JSON string input, assuming the orchestrator can parse it
        # or takes a general message. A more robust way would be if the orchestrator agent defines specific input fields.
        orchestrator_input_message = json.dumps(orchestrator_input_details)


        thoughts.append(f"Delegating event posting to Orchestrate Agent: {self.orchestrate_agent_resource_name}")
        logger.info(f"Calling Orchestrate Agent ({self.orchestrate_agent_resource_name}) for user '{user_name}'.")

        try:
            orchestrate_executor = AdkAgentExecutor(agent=self.orchestrate_agent_resource_name)

            # Assuming Orchestrate Agent takes 'input' or 'message'
            response_text = orchestrate_executor.run(input=orchestrator_input_message, session=adk_session)

            thoughts.append(f"Orchestrate Agent raw response: {response_text[:200]}...")
            logger.info(f"Orchestrate Agent raw response (user '{user_name}'): {response_text[:200]}...")

            if response_text and response_text.strip():
                thoughts.append("Successfully delegated to Orchestrate Agent.")
                # The response_text itself is the confirmation/narration from the Orchestrate Agent
                return True, response_text.strip(), thoughts
            else:
                thoughts.append("Orchestrate Agent returned an empty response.")
                return False, "Orchestrate Agent returned empty response.", thoughts

        except Exception as e:
            thoughts.append(f"Error calling Orchestrate Agent: {str(e)}")
            logger.error(f"Error calling Orchestrate Agent (user '{user_name}'): {str(e)}", exc_info=True)
            return False, str(e), thoughts

    def run(self, action: str, payload: dict, adk_session=None):
        """
        Main execution method for the agent.
        Determines the action and calls the appropriate internal method.
        `adk_session` is the ADK Session object created by main.py for this workflow's execution.
        """
        logger.info(f"Workflow agent received action: '{action}' for user: {payload.get('user_name', payload.get('user_id','Unknown User'))}")

        if not adk_session:
            logger.error("Workflow agent run called without an ADK session.")
            return {"success": False, "error": "ADK session is required for workflow agent execution.", "thoughts": ["ADK session missing."]}

        if action == "generate_plan":
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
                return {"success": False, "error": "Failed to generate plan via Planner Agent.", "thoughts": thoughts}

        elif action == "post_event":
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            agent_session_user_id = payload.get("agent_session_user_id", user_name)

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            success, message, thoughts = self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session
            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting via Orchestrate Agent: {message}", "thoughts": thoughts}

        else:
            logger.warning(f"Unknown action received: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}
