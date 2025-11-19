import asyncio
from google.adk.agents import Agent
import logging
from typing import Any, Dict, List, Tuple, Optional
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# 2. FIX: Import GenerativeModel for the resource leak fix
from google.generativeai import GenerativeModel
from google.adk.tools.mcp_tool import mcp_toolset, StreamableHTTPConnectionParams
from pydantic import PrivateAttr
from common.observability import setup_observability # Now this import works

# Configure standard logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)
logger = logging.getLogger(__name__)
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
    display_name: Optional[str] = None
    mcp_server_address: str
    api_key_secret: Optional[str] = None
    otel_collector_endpoint: Optional[str] = None
    _mcp_tools: List[Any] = PrivateAttr(default_factory=list)

    # 3. FIX: Declare model_client for the resource leak fix
    model_client: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # 4. FIX: Add __post_init__ for the resource leak fix
    def __post_init__(self):
        """(Pydantic v1) Runs after model is initialized."""
        super().__post_init__()  # Call the parent's post_init
        if self.model:
            self.model_client = GenerativeModel(self.model)
        else:
            print(f"WARNING: {self.__class__.__name__} initialized without a model name.")
        # Note: The base Agent's _run_async_impl will
        # automatically use self.model_client if it exists.

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
        logger.info(f"Fetching API key from secret: {secret_name}")
        return os.getenv("MCP_API_KEY", "DUMMY_API_KEY")

    async def __async_set_up(self, **kwargs):
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name

        # This import is now at the top of the file
        setup_observability(endpoint_override=self.otel_collector_endpoint)

        if self._mcp_tools:
            logger.info("MCP Tools already loaded.")
            return

        with tracer.start_as_current_span("PlatformMCPClientAgent.set_up") as main_span:
            logger.info(f"Starting set_up - Fetching tools from MCP server at {self.mcp_server_address}")
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
                logger.info(f"Connecting to MCP server with params: {conn_params}")

                toolset = await mcp_toolset.MCPToolset.from_server(conn_params)
                self._mcp_tools = list(toolset)

                tool_names = [t.name for t in self._mcp_tools]
                logger.info(f"Successfully loaded {len(self._mcp_tools)} tools from MCP server: {tool_names}")
                main_span.set_attribute("mcp.tool_count", len(self._mcp_tools))
                main_span.set_attribute("mcp.tool_names", ",".join(tool_names))
                main_span.set_status(Status(StatusCode.OK))

            except Exception as e:
                logger.error(f"Error fetching tools from MCP server in set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(Status(StatusCode.ERROR, str(e)))
                self._mcp_tools = []
                logger.warning("MCP Tools initialization failed, agent will have no tools from this source.")

    def set_up(self, **kwargs):
        """A synchronous wrapper for the async setup."""
        logger.info(f"Sync set_up called for {self.__class__.__name__}")
        try:
            asyncio.run(self._async_set_up(**kwargs))
            logger.info(f"set_up completed for {self.__class__.__name__}.")
        except Exception as e:
            logger.error(f"Error during set_up for {self.__class__.__name__}: {e}", exc_info=True)
            raise
        return self

    @property
    def tools(self) -> List[Any]:
        """Exposes the dynamically loaded MCP tools to the ADK framework."""
        return self._mcp_tools

    def query(self, **kwargs):
        """The entry point for the reasoning engine."""
        # The base Agent's entry point is __call__
        return self(**kwargs)

mcp_address = os.getenv("MCP_SERVER_ADDRESS")
if not mcp_address:
    raise ValueError("MCP_SERVER_ADDRESS not set in .env file")

root_agent = PlatformMCPClientAgent(
    name="platform_mcp_client_agent",
    model="gemini-1.5-flash",
    tools=[], # Tools are loaded dynamically in set_up
    display_name="Platform MCP Client Agent",
    mcp_server_address=mcp_address,
)
