import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional

from .social_node import build_social_graph, SocialGraphState # Import graph builder and state type

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class SocialAgent:
  """An agent that handles social profile analysis using LangGraph."""

  def __init__(self):
    # Build and compile the graph when the agent is initialized.
    # The graph is stateless from the perspective of the SocialAgent instance itself,
    # state is passed per invocation.
    self.graph = build_social_graph()
    # No _agent, _runner, or _user_id needed anymore.

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """Handles the user's request for social profile analysis using the LangGraph."""

    # Prepare the initial state for the graph.
    # All fields must be present as defined in SocialGraphState, even if None initially.
    initial_state: SocialGraphState = {
        "user_request": query,
        "profile_info": None,
        "summary": None,
        "summary_status": None,
        "final_output": None,
        "error_message": None,
        # "iteration_count": 0 # If using iteration control within the graph
    }

    try:
      print(f"SocialAgent invoking graph with initial state: {initial_state}")
      # Invoke the graph with the initial state.
      # ainvoke returns the final state of the graph.
      final_state = await self.graph.ainvoke(initial_state)
      print(f"SocialAgent received final state from graph: {final_state}")

      if final_state:
        output = final_state.get("final_output")
        error = final_state.get("error_message")

        if error and not output: # If there's an error and no primary output
            # Prefer error message as output if final_output is None or empty
             return {"output": None, "error": str(error)}
        elif output:
             return {"output": str(output)} # Ensure output is string if not None
        else: # No specific output, no specific error, but something unexpected
             return {"output": None, "error": "Graph execution finished with no clear output or error."}
      else:
        # This case should ideally not be reached if the graph is correctly structured to always return a state.
        return {"output": None, "error": "Graph execution failed to return a final state."}

    except Exception as e:
      import traceback
      print(f"Error during SocialAgent graph invocation: {e}\n{traceback.format_exc()}")
      return {"output": None, "error": f"An unexpected error occurred during social analysis: {str(e)}"}