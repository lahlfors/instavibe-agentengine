import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv

from agents.app.common.graph_state import OrchestratorState
from agents.planner.planner_agent import PlannerAgent # Import the refactored PlannerAgent

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

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
    task_description = state.get("current_task_description")
    current_agent_name = "planner"

    if not task_description:
        logger.error("Planner Node: No task description provided.")
        return {
            "error_message": "No task description provided for Planner Agent.",
            "current_agent_name": current_agent_name
        }

    try:
        agent = PlannerAgent() # PlannerAgent initializes its own LLM, prompt, tools
        logger.info(f"Planner Node: Querying PlannerAgent with task: {task_description}")
        # PlannerAgent.async_query is an async method
        response = await agent.async_query(task_description)

        output = response.get("output")
        error = response.get("error")

        if error:
            logger.error(f"Planner Node: PlannerAgent returned an error: {error}")
            # Return both intermediate_output (if any) and the error
            return {"intermediate_output": output, "error_message": str(error), "current_agent_name": current_agent_name}

        logger.info(f"Planner Node: PlannerAgent returned output: {str(output)[:500]}...") # Log snippet
        return {"intermediate_output": output, "error_message": None, "current_agent_name": current_agent_name}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Planner Node: Unexpected error - {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the Planner Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
