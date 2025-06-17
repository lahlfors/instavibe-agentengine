import asyncio
from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
import logging
import os
import nest_asyncio # Import nest_asyncio
from google.adk.agents import BaseAgent # Add BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from typing import Any, Dict, List, Tuple # Ensure Tuple, Dict, Any, List are imported


# Load environment variables from the root .env file
# Place this near the top, before using env vars like API keys
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class PlatformMCPClientServiceAgent:
    SUPPORTED_CONTENT_TYPES: List[str] = ["text", "text/plain"]

    def __init__(self, mcp_server_url: str):
        self._user_id: str = "platform_mcp_client_service_user"
        self.mcp_server_url = mcp_server_url
        self._agent: BaseAgent | None = None
        self._runner: Runner | None = None
        self._mcp_toolset: MCPToolset | None = None

        # Apply nest_asyncio before running async code if not already applied module-wide
        # nest_asyncio.apply() # Consider if this is needed here or once globally
        try:
            asyncio.run(self._async_init_components())
        except Exception as e:
            log.error(f"Error during PlatformMCPClientServiceAgent async initialization: {e}", exc_info=True)
            raise

    async def _async_init_components(self):
        log.info(f"PlatformMCPClientServiceAgent: Initializing MCPToolset with URL: {self.mcp_server_url}")
        self._mcp_toolset = MCPToolset(
            connection_params=SseServerParams(url=self.mcp_server_url, headers={})
        )
        # If MCPToolset has an explicit async connect method, call it here.

        self._agent = LlmAgent(
            model='gemini-2.0-flash',
            name='platform_mcp_client_agent',
            instruction="""
            You are a friendly and efficient assistant for the Instavibe social app.
            Your primary goal is to help users create posts and register for events using the available tools.

            When a user asks to create a post:
            1.  You MUST identify the **author's name** and the **post text**.
            2.  You MUST determine the **sentiment** of the post.
                - If the user explicitly states a sentiment (e.g., "make it positive", "this is a sad post", "keep it neutral"), use that sentiment. Valid sentiments are 'positive', 'negative', or 'neutral'.
                - **If the user does NOT provide a sentiment, you MUST analyze the post text yourself, infer the most appropriate sentiment ('positive', 'negative', or 'neutral'), and use this inferred sentiment directly for the tool call. Do NOT ask the user to confirm your inferred sentiment. Simply state the sentiment you've chosen as part of a summary if you confirm the overall action.**
            3.  Once you have the `author_name`, `text`, and `sentiment` (either provided or inferred), you will prepare to call the `create_post` tool with these three arguments.

            When a user asks to create an event or register for one:
            1.  You MUST identify the **event name**, the **event date**, and the **attendee's name**.
            2.  For the `event_date`, aim to get it in a structured format if possible (e.g., "YYYY-MM-DDTHH:MM:SSZ" or "tomorrow at 3 PM"). If the user provides a vague date, you can ask for clarification or make a reasonable interpretation. The tool expects a string.
            3.  Once you have the `event_name`, `event_date`, and `attendee_name`, you will prepare to call the `create_event` tool with these three arguments.

            General Guidelines:
            - If any required information for an action (like author_name for a post, or event_name for an event) is missing from the user's initial request, politely ask the user for the specific missing pieces of information.
            - Before executing an action (calling a tool), you can optionally provide a brief summary of what you are about to do (e.g., "Okay, I'll create a post for [author_name] saying '[text]' with a [sentiment] sentiment."). This summary should include the inferred sentiment if applicable, but it should not be phrased as a question seeking validation for the sentiment.
            - Use only the provided tools. Do not try to perform actions outside of their scope.
            """,
            tools=[self._mcp_toolset]
        )
        log.info("PlatformMCPClientServiceAgent: LlmAgent created.")

        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        log.info("PlatformMCPClientServiceAgent: Runner created.")

    async def query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        if not self._runner or not self._agent:
            log.error("PlatformMCPClientServiceAgent: Agent/Runner not initialized for query.")
            return {"error": "Agent not initialized"}
        session_id = kwargs.pop("session_id", self._user_id + "_" + os.urandom(4).hex())
        agent_response = await self._runner.arun(
            app_name=self._agent.name, session_id=session_id,
            inputs={"text_content": query}, stream=False, **kwargs
        )
        return agent_response

    async def close_async(self): # Optional: for explicit cleanup if needed elsewhere
        if self._mcp_toolset:
            log.info("PlatformMCPClientServiceAgent: Closing MCPToolset connection.")
            await self._mcp_toolset.close()

# Global agent instance for pickling
root_agent: PlatformMCPClientServiceAgent | None = None

# Apply nest_asyncio once at the module level if needed by the constructor's asyncio.run
nest_asyncio.apply()

def initialize_global_agent():
    global root_agent
    if root_agent is None:
        log.info("Initializing PlatformMCPClientServiceAgent...")
        mcp_url = os.environ.get("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL", "http://0.0.0.0:8080/sse")
        if not mcp_url:
            log.error("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL is not set.")
            raise ValueError("AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL not set for PlatformMCPClientServiceAgent.")

        try:
            root_agent = PlatformMCPClientServiceAgent(mcp_server_url=mcp_url)
            log.info("PlatformMCPClientServiceAgent initialized successfully and assigned to agent.root_agent.")
        except Exception as e:
            log.critical(f"CRITICAL: Failed to initialize PlatformMCPClientServiceAgent: {e}", exc_info=True)
            raise # Re-raise to ensure failure is visible, RE deployment will fail.
    else:
        log.info("PlatformMCPClientServiceAgent (agent.root_agent) already initialized.")

# Initialize the agent when the module is loaded so deploy.py can pickle agent.root_agent
try:
    initialize_global_agent()
except Exception as e:
    log.critical(f"CRITICAL: Module-level initialization of root_agent failed: {e}", exc_info=True)
    # If this fails, agent.root_agent might be None, which will cause issues for pickling/deployment.

