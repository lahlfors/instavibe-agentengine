import asyncio
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.function_tool import FunctionTool
import logging
import os
from typing import Any, Dict, List, Tuple, Optional
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import sys
sys.path.append('.')
from mcp import client as mcp_client

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Configure standard logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)
log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

from pydantic import Field, model_validator

class PlatformMCPClientAgent(Agent):
    """An agent that interacts with the MCP server."""
    mcp_server_address: str
    api_key_secret: Optional[str] = None
    mcp_client: "Optional[Any]" = None
    tools: List[FunctionTool] = []

    @model_validator(mode='after')
    def _initialize_tools(self) -> "PlatformMCPClientAgent":
        """Initializes the tools for the agent."""
        self.tools = [
            FunctionTool(self.create_event),
            FunctionTool(self.get_person_posts),
            FunctionTool(self.get_person_friends),
            FunctionTool(self.get_person_id_by_name),
            FunctionTool(self.get_person_attended_events),
            FunctionTool(self.create_post),
        ]
        return self

    def _initialize_mcp_client(self):
        """Helper function to contain client creation logic."""
        api_key = None
        if self.api_key_secret:
            api_key = self._get_api_key(self.api_key_secret)
        else:
            log.info("api_key_secret not provided, using Application Default Credentials for MCPClient.")
        log.info(f"Initializing MCPClient for {self.mcp_server_address}")
        return mcp_client.Client(self.mcp_server_address, api_key)

    def _get_api_key(self, secret_name):
        # Placeholder for fetching secret
        log.info(f"Fetching API key from secret: {secret_name}")
        # In a real scenario, this would fetch from Secret Manager or other secure store.
        return os.getenv("MCP_API_KEY", "DUMMY_API_KEY")

    def set_up(self):
        """
        Called by Vertex AI Agent Engine after deserialization.
        Initialize non-serializable resources like network clients here.
        """
        with tracer.start_as_current_span("PlatformMCPClientAgent.set_up") as main_span:
            log.info("Starting PlatformMCPClientAgent.set_up - MCP Client init")
            main_span.add_event("Starting PlatformMCPClientAgent.set_up")
            try:
                self.mcp_client = self._initialize_mcp_client()
                log.info("MCPClient initialized successfully in set_up.")
                main_span.set_status(Status(StatusCode.OK))
            except Exception as e:
                log.error(f"Error during MCPClient initialization in set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(Status(StatusCode.ERROR, str(e)))
                self.mcp_client = None
                log.warning("MCPClient initialization failed, agent methods will not function.")

    async def create_event(self, event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str]):
        if not self.mcp_client:
            log.error("MCP Client is not initialized in create_event.")
            raise RuntimeError("MCP Client is not initialized.")
        return await self.mcp_client.call_tool("create_event", event_name=event_name, description=description, event_date=event_date, locations=locations, attendee_names=attendee_names)

    async def get_person_posts(self, person_id: str):
        if not self.mcp_client:
            log.error("MCP Client is not initialized in get_person_posts.")
            raise RuntimeError("MCP Client is not initialized.")
        return await self.mcp_client.call_tool("get_person_posts", person_id=person_id)

    async def get_person_friends(self, person_id: str):
        if not self.mcp_client:
            log.error("MCP Client is not initialized in get_person_friends.")
            raise RuntimeError("MCP Client is not initialized.")
        return await self.mcp_client.call_tool("get_person_friends", person_id=person_id)

    async def get_person_id_by_name(self, name: str):
        if not self.mcp_client:
            log.error("MCP Client is not initialized in get_person_id_by_name.")
            raise RuntimeError("MCP Client is not initialized.")
        return await self.mcp_client.call_tool("get_person_id_by_name", name=name)

    async def get_person_attended_events(self, person_id: str):
        if not self.mcp_client:
            log.error("MCP Client is not initialized in get_person_attended_events.")
            raise RuntimeError("MCP Client is not initialized.")
        return await self.mcp_client.call_tool("get_person_attended_events", person_id=person_id)

    async def create_post(self, author_name: str, text: str, sentiment: str):
        if not self.mcp_client:
            log.error("MCP Client is not initialized in create_post.")
            raise RuntimeError("MCP Client is not initialized.")
        return await self.mcp_client.call_tool("create_post", author_name=author_name, text=text, sentiment=sentiment)
