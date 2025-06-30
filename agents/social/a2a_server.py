import asyncio
import os
import logging

from fastapi import FastAPI # Used by A2AStarletteApplication
import uvicorn

from a2a.server import A2AStarletteApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, Part
from a2a.agent_executor import AgentExecutor
from a2a.events import EventQueue, TaskUpdater
from a2a.request_context import RequestContext

# Import the existing ADK agent from social.agent
try:
    from agents.social.agent import root_agent as adk_social_agent
    from agents.social.agent import SERVICE_NAME as SOCIAL_SERVICE_NAME
except ImportError as e:
    logging.error(f"Failed to import ADK social agent: {e}. Ensure agents.social.agent is accessible.")
    adk_social_agent = None
    SOCIAL_SERVICE_NAME = "social-agent" # Fallback

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) # Basic logging for the server

# Configuration
AGENT_NAME = SOCIAL_SERVICE_NAME
AGENT_DESCRIPTION = "Agent for finding and summarizing social profiles, posts, friends, and event attendance." # From LoopAgent description

HOST = os.environ.get("A2A_HOST", "0.0.0.0")
PORT = int(os.environ.get("A2A_PORT", os.environ.get("PORT", 8080)))
BASE_URL = os.environ.get("A2A_BASE_URL", f"http://{HOST}:{PORT}")
# For deployed agents, BASE_URL should be the public URL.

# Define the AgentExecutor for the Social ADK Agent
class SocialAgentExecutor(AgentExecutor):
    def __init__(self, adk_agent_instance):
        if adk_agent_instance is None:
            raise ValueError("ADK Social agent instance is None. Cannot initialize Executor.")
        self.adk_agent = adk_agent_instance
        logger.info(f"SocialAgentExecutor initialized with ADK agent: {self.adk_agent.name}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        if not query:
            logger.warning("No user input found in request context for SocialAgentExecutor.")
            # Consider updater.fail() if query is essential
            return

        task = context.current_task
        if not task:
            task = context.new_task()
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)
        logger.info(f"SocialAgentExecutor: Executing task {task.id} for query: {query[:100]}...")

        try:
            # ADK LoopAgent.run is synchronous.
            loop = asyncio.get_event_loop()
            adk_agent_response = await loop.run_in_executor(None, self.adk_agent.run, query)

            logger.info(f"ADK social agent executed. Result type: {type(adk_agent_response)}")
            logger.debug(f"ADK social agent result: {str(adk_agent_response)[:200]}")

            # The Social agent (LoopAgent) might return a string or dict.
            # The 'modify_output_after_agent' callback in social.agent returns a types.Content object
            # which then gets converted. We need to extract the text part.
            final_text_response = ""
            if isinstance(adk_agent_response, types.Content) and adk_agent_response.parts:
                final_text_response = adk_agent_response.parts[0].text if adk_agent_response.parts[0].text else str(adk_agent_response)
            elif isinstance(adk_agent_response, str):
                final_text_response = adk_agent_response
            else: # Fallback for other types
                final_text_response = str(adk_agent_response)

            updater.add_artifact(parts=[Part(text=final_text_response)], mime_type="text/plain")
            updater.complete()
            logger.info(f"Task {task.id} completed successfully by SocialAgentExecutor.")

        except Exception as e:
            logger.error(f"Error during ADK social agent execution for task {task.id}: {e}", exc_info=True)
            try:
                updater.fail(message=f"Error executing social agent: {str(e)}")
            except Exception as ue:
                logger.error(f"Error sending failure update for social task {task.id}: {ue}", exc_info=True)

async def create_social_a2a_server():
    if adk_social_agent is None:
        logger.critical("ADK Social Agent is not loaded. Cannot start A2A server.")
        return None

    logger.info(f"Creating A2A server for Social Agent: {AGENT_NAME}")
    logger.info(f"Base URL for Agent Card: {BASE_URL}")

    agent_capabilities = AgentCapabilities(streaming=True) # Social agent might involve multiple steps (LoopAgent)

    social_skill = AgentSkill(
        id='get_social_profile_summary',
        name='Get Social Profile Summary',
        description='Finds and summarizes social profiles, including posts, friends, and event attendance for one or more individuals.'
    )

    agent_card = AgentCard(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        url=BASE_URL,
        version="1.0.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"], # Social agent's final output is text
        capabilities=agent_capabilities,
        skills=[social_skill]
    )

    executor = SocialAgentExecutor(adk_social_agent)
    a2a_app = A2AStarletteApplication(agent_card=agent_card, executor=executor)

    logger.info(f"A2AStarletteApplication created for {AGENT_NAME}.")
    return a2a_app

async def serve():
    a2a_starlette_app = await create_social_a2a_server()
    if a2a_starlette_app:
        config = uvicorn.Config(a2a_starlette_app, host=HOST, port=PORT, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Starting Uvicorn server for {AGENT_NAME} on {HOST}:{PORT}")
        await server.serve()
    else:
        logger.error(f"Could not create A2A server application for {AGENT_NAME}. Server will not start.")

if __name__ == "__main__":
    logger.info(f"Attempting to start {AGENT_NAME} A2A server directly...")
    asyncio.run(serve())
else:
    # For uvicorn called as `uvicorn agents.social.a2a_server:app`
    # This requires 'app' to be defined at module level and initialized appropriately.
    # The current structure with `if __name__ == "__main__"` is for direct execution.
    pass
