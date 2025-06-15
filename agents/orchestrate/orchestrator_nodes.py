import os
import json
from dotenv import load_dotenv
from agents.app.common.graph_state import OrchestratorState # OrchestratorState will be a TypedDict-like structure in LangGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage # SystemMessage can be used for more static parts of prompt
import uuid # For session_id

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
# Ensure GOOGLE_API_KEY is set for GenAI

def entry_point_node(state: OrchestratorState) -> dict:
    print("---Entry Point Node---")
    session_id = str(uuid.uuid4())
    user_request = state.get('user_request')

    if not user_request:
        print("Error: User request missing in initial state.")
        # Even with an error, initialize all fields for consistency
        return {
            "session_id": state.get('session_id') or session_id,
            "user_request": None,
            "current_task_description": None,
            "intermediate_output": None,
            "final_output": None,
            "current_agent_name": "entry_point",
            "error_message": "User request missing in initial state.",
            "route": "error_handler" # Route to error handler
        }

    print(f"Entry point: Received user request: {user_request}")
    return {
        "session_id": state.get('session_id') or session_id,
        "user_request": user_request,
        "current_task_description": user_request, # Initialize current_task_description
        "intermediate_output": None,
        "final_output": None,
        "current_agent_name": "entry_point",
        "error_message": None,
        "route": None
    }

ORCHESTRATOR_PROMPT_TEMPLATE = """
You are an expert AI Orchestrator. Your primary responsibility is to intelligently interpret user requests and the current state of the operation, then decide the next specialized processing step (node) to perform. You manage the sequence of these steps.

**Core Workflow & Decision Making:**

1.  **Understand User Intent & Complexity:**
    *   Carefully analyze the user's request: {user_request}
    *   And any output from the previously executed node: {intermediate_output}
    *   Determine the core task(s).
    *   Identify if the request requires a single processing step or a sequence. For example, "Analyze John Doe's profile and then create a positive post" would require two steps.

2.  **Node Selection:**
    *   Based on the user's intent and current state, select the most appropriate next node from the available options:
        *   **'planner'**: Use this node to generate creative and fun event plan suggestions. It typically requires details like dates, location, and user interests. If you select 'planner', ensure the 'current_task_description' you provide for it is a clear, self-contained request that the planner can understand (e.g., "For the upcoming weekend, from YYYY-MM-DD to YYYY-MM-DD, in LOCATION, for someone interested in INTERESTS, generate N plan suggestions.").
        *   **'social'**: (Placeholder - capabilities to be defined) Use for tasks related to social media.
        *   **'final_responder'**: Select this node when all processing is complete and the 'intermediate_output' contains the final information to be presented to the user, or if an error has occurred that needs to be communicated.
        *   **'error_handler'**: If you detect an unrecoverable error or an incoherent state from the previous steps, or if the user request is fundamentally flawed for the available tools, select this.

3.  **Task Parameterization (Crucial for 'planner' and similar nodes):**
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

def planner_router_node(state: OrchestratorState) -> dict:
    print("---Planner/Router Node---")
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.3, convert_system_message_to_human=True) # Using convert_system_message_to_human for older models if needed

        user_request = state.get('user_request')
        if not user_request: # Should have been caught by entry_point, but good to double check
            return {**state, "route": "error_handler", "error_message": "User request missing in state for planner_router.", "current_agent_name": "planner_router"}

        intermediate_output_str = "None"
        if state.get('intermediate_output') is not None:
            try:
                intermediate_output_str = json.dumps(state.get('intermediate_output'))
            except TypeError:
                intermediate_output_str = str(state.get('intermediate_output'))

        prompt_content = ORCHESTRATOR_PROMPT_TEMPLATE.format(
            user_request=user_request,
            intermediate_output=intermediate_output_str
        )

        # Using HumanMessage for the full prompt as Gemini API prefers this for complex instructions
        # SystemMessage could be used if there was a more static part of the role definition.
        messages = [HumanMessage(content=prompt_content)]

        print(f"Router node invoking LLM. First 200 chars of prompt: {prompt_content[:200]}...")
        response = llm.invoke(messages)
        llm_output_json_str = response.content.strip()

        print(f"Router LLM raw output: {llm_output_json_str}")

        parsed_llm_response = None
        next_route = None
        task_description_for_next_node = user_request # Default

        try:
            # Attempt to find JSON block if markdown backticks are present
            if llm_output_json_str.startswith("```json"):
                llm_output_json_str = llm_output_json_str[7:]
                if llm_output_json_str.endswith("```"):
                    llm_output_json_str = llm_output_json_str[:-3]
            elif llm_output_json_str.startswith("```"): # Just ```
                llm_output_json_str = llm_output_json_str[3:]
                if llm_output_json_str.endswith("```"):
                    llm_output_json_str = llm_output_json_str[:-3]

            parsed_llm_response = json.loads(llm_output_json_str)
            next_route = parsed_llm_response.get("next_node")
            task_description_for_next_node = parsed_llm_response.get("current_task_description_for_next_node", user_request)
        except json.JSONDecodeError as e:
            error_msg = f"Router LLM did not return valid JSON. Error: {e}. Raw output: {llm_output_json_str}"
            print(error_msg)
            return {**state, "route": "error_handler", "error_message": error_msg, "current_agent_name": "planner_router"}
        except AttributeError as e: # If LLM output is not even a string with .get, or parsed_llm_response is not a dict
            error_msg = f"Router LLM response structure error or not a dict. Error: {e}. Raw output: {llm_output_json_str}"
            print(error_msg)
            return {**state, "route": "error_handler", "error_message": error_msg, "current_agent_name": "planner_router"}

        known_routes = ["planner", "social", "final_responder", "error_handler"]
        if not next_route or next_route not in known_routes:
            error_msg = f"Router LLM decided an invalid or missing route: '{next_route}'. Valid routes are: {known_routes}."
            print(error_msg)
            # Pass through the potentially problematic task_description if it exists, or default.
            state['current_task_description'] = task_description_for_next_node
            return {**state, "route": "error_handler", "error_message": error_msg, "current_agent_name": "planner_router"}

        print(f"Router successfully decided route: '{next_route}' with task description: '{task_description_for_next_node[:100]}...'")
        return {
            **state,
            "route": next_route,
            "current_task_description": task_description_for_next_node,
            "current_agent_name": "planner_router",
            "error_message": None # Clear previous errors if successfully routed
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Generic error in planner_router_node: {e}\n{error_trace}")
        return {
            **state,
            "route": "error_handler",
            "error_message": f"Generic error in planner_router_node: {str(e)}",
            "current_agent_name": "planner_router"
        }

def error_handler_node(state: OrchestratorState) -> dict:
    print("---Error Handler Node---")
    error_message = state.get('error_message', "An unspecified error occurred and was routed to error_handler.")
    print(f"Error Handler Node processing message: {error_message}")

    # This node prepares a final error output.
    # The actual presentation to the user happens via 'final_responder' / 'output_node'.
    # We set intermediate_output here, which output_node will pick up.
    # The route to 'final_responder' will be set by the graph's edge from error_handler.
    return {
        **state, # Persist other state fields
        "intermediate_output": {"error": error_message, "details": "Processing was halted due to an error."},
        "current_agent_name": "error_handler",
        "route": "final_responder" # Explicitly route to final_responder
    }

def output_node(state: OrchestratorState) -> dict:
    print("---Output Node---")
    # This node prepares the final response for the user.
    # It looks for 'error_message' first, then 'intermediate_output'.

    error_msg_from_state = state.get('error_message') # Error that might have occurred in a node before error_handler
    intermediate_out = state.get('intermediate_output') # This might be a success payload or an error payload from error_handler_node

    final_response_payload = None

    # Check if intermediate_output itself is an error structure (e.g., from error_handler_node)
    if isinstance(intermediate_out, dict) and "error" in intermediate_out:
        print(f"Output node processing error payload from intermediate_output: {intermediate_out.get('error')}")
        final_response_payload = intermediate_out
    elif error_msg_from_state: # If an error occurred in a node and wasn't yet formatted by error_handler
        print(f"Output node processing direct error_message from state: {error_msg_from_state}")
        final_response_payload = {"error": error_msg_from_state, "details": "An error occurred during processing."}
        if intermediate_out: # Include intermediate_output if it exists, might give context
            final_response_payload["last_known_output"] = intermediate_out
    elif intermediate_out is not None:
        print(f"Output node processing successful intermediate output: {str(intermediate_out)[:200]}...")
        final_response_payload = intermediate_out
    else:
        print("Output node: No definitive error or intermediate output. This may indicate an issue.")
        final_response_payload = {"message": "Processing completed with no specific output or error provided."}

    final_output_str = None
    if isinstance(final_response_payload, (dict, list)):
        try:
            final_output_str = json.dumps(final_response_payload)
        except TypeError as te:
            print(f"Error serializing final_response_payload to JSON: {te}")
            final_output_str = json.dumps({"error": "Output serialization error", "details": str(te)})
    elif isinstance(final_response_payload, str): # If it's already a string (e.g. simple message)
        final_output_str = final_response_payload
    elif final_response_payload is None: # Should ideally not happen if logic above is correct
        final_output_str = json.dumps({"message": "No output generated."})
    else: # Other types
        final_output_str = str(final_response_payload)

    print(f"Output node final_output: {final_output_str}")
    return {
        **state,
        "final_output": final_output_str,
        "current_agent_name": "output_node",
        # No route needed from output_node as it's an end state or graph END.
    }
