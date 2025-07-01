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

# Import the ADK agent type for type hinting
from google.adk.agents import Agent as AdkAgentType

# Try to get some metadata from the original agent module for AgentCard details
try:
    from agents.planner.agent import SERVICE_NAME as PLANNER_SERVICE_NAME_FROM_MODULE
    from agents.planner.agent import AGENT_INSTRUCTION as AGENT_INSTRUCTION_FROM_MODULE
except ImportError as e:
    logging.warning(f"Could not import from agents.planner.agent for metadata: {e}. Using fallbacks.")
    PLANNER_SERVICE_NAME_FROM_MODULE = "planner-agent"
    AGENT_INSTRUCTION_FROM_MODULE = "Planner agent for suggesting activities."

logger = logging.getLogger(__name__)
# Basic logging configuration. AdkApp's setup can enhance this.
if not logger.handlers: # Avoid duplicate basicConfig if already set by another module
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Configuration for the A2A server component
A2A_UVICORN_PORT_PLANNER = int(os.environ.get("A2A_UVICORN_PORT_PLANNER", 8001)) # Internal port for Uvicorn
AGENT_NAME_FOR_CARD = PLANNER_SERVICE_NAME_FROM_MODULE
AGENT_DESCRIPTION_FOR_CARD = "A specialized AI assistant tasked with generating creative and fun plan suggestions."
if AGENT_INSTRUCTION_FROM_MODULE:
    try:
        AGENT_DESCRIPTION_FOR_CARD = AGENT_INSTRUCTION_FROM_MODULE.strip().split('.')[0] + "."
        if len(AGENT_DESCRIPTION_FOR_CARD) > 150:
             AGENT_DESCRIPTION_FOR_CARD = "Generates creative and fun plan suggestions."
    except:
        pass # Use the default AGENT_DESCRIPTION_FOR_CARD


class PlannerAgentExecutor(AgentExecutor):
    def __init__(self, adk_agent_instance: AdkAgentType):
        if adk_agent_instance is None:
            raise ValueError("ADK Planner agent instance is None for PlannerAgentExecutor.")
        self.adk_agent = adk_agent_instance
        logger.info(f"PlannerAgentExecutor initialized with ADK agent: {getattr(self.adk_agent, 'name', 'Unnamed ADK Agent')}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        task = context.current_task or context.new_task() # Get current or create new
        if not context.current_task: # If new_task() was called, it's not yet in the queue
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        if not query:
            logger.warning(f"No user input found in request context for task {task.id}.")
            updater.fail(message="User input is missing for planner.")
            return

        logger.info(f"PlannerAgentExecutor: Executing task {task.id} for query: {query[:100]}...")
        try:
            loop = asyncio.get_event_loop()
            adk_agent_response = await loop.run_in_executor(None, self.adk_agent.run, query)

            logger.info(f"ADK planner agent executed for task {task.id}. Result type: {type(adk_agent_response)}")
            logger.debug(f"ADK planner agent result for task {task.id}: {str(adk_agent_response)[:200]}")

            response_text = ""
            if isinstance(adk_agent_response, str):
                response_text = adk_agent_response
            elif isinstance(adk_agent_response, dict) and 'output' in adk_agent_response:
                 response_text = str(adk_agent_response['output'])
            else:
                response_text = str(adk_agent_response)

            updater.add_artifact(parts=[Part(text=response_text)], mime_type="application/json")
            updater.complete()
            logger.info(f"Task {task.id} completed successfully by PlannerAgentExecutor.")

        except Exception as e:
            logger.error(f"Error during ADK agent execution for task {task.id}: {e}", exc_info=True)
            updater.fail(message=f"Error executing planner agent: {str(e)}")


def create_planner_a2a_server(passed_adk_planner_agent: AdkAgentType) -> A2AStarletteApplication:
    """
    Creates and returns the A2AStarletteApplication for the Planner agent.
    This function will be called by the AdkApp setup process.
    Args:
        passed_adk_planner_agent: The instantiated core ADK Agent for the planner.
    """
    if passed_adk_planner_agent is None:
        logger.critical("Passed ADK Planner Agent is None. Cannot create A2A server.")
        raise ValueError("ADK Planner Agent instance is required by create_planner_a2a_server.")

    # A2A_PUBLIC_BASE_URL is expected to be set by the deployment environment (Vertex AI Agent Engine)
    # It's derived from the public_endpoint_uri of the deployed Reasoning Engine.
    # Fallback to a local URL (using the specific Uvicorn port for this agent) for local/standalone testing.
    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_PLANNER}")

    logger.info(f"Creating A2A server component for Planner Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    agent_capabilities = AgentCapabilities(streaming=True) # A2A server supports streaming task updates
    planner_skill = AgentSkill(
        id='generate_plans',
        name='Generate Event Plans',
        description='Generates creative and fun event plan suggestions based on user criteria like date, location, and interests.'
    )

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url, # This is the crucial public URL for discovery and interaction
        version="1.0.0",
        defaultInputModes=["text/plain"], # Planner's ADK agent expects a text query
        defaultOutputModes=["application/json"], # Planner's ADK agent produces a JSON string
        capabilities=agent_capabilities,
        skills=[planner_skill]
    )

    executor = PlannerAgentExecutor(passed_adk_planner_agent)

    # Optional: Health check endpoint for the A2A interface
    a2a_custom_app = FastAPI()
    @a2a_custom_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_starlette_app = A2AStarletteApplication(
        agent_card=agent_card,
        executor=executor,
        app=a2a_custom_app # Mounts health check under A2A app (e.g. /a2a/_a2a_health)
                           # Or pass to app_factory if A2AStarletteApplication supports it for root path
    )

    logger.info(f"A2AStarletteApplication created for {AGENT_NAME_FOR_CARD} with AgentCard URL pointing to {public_base_url}.")
    return a2a_starlette_app

# The `if __name__ == "__main__":` block for direct Uvicorn execution is removed.
# Uvicorn will be started by the AdkApp's setup_fn in deploy.py.
