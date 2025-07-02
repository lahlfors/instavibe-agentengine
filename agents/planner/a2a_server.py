# agents/planner/a2a_server.py
from python_a2a.server import A2AServer
from python_a2a import AgentCard, AgentSkill # Direct imports for these
from python_a2a.models import Message, MessageRole, TextContent # Final correct imports
# AgentCapabilities already removed.
# The actual agent instance (from agents.planner.agent.root_agent) is passed in.
# Type hint it with the base ADK LlmAgent.
from google.adk.agents import LlmAgent as AdkLlmAgent
from typing import AsyncIterable # For stream handler type hint
import asyncio
from fastapi import FastAPI
import os
# AgentExecutor, Task, EventQueue, TaskUpdater are removed as they are part of the old pattern
# from python_a2a.agent import AgentExecutor, Task
# from python_a2a.server.events import EventQueue, TaskUpdater
from python_a2a.mcp import FastMCP # For MCP integration example
from python_a2a.server import A2AServer # RequestContext removed from this import line

import logging

# Configure Logger
# logging.basicConfig(level=logging.INFO) # BasicConfig should be called once, usually at app entry.
# Assuming logger is configured by AdkApp or deploy script.
logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid duplicate basicConfig if already set by another module
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())


A2A_UVICORN_PORT_PLANNER = int(os.environ.get("A2A_UVICORN_PORT_PLANNER", 8001))
AGENT_NAME_FOR_CARD = "Planner A2A Agent" # From your example
AGENT_DESCRIPTION_FOR_CARD = "A Planner agent that exposes an A2A API and MCP tools." # From your example


def create_planner_a2a_server(planner_core_agent: AdkLlmAgent) -> A2AServer:
    """
    Creates an A2A Server for the Planner agent.
    MCP handling will be done within the planner_core_agent.
    """
    # Define a skill
    skill = AgentSkill(
        id="planner_skill",
        name="Planner Agent Skill",
        description="Handles planning requests.",
    )
    # AgentCapabilities removed, streaming is handled by method implementation

    # Create an Agent Card
    # A2A_PUBLIC_BASE_URL will be read from environment by the running agent
    agent_card_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_PLANNER}")
    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=agent_card_url,
        version="1.0.0",
        # defaultInputModes=["text/plain"], # Planner ADK agent takes text - Removed
        # defaultOutputModes=["application/json"], # Planner ADK agent outputs JSON string - Removed
        skills=[skill]
        # capabilities attribute removed from AgentCard
    )
    logger.info(f"Planner AgentCard created. URL will be: {agent_card_url}")

    # --- MCP Setup a_server.py
    # MCP instance needs to be accessible to the on_message_handler
    # mcp = FastMCP(f"{AGENT_NAME_FOR_CARD} MCP Server") # MCP logic now moved to ADK agent

    # @mcp.tool() # MCP logic now moved to ADK agent
    # def get_weather_forecast(city: str = "New York") -> dict:
    #     """Returns a weather forecast for the given city. (MCP tool)"""
    #     logging.info(f"MCP tool 'get_weather_forecast' called for city: {city}")
    #     return {"forecast": f"The weather in {city} is mostly sunny with a chance of awesome."}

    # Import AGENT_INSTRUCTION and generate_plan_stream from the agent module
    # generate_plan_stream will be replaced by planner_core_agent.stream
    from agents.planner.agent import AGENT_INSTRUCTION # AGENT_INSTRUCTION might still be used by ADK agent
    # from agents.planner.agent import generate_plan_stream # This will be planner_core_agent.stream
    import json # For parsing query_details_json
    from python_a2a.models import DataPart # For constructing messages with data

    # Define message handlers within create_planner_a2a_server to close over planner_core_agent
    async def on_message_handler(message: Message) -> Message:
        logger.info(f"A2A on_message_handler received message: {message.model_dump_json(indent=2)}")
        try:
            if not message.parts or not isinstance(message.parts[0], DataPart) or message.parts[0].type != "data":
                logger.warning("Invalid message format: Expected a DataPart with type 'data'.")
                return Message(role=MessageRole.AGENT, parts=[TextContent(text="Invalid message format: Expected a DataPart with type 'data'.")])

            input_data_dict = message.parts[0].data # This is already a dict if pydantic model is used correctly by client

            if not isinstance(input_data_dict, dict):
                logger.warning(f"DataPart content is not a dict: {type(input_data_dict)}")
                return Message(role=MessageRole.AGENT, parts=[TextContent(text="Invalid DataPart content: Expected a JSON object/dict.")])

            # Call the ADK agent's invoke method
            # Loop is not strictly necessary here if planner_core_agent.invoke is already async
            # However, ADK LlmAgent.invoke is synchronous, so running in executor is correct.
            loop = asyncio.get_event_loop()
            response_dict = await loop.run_in_executor(None, planner_core_agent.invoke, input_data_dict)

            # Format the response as an A2A Message
            # The ADK agent's invoke method should return a dict. We'll JSON stringify it for TextContent.
            response_text = json.dumps(response_dict)
            logger.info(f"Response from ADK agent (invoke): {response_text[:200]}...")
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=response_text)])

        except json.JSONDecodeError as e: # Should not happen if DataPart.data is already a dict
            error_message = f"Invalid JSON in DataPart: {e}"
            logger.error(error_message, exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=error_message)])
        except Exception as e:
            error_message = f"Unexpected error in on_message_handler: {e}"
            logger.error(error_message, exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=error_message)])

    async def on_message_stream_handler(message: Message) -> AsyncIterable[Message]:
        logger.info(f"A2A on_message_stream_handler received message: {message.model_dump_json(indent=2)}")
        try:
            if not message.parts or not isinstance(message.parts[0], DataPart) or message.parts[0].type != "data":
                logger.warning("Invalid stream message format: Expected a DataPart with type 'data'.")
                yield Message(role=MessageRole.AGENT, parts=[TextContent(text="Invalid stream message format: Expected a DataPart with type 'data'.")])
                return

            input_data_dict = message.parts[0].data

            if not isinstance(input_data_dict, dict):
                logger.warning(f"Stream DataPart content is not a dict: {type(input_data_dict)}")
                yield Message(role=MessageRole.AGENT, parts=[TextContent(text="Invalid Stream DataPart content: Expected a JSON object/dict.")])
                return

            # Call ADK agent's stream method
            async for response_chunk_dict in planner_core_agent.stream(input_data_dict):
                # Format the response as an A2A Message and yield it
                response_chunk_text = json.dumps(response_chunk_dict)
                logger.debug(f"Yielding stream chunk from ADK agent: {response_chunk_text[:200]}...")
                yield Message(role=MessageRole.AGENT, parts=[TextContent(text=response_chunk_text)])

        except json.JSONDecodeError as e: # Should not happen here
            error_message = f"Invalid JSON in DataPart for stream: {e}"
            logger.error(error_message, exc_info=True)
            yield Message(role=MessageRole.AGENT, parts=[TextContent(text=error_message)])
        except Exception as e:
            error_message = f"Unexpected error in on_message_stream_handler: {e}"
            logger.error(error_message, exc_info=True)
            yield Message(role=MessageRole.AGENT, parts=[TextContent(text=error_message)])


    # Create FastAPI app for custom non-A2A routes (like health)
    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
        return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    # Create and return the A2A Server
    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        on_message=on_message_handler,
        on_message_stream=on_message_stream_handler,
        app=custom_fastapi_app
        # mcp parameter removed as MCP handling is now within the ADK agent
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD} with new handlers (MCP logic internal to ADK agent).")
    return a2a_server_instance
