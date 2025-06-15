import logging
from typing import Dict, Any
from agents.app.common.graph_state import OrchestratorState
from agents.social.social_agent import SocialAgent

logger = logging.getLogger(__name__)

async def execute_social_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Executes the social agent based on the current task description.
    """
    logger.info("---Executing Social Node---")
    task_description = state.get("current_task_description")
    current_agent_name = "social"

    if not task_description:
        logger.error("Social Node: No task description provided.")
        return {
            "error_message": "No task description provided for Social Agent.",
            "current_agent_name": current_agent_name
        }

    try:
        agent = SocialAgent()
        logger.info(f"Social Node: Querying SocialAgent with task: {task_description}")
        response = await agent.async_query(task_description)

        output = response.get("output")
        error = response.get("error")

        if error:
            logger.error(f"Social Node: SocialAgent returned an error: {error}")
            return {"intermediate_output": output, "error_message": str(error), "current_agent_name": current_agent_name}

        logger.info(f"Social Node: SocialAgent returned output: {str(output)[:500]}...") # Log snippet
        return {"intermediate_output": output, "error_message": None, "current_agent_name": current_agent_name}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Social Node: Unexpected error - {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the Social Node: {str(e)}",
            "current_agent_name": current_agent_name
        }
