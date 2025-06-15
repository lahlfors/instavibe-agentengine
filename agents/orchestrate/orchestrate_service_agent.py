import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional # List removed as SUPPORTED_CONTENT_TYPES is removed

# LangGraph and application-specific imports
from agents.app.graph_builder import build_graph # The main orchestrator graph
from agents.app.common.graph_state import OrchestratorState # The state definition for the graph

import logging

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__)

class OrchestrateServiceAgent:
    """
    A service agent that uses a LangGraph-based orchestrator
    to process user queries.
    """

    def __init__(self): # Removed remote_agent_addresses_str
        log.info("Initializing OrchestrateServiceAgent with LangGraph orchestrator.")
        # Instantiate the main orchestrator graph.
        # The graph from graph_builder.py encapsulates the entire orchestration logic.
        self.graph = build_graph()
        # ADK runner, agent, user_id are no longer needed here.

    async def async_query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Handles the user's request by invoking the LangGraph orchestrator.
        """
        log.info(f"OrchestrateServiceAgent received query: {query}")

        # Prepare the initial state for the orchestrator graph.
        # Ensure all fields of OrchestratorState are initialized.
        # Pydantic models can be initialized with defaults if not provided.
        initial_state = OrchestratorState(
            user_request=query,
            # Initialize other fields as per OrchestratorState definition,
            # most can be None initially if they are Optional.
            current_task_description=None,
            intermediate_output=None,
            final_output=None,
            session_id=kwargs.get("session_id"), # Pass through session_id if provided
            current_agent_name=None,
            error_message=None,
            route=None
        )

        try:
            # Invoke the graph. A recursion limit is often good practice for LangGraph.
            # The config dictionary is standard for passing such parameters.
            log.debug(f"Invoking graph with initial state: {initial_state.model_dump_json(indent=2)}")
            final_state_dict = await self.graph.ainvoke(
                initial_state.model_dump(), # Pass as dict if OrchestratorState is Pydantic
                config={"recursion_limit": 25}
            )

            # Convert the result dict back to OrchestratorState object to easily access fields
            final_state = OrchestratorState.model_validate(final_state_dict)
            log.debug(f"Graph returned final state: {final_state.model_dump_json(indent=2)}")

            if final_state.error_message:
                log.error(f"Graph execution resulted in an error: {final_state.error_message}")
                return {"output": final_state.final_output, "error": final_state.error_message} # Also include final_output if any

            if final_state.final_output is not None:
                return {"output": final_state.final_output}
            else:
                log.warning("Graph execution finished without a final output or an error message.")
                return {"output": None, "error": "No output or error message produced by the orchestrator."}

        except Exception as e:
            import traceback
            error_msg = f"An unexpected error occurred during orchestrator graph invocation: {str(e)}"
            log.error(f"{error_msg}\n{traceback.format_exc()}")
            return {"output": None, "error": error_msg}

    # Removed SUPPORTED_CONTENT_TYPES and get_processing_message as they are ADK-specific
    # and typically not used when directly invoking a LangGraph application.
    # If a processing message is needed, it can be returned by the caller of async_query.
