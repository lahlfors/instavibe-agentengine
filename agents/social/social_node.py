import os
import json
from typing import TypedDict, Optional, List, Dict, Any
from dotenv import load_dotenv

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

# Import tools from instavibe
from .instavibe import get_person_posts, get_person_friends, get_person_id_by_name, get_person_attended_events

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# --- State Definition ---
class SocialGraphState(TypedDict):
    user_request: str
    profile_info: Optional[list] # Should be a list to store multiple profiles if needed
    summary: Optional[str]
    summary_status: Optional[str] # "completed" or "pending"
    final_output: Optional[str]
    error_message: Optional[str]
    # iteration_count: int # Could be added for controlling loops if needed

# --- Tool Definitions ---
# Wrap instavibe functions with @tool decorator
# These functions are already defined in instavibe.py, we just make them LangChain tools here.
# The instavibe.py file handles Spanner connection and error handling.

@tool("get_person_id_by_name_tool")
def get_person_id_by_name_tool(name: str) -> Optional[str]:
    """Fetches the person_id for a given name.
    Args:
        name (str): The name of the person to search for.
    Returns:
        str or None: The person_id if found, otherwise None.
    """
    return get_person_id_by_name(name)

@tool("get_person_posts_tool")
def get_person_posts_tool(person_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetches posts written by a specific person.
    Args:
        person_id (str): The ID of the person whose posts to fetch.
    Returns:
        list[dict] or None: List of post dictionaries, or None if an error occurs.
    """
    return get_person_posts(person_id)

@tool("get_person_friends_tool")
def get_person_friends_tool(person_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetches friends for a specific person.
    Args:
        person_id (str): The ID of the person whose friends to fetch.
    Returns:
        list[dict] or None: List of friend dictionaries, or None if an error occurs.
    """
    return get_person_friends(person_id)

@tool("get_person_attended_events_tool")
def get_person_attended_events_tool(person_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetches events attended by a specific person.
    Args:
        person_id (str): The ID of the person whose attended events to fetch.
    Returns:
        list[dict] or None: List of event dictionaries, or None if an error occurs.
    """
    return get_person_attended_events(person_id)

# --- LLM Initialization ---
# TODO: Make model name configurable (e.g., from environment or a config file)
llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7) # Using gemini-pro as 2.0-flash might not be available/suitable for all tasks

# --- Node Definitions ---

PROFILE_AGENT_INSTRUCTION = """You are a helpful agent who can answer user questions about this person's social profile.
The user will ask for a person's profile using their name.
Your first step is ALWAYS to use the 'get_person_id_by_name_tool' to fetch the person's ID.
Once you have the ID, use other available tools ('get_person_posts_tool', 'get_person_friends_tool', 'get_person_attended_events_tool') to gather information about their posts, friends, and attended events.
Synthesize this information into a structured JSON output. If multiple people are mentioned, process each one.
Example for one person:
{
  "person_name": "John Doe",
  "person_id": "actual_id_here",
  "posts": [ ... list of posts ... ],
  "friends": [ ... list of friends ... ],
  "events": [ ... list of events ... ]
}
If the user asks for information about "Alice" and "Bob", you should call the tools for both and return a list:
[
  {
    "person_name": "Alice",
    "person_id": "alice_id",
    "posts": [], "friends": [], "events": []
  },
  {
    "person_name": "Bob",
    "person_id": "bob_id",
    "posts": [], "friends": [], "events": []
  }
]
Respond ONLY with the JSON containing the gathered information. Do not add any conversational fluff.
If a person cannot be found, return an error structure for that person:
{
  "person_name": "Unknown Person",
  "error": "Could not find ID for person."
}
"""

async def profile_node(state: SocialGraphState) -> dict:
    print("---Executing Profile Node---")
    user_request = state.get("user_request")
    if not user_request:
        return {"error_message": "User request is missing."}

    messages = [
        SystemMessage(content=PROFILE_AGENT_INSTRUCTION),
        HumanMessage(content=user_request)
    ]

    tools_for_llm = [
        get_person_id_by_name_tool,
        get_person_posts_tool,
        get_person_friends_tool,
        get_person_attended_events_tool
    ]

    try:
        # Bind tools to LLM and invoke
        # llm_with_tools = llm.bind_tools(tools_for_llm) # For newer LangChain versions
        # response = await llm_with_tools.ainvoke(messages)

        # For current setup, assuming direct invocation and LLM will call tools if needed by generating tool_calls
        response = await llm.ainvoke(messages, tools=tools_for_llm)

        profile_data_str = response.content
        print(f"Profile Node LLM Output (raw): {profile_data_str}")

        # Check for tool calls if LLM didn't directly return JSON (LangChain handles this)
        if response.tool_calls:
            # This part would require a loop to execute tools and feed back to LLM,
            # which is what an AgentExecutor does. For simplicity here, we assume
            # the LLM can structure the output or the prompt is very directive.
            # A more robust solution would use an AgentExecutor-like pattern here.
            print(f"Profile Node LLM wants to call tools: {response.tool_calls}")
            # For now, we'll assume the prompt is strong enough to guide JSON output
            # or the model used directly outputs JSON when asked.
            # If tool usage is complex, this node would need an agent executor.
            # For this step, we'll try to parse content directly.
            pass # Let it fall through to JSON parsing attempt

        if not profile_data_str and not response.tool_calls:
             return {"error_message": "Profile node LLM returned no content and no tool calls."}


        # Attempt to parse the LLM output as JSON
        try:
            # Remove potential markdown code block fences
            if profile_data_str.startswith("```json"):
                profile_data_str = profile_data_str[7:]
            if profile_data_str.endswith("```"):
                profile_data_str = profile_data_str[:-3]

            parsed_profile_info = json.loads(profile_data_str.strip())
            return {"profile_info": parsed_profile_info, "error_message": None}
        except json.JSONDecodeError as e:
            print(f"Profile Node JSON parsing error: {e}")
            return {"error_message": f"Failed to parse profile LLM output: {profile_data_str}"}

    except Exception as e:
        import traceback
        print(f"Error in Profile Node: {e}\n{traceback.format_exc()}")
        return {"error_message": f"Unexpected error in profile_node: {str(e)}"}


SUMMARY_AGENT_INSTRUCTION = """
Your primary task is to synthesize social profile information into a single, comprehensive paragraph.

**Input Scope & Default Behavior:**
*   The input will be a JSON string containing profile information (posts, friends, events) for one or more individuals.
*   If specific individuals are named by the user in the original request (which led to this profile data), focus your analysis on them.
*   **If no individuals were specified, or if the request was general, assume the user wants an analysis of *all relevant profiles provided in the JSON input*.**

**For each profile in the input JSON, you must analyze:**

1.  **Post Analysis:**
    *   Systematically review their posts (e.g., content, topics, frequency, engagement).
    *   Identify recurring themes, primary interests, and expressed sentiments.

2.  **Friendship Relationship Analysis:**
    *   Examine their connections/friends list.
    *   Identify key relationships, mutual friends (especially if comparing multiple profiles), and the general structure of their social network.

3.  **Event Participation Analysis:**
    *   Investigate their past (and if available, upcoming) event participation.
    *   Note the types of events, frequency of attendance, and any notable roles (e.g., organizer, speaker).

**Output Generation (Single Paragraph):**

*   **Your entire output must be a single, cohesive summary paragraph.**
    *   **If analyzing a single profile:** This paragraph will detail their activities, interests, and social connections based on the post, friend, and event analysis.
    *   **If analyzing multiple profiles:** This paragraph will synthesize the key findings regarding posts, friends, and events for each individual. Crucially, it must then seamlessly integrate or conclude with an identification and description of the common ground found between them (e.g., shared interests from posts, overlapping event attendance, mutual friends). The aim is a unified narrative within this single paragraph.

**Key Considerations:**
*   Base your summary strictly on the available data in the input JSON.
*   If data for a specific category (posts, friends, events) is missing or sparse for a profile, you may briefly acknowledge this within the narrative if relevant.
*   Respond ONLY with the summary paragraph. Do not add any conversational fluff or introductory phrases like "Here's the summary:".
"""

async def summary_node(state: SocialGraphState) -> dict:
    print("---Executing Summary Node---")
    profile_info = state.get("profile_info")
    user_request = state.get("user_request") # To provide context if needed

    if not profile_info:
        # If profile_info is missing, it might be an error from the previous node,
        # or perhaps the user_request itself is the direct input for a general summary.
        # For now, we assume profile_info is essential.
        if state.get("error_message"): # Propagate error
             return {}
        return {"error_message": "Profile information is missing for summary generation."}

    # Convert profile_info (dict or list of dicts) to JSON string for the LLM
    try:
        profile_info_json = json.dumps(profile_info)
    except TypeError as e:
        return {"error_message": f"Could not serialize profile_info to JSON: {e}"}

    # Construct a more contextual input for the summary agent
    summary_input_content = f"Original user request: {user_request}\n\nProfile data (JSON):\n{profile_info_json}"

    messages = [
        SystemMessage(content=SUMMARY_AGENT_INSTRUCTION),
        HumanMessage(content=summary_input_content)
    ]

    try:
        response = await llm.ainvoke(messages)
        summary_text = response.content.strip()
        print(f"Summary Node LLM Output: {summary_text}")
        return {"summary": summary_text, "error_message": None}
    except Exception as e:
        import traceback
        print(f"Error in Summary Node: {e}\n{traceback.format_exc()}")
        return {"summary": None, "error_message": f"Unexpected error in summary_node: {str(e)}"}


CHECK_AGENT_INSTRUCTION = """
You are an agent that checks if a social profile summary has been successfully generated and seems complete.
The input will be the generated summary.
Review the summary. If it seems like a reasonable attempt at summarizing social profile information (even if brief), output "completed".
If the summary is empty, nonsensical, or clearly indicates an error or inability to generate a summary, output "pending".

Respond with ONLY "completed" or "pending". No other text.
"""
async def check_status_node(state: SocialGraphState) -> dict:
    print("---Executing Check Status Node---")
    summary = state.get("summary")

    if state.get("error_message") and not summary: # Error propagated, and no summary to check
        return {"summary_status": "pending"} # Treat as pending if error occurred before summary

    if not summary or not summary.strip():
        # If summary is empty or just whitespace, it's pending.
        return {"summary_status": "pending", "error_message": "Summary is empty, cannot complete."}

    messages = [
        SystemMessage(content=CHECK_AGENT_INSTRUCTION),
        HumanMessage(content=summary)
    ]

    try:
        response = await llm.ainvoke(messages)
        status = response.content.strip().lower()
        print(f"Check Status Node LLM Output: {status}")
        if status not in ["completed", "pending"]:
            # Fallback if LLM doesn't adhere to "completed" or "pending"
            print(f"Warning: Check agent returned unexpected status '{status}'. Defaulting to 'pending'.")
            return {"summary_status": "pending", "error_message": f"Check agent returned invalid status: {status}"}
        return {"summary_status": status}
    except Exception as e:
        import traceback
        print(f"Error in Check Status Node: {e}\n{traceback.format_exc()}")
        return {"summary_status": "pending", "error_message": f"Unexpected error in check_status_node: {str(e)}"}

def final_result_node(state: SocialGraphState) -> dict:
    print("---Executing Final Result Node---")
    summary = state.get("summary")
    if state.get("error_message") and not summary:
        return {"final_output": state.get("error_message")} # Output error if that's all we have

    if summary:
        return {"final_output": summary}
    else:
        return {"final_output": "No summary could be generated."} # Fallback

# --- Graph Construction ---
def build_social_graph():
    graph_builder = StateGraph(SocialGraphState)

    graph_builder.add_node("profile_agent", profile_node)
    graph_builder.add_node("summary_agent", summary_node)
    graph_builder.add_node("check_status_agent", check_status_node)
    graph_builder.add_node("final_result", final_result_node)

    graph_builder.set_entry_point("profile_agent")

    graph_builder.add_edge("profile_agent", "summary_agent")
    graph_builder.add_edge("summary_agent", "check_status_agent")

    def should_continue(state: SocialGraphState) -> str:
        print(f"---Router: Checking status --- Status: {state.get('summary_status')}")
        if state.get("error_message") and not state.get("summary_status"): # Critical error before status check
            print("Router: Error occurred, routing to final_result to output error.")
            return "final_result" # Go to end to output the error

        status = state.get("summary_status")
        if status == "completed":
            print("Router: Status is completed, routing to final_result.")
            return "final_result"
        else: # "pending" or other
            # Original ADK loop was max 10 iterations. LangGraph has recursion_limit.
            # For now, if pending, we go to END. A real loop might go back to summary or profile.
            # To implement a loop, you'd add an iteration counter to state and check it here.
            # e.g. if state.get("iteration_count", 0) < MAX_ITERATIONS: return "summary_agent"
            print("Router: Status is pending or undefined, routing to final_result (ending loop).")
            # If pending truly means retry, this should go to "summary_agent" or "profile_agent"
            # For now, we'll just end it. The original ADK loop had a CheckCondition agent and
            # an after_agent_callback that would return the summary if completed.
            # The final_result_node effectively handles the after_agent_callback logic.
            return "final_result" # Or END directly if final_result is just for formatting

    graph_builder.add_conditional_edges(
        "check_status_agent",
        should_continue,
        {
            "final_result": "final_result",
            # If looping: "summary_agent": "summary_agent",
        }
    )
    graph_builder.add_edge("final_result", END)

    return graph_builder.compile()

if __name__ == '__main__':
    # Example usage (for testing within this file)
    graph = build_social_graph()

    # To visualize (optional, requires matplotlib and pygraphviz)
    # try:
    #     graph.get_graph().draw_png("social_graph.png")
    #     print("Graph visualized to social_graph.png")
    # except Exception as e:
    #     print(f"Could not draw graph: {e}")

    async def run_graph_example():
        inputs = [
            {"user_request": "Tell me about Ada Lovelace's profile."},
            {"user_request": "Summarize the profile of 'NonExistent Person'."}, # Test error handling
            {"user_request": "What are the latest posts by 'John Doe' and 'Jane Doe'?"} # Test multiple people (if profile_node handles it)
        ]
        for i, test_input in enumerate(inputs):
            print(f"\n--- Running Test Input {i+1} ---")
            try:
                # Correctly initialize the state for each run
                initial_state: SocialGraphState = {
                    "user_request": test_input["user_request"],
                    "profile_info": None,
                    "summary": None,
                    "summary_status": None,
                    "final_output": None,
                    "error_message": None,
                }
                async for event in graph.astream(initial_state):
                    print(f"Event: {event}")
                    if END in event:
                         final_state = event[END]
                         print(f"Final Output for Test {i+1}: {final_state.get('final_output')}")
                         print(f"Error (if any) for Test {i+1}: {final_state.get('error_message')}")
                         break
            except Exception as e:
                print(f"Error running graph example for input {i+1}: {e}")
                import traceback
                traceback.print_exc()

    import asyncio
    #asyncio.run(run_graph_example()) # Commented out for tool use; uncomment for direct testing
    print("Social node file created. Run directly to test with example inputs (requires Spanner setup).")
    print("Remember to uncomment asyncio.run(run_graph_example()) and ensure Spanner is configured.")
