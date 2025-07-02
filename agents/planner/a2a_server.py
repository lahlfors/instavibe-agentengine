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
from python_a2a.server import RequestContext # Corrected import path for RequestContext (it's directly under server)

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


def create_planner_a2a_server(planner_core_agent: AdkLlmAgent) -> A2AServer: # Updated type hint
    """
    Creates an A2A Server for the Planner agent with MCP integration.
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
        defaultInputModes=["text/plain"], # Planner ADK agent takes text
        defaultOutputModes=["application/json"], # Planner ADK agent outputs JSON string
        skills=[skill]
        # capabilities attribute removed from AgentCard
    )
    logger.info(f"Planner AgentCard created. URL will be: {agent_card_url}")

    # --- MCP Setup ---
    # MCP instance needs to be accessible to the on_message_handler
    mcp = FastMCP(f"{AGENT_NAME_FOR_CARD} MCP Server")

    @mcp.tool()
    def get_weather_forecast(city: str = "New York") -> dict:
        """Returns a weather forecast for the given city. (MCP tool)"""
        logging.info(f"MCP tool 'get_weather_forecast' called for city: {city}")
        return {"forecast": f"The weather in {city} is mostly sunny with a chance of awesome."}

    # Import AGENT_INSTRUCTION and generate_plan_stream from the agent module
    from agents.planner.agent import AGENT_INSTRUCTION, generate_plan_stream
    import json # For parsing query_details_json

    # Define message handlers within create_planner_a2a_server to close over planner_core_agent and mcp
    async def on_message_handler(request_context: RequestContext, message: Message) -> Message:
        raw_input_text = None
        if message.parts and isinstance(message.parts[0], TextContent):
            raw_input_text = message.parts[0].text

        if not raw_input_text:
            logger.warning("No user input text found in message parts for on_message_handler.")
            return Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: User input text is missing.")])

        # MCP Handling (MCP expects a raw string, often JSON RPC)
        if isinstance(raw_input_text, str):
            try:
                mcp_response = await mcp.handle_request(raw_input_text)
                if mcp_response is not None:
                    logger.info(f"MCP handled request. Response: {mcp_response}")
                    response_text = str(mcp_response) if not isinstance(mcp_response, str) else mcp_response
                    return Message(role=MessageRole.AGENT, parts=[TextContent(text=response_text)])
            except Exception as mcp_e:
                logger.debug(f"Input was not an MCP request or MCP error: {mcp_e}")

        # ADK Agent Call (Non-MCP) - Requires formatted prompt
        logger.info(f"Proceeding with ADK agent logic for input: {raw_input_text[:200]}...")
        try:
            # Assume raw_input_text is a JSON string containing query_details
            query_details = json.loads(raw_input_text)

            # Construct the prompt using AGENT_INSTRUCTION and query_details
            final_prompt = AGENT_INSTRUCTION
            final_prompt = final_prompt.replace("[START_DATE_YYYY-MM-DD]", query_details.get("start_date", "this weekend"))
            final_prompt = final_prompt.replace("[END_DATE_YYYY-MM-DD]", query_details.get("end_date", "this weekend"))
            final_prompt = final_prompt.replace("[TARGET_LOCATION_NAME_OR_CITY_STATE]", query_details.get("location", "the specified area"))
            final_prompt = final_prompt.replace("[TARGET_LATITUDE]", str(query_details.get("latitude", "")))
            final_prompt = final_prompt.replace("[TARGET_LONGITUDE]", str(query_details.get("longitude", "")))
            final_prompt = final_prompt.replace("[NUMBER_OF_PLANS_TO_GENERATE, e.g., 3]", str(query_details.get("num_plans", "1")))
            final_prompt = final_prompt.replace("[COMMA_SEPARATED_LIST_OF_INTERESTS, e.g., outdoors, arts & culture, foodie, nightlife, unique local events, live music, active/sports]",
                                    query_details.get("interests", "general fun activities"))

            logger.debug(f"Constructed prompt for non-streaming: {final_prompt[:500]}...")

            loop = asyncio.get_event_loop()
            # ADK LlmAgent.invoke is synchronous
            response_content_str = await loop.run_in_executor(None, planner_core_agent.invoke, final_prompt)

            logger.info(f"ADK planner agent executed. Response: {response_content_str[:200]}")
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=response_content_str)])
        except json.JSONDecodeError as je:
            logger.error(f"JSONDecodeError: Input for ADK agent was not valid JSON: {raw_input_text}. Error: {je}", exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: Input for planner agent must be a valid JSON string containing query details.")])
        except Exception as e:
            logger.error(f"Error during ADK agent execution: {e}", exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=f"Error executing planner ADK logic: {str(e)}")])

    async def on_message_stream_handler(request_context: RequestContext, message: Message) -> AsyncIterable[Message]:
        logger.info("on_message_stream_handler called for Planner.")
        raw_query_details_json = None
        if message.parts and isinstance(message.parts[0], TextContent):
            raw_query_details_json = message.parts[0].text

        if not raw_query_details_json:
            logger.warning("No input JSON for query_details found in stream message parts.")
            yield Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: Input JSON for query details is missing.")])
            return

        try:
            query_details = json.loads(raw_query_details_json)
        except json.JSONDecodeError as je:
            logger.error(f"JSONDecodeError: Input for streaming was not valid JSON: {raw_query_details_json}. Error: {je}", exc_info=True)
            yield Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: Input for streaming must be a valid JSON string containing query details.")])
            return

        async for plan_chunk_str in generate_plan_stream(query_details=query_details, planner_agent_instance=planner_core_agent):
            yield Message(role=MessageRole.AGENT, parts=[TextContent(text=plan_chunk_str)])


    # Create FastAPI app for custom non-A2A routes (like health)
    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
        return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    # Create and return the A2A Server
    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        on_message=on_message_handler, # Pass the new handler
        on_message_stream=on_message_stream_handler, # Pass the new stream handler
        app=custom_fastapi_app,
        mcp=mcp # Pass MCP instance if A2AServer mounts its routes
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD} with new handlers.")
    return a2a_server_instance
