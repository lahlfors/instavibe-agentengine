from typing import Any, Dict, Optional # Removed AsyncIterable as it's not used in the new query
import logging # Added
import asyncio # Added
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
# from google.adk.sessions import SessionNotFoundError # Removed
# from google.adk.sessions import Session # Removed
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part # Modified import
from common.task_manager import AgentTaskManager
from . import agent
import os # For path joining
from dotenv import load_dotenv # To load .env

# Load environment variables from the root .env file.
# While agent.py (imported as .agent) also does this,
# adding it here ensures that if SocialAgent is used or tested in a context
# where agent.py wasn't the first import, the environment is still correctly configured.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class SocialAgent(AgentTaskManager):
  """An agent that handles social profile analysis."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
    self._user_id = "remote_agent"
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
      return "Processing the social profile analysis request..."

  def _build_agent(self) -> LoopAgent:
    """Builds the LLM agent for the social profile analysis agent."""
    return agent.root_agent

  async def _execute_query_async(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        logger = logging.getLogger(__name__)
        app_name = self._agent.name

        interaction_user_id = str(kwargs.get("session_id", self._user_id))
        desired_session_id_for_service = interaction_user_id

        current_session_obj: Optional[Any] = None # Use Any if Session import is problematic/removed
        try:
            logger.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
            current_session_obj = await self._runner.session_service.get_session(
                app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
            )
            if current_session_obj:
                logger.info(f"Found existing session: {current_session_obj.id} for user {interaction_user_id}")
            else:
                logger.info(f"Session {desired_session_id_for_service} for user {interaction_user_id} not found (get_session returned None). Will create.")
        except Exception as e_get:
            logger.warning(f"Exception during get_session for user '{interaction_user_id}', session_id '{desired_session_id_for_service}': {e_get}. Will assume session needs creation.")
            current_session_obj = None

        if current_session_obj is None:
            try:
                logger.info(f"Creating session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}' (acting as override/specific ID)")
                current_session_obj = await self._runner.session_service.create_session(
                    app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
                )
                logger.info(f"Successfully created session: {current_session_obj.id} for user {interaction_user_id}.")
            except Exception as e_create:
                logger.error(f"Failed to create session for user {interaction_user_id} with session_id {desired_session_id_for_service}: {e_create}", exc_info=True)
                return {"error": f"Session management failure during create: {e_create}"}

        if not current_session_obj:
            logger.error(f"Critical error: Failed to obtain a session object for user {interaction_user_id}, session_id {desired_session_id_for_service}.")
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
            logger.error(f"Error during run_async for session {current_session_obj.id}: {e_run}", exc_info=True)
            return {"error": f"Agent execution error: {e_run}"}

        if response_event_data:
            if isinstance(response_event_data, dict): # Ideal case if event itself is the dict
                return response_event_data
            elif hasattr(response_event_data, 'is_final_response') and response_event_data.is_final_response():
                if response_event_data.content and response_event_data.content.parts and response_event_data.content.parts[0].text:
                    return {"output": response_event_data.content.parts[0].text} # Example structure
            logger.warning(f"run_async returned event of type {type(response_event_data)} for session {current_session_obj.id}. Content: {str(response_event_data)[:200]}")
            return {"error": "Unexpected or non-final event type from agent execution", "event_preview": str(response_event_data)[:100]}
        else:
            logger.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            return {"error": "No response event received from agent execution"}

  def query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        return asyncio.run(self._execute_query_async(query=query, **kwargs))