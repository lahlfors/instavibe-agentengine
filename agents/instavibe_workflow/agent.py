import os
import json
import logging
import asyncio # Added for async operations
import httpx   # Added for fetching agent cards

# from vertexai.preview import reasoning_engines # Old client, to be replaced by A2AClient
from python_a2a.client import A2AClient # Corrected import
# Using specific model paths based on recent feedback
from python_a2a.models.agent import AgentCard as A2AAgentCard
from python_a2a.models.message import Message as A2AMessage
from python_a2a.models.message import Part as A2APart


# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Vertex AI SDK initialization is handled by main.py for this agent's own ADK session.

class InstavibeWorkflowAgent:
    """
    Agent to handle Instavibe workflows like plan generation and event posting
    by orchestrating other specialized ADK agents using a2a-python.
    """

    def __init__(self):
        # These will now store the A2A server URLs for the target agents
        self.planner_agent_a2a_url = os.environ.get("PLANNER_AGENT_A2A_URL")
        self.orchestrate_agent_a2a_url = os.environ.get("ORCHESTRATE_AGENT_A2A_URL")

        self.a2a_client = A2AClient()
        self.http_client = httpx.AsyncClient() # For fetching agent cards, if needed

        if not self.planner_agent_a2a_url:
            logger.warning("PLANNER_AGENT_A2A_URL environment variable not set. Plan generation will fail.")
        if not self.orchestrate_agent_a2a_url:
            logger.warning("ORCHESTRATE_AGENT_A2A_URL environment variable not set. Event posting will fail.")

        logger.info("InstavibeWorkflowAgent initialized for A2A communication.")
        logger.info(f"  Planner Agent A2A URL: {self.planner_agent_a2a_url}")
        logger.info(f"  Orchestrate Agent A2A URL: {self.orchestrate_agent_a2a_url}")

    async def _fetch_agent_card(self, agent_base_url: str) -> A2AAgentCard | None:
        """Fetches and parses the Agent Card from the given A2A server base URL."""
        if not agent_base_url:
            logger.error("Agent base URL is not provided for fetching agent card.")
            return None

        agent_card_url = f"{agent_base_url.rstrip('/')}/.well-known/agent.json"
        logger.info(f"Fetching agent card from: {agent_card_url}")
        try:
            response = await self.http_client.get(agent_card_url)
            response.raise_for_status()
            agent_card_data = response.json()
            # It's good practice to validate with pydantic model if exact structure is critical
            return A2AAgentCard(**agent_card_data)
        except httpx.RequestError as e:
            logger.error(f"Error fetching agent card from {agent_card_url}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing agent card JSON from {agent_card_url}: {e}")
        except Exception as e: # Catch other Pydantic validation errors or unexpected issues
            logger.error(f"Unexpected error when fetching/parsing agent card from {agent_card_url}: {e}")
        return None

    async def _call_a2a_agent(self, agent_a2a_url: str, input_payload: str, agent_name_for_log: str) -> tuple[str | None, list[str]]:
        """Helper to call an A2A agent and get a text response."""
        thoughts = []
        if not agent_a2a_url:
            thoughts.append(f"{agent_name_for_log} A2A URL not configured.")
            logger.error(f"Cannot call {agent_name_for_log}: A2A URL not set.")
            return None, thoughts

        # Fetching agent card can be optional if the base URL is the direct A2A endpoint.
        # For now, let's assume agent_a2a_url is the base for /.well-known/agent.json and A2A calls.
        target_agent_card = await self._fetch_agent_card(agent_a2a_url)
        if not target_agent_card or not target_agent_card.url:
            thoughts.append(f"Could not retrieve or use agent card for {agent_name_for_log} at {agent_a2a_url}.")
            logger.error(f"Failed to get agent card for {agent_name_for_log}.")
            return None, thoughts
        effective_a2a_target_url = target_agent_card.url # URL from card is the A2A endpoint

        # Simplified: Assuming agent_a2a_url is the direct callable A2A endpoint.
        # If agent_card.url is different or provides more specific endpoint, use that.
        # effective_a2a_target_url = agent_a2a_url # Replaced by using card.url

        thoughts.append(f"Sending message to {agent_name_for_log} (Name from card: '{target_agent_card.name}') at {effective_a2a_target_url}.")
        logger.info(f"Calling {agent_name_for_log} (Name from card: '{target_agent_card.name}', URL from card: {effective_a2a_target_url}) via A2AClient.")

        try:
            a2a_request_message = A2AMessage(role="user", parts=[A2APart(text=input_payload)])

            # Using send_message for potentially simple request/response.
            # If these become long-running tasks, then send_task & get_task polling would be needed.
            response_message = await self.a2a_client.send_message(effective_a2a_target_url, a2a_request_message)

            if response_message and response_message.parts:
                # Assuming the first part contains the primary text response
                # This might need adjustment based on how Planner/Orchestrator A2A servers format their response parts.
                generated_text = response_message.parts[0].text
                thoughts.append(f"{agent_name_for_log} A2A raw response: {generated_text[:200]}...")
                logger.info(f"{agent_name_for_log} A2A raw response: {generated_text[:200]}...")
                return generated_text, thoughts
            else:
                thoughts.append(f"{agent_name_for_log} A2A call returned no response or no parts.")
                logger.warning(f"{agent_name_for_log} A2A call returned no response or no parts. Full response: {response_message}")
                return None, thoughts
        except Exception as e:
            thoughts.append(f"Error calling {agent_name_for_log} via A2A: {str(e)}")
            logger.error(f"Error calling {agent_name_for_log} ({effective_a2a_target_url}) via A2A: {e}", exc_info=True)
            return None, thoughts

    async def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session):
        """
        Generates an event plan by calling the Planner Agent via A2A.
        `adk_session` is for this workflow agent's own context, not directly used for A2A call here.
        """
        # Prepare input for the Planner Agent (same prompt as before)

        friends_list_example_for_prompt = json.dumps(selected_friend_names_list)
        selected_friend_names_str = ', '.join(selected_friend_names_list)

        planner_input_prompt = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".
Output the entire plan in a SINGLE, COMPLETE JSON object. (Full prompt details omitted for brevity but should be the same as before)
{{
  "friends_name_list": {friends_list_example_for_prompt}, "event_name": "string", "event_date": "{planned_date}",
  "event_description": "string", "locations_and_activities": [{{ "name": "string", "latitude": 12.345, "longitude": -67.890, "address": "string or null", "description": "string"}}],
  "post_to_go_out": "string"
}}
"""
        generated_text, thoughts = await self._call_a2a_agent(
            agent_a2a_url=self.planner_agent_a2a_url,
            input_payload=planner_input_prompt,
            agent_name_for_log="PlannerAgent"
        )

        if not generated_text:
            thoughts.append("Planner Agent A2A call returned no text.")
            return None, thoughts

        try:
            # Attempt to parse the JSON from the response
            # This logic for extracting JSON from markdown or cleaning up is kept from original
            if "```json" in generated_text:
                json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                thoughts.append("Extracted JSON from markdown block (Planner Agent A2A).")
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"):
                json_block = generated_text.strip().strip('`').strip()
                thoughts.append("Extracted JSON from simple backticks (Planner Agent A2A).")
            else:
                json_block = generated_text.strip()

            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON from Planner Agent A2A response.")

            return plan_json, thoughts
        except json.JSONDecodeError as e:
            thoughts.append(f"JSONDecodeError from Planner Agent A2A response: {str(e)}. Raw text: {generated_text}")
            logger.error(f"JSONDecodeError from Planner Agent A2A (user '{user_name}'): {str(e)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts
        except Exception as e: # Catch any other unexpected error during parsing
            thoughts.append(f"Unexpected error parsing Planner Agent A2A response: {str(e)}. Raw text: {generated_text}")
            logger.error(f"Unexpected error parsing Planner Agent A2A response (user '{user_name}'): {str(e)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts


    async def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session):
        """
        Processes event posting by calling the Orchestrate Agent via A2A.
        `adk_session` is for this workflow agent's own context.
        """
        orchestrator_input_details = {
            "user_name": user_name,
            "user_id_context": agent_session_user_id,
            "confirmed_plan": confirmed_plan, # This is likely a dict/JSON
            "invite_message": edited_invite_message,
            "task_description": f"User '{user_name}' wants to create an event based on a confirmed plan and send an invite: '{edited_invite_message}'. Plan details: {json.dumps(confirmed_plan)}"
        }
        # Orchestrator's A2A server will receive this as a JSON string in the message part.
        # The Orchestrator's AgentExecutor then needs to parse this.
        orchestrator_input_payload = json.dumps(orchestrator_input_details)

        response_text, thoughts = await self._call_a2a_agent(
            agent_a2a_url=self.orchestrate_agent_a2a_url,
            input_payload=orchestrator_input_payload,
            agent_name_for_log="OrchestrateAgent"
        )

        if response_text and response_text.strip():
            thoughts.append("Successfully delegated to Orchestrate Agent via A2A.")
            # The response_text itself is the confirmation/narration from the Orchestrate Agent's A2A server.
            return True, response_text.strip(), thoughts
        else:
            error_message = "Orchestrate Agent A2A call returned empty or no response."
            if not response_text: # Specifically if None was returned by _call_a2a_agent
                 error_message = thoughts[-1] if thoughts else "Orchestrate Agent A2A communication failed."
            thoughts.append(error_message)
            return False, error_message, thoughts

    async def run(self, action: str, payload: dict, adk_session=None):
        """
        Main execution method for the agent.
        Determines the action and calls the appropriate internal method.
        `adk_session` is the ADK Session object created by main.py for this workflow's execution.
        All sub-agent calls are now async.

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


            # Calls are now async
            plan_json, thoughts = await self._generate_event_plan(
                user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session

            )
            if plan_json:
                return {"success": True, "result_type": "plan", "data": plan_json, "thoughts": thoughts}
            else:

                return {"success": False, "error": "Failed to generate plan via Planner Agent (RE/A2A).", "thoughts": thoughts}

        elif action == "post_event":
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            agent_context_user_id = payload.get("agent_session_user_id", user_name)

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            # Calls are now async
            success, message, thoughts = await self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session

            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting via Orchestrate Agent (A2A): {message}", "thoughts": thoughts}

        else:
            logger.warning(f"Unknown action received: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}
