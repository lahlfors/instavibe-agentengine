import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv

from agents.app.common.graph_state import OrchestratorState
from agents.app.common.a2a_client import A2AClient # Import A2AClient
# from agents.planner.planner_agent import PlannerAgent # Import the refactored PlannerAgent - No longer needed

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logger = logging.getLogger(__name__)

a2a_client_instance = A2AClient() # Instantiate A2AClient

# The INSTRUCTION_PROMPT, Pydantic models (LocationActivity, FunPlan, PlannerOutput),
# and GoogleSearchAPIWrapper/tool setup are now part of PlannerAgent internally.
# They are removed from this file.

async def execute_planner_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes the planner agent based on the current task description via A2A call.
    """
    logger.info("---Executing Planner Node (A2A)---")
    task_description = state.get("current_task_description")
    current_agent_name = "planner"

    if not task_description:
        logger.error("Planner Node: No task description provided.")
        return {
            "error_message": "No task description provided for Planner Agent.",
            "current_agent_name": current_agent_name
        }

    try:
        # agent = PlannerAgent() # PlannerAgent initializes its own LLM, prompt, tools - Removed
        logger.info(f"Planner Node: Invoking Planner Agent via A2A with task: {task_description}")

        response = await a2a_client_instance.invoke_agent(
            agent_name="planner",
            query=task_description,
            session_id=state.get("session_id")
        )

        output = response.get("output") # A2AClient returns a dict with "output" and "error" keys
        error = response.get("error")

        if error:
            logger.error(f"Planner Node: A2A call to Planner Agent returned an error: {error}")
            return {"intermediate_output": output, "error_message": str(error), "current_agent_name": current_agent_name}

        logger.info(f"Planner Node: A2A call to Planner Agent succeeded. Output: {str(output)[:500]}...") # Log snippet
        return {"intermediate_output": output, "error_message": None, "current_agent_name": current_agent_name}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Planner Node: Unexpected error during A2A call - {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the Planner Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
