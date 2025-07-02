# agents/planner/a2a_server.py
from python_a2a.server import A2AServer
from python_a2a import AgentCard, AgentSkill # Direct imports for these
from python_a2a.models import Message, MessageRole, TextContent # Final correct imports
# AgentCapabilities already removed.
# The actual agent instance (from agents.planner.agent.root_agent) is passed in.
# Type hint it with the base ADK LlmAgent.
from google.adk.agents import LlmAgent as AdkLlmAgent
import asyncio
from fastapi import FastAPI
import os
from python_a2a.agent import AgentExecutor, Task # Corrected for v0.5.0
# from python_a2a.client.helpers import create_text_message_object # Not used in this server example
from python_a2a.mcp import FastMCP # For MCP integration example
from python_a2a.server.request_context import RequestContext # Assuming this path for RequestContext
from python_a2a.server.events import EventQueue, TaskUpdater # Assuming these paths for EventQueue and TaskUpdater

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
    mcp = FastMCP(f"{AGENT_NAME_FOR_CARD} MCP Server") # Give MCP server a name

    @mcp.tool()
    def get_weather_forecast(city: str = "New York") -> dict:
        """
        Returns a weather forecast for the given city. (MCP tool)
        """
        # Example weather API call
        logging.info(f"MCP tool 'get_weather_forecast' called for city: {city}")
        # In a real scenario, this would call a weather service.
        return {"forecast": f"The weather in {city} is mostly sunny with a chance of awesome."}

    class PlannerAgentExecutor(AgentExecutor): # from python_a2a.agent
        def __init__(self, agent: AdkLlmAgent, mcp_instance: FastMCP): # Updated type hint, Pass MCP instance
            if agent is None:
                raise ValueError("ADK LlmAgent instance is None for PlannerAgentExecutor.") # Updated error message
            self.agent = agent
            self.mcp = mcp_instance # Store MCP instance
            logger.info(f"PlannerAgentExecutor initialized with ADK agent: {getattr(self.agent, 'name', 'Unnamed')} and MCP.")

        async def execute(self, context: RequestContext, event_queue: EventQueue):
            query = context.get_user_input()

            task = context.current_task
            if not task:
                task_id = f"task_{os.urandom(8).hex()}"
                context_id_for_task = getattr(context.message, 'messageId', task_id)
                task = Task(id=task_id, contextId=context_id_for_task, status="working")
                event_queue.enqueue_event(task)

            updater = TaskUpdater(event_queue, task.id, task.contextId)

            if not query:
                logger.warning(f"No user input for Planner task {task.id}.")
                updater.fail(message="User input is missing for planner.")
                return

            # Check if the query is an MCP call first
            # Assuming query is a string that might contain a JSON RPC call for MCP
            logger.info(f"PlannerAgentExecutor received query for task {task.id}: {query[:100]}...")
            if isinstance(query, str): # MCP typically expects JSON string
                try:
                    # FastMCP.handle_request expects a string (JSON RPC) or a dict.
                    # If query is already a dict from A2A context, it might work directly.
                    # For now, assume query from get_user_input is the string payload.
                    mcp_response = await self.mcp.handle_request(query)
                    if mcp_response is not None: # MCP handled it
                        logger.info(f"MCP handled request for task {task.id}. Response: {mcp_response}")
                        # The MCP response itself might be a JSON string or a dict.
                        # We need to send it back as an A2A TextContent.
                        response_part = TextContent(text=str(mcp_response) if not isinstance(mcp_response, str) else mcp_response) # Changed to TextContent
                        updater.add_artifact(parts=[response_part], mime_type="application/json") # MCP often returns JSON
                        updater.complete()
                        return
                except Exception as mcp_e:
                    # Log MCP specific error, but don't let it stop A2A flow if it's not an MCP request
                    logger.debug(f"Query was not an MCP request or MCP error for task {task.id}: {mcp_e}")


            # If not an MCP call, or mcp.handle_request returned None (not handled), proceed with regular agent logic
            logger.info(f"Proceeding with ADK agent logic for task {task.id} (query: {query[:100]}...).")
            try:
                loop = asyncio.get_event_loop()
                response_content_str = await loop.run_in_executor(None, self.agent.run, query)

                logger.info(f"ADK planner agent executed for task {task.id}. Response: {response_content_str[:100]}")

                response_part = TextContent(text=response_content_str) # Changed to TextContent
                updater.add_artifact(parts=[response_part], mime_type="application/json")
                updater.complete()
                logger.info(f"Task {task.id} completed via ADK logic by PlannerAgentExecutor.")

            except Exception as e:
                logger.error(f"Error during ADK agent execution for task {task.id}: {e}", exc_info=True)
                updater.fail(message=f"Error executing planner ADK logic: {str(e)}")


    # Create FastAPI app for custom non-A2A routes (like health)
    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health") # Prefix with something to avoid A2A namespace
    async def health():
        return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    # Create and return the A2A Server
    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        agent_executor=PlannerAgentExecutor(planner_core_agent, mcp), # Pass planner_core_agent and mcp
        app=custom_fastapi_app, # Pass the custom FastAPI app
        mcp=mcp  # Pass the MCP instance to A2AServer for it to mount MCP routes
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD}.")
    return a2a_server_instance

# Standalone execution block removed as per plan.
