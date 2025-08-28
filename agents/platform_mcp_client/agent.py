import asyncio
from dotenv import load_dotenv
from common.observability import setup_observability
setup_observability(service_name="platform-mcp-client-agent")
from google.adk.agents import Agent
from google.adk.tools import Tool
from pydantic import BaseModel
import logging
import os
from typing import Any, Dict, List, Tuple, Optional
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import sys
sys.path.append('.')

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class CreateEventArgs(BaseModel):
    event_details: Dict[str, Any]
    user_id: str

class GetPersonPostsArgs(BaseModel):
    person_id: str

class PlatformMCPClientAgent(Agent):
    """An agent that interacts with the MCP server."""
    mcp_server_address: str
    api_key_secret: str
    mcp_client: "Optional[Any]" = None

    def __init__(self, mcp_server_address: str, api_key_secret: str, **kwargs):
        """Initializes the agent with serializable configuration."""
        super().__init__(name="platform_mcp_client_agent", **kwargs)
        self.mcp_server_address = mcp_server_address
        self.api_key_secret = api_key_secret
        self.tools = [
            Tool(
                name="create_event",
                function=self._create_event_impl,
                description="Creates an event on the Instavibe platform.",
                args_schema=CreateEventArgs,
            ),
            Tool(
                name="get_person_posts",
                function=self._get_person_posts_impl,
                description="Gets posts for a person from the Instavibe platform.",
                args_schema=GetPersonPostsArgs,
            ),
        ]
        log.info("PlatformMCPClientAgent __init__ called. Config stored.")

    def _initialize_mcp_client(self):
        """Helper function to contain client creation logic."""
        api_key = self._get_api_key(self.api_key_secret)
        log.info(f"Initializing MCPClient for {self.mcp_server_address}")
        # return mcp.client(self.mcp_server_address, api_key)
        return f"FakeMCPClient(server='{self.mcp_server_address}')"  # Placeholder

    def _get_api_key(self, secret_name):
        # Placeholder for fetching secret
        log.info(f"Fetching API key from secret: {secret_name}")
        return "DUMMY_API_KEY"

    def set_up(self):
        """
        Called by Vertex AI Agent Engine after deserialization.
        Initialize non-serializable resources like network clients here.
        """
        with tracer.start_as_current_span("PlatformMCPClientAgent.set_up") as main_span:
            log.info("Starting PlatformMCPClientAgent.set_up")
            main_span.add_event("Starting PlatformMCPClientAgent.set_up")
            try:
                self.mcp_client = self._initialize_mcp_client()
                log.info("MCPClient initialized successfully in set_up.")
                main_span.set_status(Status(StatusCode.OK))
            except Exception as e:
                log.error(f"Error during MCPClient initialization in set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    async def _create_event_impl(self, event_details: Dict[str, Any], user_id: str):
        with tracer.start_as_current_span("PlatformMCPClientAgent.create_event") as span:
            if not self.mcp_client:
                error_msg = "MCP Client is not initialized. The set_up() method was likely not called or failed."
                log.error(error_msg)
                span.set_status(Status(StatusCode.ERROR, error_msg))
                raise RuntimeError(error_msg)

            span.set_attributes({
                "user_id": user_id,
                "event.title": event_details.get("title", "Unknown")
            })
            log.info(f"Creating event for user {user_id}")
            try:
                # response = await self.mcp_client.call_tool("create_event", {**event_details, "user_id": user_id})
                response = {"status": "success", "event_id": "fake123"} # Placeholder
                if response.get("error"):
                    span.set_status(Status(StatusCode.ERROR, response["error"]))
                else:
                    span.set_status(Status(StatusCode.OK))
                return response
            except Exception as e:
                log.error(f"Error creating event: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return {"error": str(e)}

    async def _get_person_posts_impl(self, person_id: str):
        with tracer.start_as_current_span("PlatformMCPClientAgent.get_person_posts") as span:
            if not self.mcp_client:
                error_msg = "MCP Client is not initialized. The set_up() method was likely not called or failed."
                log.error(error_msg)
                span.set_status(Status(StatusCode.ERROR, error_msg))
                raise RuntimeError(error_msg)

            span.set_attributes({"person_id": person_id})
            log.info(f"Getting posts for person {person_id}")
            try:
                # response = await self.mcp_client.call_tool("get_person_posts", {"person_id": person_id})
                response = [{"post_id": "post1", "text": "Hello world!"}] # Placeholder
                if isinstance(response, dict) and response.get("error"):
                    span.set_status(Status(StatusCode.ERROR, response["error"]))
                else:
                    span.set_status(Status(StatusCode.OK))
                return response
            except Exception as e:
                log.error(f"Error getting posts: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return {"error": str(e)}
