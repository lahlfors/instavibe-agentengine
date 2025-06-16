# agents/platform_mcp_client/mcp_client.py
import os
import logging
from typing import List, Optional, Any
from langchain_core.tools import BaseTool, tool
from dotenv import load_dotenv # Added for the __main__ test block

logger = logging.getLogger(__name__)

# --- MCPToolset Handling (Real and Dummy) ---
IS_MCP_TOOLSET_AVAILABLE = False
SseServerParams_class = None
MCPToolset_class = None

try:
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
    MCPToolset_class = MCPToolset
    SseServerParams_class = SseServerParams
    IS_MCP_TOOLSET_AVAILABLE = True
    logger.info("MCPClient: Real MCPToolset and SseServerParams successfully imported.")
except ImportError:
    logger.warning("MCPClient: MCPToolset or SseServerParams could not be imported. Using DUMMY MCP implementation.")

    class DummySseServerParams:
        def __init__(self, url: str, headers: dict):
            self.url = url
            self.headers = headers
    SseServerParams_class = DummySseServerParams

    class DummyMCPToolset:
        def __init__(self, connection_params: DummySseServerParams):
            logger.info(f"DummyMCPToolset: Initialized with params: url='{connection_params.url}'")

        async def create_post(self, author_name: str, text: str, sentiment: str) -> str:
            logger.info(f"DummyMCPToolset: create_post called for {author_name}")
            return f"Dummy: Post created for {author_name} with text '{text}' and sentiment '{sentiment}'."

        async def create_event(self, event_name: str, event_date: str, attendee_name: str) -> str:
            logger.info(f"DummyMCPToolset: create_event called for {event_name}")
            return f"Dummy: Event '{event_name}' on {event_date} created for {attendee_name}."

        async def close(self):
            logger.info("DummyMCPToolset: close called.")

        def get_tools(self) -> List[BaseTool]:
            @tool("create_post_tool", return_direct=False)
            async def create_post_tool_dummy(author_name: str, text: str, sentiment: str) -> str:
                '''Creates a new post with the given author name, text, and sentiment.'''
                return await self.create_post(author_name, text, sentiment)

            @tool("create_event_tool", return_direct=False)
            async def create_event_tool_dummy(event_name: str, event_date: str, attendee_name: str) -> str:
                '''Creates a new event with the given name, date, and registers an attendee.'''
                return await self.create_event(event_name, event_date, attendee_name)

            logger.info("DummyMCPToolset: get_tools called, returning dummy tools.")
            return [create_post_tool_dummy, create_event_tool_dummy]
    MCPToolset_class = DummyMCPToolset # Assign the dummy class
# --- End MCPToolset Handling ---

class MCPClient:
    def __init__(self):
        self.mcp_toolset_instance: Optional[Any] = None
        self.tools: List[BaseTool] = []
        self._initialize_toolset()

    def _initialize_toolset(self):
        mcp_server_url = os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL")
        connection_headers = {} # Placeholder for actual authentication headers

        if IS_MCP_TOOLSET_AVAILABLE and mcp_server_url:
            logger.info(f"MCPClient: Initializing REAL MCPToolset with URL: {mcp_server_url}")
            connection_params = SseServerParams_class(url=mcp_server_url, headers=connection_headers)
            self.mcp_toolset_instance = MCPToolset_class(connection_params=connection_params)
        else:
            if IS_MCP_TOOLSET_AVAILABLE and not mcp_server_url:
                logger.warning("MCPClient: AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is not set. Real MCPToolset available but cannot be initialized. Using DUMMY MCPToolset.")
            elif not IS_MCP_TOOLSET_AVAILABLE:
                logger.warning("MCPClient: Real MCPToolset not imported. Using DUMMY MCPToolset.")

            dummy_params = SseServerParams_class(url="dummy_url", headers={}) # Use SseServerParams_class which points to DummySseServerParams if real one not imported
            self.mcp_toolset_instance = MCPToolset_class(connection_params=dummy_params) # This will be DummyMCPToolset if real one not imported

        if hasattr(self.mcp_toolset_instance, 'get_tools') and callable(getattr(self.mcp_toolset_instance, 'get_tools')):
            self.tools = self.mcp_toolset_instance.get_tools()
            logger.info(f"MCPClient: Tools obtained from toolset instance: {[t.name for t in self.tools]}")
        else:
            logger.error("MCPClient: Toolset instance (real or dummy) does NOT have a 'get_tools' method. This is unexpected. No tools will be available.")
            self.tools = [] # Ensure self.tools is an empty list

    def get_langchain_tools(self) -> List[BaseTool]:
        if not self.tools:
             logger.warning("MCPClient: get_langchain_tools called, but no tools were initialized.")
        return self.tools

    async def close(self):
        if self.mcp_toolset_instance and hasattr(self.mcp_toolset_instance, 'close'):
            logger.info("MCPClient: Closing MCPToolset instance.")
            await self.mcp_toolset_instance.close()
        else:
            logger.info("MCPClient: No active MCPToolset instance to close or instance does not support close().")

if __name__ == '__main__':
    import asyncio
    # For testing, ensure .env is in the root of the project, two levels up from this file's typical location.
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        logger.info(f"MCPClient __main__: Loaded .env from {dotenv_path}")
    else:
        logger.warning(f"MCPClient __main__: .env file not found at {dotenv_path}. Environment variables (like AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL) might not be set.")

    logging.basicConfig(level=logging.INFO) # Ensure logger is configured for __main__

    async def main_test():
        logger.info("--- MCPClient Test ---")
        if not os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL") and IS_MCP_TOOLSET_AVAILABLE:
            logger.info("Info: AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL not set. MCPClient will use dummy tools if real MCPToolset was imported.")

        client = MCPClient()
        tools = client.get_langchain_tools()
        logger.info(f"Tools available from MCPClient: {[t.name for t in tools]}")

        if tools:
            post_tool = next((t for t in tools if t.name == "create_post_tool"), None)
            if post_tool and isinstance(client.mcp_toolset_instance, (MCPToolset_class if IS_MCP_TOOLSET_AVAILABLE else DummyMCPToolset)): # Check instance type for direct call
                logger.info("Attempting to use 'create_post_tool' (direct dummy call if applicable)...")
                # This direct call is for testing the dummy's method; real tools are used by LangChain
                if not IS_MCP_TOOLSET_AVAILABLE or not os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL"):
                    result = await client.mcp_toolset_instance.create_post("TestAuthor", "Test Text", "positive")
                    logger.info(f"Dummy tool direct call result: {result}")
                else:
                    logger.info("Real tool would be invoked by LangChain agent based on LLM decision.")
        await client.close()
        logger.info("--- MCPClient Test Complete ---")

    asyncio.run(main_test())
