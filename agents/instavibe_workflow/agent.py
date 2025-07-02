import os
import json
import logging
import asyncio # Added for async operations
import httpx   # Added for fetching agent cards

# from vertexai.preview import reasoning_engines # Old client, to be replaced by A2AClient
from python_a2a.client import A2AClient # Corrected import
# Final python_a2a model imports
from python_a2a import AgentCard as A2AAgentCard
from python_a2a.models import Message as A2AMessage, MessageRole as A2AMessageRole, TextContent as A2ATextContent, DataPart as A2ADataPart # Corrected imports


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

    async def _call_a2a_agent(self, agent_a2a_url: str, input_payload_dict: dict, agent_name_for_log: str) -> tuple[dict | None, list[str]]:
        """Helper to call an A2A agent with a dict payload and get a dict response."""
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
            # Construct message with DataPart
            a2a_request_message = A2AMessage(role=A2AMessageRole.USER, parts=[A2ADataPart(data=input_payload_dict, type="data")])
            logger.debug(f"A2A Request to {agent_name_for_log}: {a2a_request_message.model_dump_json(indent=2)}")

            response_message = await self.a2a_client.send_message(effective_a2a_target_url, a2a_request_message)

            if response_message and response_message.parts and isinstance(response_message.parts[0], A2ATextContent):
                # A2A server now returns TextContent containing a JSON string.
                response_text_content = response_message.parts[0].text
                thoughts.append(f"{agent_name_for_log} A2A raw JSON string response: {response_text_content[:200]}...")
                logger.info(f"{agent_name_for_log} A2A raw JSON string response: {response_text_content[:200]}...")
                try:
                    response_dict = json.loads(response_text_content)
                    return response_dict, thoughts
                except json.JSONDecodeError as e:
                    thoughts.append(f"Failed to parse JSON response from {agent_name_for_log}: {str(e)}. Raw: {response_text_content}")
                    logger.error(f"JSONDecodeError from {agent_name_for_log} response: {e}. Raw: {response_text_content}", exc_info=True)
                    return {"error": f"Failed to parse JSON response from {agent_name_for_log}", "raw_response": response_text_content}, thoughts
            else:
                thoughts.append(f"{agent_name_for_log} A2A call returned no response, no parts, or part was not TextContent.")
                logger.warning(f"{agent_name_for_log} A2A call returned invalid response. Full response: {response_message.model_dump_json(indent=2) if response_message else 'None'}")
                return None, thoughts
        except Exception as e:
            thoughts.append(f"Error calling {agent_name_for_log} via A2A: {str(e)}")
            logger.error(f"Error calling {agent_name_for_log} ({effective_a2a_target_url}) via A2A: {e}", exc_info=True)
            return None, thoughts

    async def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session):
        """
        Generates an event plan by calling the Planner Agent via A2A.
        """
        thoughts = [f"Preparing to call Planner Agent for user {user_name}."]

        # Construct the payload dictionary for the Planner Agent's "query_details"
        planner_payload_dict = {
            "query_details": {
                "user_name": user_name,
                "start_date": planned_date,
                "end_date": planned_date, # Assuming planner uses start_date if end_date is same or for a single "night out"
                "location": location_n_perference,
                "interests": ", ".join(selected_friend_names_list) if selected_friend_names_list else "general fun activities", # Pass interests as a string
                "num_plans": "1" # Example, can be parameterized if needed
            }
        }
        thoughts.append(f"Planner payload: {json.dumps(planner_payload_dict)}")

        response_dict, call_thoughts = await self._call_a2a_agent(
            agent_a2a_url=self.planner_agent_a2a_url,
            input_payload_dict=planner_payload_dict,
            agent_name_for_log="PlannerAgent"
        )
        thoughts.extend(call_thoughts)

        if not response_dict or response_dict.get("error"):
            error_msg = response_dict.get("error", "Planner Agent A2A call returned no data or an error.") if response_dict else "Planner Agent A2A call returned None."
            thoughts.append(error_msg)
            logger.error(f"Error from Planner Agent A2A call: {error_msg}. Full response dict: {response_dict}")
            return None, thoughts

        # The Planner ADK agent (after refactor) should return a dict,
        # potentially with a "fun_plans" key or directly the plan if only one.
        # If it's the structure `{"fun_plans": [...]}`:
        plan_data = response_dict.get("fun_plans")
        if isinstance(plan_data, list) and len(plan_data) > 0:
            plan_json = plan_data[0] # Assuming we take the first plan if multiple are returned
            thoughts.append("Successfully received and extracted plan from Planner Agent.")
            return plan_json, thoughts
        elif isinstance(response_dict, dict) and "plan_description" in response_dict : # If planner returns a single plan dict directly
            thoughts.append("Successfully received plan object directly from Planner Agent.")
            return response_dict, thoughts
        else:
            thoughts.append(f"Unexpected response structure from Planner Agent. Expected 'fun_plans' list or a plan object. Got: {str(response_dict)[:200]}")
            logger.warning(f"Unexpected response structure from Planner: {response_dict}")
            return None, thoughts


    async def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session):
        """
        Processes event posting by calling the Orchestrate Agent via A2A.
        """
        thoughts = [f"Preparing to call Orchestrate Agent for user {user_name} to post event."]

        # This is the dictionary that the Orchestrator's ADK agent will receive.
        # The Orchestrator's A2A server expects a `DataPart` containing a dict.
        # This dict should have a key (e.g., "task_description_json" or "query")
        # whose value is the string prompt for the Orchestrator's LLM.
        orchestrator_task_details_dict = {
            "user_name": user_name,
            "user_id_context": agent_session_user_id,
            "confirmed_plan": confirmed_plan,
            "invite_message": edited_invite_message,
            "task_description": f"User '{user_name}' wants to create an event based on a confirmed plan and send an invite: '{edited_invite_message}'. Plan details: {json.dumps(confirmed_plan)}"
        }

        # The Orchestrator A2A server was refactored to look for "task_description_json" or "query".
        # Let's use "task_description_json" and pass the stringified details.
        orchestrator_a2a_payload_dict = {
            "task_description_json": json.dumps(orchestrator_task_details_dict)
        }
        thoughts.append(f"Orchestrator A2A payload: {json.dumps(orchestrator_a2a_payload_dict)}")

        response_dict, call_thoughts = await self._call_a2a_agent(
            agent_a2a_url=self.orchestrate_agent_a2a_url,
            input_payload_dict=orchestrator_a2a_payload_dict,
            agent_name_for_log="OrchestrateAgent"
        )
        thoughts.extend(call_thoughts)

        if response_dict and not response_dict.get("error"):
            # The Orchestrator A2A server returns TextContent, which _call_a2a_agent parses from JSON string.
            # The content of that JSON string is what the Orchestrator ADK agent returned.
            # Let's assume the Orchestrator ADK agent returns something like {"status": "success", "message": "..."} or {"output": "..."}
            response_text = response_dict.get("response", response_dict.get("output", str(response_dict)))
            thoughts.append(f"Successfully delegated to Orchestrate Agent. Response: {response_text[:200]}")
            return True, response_text.strip(), thoughts
        else:
            error_message = response_dict.get("error", "Orchestrate Agent A2A call returned no data or an error.") if response_dict else "Orchestrate Agent A2A call returned None."
            thoughts.append(error_message)
            logger.error(f"Error from Orchestrate Agent A2A call: {error_message}. Full response dict: {response_dict}")
            return False, error_message, thoughts

    async def process_request(self, action: str, payload: dict, adk_session_context=None): # Renamed from run to match main.py caller
        """
        Main execution method for the agent.
        Determines the action and calls the appropriate internal method.
        `adk_session_context` is the ADK Session object created by main.py for this workflow's execution.
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
