import logging
from typing import Dict, Any
from agents.app.common.graph_state import OrchestratorState
from agents.app.common.a2a_client import A2AClient # Import A2AClient
# from agents.social.social_agent import SocialAgent # No longer needed

logger = logging.getLogger(__name__)

a2a_client_instance = A2AClient() # Instantiate A2AClient

async def execute_social_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes the social agent based on the current task description via A2A call.
    """
    logger.info("---Executing Social Node (A2A)---")
    task_description = state.get("current_task_description")
    current_agent_name = "social"

    if not task_description:
        logger.error("Social Node: No task description provided.")
        return {
            "error_message": "No task description provided for Social Agent.",
            "current_agent_name": current_agent_name
        }

    try:
        # agent = SocialAgent() - Removed
        logger.info(f"Social Node: Invoking Social Agent via A2A with task: {task_description}")

        response = await a2a_client_instance.invoke_agent(
            agent_name="social",
            query=task_description,
            session_id=state.get("session_id")
        )

        output = response.get("output") # A2AClient returns a dict with "output" and "error" keys
        error = response.get("error")

        if error:
            logger.error(f"Social Node: A2A call to Social Agent returned an error: {error}")
            return {"intermediate_output": output, "error_message": str(error), "current_agent_name": current_agent_name}

        logger.info(f"Social Node: A2A call to Social Agent succeeded. Output: {str(output)[:500]}...") # Log snippet
        return {"intermediate_output": output, "error_message": None, "current_agent_name": current_agent_name}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Social Node: Unexpected error during A2A call - {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the Social Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
