import asyncio
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
import logging 
import os
import nest_asyncio # Import nest_asyncio


# Load environment variables from the root .env file
# Place this near the top, before using env vars like API keys
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
MCP_SERVER_URL=os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL", "http://0.0.0.0:8080/sse")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
 
# --- Global variables ---
# Define them first, initialize as None
root_agent: LlmAgent | None = None
mcp_toolset_instance: MCPToolset | None = None # Changed from exit_stack


async def get_tools_async() -> MCPToolset: # Return MCPToolset instance
  """Initializes and returns the MCPToolset."""
  print("Attempting to connect to MCP Filesystem server...")
  # Instantiate MCPToolset directly
  mcp_toolset = MCPToolset(
      connection_params=SseServerParams(url=MCP_SERVER_URL, headers={})
  )
  # Assuming MCPToolset connects on first use or has an explicit connect method if needed.
  # If it has an async init/connect method, it should be awaited here.
  # For now, we assume direct instantiation is sufficient based on the documentation.
  log.info("MCPToolset instance created.")
  return mcp_toolset
 

async def get_agent_async() -> tuple[LlmAgent | None, MCPToolset | None]:
  """
  Asynchronously creates the MCP Toolset and the LlmAgent.

  Returns:
      tuple: (LlmAgent instance, MCPToolset instance for cleanup)
  """
  mcp_toolset = await get_tools_async()

  current_root_agent = LlmAgent(
      model='gemini-2.0-flash', # Adjust model name if needed based on availability
      name='platform_mcp_client_agent', # Corrected agent name
      instruction="""
        You are a friendly and efficient assistant for the Instavibe social app.
        Your primary goal is to help users create posts and register for events using the available tools.

        When a user asks to create a post:
        1.  You MUST identify the **author's name** and the **post text**.
        2.  You MUST determine the **sentiment** of the post.
            - If the user explicitly states a sentiment (e.g., "make it positive", "this is a sad post", "keep it neutral"), use that sentiment. Valid sentiments are 'positive', 'negative', or 'neutral'.
            - **If the user does NOT provide a sentiment, you MUST analyze the post text yourself, infer the most appropriate sentiment ('positive', 'negative', or 'neutral'), and use this inferred sentiment directly for the tool call. Do NOT ask the user to confirm your inferred sentiment. Simply state the sentiment you've chosen as part of a summary if you confirm the overall action.**
        3.  Once you have the `author_name`, `text`, and `sentiment` (either provided or inferred), you will prepare to call the `create_post` tool with these three arguments.

        When a user asks to create an event or register for one:
        1.  You MUST identify the **event name**, the **event date**, and the **attendee's name**.
        2.  For the `event_date`, aim to get it in a structured format if possible (e.g., "YYYY-MM-DDTHH:MM:SSZ" or "tomorrow at 3 PM"). If the user provides a vague date, you can ask for clarification or make a reasonable interpretation. The tool expects a string.
        3.  Once you have the `event_name`, `event_date`, and `attendee_name`, you will prepare to call the `create_event` tool with these three arguments.

        General Guidelines:
        - If any required information for an action (like author_name for a post, or event_name for an event) is missing from the user's initial request, politely ask the user for the specific missing pieces of information.
        - Before executing an action (calling a tool), you can optionally provide a brief summary of what you are about to do (e.g., "Okay, I'll create a post for [author_name] saying '[text]' with a [sentiment] sentiment."). This summary should include the inferred sentiment if applicable, but it should not be phrased as a question seeking validation for the sentiment.
        - Use only the provided tools. Do not try to perform actions outside of their scope.

      """,
        tools=[mcp_toolset], # Pass the MCPToolset instance as a list
  )
  print("LlmAgent created.")

  # Return both the agent and the mcp_toolset needed for cleanup
  return current_root_agent, mcp_toolset


async def initialize():
   """Initializes the global root_agent and mcp_toolset_instance."""
   global root_agent, mcp_toolset_instance # Updated global variable name
   if root_agent is None:
       log.info("Initializing agent...")
       agent_instance, toolset_instance = await get_agent_async()
       if agent_instance:
           root_agent = agent_instance
           mcp_toolset_instance = toolset_instance # Store the toolset instance
           log.info("Agent initialized successfully.")
       else:
           log.error("Agent initialization failed.")
       
   else:
       log.info("Agent already initialized.")

def _cleanup_sync():
    """Synchronous wrapper to attempt async cleanup of MCPToolset."""
    global mcp_toolset_instance # Ensure we're referencing the global
    if mcp_toolset_instance:
        log.info("Attempting to close MCP connection via atexit...")
        try:
            # MCPToolset.close() is an async method
            asyncio.run(mcp_toolset_instance.close())
            log.info("MCP connection closed via atexit.")
        except Exception as e:
            log.error(f"Error during atexit MCP toolset cleanup: {e}", exc_info=True)
        finally:
            mcp_toolset_instance = None # Clear the global instance


nest_asyncio.apply()

log.info("Running agent initialization at module level using asyncio.run()...")
try:
    asyncio.run(initialize())
    log.info("Module level asyncio.run(initialize()) completed.")
except RuntimeError as e:
    log.error(f"RuntimeError during module level initialization (likely nested loops): {e}", exc_info=True)
except Exception as e:
    log.error(f"Unexpected error during module level initialization: {e}", exc_info=True)

