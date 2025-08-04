import asyncio
from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
from toolbox_core import ToolboxClient
import logging
import os
import nest_asyncio
from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from typing import Any, Dict, List, Tuple, Optional
from google.genai.types import Content, Part


# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class PlatformMCPClientServiceAgent:
    SUPPORTED_CONTENT_TYPES: List[str] = ["text", "text/plain"]

    def __init__(self, toolbox_url: str):
        self.toolbox_url = toolbox_url
        self._user_id: str = "platform_mcp_client_service_user"
        self._toolbox_client: Optional[ToolboxClient] = None
        self._agent: Optional[BaseAgent] = None
        self._runner: Optional[Runner] = None
        # Removed asyncio.run for lazy initialization

    async def _ensure_components_initialized_async(self):
        if self._runner is not None:
            return

        log.info(f"PlatformMCPClientServiceAgent: Initializing components with Toolbox URL: {self.toolbox_url}")
        self._toolbox_client = ToolboxClient(service_url=self.toolbox_url)

        # Load the tools from the 'genai-toolbox' server
        instavibe_tools = await self._toolbox_client.load_toolset("instavibe_v2")

        self._agent = LlmAgent(
            model='gemini-2.0-flash-001',
            name='platform_mcp_client_agent',
            instruction="""
            You are a friendly and efficient assistant for the Instavibe social app.
            Your primary goal is to help users create posts and events using the available tools.

            When a user asks to create a post:
            1.  You MUST identify the **author's name** and the **post text**.
            2.  You MUST determine the **sentiment** of the post ('positive', 'negative', or 'neutral'). If the user does not provide one, you MUST infer it from the text. Do not ask for confirmation.
            3.  You will then call the `create_post` tool with `author_name`, `text`, and `sentiment`.

            When a user asks to create an event:
            1.  You MUST identify the **event name**, a **description**, the **event date** (in ISO 8601 format), a list of **locations**, and a list of **attendee names**.
            2.  For locations, you need a list of objects, each with 'name', 'latitude', and 'longitude'.
            3.  You will then call the `create_event` tool with these arguments.

            General Guidelines:
            - If any required information is missing, politely ask the user for it.
            - Before executing an action, you can optionally provide a brief summary of what you are about to do.
            - Use only the provided tools. Do not try to perform actions outside of their scope.
            """,
            tools=instavibe_tools
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

    async def _execute_query_async(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        await self._ensure_components_initialized_async()

        if not self._runner or not self._agent:
            log.error("PlatformMCPClientServiceAgent: Agent/Runner not initialized properly.")
            return {"error": "Agent components not initialized"}

        app_name = self._agent.name
        external_session_id = kwargs.get("session_id")
        interaction_user_id = self._user_id
        desired_session_id: str

        if external_session_id:
            interaction_user_id = str(external_session_id)
            desired_session_id = str(external_session_id)
            log.info(f"External session_id '{desired_session_id}' provided, setting interaction_user_id to match.")
        else:
            desired_session_id = self._user_id + "_" + os.urandom(4).hex()
            log.info(f"No external session_id. Generated '{desired_session_id}' for user '{interaction_user_id}'.")

        current_session_obj: Optional[Any] = None
        try:
            log.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id}'")
            current_session_obj = await self._runner.session_service.get_session(
                app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id
            )
            if current_session_obj:
                 log.info(f"Found existing session: {current_session_obj.id} for user {interaction_user_id}")
            else:
                log.info(f"Session {desired_session_id} for user {interaction_user_id} not found (get_session returned None). Will create.")
        except Exception as e_get:
            log.warning(f"Exception during get_session for user '{interaction_user_id}', session_id '{desired_session_id}': {e_get}. Will assume session needs creation.")
            current_session_obj = None

        if current_session_obj is None:
            try:
                log.info(f"Creating session: app='{app_name}', user='{interaction_user_id}', session_id_override='{desired_session_id}'")
                current_session_obj = await self._runner.session_service.create_session(
                    app_name=app_name, user_id=interaction_user_id, session_id_override=desired_session_id
                )
                log.info(f"Successfully created session: {current_session_obj.id} for user {interaction_user_id}.")
            except Exception as e_create:
                log.error(f"Failed to create session for user {interaction_user_id} with session_id_override {desired_session_id}: {e_create}", exc_info=True)
                return {"error": f"Session management failure during create: {e_create}"}

        if not current_session_obj:
            log.error(f"Critical error: Failed to obtain a session object for user {interaction_user_id}, session_id {desired_session_id}.")
            return {"error": "Failed to get or create a session."}

        response_event_data = None
        try:
            async for event in self._runner.run_async(
                user_id=interaction_user_id,
                session_id=current_session_obj.id,
                new_message=Content(parts=[Part(text=query)], role="user")
            ):
                response_event_data = event
                break
        except Exception as e_run:
            log.error(f"Error during run_async for session {current_session_obj.id}: {e_run}", exc_info=True)
            return {"error": f"Agent execution error: {e_run}"}

        if response_event_data:
            if isinstance(response_event_data, dict):
                return response_event_data
            elif hasattr(response_event_data, 'is_final_response') and response_event_data.is_final_response():
                if response_event_data.content and response_event_data.content.parts and response_event_data.content.parts[0].text:
                    return {"output": response_event_data.content.parts[0].text}
            log.warning(f"run_async returned event of type {type(response_event_data)} for session {current_session_obj.id}. Content: {str(response_event_data)[:200]}")
            return {"error": "Unexpected or non-final event type from agent execution", "event_preview": str(response_event_data)[:100]}
        else:
            log.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            return {"error": "No response event received from agent execution"}

    def query(self, input: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        action = input.get("action")
        data = input.get("data", {})

        if action == "create_post":
            # Construct a natural language query for the LLM
            query = f"Create a post for {data.get('author_name')} with text '{data.get('text')}' and sentiment '{data.get('sentiment')}'"
        elif action == "create_event":
            # This part of the query might need to be adjusted based on how the LLM best handles structured data like locations
            query = f"Create an event named '{data.get('event_name')}' on {data.get('event_date')} for attendees {data.get('attendee_names')} with description '{data.get('description')}' and locations {data.get('locations')}"
        else:
            return {"error": f"Unsupported action: {action}"}

        return asyncio.run(self._execute_query_async(query=query, **kwargs))

    async def close_async(self):
        if self._toolbox_client:
            log.info("PlatformMCPClientServiceAgent: Closing ToolboxClient connection.")
            await self._toolbox_client.close()

# Global agent instance for pickling
root_agent: PlatformMCPClientServiceAgent | None = None

# Apply nest_asyncio once at the module level
nest_asyncio.apply()

def initialize_global_agent():
    global root_agent
    if root_agent is None:
        log.info("Initializing PlatformMCPClientServiceAgent...")
        toolbox_url = os.environ.get("GENAI_TOOLBOX_URL", "http://127.0.0.1:5000")
        if not toolbox_url:
            log.error("GENAI_TOOLBOX_URL is not set.")
            raise ValueError("GENAI_TOOLBOX_URL not set for PlatformMCPClientServiceAgent.")

        try:
            root_agent = PlatformMCPClientServiceAgent(toolbox_url=toolbox_url)
            log.info("PlatformMCPClientServiceAgent initialized successfully and assigned to agent.root_agent.")
        except Exception as e:
            log.critical(f"CRITICAL: Failed to initialize PlatformMCPClientServiceAgent: {e}", exc_info=True)
            raise
    else:
        log.info("PlatformMCPClientServiceAgent (agent.root_agent) already initialized.")

# try:
#     initialize_global_agent()
# except Exception as e:
#     log.critical(f"CRITICAL: Module-level initialization of root_agent failed: {e}", exc_info=True)
