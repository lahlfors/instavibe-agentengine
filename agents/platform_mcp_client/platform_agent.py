import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional

# Assuming AgentWithTaskManager is a custom base class or similar to AgentTaskManager
# If it's specific to ADK runners, it might need adjustment or replacement.
import logging

# Removed: from common.task_manager import AgentWithTaskManager
from .platform_node import build_platform_graph, PlatformGraphState # Import graph builder and state type

# Load environment variables from the root .env file.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logging.info("PlatformAgent: .env file loaded.")
else:
    logging.warning(f"PlatformAgent: .env file not found at {dotenv_path}.")


class PlatformAgent: # Removed AgentWithTaskManager inheritance
  """
  An agent that posts events and messages to a platform (e.g., Instavibe)
  by orchestrating an internal LangGraph.
  """

  def __init__(self):
    # super().__init__() # Removed call to AgentWithTaskManager's init
    # Build and compile the graph when the agent is initialized.
    # The MCP server URL (or other platform specifics) is typically read from ENV
    # within build_platform_graph or its components.
    self.graph = build_platform_graph()
    logging.info("PlatformAgent initialized, platform_graph built and compiled.")

  # get_processing_message method removed.

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """
    Handles the user's request for platform actions by invoking its internal LangGraph.

    Args:
        query: The user's request, detailing the action to be performed on the platform.
        **kwargs: Additional keyword arguments (currently not used).

    Returns:
        A dictionary containing "output" with the result of the platform action
        or "error" with an error message.
    """
    logging.info(f"PlatformAgent received query for async_query: '{query[:100]}...'")

    # Prepare the initial state for the internal graph.
    initial_state: PlatformGraphState = {
        "user_request": query,
        "llm_response": None, # Assuming platform_node might use an LLM for formatting/confirmation
        "final_output": None, # Result from the platform interaction
        "error_message": None, # Errors from the internal graph
    }
    # If PlatformGraphState is a Pydantic model, instantiation might look like:
    # initial_state = PlatformGraphState(user_request=query)

    try:
      logging.debug(f"PlatformAgent invoking internal graph with initial state: {initial_state}")
      # Invoke the internal graph with the initial state.
      final_state_internal_graph = await self.graph.ainvoke(initial_state)
      logging.debug(f"PlatformAgent received final state from internal graph: {final_state_internal_graph}")

      if final_state_internal_graph:
        output = final_state_internal_graph.get("final_output")
        error = final_state_internal_graph.get("error_message")

        if error and not output:
             logging.warning(f"PlatformAgent internal graph finished with error: {error}")
             return {"output": None, "error": str(error)}
        elif output is not None:
             logging.info(f"PlatformAgent internal graph finished with output: {str(output)[:100]}...")
             return {"output": str(output)}
        elif error: # Output might be None, but an error was also set
             logging.warning(f"PlatformAgent internal graph finished with error (and no primary output): {error}")
             return {"output": None, "error": str(error)}
        else:
             logging.warning("PlatformAgent internal graph execution finished with no clear output or error message.")
             return {"output": None, "error": "Platform action finished with no specific output or error."}
      else:
        logging.error("PlatformAgent: Internal graph execution failed to return a final state.")
        return {"output": None, "error": "Platform action graph execution failed to return a final state."}

    except Exception as e:
      error_msg = f"An unexpected error occurred during PlatformAgent's internal graph invocation: {str(e)}"
      logging.error(error_msg, exc_info=True)
      return {"output": None, "error": error_msg}