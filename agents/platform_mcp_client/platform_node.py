import os
import json
import asyncio
from typing import TypedDict, Optional, List, Dict, Any
from dotenv import load_dotenv

import nest_asyncio

from langchain_core.tools import tool, BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from .mcp_client import MCPClient # Import the new client

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# --- Logger ---
logger = logging.getLogger(__name__)

# --- State Definition ---
class PlatformGraphState(TypedDict):
    user_request: str
    llm_response: Optional[Any] # Can be LLM text or tool call results
    final_output: Optional[str]
    error_message: Optional[str]

# --- LLM and Tool Initialization ---
LLM = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7) # Using gemini-pro

PLATFORM_AGENT_INSTRUCTION = """
You are a friendly and efficient assistant for the Instavibe social app.
Your primary goal is to help users create posts and register for events using the available tools.

When a user asks to create a post:
1.  You MUST identify the **author's name** and the **post text**.
2.  You MUST determine the **sentiment** of the post.
    - If the user explicitly states a sentiment (e.g., "make it positive", "this is a sad post", "keep it neutral"), use that sentiment. Valid sentiments are 'positive', 'negative', or 'neutral'.
    - **If the user does NOT provide a sentiment, you MUST analyze the post text yourself, infer the most appropriate sentiment ('positive', 'negative', or 'neutral'), and use this inferred sentiment directly for the tool call. Do NOT ask the user to confirm your inferred sentiment. Simply state the sentiment you've chosen as part of a summary if you confirm the overall action.**
3.  Once you have the `author_name`, `text`, and `sentiment` (either provided or inferred), you will prepare to call the `create_post_tool` with these three arguments.

When a user asks to create an event or register for one:
1.  You MUST identify the **event name**, the **event date**, and the **attendee's name**.
2.  For the `event_date`, aim to get it in a structured format if possible (e.g., "YYYY-MM-DDTHH:MM:SSZ" or "tomorrow at 3 PM"). If the user provides a vague date, you can ask for clarification or make a reasonable interpretation. The tool expects a string.
3.  Once you have the `event_name`, `event_date`, and `attendee_name`, you will prepare to call the `create_event_tool` with these three arguments.

General Guidelines:
- If any required information for an action (like author_name for a post, or event_name for an event) is missing from the user's initial request, politely ask the user for the specific missing pieces of information.
- Before executing an action (calling a tool), you can optionally provide a brief summary of what you are about to do (e.g., "Okay, I'll create a post for [author_name] saying '[text]' with a [sentiment] sentiment."). This summary should include the inferred sentiment if applicable, but it should not be phrased as a question seeking validation for the sentiment.
- Use only the provided tools. Do not try to perform actions outside of their scope.
- If you use a tool, the observation will be the direct result from the tool. Present this result clearly to the user. If the tool indicates success, confirm the action. If it indicates failure or an error, inform the user.
"""

# Global list to hold tools, populated by build_platform_graph
platform_tools_global: List[BaseTool] = []


# --- Node Definitions ---
async def platform_interaction_node(state: PlatformGraphState) -> dict:
    logger.info("---Executing Platform Interaction Node---")
    user_request = state.get("user_request")
    if not user_request:
        logger.error("Platform Interaction Node: User request is missing.")
        return {"error_message": "User request is missing."}

    if not platform_tools_global:
         logger.error("Platform Interaction Node: Platform tools not initialized. MCPClient might have failed or returned no tools.")
         return {"error_message": "Platform tools could not be initialized via MCPClient."}

    messages = [
        SystemMessage(content=PLATFORM_AGENT_INSTRUCTION),
        HumanMessage(content=user_request)
    ]

    try:
        # Invoke LLM with tools. LangChain handles the tool calling and response cycle if LLM decides to use a tool.
        # The response will include the LLM's message and any tool calls/results.
        response = await LLM.ainvoke(messages, tools=platform_tools_global)

        # The 'content' of the response is the LLM's textual answer.
        # If a tool was called, LangChain's default agent executors would typically handle
        # the loop of calling tool -> getting observation -> feeding back to LLM.
        # With a direct .ainvoke and tools, the 'response' object itself might contain tool_calls.
        # If response.tool_calls is present, it means LLM wants to use a tool.
        # For a simple graph, we might not implement the full agent loop here.
        # The prompt guides the LLM to summarize or directly use tool output.

        llm_output_content = response.content
        if response.tool_calls:
            # This indicates the LLM decided to use a tool.
            # For simplicity in this single interaction node, we are not building a full agent executor loop here.
            # The LangChain `ChatGoogleGenerativeAI` with `tools` argument should handle
            # executing the tool and returning its output as part of the `AIMessage` in `response.content`
            # or in `response.additional_kwargs['tool_calls']` if further processing is needed.
            # Often, the tool's output is directly incorporated into the `response.content` by the LLM.
            print(f"LLM initiated tool calls: {response.tool_calls}")
            # If LangChain's default tool handling with `ainvoke(tools=...)` doesn't automatically
            # place tool results into `response.content` as expected by the prompt, this node
            # would need to be more complex (like an AgentExecutor step).
            # For now, we assume the LLM's response content will be sufficient.
            # If `response.content` is empty and `tool_calls` exist, it implies the LLM expects the human/system to run them.
            # However, `ChatGoogleGenerativeAI().ainvoke(tools=...)` should handle this.
            pass

        logger.info(f"Platform Interaction Node LLM Output (content): {llm_output_content[:200]}...") # Log snippet
        return {"llm_response": llm_output_content, "error_message": None}

    except Exception as e:
        import traceback
        logger.error(f"Error in Platform Interaction Node: {e}\n{traceback.format_exc()}")
        return {"error_message": f"Unexpected error in platform_interaction_node: {str(e)}"}

def final_result_node(state: PlatformGraphState) -> dict:
    logger.info("---Executing Final Result Node---")
    if state.get("error_message"):
        # If an error occurred upstream, that's our final output (as error)
        return {"final_output": state.get("error_message")}

    llm_response = state.get("llm_response")
    if llm_response:
        # Assuming llm_response is the string content to be returned.
        # If it was a complex object (e.g. AIMessage with tool calls), it should be processed before this node.
        return {"final_output": str(llm_response)}
    else:
        return {"final_output": "No response generated by the platform agent."}

# --- Graph Construction ---
def build_platform_graph():
    # Apply nest_asyncio: ADK's agent.py did this globally.
    # It's important if MCPToolset or other components use asyncio.run in a running loop.
    nest_asyncio.apply() # Ensure this is called if not already globally managed

    # Initialize MCPClient and get tools
    logger.info("build_platform_graph: Initializing MCPClient...")
    mcp_client_instance = MCPClient() # Instantiate client

    global platform_tools_global # Declare intent to modify global
    platform_tools_global = mcp_client_instance.get_langchain_tools()

    if not platform_tools_global:
        logger.warning("build_platform_graph: MCPClient returned no tools. Platform agent might not function as expected.")
    else:
        logger.info(f"build_platform_graph: Tools loaded from MCPClient: {[t.name for t in platform_tools_global]}")

    # IMPORTANT: Consider MCPClient's lifecycle. If it holds connections (like real MCPToolset),
    # it might need to be closed. For a persistent service, MCPClient could be a singleton
    # managed outside the graph build, or build_platform_graph could return the client
    # instance for later cleanup. For now, it's created and tools are extracted per build.

    graph_builder = StateGraph(PlatformGraphState)

    graph_builder.add_node("platform_interaction_node", platform_interaction_node)
    graph_builder.add_node("final_result_node", final_result_node)

    graph_builder.set_entry_point("platform_interaction_node")
    graph_builder.add_edge("platform_interaction_node", "final_result_node")
    graph_builder.add_edge("final_result_node", END)

    return graph_builder.compile()

if __name__ == '__main__':
    # This block is for testing within this file.
    # Ensure AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is set in your .env file if using real MCPToolset.

    print("Platform Node File - Main Execution (for testing)")
    # To test, you would need to run an async function.
    # Example:
    async def test_graph():
        graph = build_platform_graph() # This will initialize tools via MCPClient

        # Log whether real or dummy tools are expected based on MCPClient's own logging
        # (MCPClient logs this during its initialization)
        logger.info("Test_graph: build_platform_graph() completed. Refer to MCPClient logs for tool status (real/dummy).")

        test_queries = [
            "Please create a post for author 'Alice' with text 'Hello world from LangGraph!' and make it positive.",
            "Register 'Bob' for the event 'Tech Meetup' happening tomorrow at 3 PM.",
            "What can you do?" # A general query
        ]

        for query in test_queries:
            print(f"\n--- Testing Query: {query} ---")
            initial_state: PlatformGraphState = {
                "user_request": query,
                "llm_response": None,
                "final_output": None,
                "error_message": None,
            }
            try:
                async for event in graph.astream(initial_state):
                    logger.info(f"Event: {event}")
                    if END in event:
                        final_state = event[END]
                        logger.info(f"Final Output: {final_state.get('final_output')}")
                        logger.info(f"Error (if any): {final_state.get('error_message')}")
                        break
            except Exception as e:
                logger.error(f"Error during test run for query '{query}': {e}", exc_info=True)
                import traceback
                traceback.print_exc() # Still useful for console debugging

    # asyncio.run(test_graph()) # Commented out for tool use
    logger.info("Platform node file created. Run directly to test with example inputs.")
    logger.info("Remember to uncomment asyncio.run(test_graph()) and ensure Spanner/MCP is configured if needed.")

```
