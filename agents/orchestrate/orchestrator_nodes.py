import os
import json
from dotenv import load_dotenv
from agents.app.common.graph_state import OrchestratorState # OrchestratorState will be a TypedDict-like structure in LangGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage # SystemMessage can be used for more static parts of prompt
import uuid # For session_id
import logging
from typing import Dict, Any, Optional # Added for type hinting

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logging.info("OrchestratorNodes: .env file loaded.")
else:
    logging.warning(f"OrchestratorNodes: .env file not found at {dotenv_path}. API keys may not be available.")

# Configure basic logging if this file is run standalone or for visibility during setup.
# This might be overridden by a central logging configuration if this is part of a larger app.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')


def entry_point_node(state: OrchestratorState) -> Dict[str, Any]:
    logging.info("---Entry Point Node---")
    session_id = str(uuid.uuid4())
    user_request = state.user_request # Pydantic attribute access

    if not user_request:
        logging.error("Entry Point Node: User request missing in initial state.")
        return {
            "session_id": state.session_id or session_id, # Use existing session_id if available (e.g. retry)
            "user_request": None,
            "current_task_description": None,
            "intermediate_output": None,
            "final_output": None,
            "current_agent_name": "entry_point",
            "error_message": "User request missing in initial state.",
            "route": "error_handler"
        }

    logging.info(f"Entry Point Node: Received user request: '{user_request[:100]}...'")
    return {
        "session_id": state.session_id or session_id,
        "user_request": user_request,
        "current_task_description": user_request, # Initialize current_task_description
        "intermediate_output": None, # Ensure this is initialized
        "final_output": None, # Ensure this is initialized
        "current_agent_name": "entry_point",
        "error_message": None, # Clear any previous error
        "route": None # Let planner_router decide next
    }

ORCHESTRATOR_PROMPT_TEMPLATE = """
You are an expert AI Orchestrator. Your primary responsibility is to intelligently interpret user requests and the current state of the operation, then decide the next specialized processing step (node) to perform. You manage the sequence of these steps.

**Core Workflow & Decision Making:**

1.  **Understand User Intent & Complexity:**
    *   Carefully analyze the user's request: {user_request}
    *   And any output from the previously executed node: {intermediate_output}
    *   Determine the core task(s).
    *   Identify if the request requires a single processing step or a sequence. For example, "Analyze John Doe's profile and then create a positive post about his latest event attendance" would require two steps ('social' then 'platform').

2.  **Node Selection:**
    *   Based on the user's intent and current state, select the most appropriate next node from the available options:
        *   **'planner'**: Use this node to generate creative and fun event plan suggestions. It typically requires details like dates, location, and user interests. If you select 'planner', ensure the 'current_task_description' you provide for it is a clear, self-contained request that the planner can understand (e.g., "For the upcoming weekend, from YYYY-MM-DD to YYYY-MM-DD, in LOCATION, for someone interested in INTERESTS, generate N plan suggestions.").
        *   **'social'**: Use for tasks related to social media analysis, like fetching user posts, friends, or attended events. Requires person's name or other identifiers. Example task: "Get recent posts for John Doe." or "Find friends of Jane Smith."
        *   **'platform'**: Use for interacting with the Instavibe platform, such as creating posts or registering for events. Requires details like author name, post text, sentiment for posts; or event name, date, attendee name for events. Example task: "Create a positive post for 'User123' saying 'Having a great time! #fun'." or "Register 'User123' for 'Tech Conference 2024' on '2024-12-01'."
        *   **'final_responder'**: Select this node when all processing is complete and the 'intermediate_output' contains the final information to be presented to the user, or if an error has occurred that needs to be communicated.
        *   **'error_handler'**: If you detect an unrecoverable error or an incoherent state from the previous steps, or if the user request is fundamentally flawed for the available tools, select this.

3.  **Task Parameterization (Crucial for 'planner', 'social', 'platform' and similar nodes):**
    *   If you select a node like 'planner' that requires specific input, you MUST formulate a concise 'current_task_description' for it based on the user's overall request ({user_request}) and any relevant information from 'intermediate_output'. This description should be what the target node needs to perform its task.
    *   If the necessary information is not clear from the user request, you might need to guide the user to provide more details (though this version of the orchestrator doesn't directly support asking user for clarification, aim to make the best decision with available info or route to 'final_responder' with a message indicating missing details).

**Communication with User (Handled by 'final_responder'):**
*   Your goal is to route processing correctly. The 'final_responder' will handle user communication.

**Important Reminders:**
*   Always prioritize selecting the correct node based on its documented purpose.
*   If routing to a node that needs specific input (like 'planner'), ensure 'current_task_description' is properly formulated.
*   If the request is fully addressed, route to 'final_responder'.

**Output Format:**
Your response should be a single JSON object containing two keys:
1.  `"next_node"`: A string with the name of the next node to call (e.g., "planner", "final_responder", "error_handler").
2.  `"current_task_description_for_next_node"`: A string containing the specific input or task for the selected `next_node`. If the `next_node` is 'final_responder' or 'error_handler', this can be a brief justification, the original user request, or a summary of the situation.

Example 1 (User asks for a plan):
User Request: "I want a plan for Paris this weekend for an anniversary."
Intermediate Output: None
Your JSON Response:
{{
    "next_node": "planner",
    "current_task_description_for_next_node": "Plan a romantic anniversary weekend in Paris for the upcoming weekend. Include 2-3 suggestions."
}}

Example 2 (Planner has provided a plan, now ready to output):
User Request: "I want a plan for Paris this weekend for an anniversary."
Intermediate Output: {{ "fun_plans": [...] }} (Output from planner node)
Your JSON Response:
{{
    "next_node": "final_responder",
    "current_task_description_for_next_node": "The planner has generated event suggestions. Ready to show user."
}}

Example 3 (User request is too vague for planner):
User Request: "I want a plan."
Intermediate Output: None
Your JSON Response:
{{
    "next_node": "final_responder",
    "current_task_description_for_next_node": "The user request 'I want a plan' is too vague. Please provide more details like location, dates, and interests."
}}

Now, based on the current user_request and intermediate_output, provide your JSON response.
User Request: {user_request}
Intermediate Output: {intermediate_output}
Your JSON Response:
"""

async def planner_router_node(state: OrchestratorState) -> Dict[str, Any]: # Made async
    logging.info("---Planner/Router Node---")
    current_agent_name = "planner_router"
    try:
        # Ensure GOOGLE_API_KEY is loaded for ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.3, convert_system_message_to_human=True)

        user_request = state.user_request
        if not user_request:
            logging.error("Planner Router Node: User request missing in state.")
            return {
                "route": "error_handler",
                "error_message": "User request missing in state for planner_router.",
                "current_agent_name": current_agent_name
            }

        intermediate_output_str = "None"
        if state.intermediate_output is not None:
            try:
                intermediate_output_str = json.dumps(state.intermediate_output)
            except TypeError: # Handle non-serializable intermediate_output gracefully
                intermediate_output_str = str(state.intermediate_output)
                logging.warning(f"Planner Router Node: Intermediate output was not JSON serializable, used str(): {intermediate_output_str[:100]}...")


        prompt_content = ORCHESTRATOR_PROMPT_TEMPLATE.format(
            user_request=user_request,
            intermediate_output=intermediate_output_str
        )
        messages = [HumanMessage(content=prompt_content)]

        logging.info(f"Router node invoking LLM. Prompt snippet: {prompt_content[:200]}...")
        response = await llm.ainvoke(messages) # Changed to ainoke for async
        llm_output_json_str = response.content.strip()
        logging.info(f"Router LLM raw output: {llm_output_json_str}")

        parsed_llm_response = None
        next_route = None
        # Default to original user_request if LLM doesn't provide a new one
        task_description_for_next_node = user_request

        try:
            if llm_output_json_str.startswith("```json"):
                json_str_cleaned = llm_output_json_str[7:-3].strip() if llm_output_json_str.endswith("```") else llm_output_json_str[7:].strip()
            elif llm_output_json_str.startswith("```"):
                 json_str_cleaned = llm_output_json_str[3:-3].strip() if llm_output_json_str.endswith("```") else llm_output_json_str[3:].strip()
            else:
                json_str_cleaned = llm_output_json_str

            parsed_llm_response = json.loads(json_str_cleaned)
            next_route = parsed_llm_response.get("next_node")
            # Update task_description only if provided by LLM and valid, else keep default
            task_description_for_next_node = parsed_llm_response.get("current_task_description_for_next_node", task_description_for_next_node)

        except json.JSONDecodeError as e:
            error_msg = f"Router LLM did not return valid JSON. Error: {e}. Raw output: {llm_output_json_str}"
            logging.error(error_msg)
            return {
                "route": "error_handler",
                "error_message": error_msg,
                "current_agent_name": current_agent_name
            }
        except AttributeError as e:
            error_msg = f"Router LLM response structure error. Error: {e}. Raw output: {llm_output_json_str}"
            logging.error(error_msg)
            return {
                "route": "error_handler",
                "error_message": error_msg,
                "current_agent_name": current_agent_name
            }

        known_routes = ["planner", "social", "platform", "final_responder", "error_handler"]
        if not next_route or next_route not in known_routes:
            error_msg = f"Router LLM decided an invalid or missing route: '{next_route}'. Valid routes: {known_routes}. Raw output: {llm_output_json_str}"
            logging.error(error_msg)
            # Do not change current_task_description if route is invalid, keep what was there.
            return {
                "route": "error_handler", # Default to error_handler on invalid route
                "error_message": error_msg,
                "current_agent_name": current_agent_name,
                 # "current_task_description": state.current_task_description # Keep existing task description
            }

        logging.info(f"Router successfully decided route: '{next_route}' with task: '{task_description_for_next_node[:100]}...'")
        return {
            "route": next_route,
            "current_task_description": task_description_for_next_node,
            "current_agent_name": current_agent_name,
            "error_message": None # Clear previous errors
        }

    except Exception as e:
        logging.error(f"Generic error in planner_router_node: {e}", exc_info=True)
        return {
            "route": "error_handler",
            "error_message": f"Generic error in planner_router_node: {str(e)}",
            "current_agent_name": current_agent_name
        }

def error_handler_node(state: OrchestratorState) -> Dict[str, Any]:
    logging.info("---Error Handler Node---")
    error_message = state.error_message or "An unspecified error occurred and was routed to error_handler."
    logging.info(f"Error Handler Node processing message: {error_message}")

    # This node prepares a final error output for the output_node.
    # The graph edge from 'error_handler' should lead to 'final_output_node'.
    return {
        "intermediate_output": {"error": error_message, "details": "Processing was halted due to an error."},
        "current_agent_name": "error_handler",
        "error_message": error_message, # Keep the error message in the state as well for clarity
        # "route": "final_responder" # This might be redundant if graph structure handles it.
                                  # Keep if explicit routing is desired.
                                  # For now, assuming graph routes error_handler to final_output_node.
    }

def output_node(state: OrchestratorState) -> Dict[str, Any]:
    logging.info("---Output Node---")
    # This node prepares the final response string for the user.
    # It prioritizes error messages if present.

    error_msg_to_display = state.error_message # Error from a node or explicitly set by error_handler.
    intermediate_out = state.intermediate_output

    final_response_payload = None

    # Check if intermediate_output itself is an error structure (e.g., from error_handler_node)
    if isinstance(intermediate_out, dict) and "error" in intermediate_out:
        logging.info(f"Output node using error payload from intermediate_output: {intermediate_out.get('error')}")
        final_response_payload = intermediate_out
    elif error_msg_to_display: # If an error occurred and is in error_message (possibly not yet formatted by error_handler)
        logging.info(f"Output node using direct error_message from state: {error_msg_to_display}")
        final_response_payload = {"error": error_msg_to_display, "details": "An error occurred during processing."}
        if intermediate_out: # Include intermediate_output if it exists, might give context
            final_response_payload["last_known_output"] = intermediate_out
    elif intermediate_out is not None:
        logging.info(f"Output node using successful intermediate_output: {str(intermediate_out)[:200]}...")
        final_response_payload = intermediate_out
    else:
        logging.warning("Output node: No definitive error or intermediate output. This may indicate an issue.")
        final_response_payload = {"message": "Processing completed with no specific output or error provided."}

    final_output_str = None
    if isinstance(final_response_payload, (dict, list)):
        try:
            final_output_str = json.dumps(final_response_payload, indent=2)
        except TypeError as te:
            logging.error(f"Error serializing final_response_payload to JSON: {te}", exc_info=True)
            final_output_str = json.dumps({"error": "Output serialization error", "details": str(te)}, indent=2)
    elif isinstance(final_response_payload, str):
        final_output_str = final_response_payload
    elif final_response_payload is None:
        final_output_str = json.dumps({"message": "No output generated."}, indent=2)
    else: # Other types
        final_output_str = str(final_response_payload)

    logging.info(f"Output node final_output string: {final_output_str}")
    return {
        "final_output": final_output_str, # The final, user-facing string
        "current_agent_name": "output_node",
        # No "route" needed; this is typically an end node.
        # "error_message": state.error_message, # Preserve error message if any
        # "intermediate_output": state.intermediate_output # Preserve intermediate output
    }
