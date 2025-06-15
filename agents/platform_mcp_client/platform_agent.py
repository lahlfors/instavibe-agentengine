import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional

# Assuming AgentWithTaskManager is a custom base class or similar to AgentTaskManager
# If it's specific to ADK runners, it might need adjustment or replacement.
# For now, let's assume it's compatible or a simple base class.
from common.task_manager import AgentWithTaskManager # Or common.task_manager.AgentTaskManager if AgentWithTaskManager is not the one
from .platform_node import build_platform_graph, PlatformGraphState # Import graph builder and state type

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class PlatformAgent(AgentWithTaskManager):
  """An agent that posts events and messages to Instavibe using LangGraph."""

  def __init__(self):
    super().__init__()
    # Build and compile the graph when the agent is initialized.
    # The MCP server URL is read from ENV within build_platform_graph.
    self.graph = build_platform_graph()
    # No _agent, _runner, or _user_id needed from ADK.

  def get_processing_message(self) -> str:
      return "Processing the Instavibe post/event request with LangGraph..."

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """Handles the user's request for platform actions using the LangGraph."""

    initial_state: PlatformGraphState = {
        "user_request": query,
        "llm_response": None,
        "final_output": None,
        "error_message": None,
    }

    try:
      print(f"PlatformAgent invoking graph with initial state: {initial_state}")
      # Invoke the graph with the initial state.
      final_state = await self.graph.ainvoke(initial_state)
      print(f"PlatformAgent received final state from graph: {final_state}")

      if final_state:
        output = final_state.get("final_output")
        error = final_state.get("error_message")

        if error and not output:
             return {"output": None, "error": str(error)}
        elif output:
             return {"output": str(output)}
        else:
             return {"output": None, "error": "Graph execution finished with no clear output or error."}
      else:
        return {"output": None, "error": "Graph execution failed to return a final state."}

    except Exception as e:
      import traceback
      error_msg = f"An unexpected error occurred during platform agent graph invocation: {str(e)}"
      print(f"{error_msg}\n{traceback.format_exc()}")
      return {"output": None, "error": error_msg}