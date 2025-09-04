import asyncio
from dotenv import load_dotenv
from google.adk.agents import Agent
import logging
import os
from typing import Any, Dict, List, Tuple, Optional
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import sys
sys.path.append('.')
from google.adk.tools.mcp_tool import mcp_toolset, StreamableHTTPConnectionParams
from pydantic import PrivateAttr

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Configure standard logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)
log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Builder function for pickling
def _build_platform_mcp_client_agent(state):
    """
    A top-level function to reconstruct the agent from its pickled state.
    This is used by the __reduce__ method to control pickling.
    """
    return PlatformMCPClientAgent(**state)

class PlatformMCPClientAgent(Agent):
    """An agent that interacts with the MCP server by dynamically loading tools."""
    mcp_server_address: str
    api_key_secret: Optional[str] = None
    otel_collector_endpoint: Optional[str] = None
    _mcp_tools: List[Any] = PrivateAttr(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __getstate__(self):
        return {
            "name": self.name,
            "mcp_server_address": self.mcp_server_address,
            "api_key_secret": self.api_key_secret,
            "description": self.description,
            "instruction": self.instruction,
            "global_instruction": self.global_instruction,
            "model": self.model,
        }

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._mcp_tools = []

    def __reduce__(self):
        """
        Hijacks the pickling process to ensure only the safe state is used.
        """
        return (_build_platform_mcp_client_agent, (self.__getstate__(),))

    def _get_api_key(self, secret_name):
        log.info(f"Fetching API key from secret: {secret_name}")
        return os.getenv("MCP_API_KEY", "DUMMY_API_KEY")

    def set_up(self, **kwargs):
        print(f"--- {self.__class__.__name__} set_up called (sync) ---")
        try:
            asyncio.run(self._async_setup_logic(**kwargs))
            print(f"--- {self.__class__.__name__} async_setup_logic completed ---")
        except Exception as e:
            print(f"Error running async_setup_logic in {self.__class__.__name__}: {e}")
            raise

    async def _async_setup_logic(self, **kwargs):
        print(f"--- Running _async_setup_logic for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        from common.observability import setup_observability
        setup_observability()
        if self._mcp_tools:
            log.info("MCP Tools already loaded.")
            return

        with tracer.start_as_current_span("PlatformMCPClientAgent.set_up") as main_span:
            log.info(f"Starting set_up - Fetching tools from MCP server at {self.mcp_server_address}")
            main_span.add_event("Fetching MCP tools")
            try:
                api_key = None
                if self.api_key_secret:
                    api_key = self._get_api_key(self.api_key_secret)

                headers = {"Accept": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                conn_params = StreamableHTTPConnectionParams(
                    url=self.mcp_server_address,
                    headers=headers,
                )
                log.info(f"Connecting to MCP server with params: {conn_params}")

                toolset = await mcp_toolset.MCPToolset.from_server(conn_params)
                self._mcp_tools = list(toolset)

                tool_names = [t.name for t in self._mcp_tools]
                log.info(f"Successfully loaded {len(self._mcp_tools)} tools from MCP server: {tool_names}")
                main_span.set_attribute("mcp.tool_count", len(self._mcp_tools))
                main_span.set_attribute("mcp.tool_names", ",".join(tool_names))
                main_span.set_status(Status(StatusCode.OK))

            except Exception as e:
                log.error(f"Error fetching tools from MCP server in set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(Status(StatusCode.ERROR, str(e)))
                self._mcp_tools = []
                log.warning("MCP Tools initialization failed, agent will have no tools from this source.")
        print(f"--- _async_setup_logic complete for {self.__class__.__name__} ---")

    @property
    def tools(self) -> List[Any]:
        """Exposes the dynamically loaded MCP tools to the ADK framework."""
        return self._mcp_tools

    def query(self, **kwargs):
        """The entry point for the reasoning engine."""
        # The base Agent's entry point is __call__
        return self(**kwargs)
