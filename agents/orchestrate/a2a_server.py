import asyncio
import os
import logging
import json
from fastapi import FastAPI

# Corrected A2A SDK imports for python-a2a==0.5.0
from python_a2a.server import A2AServer
from python_a2a.models.agent import AgentCard
from python_a2a.models.skill import AgentSkill
from python_a2a.models.message import Part # Corrected import for Part
# AgentCapabilities removed
from python_a2a.agent import AgentExecutor, Task # For v0.5.0
from python_a2a.server.events import EventQueue, TaskUpdater
from python_a2a.server.request_context import RequestContext
# from python_a2a.client.helpers import create_text_message_object # Not directly used by this executor

# ADK and agent-specific imports
from google.adk.agents import Agent as AdkAgentType # For type hinting
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Configuration for the A2A server component
A2A_UVICORN_PORT_ORCHESTRATE = int(os.environ.get("A2A_UVICORN_PORT_ORCHESTRATE", 8003))
AGENT_NAME_FOR_CARD = os.environ.get("AGENT_SERVICE_NAME", "orchestrate-agent") # From orchestrate.agent
AGENT_DESCRIPTION_FOR_CARD = "Orchestrator agent that delegates tasks to specialized remote agents via A2A."

class OrchestratorAgentExecutor(AgentExecutor): # Inherits from python_a2a.agent.AgentExecutor
    def __init__(self, passed_orchestrate_service_agent: OrchestrateServiceAgent):
        if passed_orchestrate_service_agent is None:
            raise ValueError("OrchestrateServiceAgent instance is None for OrchestratorAgentExecutor.")
        self.orchestrate_service_agent = passed_orchestrate_service_agent
        self.adk_llm_agent = self.orchestrate_service_agent.host_agent_logic.root_agent
        if self.adk_llm_agent is None:
            raise ValueError("Core ADK LlmAgent (root_agent) not found within OrchestrateServiceAgent.")
        logger.info(f"OrchestratorAgentExecutor initialized with ADK LLM agent: {getattr(self.adk_llm_agent, 'name', 'Unnamed ADK Agent')}")

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        json_input_str = context.get_user_input()

        task = context.current_task
        if not task:
            task_id = f"task_{os.urandom(8).hex()}"
            context_id_for_task = getattr(context.message, 'messageId', task_id)
            task = Task(id=task_id, contextId=context_id_for_task, status="working") # from python_a2a.agent
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        if not json_input_str:
            logger.warning(f"No user input (JSON string) found for Orchestrator task {task.id}.")
            updater.fail(message="User input (JSON string) is missing for orchestrator.")
            return

        logger.info(f"OrchestratorAgentExecutor: Executing task {task.id} with input: {json_input_str[:200]}...")
        try:
            loop = asyncio.get_event_loop()
            # The input JSON string is the query for the orchestrator's ADK LlmAgent.
            adk_agent_response_obj = await loop.run_in_executor(None, self.adk_llm_agent.run, json_input_str)

            logger.info(f"ADK orchestrator LLM agent executed for task {task.id}. Response type: {type(adk_agent_response_obj)}")

            response_text = ""
            if isinstance(adk_agent_response_obj, str):
                response_text = adk_agent_response_obj
            elif isinstance(adk_agent_response_obj, dict) and "output" in adk_agent_response_obj:
                response_text = str(adk_agent_response_obj['output'])
            else:
                response_text = str(adk_agent_response_obj)

            # The InstavibeWorkflowAgent expects a simple text response from the orchestrator A2A call.
            updater.add_artifact(parts=[Part(text=response_text)], mime_type="text/plain")
            updater.complete()
            logger.info(f"Orchestrator task {task.id} completed. Response: {response_text[:200]}")

        except json.JSONDecodeError as je: # Should ideally not happen if input is a pre-serialized JSON string
            logger.error(f"Error decoding input JSON for task {task.id}: {je}", exc_info=True)
            updater.fail(message=f"Invalid input JSON format for orchestrator: {str(je)}")
        except Exception as e:
            logger.error(f"Error during ADK orchestrator agent execution for task {task.id}: {e}", exc_info=True)
            updater.fail(message=f"Error executing orchestrator agent: {str(e)}")

def create_orchestrator_a2a_server(passed_orchestrate_service_agent: OrchestrateServiceAgent) -> A2AServer:
    if passed_orchestrate_service_agent is None:
        logger.critical("Passed OrchestrateServiceAgent is None. Cannot create A2A server.")
        raise ValueError("OrchestrateServiceAgent instance is required by create_orchestrator_a2a_server.")

    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_ORCHESTRATE}")

    logger.info(f"Creating A2A server component for Orchestrator Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    # AgentCapabilities removed
    orchestrator_main_skill = AgentSkill(
        id='orchestrate_task_delegation', # More specific ID
        name='Orchestrate Task Delegation',
        description='Receives a task description (usually JSON), understands intent, and coordinates other specialized agents using its internal tools.',
        inputModes=["application/json"],
        outputModes=["text/plain"]
    )

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url,
        version="1.0.0",
        defaultInputModes=["application/json"],
        defaultOutputModes=["text/plain"],
        # capabilities attribute removed
        skills=[orchestrator_main_skill]
    )

    executor = OrchestratorAgentExecutor(passed_orchestrate_service_agent)

    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        agent_executor=executor,
        app=custom_fastapi_app,
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD}.")
    return a2a_server_instance

# Standalone execution block removed.
