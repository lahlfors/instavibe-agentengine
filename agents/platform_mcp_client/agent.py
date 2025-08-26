import asyncio
from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseConnectionParams
import logging
import os
import nest_asyncio
import json
from google.adk.agents import BaseAgent
from typing import Any, Dict, List, Tuple, Optional
from google.genai.types import Content, Part
from opentelemetry import trace
import sys
sys.path.append('.')

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

from typing import Optional, Any
from mcp import client

class PlatformMCPClientAgent(BaseAgent):
    """An agent that interacts with the MCP server."""
    mcp_server_address: str
    api_key_secret: str
    mcp_client: "Optional[Any]" = None

    def __init__(self, mcp_server_address: str, api_key_secret: str):
        """Initializes the agent with serializable configuration.

        No network operations or client instantiations here.
        """
        super().__init__(name="platform_mcp_client_agent", mcp_server_address=mcp_server_address, api_key_secret=api_key_secret)
        log.info("PlatformMCPClientAgent __init__ called. Config stored.")

    def _initialize_mcp_client(self):
        """Helper function to contain client creation logic."""
        api_key = self._get_api_key(self.api_key_secret)
        log.info(f"Initializing MCPClient for {self.mcp_server_address}")
        # NOTE: Assuming 'mcp.client.Client' is the correct constructor.
        return client.Client(self.mcp_server_address, api_key=api_key)

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
            if self.mcp_client:
                log.info("MCPClient already initialized.")
                return

            main_span.add_event("Initializing MCPClient")
            try:
                self.mcp_client = self._initialize_mcp_client()
                log.info("MCPClient initialized successfully in set_up.")
                main_span.set_status(trace.Status(trace.StatusCode.OK))
            except Exception as e:
                log.error(f"Error during MCPClient initialization in set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        """The A2A capability to call a tool on the MCP server."""
        if not self.mcp_client:
            log.error("MCP Client not initialized. Calling set_up().")
            self.set_up()

        log.info(f"A2A: Calling MCP tool '{tool_name}' with args: {arguments}")
        try:
            # Assuming the client has a method 'call_tool' that returns a list of content parts.
            response_parts = await self.mcp_client.call_tool(name=tool_name, arguments=arguments)

            # The server wraps the result in a TextContent part and JSON-encodes it.
            if response_parts and isinstance(response_parts, list) and hasattr(response_parts[0], 'text'):
                response_text = response_parts[0].text
                log.info(f"A2A: Received raw response: {response_text}")
                return json.loads(response_text)
            else:
                log.warning(f"A2A: Received unexpected response format: {response_parts}")
                return {"error": "Unexpected response format from MCP server"}

        except Exception as e:
            log.error(f"A2A: Error calling MCP tool '{tool_name}': {e}", exc_info=True)
            return {"error": str(e)}

    def query(self, user_query: str, **kwargs):
        """
        Example method to handle user queries.
        """
        if not self.mcp_client:
            raise RuntimeError(
                "MCP Client is not initialized. "
                "The set_up() method was likely not called or failed."
            )

        print(f"Querying MCP server with: '{user_query}'")
        # This method remains a placeholder for direct user queries.
        # The primary interaction will be via the A2A capability.
        response = f"MCP response to '{user_query}'"  # Placeholder
        return response

nest_asyncio.apply()

# Example of how the ADK would use this agent:
#
# mcp_url = os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL", "http://0.0.0.0:8080/sse")
# api_key_secret = os.environ.get("MCP_API_KEY_SECRET", "default-secret")
#
# 1. agent = PlatformMCPClientAgent(mcp_server_address=mcp_url, api_key_secret=api_key_secret)
# 2. engine serializes 'agent' (only config data)
# 3. engine deserializes 'agent' in the container
# 4. engine calls agent.set_up() <-- Client initialization happens here
# 5. engine calls agent.query(...) for incoming requests
