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
    task_description = state.get("current_task_description")
    current_agent_name = "platform"

    if not task_description:
        logger.error("Platform Node: No task description provided.")
        return {
            "error_message": "No task description provided for Platform Agent.",
            "current_agent_name": current_agent_name
        }

    try:
        agent = PlatformAgent() # PlatformAgent initializes its own tools (MCPToolset)
        logger.info(f"Platform Node: Querying PlatformAgent with task: {task_description}")
        response = await agent.async_query(task_description)

        output = response.get("output")
        error = response.get("error")

        if error:
            logger.error(f"Platform Node: PlatformAgent returned an error: {error}")
            return {"intermediate_output": output, "error_message": str(error), "current_agent_name": current_agent_name}

        logger.info(f"Platform Node: PlatformAgent returned output: {str(output)[:500]}...") # Log snippet
        return {"intermediate_output": output, "error_message": None, "current_agent_name": current_agent_name}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Platform Node: Unexpected error - {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the Platform Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
