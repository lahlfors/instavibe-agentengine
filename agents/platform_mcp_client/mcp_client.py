# agents/platform_mcp_client/mcp_client.py
import os
import logging
from typing import List, Optional, Any

from langchain_core.tools import BaseTool, tool

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
    logger.info("Real MCPToolset and SseServerParams successfully imported.")
except ImportError:
    logger.warning("MCPToolset or SseServerParams could not be imported from google.adk.tools.mcp_tool.mcp_toolset. Using dummy MCP implementation.")

    class DummySseServerParams:
        def __init__(self, url: str, headers: dict):
            self.url = url
            self.headers = headers
    SseServerParams_class = DummySseServerParams

    class DummyMCPToolset:
        def __init__(self, connection_params: DummySseServerParams):
            logger.info(f"Dummy MCPToolset initialized with params: url='{connection_params.url}'")

        async def create_post(self, author_name: str, text: str, sentiment: str) -> str:
            logger.info(f"DummyMCPToolset: create_post called for {author_name}")
            return f"Dummy: Post created for {author_name} with text '{text}' and sentiment '{sentiment}'."

        async def create_event(self, event_name: str, event_date: str, attendee_name: str) -> str:
            logger.info(f"DummyMCPToolset: create_event called for {event_name}")
            return f"Dummy: Event '{event_name}' on {event_date} created for {attendee_name}."

        async def close(self): # Ensure dummy has a close method
            logger.info("DummyMCPToolset: close called.")

        def get_tools(self) -> List[BaseTool]:
            @tool("create_post_tool", return_direct=False) # Set return_direct based on typical LangChain agent usage
            async def create_post_tool_dummy(author_name: str, text: str, sentiment: str) -> str:
                '''Creates a new post with the given author name, text, and sentiment.'''
                return await self.create_post(author_name, text, sentiment)

            @tool("create_event_tool", return_direct=False)
            async def create_event_tool_dummy(event_name: str, event_date: str, attendee_name: str) -> str:
                '''Creates a new event with the given name, date, and registers an attendee.'''
                return await self.create_event(event_name, event_date, attendee_name)

            logger.info("DummyMCPToolset: get_tools called, returning dummy tools.")
            return [create_post_tool_dummy, create_event_tool_dummy]
    MCPToolset_class = DummyMCPToolset
# --- End MCPToolset Handling ---


class MCPClient:
    def __init__(self):
        self.mcp_toolset_instance: Optional[Any] = None # Can be MCPToolset or DummyMCPToolset
        self.tools: List[BaseTool] = []
        self._initialize_toolset()

    def _initialize_toolset(self):
        mcp_server_url = os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL")

        # Determine actual headers (e.g., for authentication)
        # This is a placeholder; real implementation might fetch tokens or use other config
        connection_headers = {}
        # Example: if os.environ.get("MCP_API_KEY"):
        #    connection_headers["X-API-Key"] = os.environ.get("MCP_API_KEY")

        if IS_MCP_TOOLSET_AVAILABLE and mcp_server_url:
            logger.info(f"MCPClient: Initializing REAL MCPToolset with URL: {mcp_server_url}")
            connection_params = SseServerParams_class(url=mcp_server_url, headers=connection_headers)
            self.mcp_toolset_instance = MCPToolset_class(connection_params=connection_params)
        else:
            if IS_MCP_TOOLSET_AVAILABLE and not mcp_server_url:
                logger.warning("MCPClient: AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is not set. Real MCPToolset available but cannot be initialized. Using DUMMY MCPToolset.")
            elif not IS_MCP_TOOLSET_AVAILABLE:
                logger.warning("MCPClient: Real MCPToolset not imported. Using DUMMY MCPToolset.")

            # Initialize with dummy parameters for the dummy toolset
            dummy_params = SseServerParams_class(url="dummy_url", headers={})
            self.mcp_toolset_instance = DummyMCPToolset(connection_params=dummy_params) # Ensure DummyMCPToolset is used here

        # Get tools from the initialized toolset instance
        if hasattr(self.mcp_toolset_instance, 'get_tools') and callable(getattr(self.mcp_toolset_instance, 'get_tools')):
            self.tools = self.mcp_toolset_instance.get_tools()
            logger.info(f"MCPClient: Tools obtained from toolset instance: {[t.name for t in self.tools]}")
        else:
            # This else block might be redundant if DummyMCPToolset always provides get_tools,
            # and if the real MCPToolset is assumed to also provide it.
            logger.warning("MCPClient: Toolset instance does not have a 'get_tools' method. Manually creating dummy tools as a last resort.")
            self.tools = self._create_manual_dummy_tools() # Fallback

    def _create_manual_dummy_tools(self) -> List[BaseTool]:
        # This is a fallback if mcp_toolset_instance.get_tools() fails for some reason
        @tool("create_post_tool_manual_dummy")
        async def create_post_manual(author_name: str, text: str, sentiment: str) -> str:
            return "Manual Dummy: Post created."
        @tool("create_event_tool_manual_dummy")
        async def create_event_manual(event_name: str, event_date: str, attendee_name: str) -> str:
            return "Manual Dummy: Event created."
        return [create_post_manual, create_event_manual]

    def get_langchain_tools(self) -> List[BaseTool]:
        if not self.tools:
             logger.warning("MCPClient: get_langchain_tools called, but no tools were initialized. This might indicate an issue during _initialize_toolset.")
        return self.tools

    async def close(self):
        if self.mcp_toolset_instance and hasattr(self.mcp_toolset_instance, 'close'):
            logger.info("MCPClient: Closing MCPToolset instance.")
            await self.mcp_toolset_instance.close()
        else:
            logger.info("MCPClient: No active MCPToolset instance to close or instance does not support close().")

# Example of how it might be used (for testing or in platform_node.py)
async def main_test():
    print("--- MCPClient Test ---")
    # To test real MCPToolset, ensure AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is set in .env
    # and google.adk.tools.mcp_tool.mcp_toolset is available.
    if not os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL"):
        print("Info: AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL not set. MCPClient will use dummy tools.")

    client = MCPClient()
    tools = client.get_langchain_tools()
    print(f"Tools available from MCPClient: {[t.name for t in tools]}")

    if tools:
        # Example: try to use a tool (conceptually)
        # In a real scenario, these would be invoked by a LangChain agent/graph
        post_tool = next((t for t in tools if t.name == "create_post_tool"), None)
        if post_tool:
            print("Attempting to use 'create_post_tool' (conceptually)...")
            # This is a conceptual call; actual tool use is via LangChain agent execution
            # For dummy tools, we can call their underlying methods if they are exposed
            if isinstance(client.mcp_toolset_instance, DummyMCPToolset):
                result = await client.mcp_toolset_instance.create_post("TestAuthor", "Test Text", "positive")
                print(f"Dummy tool direct call result: {result}")
            else:
                 print("Real tool would be invoked by LangChain agent based on LLM decision.")

    await client.close()
    print("--- MCPClient Test Complete ---")

if __name__ == "__main__":
    import asyncio
    # Load .env for testing AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL
    from dotenv import load_dotenv
    # Assuming this script is in agents/platform_mcp_client/
    # Adjust path to .env as needed, e.g., ../../.env if repository root is two levels up.
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded .env from {dotenv_path} for MCPClient test.")

    asyncio.run(main_test())
