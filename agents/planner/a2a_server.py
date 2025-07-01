import asyncio
import os
import logging
from fastapi import FastAPI

# Corrected A2A SDK imports based on user's guide and package name `python_a2a`
from python_a2a.server import A2AServer
from python_a2a import AgentCard, AgentSkill, AgentCapabilities, Part # Assuming Part is in python_a2a
from python_a2a.server.executors import AgentExecutor
from python_a2a.server.tasks import Task # For creating new tasks
from python_a2a.server.events import EventQueue, TaskUpdater # Assuming these are here
from python_a2a.server.request_context import RequestContext # Assuming this is here
from python_a2a.client.helpers import create_text_message_object # For creating response messages

# Import the ADK agent type for type hinting
from google.adk.agents import Agent as AdkAgentType
# Import the actual PlannerAgent class (or the module that defines root_agent)
from agents.planner.agent import PlannerAgent, root_agent as planner_core_adk_agent_instance # For type hint and potentially local testing default

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Configuration for the A2A server component
A2A_UVICORN_PORT_PLANNER = int(os.environ.get("A2A_UVICORN_PORT_PLANNER", 8001))
AGENT_NAME_FOR_CARD = "Planner A2A Agent" # From example
AGENT_DESCRIPTION_FOR_CARD = "A Planner agent that exposes an A2A API." # From example

class PlannerAgentExecutor(AgentExecutor):
    def __init__(self, agent: AdkAgentType): # Use AdkAgentType
        if agent is None:
            raise ValueError("ADK Planner agent instance is None for PlannerAgentExecutor.")
        self.agent = agent
        logger.info(f"PlannerAgentExecutor initialized with ADK agent: {getattr(self.agent, 'name', 'Unnamed ADK Agent')}")

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        query = context.get_user_input()

        # Ensure task object exists, create if necessary
        task = context.current_task
        if not task:
            # Create a new task using A2A SDK types
            # Assuming context.message.messageId is available for contextId
            # If not, a new UUID or context.request_id might be needed
            task_id = f"task_{os.urandom(8).hex()}" # Generate a simple unique task ID
            context_id_for_task = getattr(context.message, 'messageId', None) or getattr(context, 'request_id', task_id)

            task = Task(id=task_id, contextId=context_id_for_task, status="working")
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        if not query:
            logger.warning(f"No user input found in request context for Planner task {task.id}.")
            updater.fail(message="User input is missing for planner.")
            return

        logger.info(f"PlannerAgentExecutor: Executing task {task.id} for query: {query[:100]}...")
        try:
            # ADK LlmAgent.run is synchronous. Run it in an executor.
            loop = asyncio.get_event_loop()
            response_content_str = await loop.run_in_executor(None, self.agent.run, query)

            logger.info(f"ADK planner agent executed for task {task.id}. Response type: {type(response_content_str)}")

            # Assuming the planner's ADK agent (LlmAgent) returns a JSON string as per its prompt.
            # The A2A spec suggests using Message objects for responses too.
            # The example used create_text_message_object, but for a planner outputting JSON,
            # adding an artifact with mime_type="application/json" is more direct.

            # Create a Part object for the artifact
            # Assuming 'Part' is imported from 'a2a' or 'a2a.types'
            response_part = Part(text=response_content_str)
            updater.add_artifact(parts=[response_part], mime_type="application/json") # Planner outputs JSON

            updater.complete() # Mark task as completed
            logger.info(f"Task {task.id} completed successfully by PlannerAgentExecutor.")

        except Exception as e:
            logger.error(f"Error during ADK agent execution for task {task.id}: {e}", exc_info=True)
            updater.fail(message=f"Error executing planner agent: {str(e)}")

def create_planner_a2a_server(passed_planner_agent: AdkAgentType) -> A2AServer:
    """
    Creates an A2A Server for the Planner agent.
    Args:
        passed_planner_agent: The instantiated core ADK Agent for the planner.
    """
    if passed_planner_agent is None:
        logger.critical("Passed ADK Planner Agent is None. Cannot create A2A server.")
        raise ValueError("ADK Planner Agent instance is required by create_planner_a2a_server.")

    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_PLANNER}")

    logger.info(f"Creating A2A server component for Planner Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    skill = AgentSkill(
        id="planner_skill",
        name="Planner Agent Skill",
        description="Handles planning requests by generating creative event plans.",
    )
    capabilities = AgentCapabilities(streaming=True) # A2A server supports streaming task updates

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url,
        version="1.0.0",
        defaultInputModes=["text/plain"], # Planner's ADK agent takes a text query
        defaultOutputModes=["application/json"], # Planner's ADK agent is instructed to output JSON
        skills=[skill],
        capabilities=capabilities,
    )

    executor = PlannerAgentExecutor(passed_planner_agent)

    # Optional FastAPI app for custom health checks or other non-A2A routes
    custom_fastapi_app = FastAPI()
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        agent_executor=executor,
        app=custom_fastapi_app, # Pass the FastAPI app here
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD}.")
    return a2a_server_instance

# Standalone execution block (if __name__ == "__main__") is removed
# as Uvicorn will be started by AdkApp's setup_fn.
# For local testing, the deploy.py script's __main__ block can be used.
