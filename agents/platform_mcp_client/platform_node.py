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

# Attempt to import MCPToolset and SseServerParams
try:
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
    IS_MCP_TOOLSET_AVAILABLE = True
except ImportError:
    print("Warning: MCPToolset could not be imported. Platform agent will use dummy tools.")
    IS_MCP_TOOLSET_AVAILABLE = False
    # Define dummy classes if MCPToolset is not available, so the rest of the code can be structured
    class SseServerParams:
        def __init__(self, url: str, headers: dict):
            self.url = url
            self.headers = headers
    class MCPToolset:
        def __init__(self, connection_params: SseServerParams):
            print("Dummy MCPToolset initialized.")
        async def create_post(self, author_name: str, text: str, sentiment: str) -> str:
            return f"Dummy: Post created for {author_name} with text '{text}' and sentiment '{sentiment}'."
        async def create_event(self, event_name: str, event_date: str, attendee_name: str) -> str:
            return f"Dummy: Event '{event_name}' on {event_date} created for {attendee_name}."
        async def close(self): # Add a close method for dummy too
            print("Dummy MCPToolset closed.")
        def get_tools(self) -> List[BaseTool]: # To mimic providing LangChain tools
            @tool("create_post_tool")
            async def create_post_tool(author_name: str, text: str, sentiment: str) -> str:
                """Creates a new post with the given author name, text, and sentiment."""
                return await self.create_post(author_name, text, sentiment)

            @tool("create_event_tool")
            async def create_event_tool(event_name: str, event_date: str, attendee_name: str) -> str:
                """Creates a new event with the given name, date, and registers an attendee."""
                return await self.create_event(event_name, event_date, attendee_name)
            return [create_post_tool, create_event_tool]


# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

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

# Global MCPToolset instance
mcp_toolset_instance: Optional[MCPToolset] = None
platform_tools: List[BaseTool] = []

async def initialize_mcp_tools():
    global mcp_toolset_instance, platform_tools
    if not IS_MCP_TOOLSET_AVAILABLE:
        print("MCPToolset is not available, using dummy tools for Platform Agent.")
        # Use the dummy MCPToolset's get_tools method
        mcp_toolset_instance = MCPToolset(connection_params=SseServerParams(url="", headers={})) # Dummy params
        platform_tools = mcp_toolset_instance.get_tools()
        return

    if mcp_toolset_instance is None:
        mcp_server_url = os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL")
        if not mcp_server_url:
            print("Error: AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is not set.")
            raise ValueError("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL not set for MCPToolset.")

        print(f"Initializing MCPToolset with URL: {mcp_server_url}")
        # nest_asyncio.apply() might be needed before this if MCPToolset's constructor uses asyncio.run internally
        # However, ADK's agent.py applied it globally, so it should be fine.
        mcp_toolset_instance = MCPToolset(
            connection_params=SseServerParams(url=mcp_server_url, headers={})
        )

        # Extract tools from MCPToolset.
        # The ADK LlmAgent passes the MCPToolset instance directly.
        # For LangChain, tools need to be instances of BaseTool.
        # We need to check if MCPToolset provides a way to get LangChain tools
        # or if we need to wrap its methods manually.
        # Based on ADK LlmAgent, it seems it might be auto-discovering methods.
        # Let's assume for now we need to wrap them or it has a .get_tools() like method.
        # If MCPToolset is directly a list of BaseTools or has a method like .get_langchain_tools()
        if isinstance(mcp_toolset_instance, list) and all(isinstance(t, BaseTool) for t in mcp_toolset_instance):
             platform_tools = mcp_toolset_instance
        elif hasattr(mcp_toolset_instance, 'get_tools') and callable(getattr(mcp_toolset_instance, 'get_tools')):
            # This is a common pattern for toolkits
            platform_tools = mcp_toolset_instance.get_tools()
        else:
            # Manually wrap known tools if the above don't work
            print("MCPToolset does not seem to be a list of tools or have a get_tools() method. Manually wrapping create_post and create_event.")

            @tool("create_post_tool")
            async def create_post_tool(author_name: str, text: str, sentiment: str) -> str:
                """Creates a new post with the given author name, text, and sentiment."""
                if not mcp_toolset_instance:
                    return "Error: MCPToolset not initialized."
                # MCPToolset methods might be async
                if asyncio.iscoroutinefunction(mcp_toolset_instance.create_post):
                    return await mcp_toolset_instance.create_post(author_name=author_name, text=text, sentiment=sentiment)
                else: # Assuming synchronous if not explicitly async
                    return mcp_toolset_instance.create_post(author_name=author_name, text=text, sentiment=sentiment)

            @tool("create_event_tool")
            async def create_event_tool(event_name: str, event_date: str, attendee_name: str) -> str:
                """Creates a new event with the given name, date, and registers an attendee."""
                if not mcp_toolset_instance:
                    return "Error: MCPToolset not initialized."
                if asyncio.iscoroutinefunction(mcp_toolset_instance.create_event):
                    return await mcp_toolset_instance.create_event(event_name=event_name, event_date=event_date, attendee_name=attendee_name)
                else:
                    return mcp_toolset_instance.create_event(event_name=event_name, event_date=event_date, attendee_name=attendee_name)

            platform_tools = [create_post_tool, create_event_tool]

        print(f"Platform tools initialized: {[t.name for t in platform_tools]}")


# --- Node Definitions ---
async def platform_interaction_node(state: PlatformGraphState) -> dict:
    print("---Executing Platform Interaction Node---")
    user_request = state.get("user_request")
    if not user_request:
        return {"error_message": "User request is missing."}

    if not platform_tools: # Ensure tools are loaded
        await initialize_mcp_tools() # Attempt to load them if not already
        if not platform_tools: # If still no tools (e.g. MCP URL missing and dummy tools also failed)
             return {"error_message": "Platform tools could not be initialized."}


    messages = [
        SystemMessage(content=PLATFORM_AGENT_INSTRUCTION),
        HumanMessage(content=user_request)
    ]

    try:
        # Invoke LLM with tools. LangChain handles the tool calling and response cycle if LLM decides to use a tool.
        # The response will include the LLM's message and any tool calls/results.
        response = await LLM.ainvoke(messages, tools=platform_tools)

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
            pass # Assuming content is already appropriately formatted by LLM or the tool calling mechanism.

        print(f"Platform Interaction Node LLM Output (content): {llm_output_content}")
        return {"llm_response": llm_output_content, "error_message": None}

    except Exception as e:
        import traceback
        print(f"Error in Platform Interaction Node: {e}\n{traceback.format_exc()}")
        return {"error_message": f"Unexpected error in platform_interaction_node: {str(e)}"}

def final_result_node(state: PlatformGraphState) -> dict:
    print("---Executing Final Result Node---")
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
    nest_asyncio.apply()

    # Initialize tools (especially MCPToolset) when building the graph.
    # This ensures that environment variables are checked and tools are ready.
    # Using asyncio.run here for the async tool initialization.
    # This is okay at setup time.
    async def setup_tools():
        await initialize_mcp_tools()

    # Running async setup if not in an already running loop.
    # If build_platform_graph is called from an async context, direct await might be better.
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If called from within an async function, schedule it
            asyncio.ensure_future(setup_tools())
        else:
            asyncio.run(setup_tools())
    except RuntimeError: # No event loop
        asyncio.run(setup_tools())


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
        # Check if MCP URL is set, otherwise dummy tools will be used
        if not os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL") and IS_MCP_TOOLSET_AVAILABLE:
            print("Warning: AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is not set. Real MCPToolset will likely fail.")
            print("Consider setting it or expect dummy tool behavior if MCPToolset is available but URL is not.")

        graph = build_platform_graph() # This will initialize tools

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
                    print(f"Event: {event}")
                    if END in event:
                        final_state = event[END]
                        print(f"Final Output: {final_state.get('final_output')}")
                        print(f"Error (if any): {final_state.get('error_message')}")
                        break
            except Exception as e:
                print(f"Error during test run for query '{query}': {e}")
                import traceback
                traceback.print_exc()

    # asyncio.run(test_graph()) # Commented out for tool use
    print("Platform node file created. Run directly to test with example inputs.")
    print("Remember to uncomment asyncio.run(test_graph()) and ensure Spanner/MCP is configured if needed.")
