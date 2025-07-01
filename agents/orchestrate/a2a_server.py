import asyncio
import os
import logging
import json

from fastapi import FastAPI
import uvicorn

from a2a.server import A2AStarletteApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, Part, MessageSendParams
from a2a.agent_executor import AgentExecutor
from a2a.events import EventQueue, TaskUpdater
from a2a.request_context import RequestContext

# Import the ADK agent type for type hinting
from google.adk.agents import Agent as AdkAgentType
# Import the OrchestrateServiceAgent which wraps the ADK agent
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

# Try to get some metadata from the original agent module for AgentCard details
try:
    # Assuming SERVICE_NAME is defined in agents.orchestrate.agent module
    from agents.orchestrate.agent import SERVICE_NAME as ORCHESTRATE_SERVICE_NAME_FROM_MODULE
    # Assuming a default description or one can be derived
    ORCHESTRATE_AGENT_DEFAULT_DESCRIPTION = "Orchestrator agent that delegates tasks to specialized remote agents."
except ImportError as e:
    logging.warning(f"Could not import from agents.orchestrate.agent for metadata: {e}. Using fallbacks.")
    ORCHESTRATE_SERVICE_NAME_FROM_MODULE = "orchestrate-agent"
    ORCHESTRATE_AGENT_DEFAULT_DESCRIPTION = "Orchestrator agent that delegates tasks."

logger = logging.getLogger(__name__)
# Basic logging configuration. AdkApp's setup can enhance this.
if not logger.handlers: # Avoid duplicate basicConfig
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Configuration for the A2A server component
A2A_UVICORN_PORT_ORCHESTRATE = int(os.environ.get("A2A_UVICORN_PORT_ORCHESTRATE", 8003)) # Internal port
AGENT_NAME_FOR_CARD = ORCHESTRATE_SERVICE_NAME_FROM_MODULE
AGENT_DESCRIPTION_FOR_CARD = ORCHESTRATE_AGENT_DEFAULT_DESCRIPTION


class OrchestratorAgentExecutor(AgentExecutor):
    def __init__(self, passed_orchestrate_service_agent: OrchestrateServiceAgent):
        if passed_orchestrate_service_agent is None:
            raise ValueError("OrchestrateServiceAgent instance is None for OrchestratorAgentExecutor.")
        self.orchestrate_service_agent = passed_orchestrate_service_agent
        # The actual ADK LlmAgent is nested inside HostAgent
        self.adk_llm_agent = self.orchestrate_service_agent.host_agent_logic.root_agent
        if self.adk_llm_agent is None:
            raise ValueError("Core ADK LlmAgent not found within OrchestrateServiceAgent.")
        logger.info(f"OrchestratorAgentExecutor initialized with ADK LLM agent: {getattr(self.adk_llm_agent, 'name', 'Unnamed ADK Agent')}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        json_input_str = context.get_user_input()
        task = context.current_task or context.new_task()
        if not context.current_task:
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        if not json_input_str:
            logger.warning(f"No user input (JSON string) found for Orchestrator task {task.id}.")
            updater.fail(message="User input (JSON string) is missing for orchestrator.")
            return

        logger.info(f"OrchestratorAgentExecutor: Executing task {task.id} with input: {json_input_str[:200]}...")
        try:
            # The input JSON string is the query for the orchestrator's ADK LlmAgent.
            # This LlmAgent uses tools (like send_task) based on this query.
            loop = asyncio.get_event_loop()
            adk_agent_response_obj = await loop.run_in_executor(None, self.adk_llm_agent.run, json_input_str)

            logger.info(f"ADK orchestrator LLM agent executed for task {task.id}. Response type: {type(adk_agent_response_obj)}")
            logger.debug(f"ADK orchestrator LLM agent response for task {task.id}: {str(adk_agent_response_obj)[:500]}")

            response_text = ""
            if isinstance(adk_agent_response_obj, str):
                response_text = adk_agent_response_obj
            elif isinstance(adk_agent_response_obj, dict) and "output" in adk_agent_response_obj:
                response_text = str(adk_agent_response_obj['output'])
            else:
                response_text = str(adk_agent_response_obj)

            updater.add_artifact(parts=[Part(text=response_text)], mime_type="text/plain")
            updater.complete()
            logger.info(f"Orchestrator task {task.id} completed. Response: {response_text[:200]}")

        except json.JSONDecodeError as je: # Should not happen if input is already a string for LLM
            logger.error(f"Error related to JSON (unexpected) for task {task.id}: {je}", exc_info=True)
            updater.fail(message=f"Invalid input data format for orchestrator: {str(je)}")
        except Exception as e:
            logger.error(f"Error during ADK orchestrator agent execution for task {task.id}: {e}", exc_info=True)
            updater.fail(message=f"Error executing orchestrator agent: {str(e)}")


def create_orchestrator_a2a_server(passed_orchestrate_service_agent: OrchestrateServiceAgent) -> A2AStarletteApplication:
    """
    Creates and returns the A2AStarletteApplication for the Orchestrator agent.
    Args:
        passed_orchestrate_service_agent: The instantiated OrchestrateServiceAgent.
    """
    if passed_orchestrate_service_agent is None:
        logger.critical("Passed OrchestrateServiceAgent is None. Cannot create A2A server.")
        raise ValueError("OrchestrateServiceAgent instance is required by create_orchestrator_a2a_server.")

    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_ORCHESTRATE}")

    logger.info(f"Creating A2A server component for Orchestrator Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    agent_capabilities = AgentCapabilities(streaming=True)
    orchestrator_main_skill = AgentSkill(
        id='orchestrate_task',
        name='Orchestrate Complex Task',
        description='Receives a task description (often JSON), understands intent, and coordinates other agents.',
        inputModes=["application/json"], # Expects a JSON string defining the task for the LLM
        outputModes=["text/plain"]       # LLM provides a textual summary/confirmation
    )

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url,
        version="1.0.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["text/plain"],
        capabilities=agent_capabilities,
        skills=[orchestrator_main_skill]
    )

    executor = OrchestratorAgentExecutor(passed_orchestrate_service_agent)

    a2a_custom_app = FastAPI()
    @a2a_custom_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_starlette_app = A2AStarletteApplication(
        agent_card=agent_card,
        executor=executor,
        app=a2a_custom_app
    )

    logger.info(f"A2AStarletteApplication created for {AGENT_NAME_FOR_CARD} with AgentCard URL: {public_base_url}.")
    return a2a_starlette_app

# The `if __name__ == "__main__":` block for direct Uvicorn execution is removed.
# Uvicorn will be started by AdkApp's setup_fn in deploy.py.
# The serve_app_factory is also removed as AdkApp's setup_fn will directly use create_orchestrator_a2a_server
# and start_uvicorn_in_thread.
