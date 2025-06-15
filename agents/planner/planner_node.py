import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv

from agents.app.common.graph_state import OrchestratorState
from agents.planner.planner_agent import PlannerAgent # Import the refactored PlannerAgent

# Load environment variables from the root .env file.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path) # project_core .env is repository root
    logging.info("Planner Node: .env file loaded.")
else:
    logging.warning(f"Planner Node: .env file not found at {dotenv_path}.")


logger = logging.getLogger(__name__)

# The INSTRUCTION_PROMPT, Pydantic models (LocationActivity, FunPlan, PlannerOutput),
# and GoogleSearchAPIWrapper/tool setup are now part of PlannerAgent internally.
# They are removed from this file.

async def execute_planner_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes the planner agent based on the current task description.
    The PlannerAgent itself now handles LLM calls, prompt construction, and tool use.
    """
    logger.info("---Executing Planner Node---")
    # Access Pydantic model fields using attribute access
    task_description = state.current_task_description
    current_agent_name = "planner" # Set current agent name

    if not task_description:
        logger.warning("Planner Node: No task description provided in the current state.")
        return {
            "error_message": "Planner Node: No task description provided.",
            "current_agent_name": current_agent_name,
            "intermediate_output": None, # Ensure intermediate_output is explicitly set to None
        }

    try:
        # PlannerAgent instantiation should be lightweight.
        agent = PlannerAgent()
        logger.info(f"Planner Node: Querying PlannerAgent with task: '{task_description[:100]}...'")
        response = await agent.async_query(task_description)

        output = response.get("output")
        error = response.get("error")

        if error:
            logger.error(f"Planner Node: PlannerAgent execution resulted in an error: {error}")
            return {
                "intermediate_output": output, # Could be None or partial data from a failed plan
                "error_message": str(error),
                "current_agent_name": current_agent_name
            }

        logger.info(f"Planner Node: PlannerAgent executed successfully. Output snippet: {str(output)[:200]}...")
        return {
            "intermediate_output": output,
            "error_message": None, # Explicitly clear any previous error
            "current_agent_name": current_agent_name
        }

    except Exception as e:
        logger.error(f"Planner Node: An unexpected error occurred during execution - {e}", exc_info=True)
        return {
            "intermediate_output": None, # Ensure intermediate_output is None in case of unexpected error
            "error_message": f"An unexpected error occurred in the Planner Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
