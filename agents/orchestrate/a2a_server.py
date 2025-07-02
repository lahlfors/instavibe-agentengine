import asyncio
import os
import logging
import json
from fastapi import FastAPI

# python_a2a model imports
from python_a2a import AgentCard, AgentSkill
from python_a2a.models import Message, MessageRole, TextContent # Final correct imports
# Other necessary imports from python_a2a
from python_a2a.server import A2AServer # Removed RequestContext from this line
from typing import AsyncIterable # For stream handler type hint
# AgentExecutor, Task, EventQueue, TaskUpdater are removed
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

# OrchestratorAgentExecutor class removed

def create_orchestrator_a2a_server(passed_orchestrate_service_agent: OrchestrateServiceAgent) -> A2AServer:
    if passed_orchestrate_service_agent is None:
        logger.critical("Passed OrchestrateServiceAgent is None. Cannot create A2A server.")
        raise ValueError("OrchestrateServiceAgent instance is required by create_orchestrator_a2a_server.")

    # Extract the core ADK LlmAgent from the passed service agent
    adk_llm_agent = passed_orchestrate_service_agent.host_agent_logic.root_agent
    if adk_llm_agent is None:
        raise ValueError("Core ADK LlmAgent (root_agent) not found within OrchestrateServiceAgent for A2A server setup.")

    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_ORCHESTRATE}")

    logger.info(f"Creating A2A server component for Orchestrator Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    orchestrator_main_skill = AgentSkill(
        id='orchestrate_task_delegation',
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
        skills=[orchestrator_main_skill]
    )

    async def on_message_handler(message: Message) -> Message: # Removed request_context
        json_input_str = None
        if message.parts and isinstance(message.parts[0], TextContent):
            json_input_str = message.parts[0].text

        if not json_input_str:
            logger.warning("No user input (JSON string) found for Orchestrator.")
            return Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: User input (JSON string) is missing.")])

        logger.info(f"Orchestrator on_message_handler received input: {json_input_str[:200]}...")
        try:
            loop = asyncio.get_event_loop()
            # The input JSON string is the query for the orchestrator's ADK LlmAgent.
            adk_agent_response_obj = await loop.run_in_executor(None, adk_llm_agent.invoke, json_input_str) # Use invoke

            logger.info(f"ADK orchestrator LLM agent executed. Response type: {type(adk_agent_response_obj)}")

            response_text = ""
            if isinstance(adk_agent_response_obj, str):
                response_text = adk_agent_response_obj
            elif isinstance(adk_agent_response_obj, dict) and "output" in adk_agent_response_obj: # Handle if ADK agent returns a dict
                response_text = str(adk_agent_response_obj['output'])
            else:
                response_text = str(adk_agent_response_obj) # Fallback

            return Message(role=MessageRole.AGENT, parts=[TextContent(text=response_text)])
        except json.JSONDecodeError as je: # Should not happen if input is pre-serialized JSON
            logger.error(f"Error decoding input JSON: {je}", exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=f"Error: Invalid input JSON format: {str(je)}")])
        except Exception as e:
            logger.error(f"Error during ADK orchestrator agent execution: {e}", exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=f"Error executing orchestrator agent: {str(e)}")])

    async def on_message_stream_handler(message: Message) -> AsyncIterable[Message]: # Removed request_context
        logger.warning("Streaming not implemented for Orchestrator Agent.")
        yield Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: Streaming not supported by this agent.")])

    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        on_message=on_message_handler,
        on_message_stream=on_message_stream_handler,
        app=custom_fastapi_app,
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD} with new handlers.")
    return a2a_server_instance
