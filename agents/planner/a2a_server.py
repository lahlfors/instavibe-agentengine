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

# Import the existing ADK agent from planner.agent
try:
    from agents.planner.agent import root_agent as adk_planner_agent
    from agents.planner.agent import SERVICE_NAME as PLANNER_SERVICE_NAME
    from agents.planner.agent import AGENT_INSTRUCTION # To get description hint
except ImportError as e:
    logging.error(f"Failed to import ADK planner agent: {e}. Ensure agents.planner.agent is accessible.")
    adk_planner_agent = None
    PLANNER_SERVICE_NAME = "planner-agent" # Fallback
    AGENT_INSTRUCTION = "Planner agent for suggesting activities." # Fallback

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) # Basic logging for the server

# Configuration
AGENT_NAME = PLANNER_SERVICE_NAME # Use the service name from the agent module
AGENT_DESCRIPTION = "A specialized AI assistant tasked with generating creative and fun plan suggestions."
# Extract a more concise description if possible, or use a summary.
# For now, taking a snippet from the detailed instruction.
if AGENT_INSTRUCTION:
    try:
        AGENT_DESCRIPTION = AGENT_INSTRUCTION.strip().split('.')[0] + "."
        if len(AGENT_DESCRIPTION) > 150: # Keep it reasonably short
             AGENT_DESCRIPTION = "Generates creative and fun plan suggestions."
    except:
        pass # Stick to default if parsing fails

HOST = os.environ.get("A2A_HOST", "0.0.0.0")  # Listen on all interfaces
PORT = int(os.environ.get("A2A_PORT", os.environ.get("PORT", 8080))) # Use A2A_PORT, fallback to PORT, then 8080
BASE_URL = os.environ.get("A2A_BASE_URL", f"http://{HOST}:{PORT}")
# For deployed agents, BASE_URL should be the public URL. This might need to be set via env var during deployment.
# If running in Cloud Run, Cloud Run provides the public URL.

# Define the AgentExecutor for the Planner ADK Agent
class PlannerAgentExecutor(AgentExecutor):
    def __init__(self, adk_agent_instance):
        if adk_agent_instance is None:
            raise ValueError("ADK Planner agent instance is None. Cannot initialize Executor.")
        self.adk_agent = adk_agent_instance
        logger.info(f"PlannerAgentExecutor initialized with ADK agent: {self.adk_agent.name}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        if not query:
            logger.warning("No user input found in request context.")
            # TODO: How to signal error back via TaskUpdater if query is missing?
            # For now, proceeding might lead to ADK agent error.
            # updater.fail(message="User input is missing.") might be an option.
            return

        task = context.current_task
        if not task:
            task = context.new_task()
            event_queue.enqueue_event(task) # Enqueue the initial task creation event

        updater = TaskUpdater(event_queue, task.id, task.contextId)
        logger.info(f"PlannerAgentExecutor: Executing task {task.id} for query: {query[:100]}...")

        try:
            # The ADK agent's run method might be synchronous or require specific async handling.
            # Assuming self.adk_agent.run can be awaited if it's an async method,
            # or needs to be run in a thread pool if it's synchronous.
            # For now, let's assume it's awaitable or ADK handles it.
            # If ADK's LlmAgent.run is synchronous, this needs adjustment:
            # result = await asyncio.to_thread(self.adk_agent.run, query)

            # ADK LlmAgent.run is synchronous. We need to run it in a thread.
            loop = asyncio.get_event_loop()
            # The ADK agent expects a simple string query.
            # If the ADK agent itself handles complex input objects, adjust here.
            adk_agent_response = await loop.run_in_executor(None, self.adk_agent.run, query)

            logger.info(f"ADK planner agent executed. Result type: {type(adk_agent_response)}")
            logger.debug(f"ADK planner agent result: {str(adk_agent_response)[:200]}")

            # The ADK LlmAgent typically returns a string (or a dict if output_key is used and it's complex).
            # The planner agent's output is expected to be a JSON string.
            if isinstance(adk_agent_response, str):
                # A2A expects artifacts to be added. The text itself can be an artifact.
                updater.add_artifact(parts=[Part(text=adk_agent_response)], mime_type="text/plain") # Or application/json if it's always JSON
            elif isinstance(adk_agent_response, dict) and 'output' in adk_agent_response: # Common ADK pattern
                 updater.add_artifact(parts=[Part(text=str(adk_agent_response['output']))], mime_type="text/plain")
            else:
                updater.add_artifact(parts=[Part(text=str(adk_agent_response))], mime_type="text/plain")

            updater.complete()
            logger.info(f"Task {task.id} completed successfully.")

        except Exception as e:
            logger.error(f"Error during ADK agent execution for task {task.id}: {e}", exc_info=True)
            try:
                updater.fail(message=f"Error executing planner agent: {str(e)}")
            except Exception as ue:
                logger.error(f"Error sending failure update for task {task.id}: {ue}", exc_info=True)

async def create_planner_a2a_server():
    if adk_planner_agent is None:
        logger.critical("ADK Planner Agent is not loaded. Cannot start A2A server.")
        return None

    logger.info(f"Creating A2A server for Planner Agent: {AGENT_NAME}")
    logger.info(f"Base URL for Agent Card: {BASE_URL}")

    # Define Agent Capabilities and Skills
    # TODO: Accurately define skills based on what the Planner agent can do.
    # For now, a generic skill. If the agent has specific tools, they could be mapped to skills.
    agent_capabilities = AgentCapabilities(streaming=True) # Planner agent might not stream, but SSE can still be used for task updates.

    # The Planner agent uses google_search tool. This could be a skill.
    # However, A2A skills are usually higher-level actions the agent offers.
    # For an LLM-based agent, the main "skill" is its ability to respond to instructions.
    planner_skill = AgentSkill(
        id='generate_plans',
        name='Generate Event Plans',
        description='Generates creative and fun event plan suggestions based on user criteria like date, location, and interests.'
    )

    agent_card = AgentCard(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        url=BASE_URL, # This should be the publicly accessible URL of this A2A server
        version="1.0.0",
        defaultInputModes=["text/plain"], # Planner agent takes natural language query
        defaultOutputModes=["application/json"], # Planner agent outputs JSON
        capabilities=agent_capabilities,
        skills=[planner_skill]
    )

    executor = PlannerAgentExecutor(adk_planner_agent)
    a2a_app = A2AStarletteApplication(agent_card=agent_card, executor=executor)

    logger.info(f"A2AStarletteApplication created for {AGENT_NAME}.")
    return a2a_app

async def serve():
    a2a_starlette_app = await create_planner_a2a_server()
    if a2a_starlette_app:
        config = uvicorn.Config(a2a_starlette_app, host=HOST, port=PORT, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Starting Uvicorn server for {AGENT_NAME} on {HOST}:{PORT}")
        await server.serve()
    else:
        logger.error(f"Could not create A2A server application for {AGENT_NAME}. Server will not start.")

if __name__ == "__main__":
    # This allows running the server directly for testing, e.g., python -m agents.planner.a2a_server
    # Ensure environment variables like GOOGLE_CLOUD_PROJECT are set if adk_planner_agent needs them at init.
    # The adk_planner_agent itself loads .env.
    logger.info(f"Attempting to start {AGENT_NAME} A2A server directly...")
    asyncio.run(serve())
else:
    # This is for when Uvicorn is started by a process manager like Gunicorn via Docker CMD
    # Uvicorn looks for an 'app' callable by default if not using the __main__ block.
    # We need to expose the A2AStarletteApplication instance.
    # However, A2AStarletteApplication needs to be created in an async context.
    # One way is to have a global 'app' and initialize it.
    # For Uvicorn called as `uvicorn agents.planner.a2a_server:app`, `app` must be defined at module level.
    # This can be tricky with async factory. A common pattern is to have a sync function that returns the app.
    # Or, ensure uvicorn is called with a factory pattern: `uvicorn module:factory_function --factory`
    # For simplicity in Docker, often the `if __name__ == "__main__":` is the entry point.
    # If deployed via `python -m agents.planner.a2a_server`, the __main__ block handles it.
    # If a WSGI/ASGI server (like one from Agent Engine) tries to import 'app', this needs care.
    # For now, assuming direct execution via `python -m ...` or that deployment handles async app creation.

    # To make it discoverable by uvicorn without `if __name__ == "__main__"`
    # when run as `uvicorn agents.planner.a2a_server:planner_asgi_app`
    # This requires careful handling of async setup.
    # One approach:
    # planner_asgi_app_instance = None
    # async def get_application():
    #     global planner_asgi_app_instance
    #     if planner_asgi_app_instance is None:
    #         planner_asgi_app_instance = await create_planner_a2a_server()
    #     return planner_asgi_app_instance
    # This doesn't directly expose 'app', uvicorn might need a factory.
    # The `if __name__ == "__main__":` is the most straightforward for direct python module execution.
    pass
