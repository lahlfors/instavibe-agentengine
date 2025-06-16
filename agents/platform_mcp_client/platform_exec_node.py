import logging
from typing import Dict, Any
from agents.app.common.graph_state import OrchestratorState
from agents.app.common.a2a_client import A2AClient # Import A2AClient
# from agents.platform_mcp_client.platform_agent import PlatformAgent # No longer needed

logger = logging.getLogger(__name__)

a2a_client_instance = A2AClient() # Instantiate A2AClient

async def execute_platform_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes the platform agent based on the current task description via A2A call.
    """
    logger.info("---Executing Platform Node (A2A)---")
    task_description = state.get("current_task_description")
    current_agent_name = "platform"

    if not task_description:
        logger.error("Platform Node: No task description provided.")
        return {
            "error_message": "No task description provided for Platform Agent.",
            "current_agent_name": current_agent_name
        }

    try:
        # agent = PlatformAgent() # PlatformAgent initializes its own tools (MCPToolset) - Removed
        logger.info(f"Platform Node: Invoking Platform Agent via A2A with task: {task_description}")

        response = await a2a_client_instance.invoke_agent(
            agent_name="platform",
            query=task_description,
            session_id=state.get("session_id")
        )

        output = response.get("output") # A2AClient returns a dict with "output" and "error" keys
        error = response.get("error")

        if error:
            logger.error(f"Platform Node: A2A call to Platform Agent returned an error: {error}")
            return {"intermediate_output": output, "error_message": str(error), "current_agent_name": current_agent_name}

        logger.info(f"Platform Node: A2A call to Platform Agent succeeded. Output: {str(output)[:500]}...") # Log snippet
        return {"intermediate_output": output, "error_message": None, "current_agent_name": current_agent_name}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Platform Node: Unexpected error during A2A call - {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the Platform Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
