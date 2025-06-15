import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional
import logging

# Removed: from common.task_manager import AgentTaskManager
from .social_node import build_social_graph, SocialGraphState # Import graph builder and state type

# Load environment variables from the root .env file.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logging.info("SocialAgent: .env file loaded.")
else:
    logging.warning(f"SocialAgent: .env file not found at {dotenv_path}.")


class SocialAgent: # Removed AgentTaskManager inheritance
  """
  An agent that handles social profile analysis by orchestrating an internal LangGraph.
  """

  def __init__(self):
    # super().__init__() # Removed call to AgentTaskManager's init
    # Build and compile the graph when the agent is initialized.
    # The graph is stateless from the perspective of the SocialAgent instance itself;
    # state is passed per invocation to the internal graph.
    self.graph = build_social_graph()
    logging.info("SocialAgent initialized, social_profile_graph built and compiled.")

  # get_processing_message method removed.

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """
    Handles the user's request for social profile analysis by invoking its internal LangGraph.

    Args:
        query: The user's request, typically containing information for social analysis.
        **kwargs: Additional keyword arguments (currently not used).

    Returns:
        A dictionary containing "output" with the analysis result or "error" with an error message.
    """
    logging.info(f"SocialAgent received query for async_query: '{query[:100]}...'")

    # Prepare the initial state for the internal graph.
    # Ensure all fields defined in SocialGraphState are initialized, typically to None or a default.
    initial_state: SocialGraphState = {
        "user_request": query,
        "profile_info": None,
        "summary": None,
        "summary_status": None, # This field seems specific to the internal graph's state
        "final_output": None,   # This will be the primary result passed back to orchestrator
        "error_message": None,  # Errors from the internal graph
    }
    # If SocialGraphState is a Pydantic model, instantiation might look like:
    # initial_state = SocialGraphState(user_request=query)

    try:
      logging.debug(f"SocialAgent invoking internal graph with initial state: {initial_state}")
      # Invoke the internal graph with the initial state.
      # ainvoke returns the final state of this internal graph.
      final_state_internal_graph = await self.graph.ainvoke(initial_state)
      logging.debug(f"SocialAgent received final state from internal graph: {final_state_internal_graph}")

      if final_state_internal_graph:
        # Extract 'final_output' and 'error_message' from the internal graph's state.
        # These are the fields relevant to the orchestrator.
        output = final_state_internal_graph.get("final_output")
        error = final_state_internal_graph.get("error_message")

        if error and not output:
             logging.warning(f"SocialAgent internal graph finished with error: {error}")
             return {"output": None, "error": str(error)}
        elif output is not None: # Check for not None, as output could be an empty string or other valid non-error value
             logging.info(f"SocialAgent internal graph finished with output: {str(output)[:100]}...")
             return {"output": str(output)}
        elif error: # Output might be None, but an error was also set
             logging.warning(f"SocialAgent internal graph finished with error (and no primary output): {error}")
             return {"output": None, "error": str(error)}
        else:
             logging.warning("SocialAgent internal graph execution finished with no clear output or error message.")
             return {"output": None, "error": "Social analysis finished with no specific output or error."}
      else:
        logging.error("SocialAgent: Internal graph execution failed to return a final state.")
        return {"output": None, "error": "Social analysis graph execution failed to return a final state."}

    except Exception as e:
      logging.error(f"Error during SocialAgent's internal graph invocation: {e}", exc_info=True)
      return {"output": None, "error": f"An unexpected error occurred during social analysis: {str(e)}"}