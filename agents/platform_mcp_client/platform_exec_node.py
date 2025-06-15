import logging
from typing import Dict, Any
from agents.app.common.graph_state import OrchestratorState
from agents.platform_mcp_client.platform_agent import PlatformAgent

logger = logging.getLogger(__name__)

async def execute_platform_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes the platform agent based on the current task description.
    """
    logger.info("---Executing Platform Node---")
    # Access Pydantic model fields using attribute access
    task_description = state.current_task_description
    current_agent_name = "platform" # Set current agent name

    if not task_description:
        logger.warning("Platform Node: No task description provided in the current state.")
        return {
            "error_message": "Platform Node: No task description provided.",
            "current_agent_name": current_agent_name,
            "intermediate_output": None, # Ensure intermediate_output is explicitly set to None
        }

    try:
        # Agent instantiation should be lightweight.
        agent = PlatformAgent()
        logger.info(f"Platform Node: Querying PlatformAgent with task: '{task_description[:100]}...'")
        response = await agent.async_query(task_description)

        output = response.get("output")
        error = response.get("error")

        if error:
            logger.error(f"Platform Node: PlatformAgent execution resulted in an error: {error}")
            return {
                "intermediate_output": output, # Could be None or partial data
                "error_message": str(error),
                "current_agent_name": current_agent_name
            }

        logger.info(f"Platform Node: PlatformAgent executed successfully. Output snippet: {str(output)[:200]}...")
        return {
            "intermediate_output": output,
            "error_message": None, # Explicitly clear any previous error
            "current_agent_name": current_agent_name
        }

    except Exception as e:
        logger.error(f"Platform Node: An unexpected error occurred during execution - {e}", exc_info=True)
        return {
            "intermediate_output": None, # Ensure intermediate_output is None in case of unexpected error
            "error_message": f"An unexpected error occurred in the Platform Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
