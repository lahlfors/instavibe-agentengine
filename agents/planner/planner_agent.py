import os # For path joining
import logging # Added
from dotenv import load_dotenv # To load .env
from typing import Any, Dict, Optional # Removed AsyncIterable, ensured Any, Dict, Optional
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
# from google.adk.sessions import SessionNotFoundError # Removed
# from google.adk.sessions import Session # Removed Session for Optional[Any]
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part # Modified import
from common.task_manager import AgentTaskManager
from . import agent

# Load environment variables from the root .env file.
# While agent.py also does this, adding it here ensures that if PlannerAgent
# is used or tested in a context where agent.py wasn't the first import,
# the environment is still correctly configured.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class PlannerAgent(AgentTaskManager):
  """An agent to help user planning a night out with its desire location."""

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
      return "Processing the planning request..."

  def _build_agent(self) -> LoopAgent:
    """Builds the LLM agent for the night out planning agent."""
    return agent.root_agent

  async def query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        logger = logging.getLogger(__name__)
        app_name = self._agent.name # Or self._runner.app_name if that's more appropriate from ADK 1.0.0 Runner

        # Determine the user_id and desired_session_id for this interaction
        # ADK 1.0.0 examples use user_id for session context and run_async.
        # The session_id from kwargs (from instavibe-app) is the user_name.
        interaction_user_id = str(kwargs.get("session_id", self._user_id)) # Default to agent's user_id if no session_id from app

        # For InMemorySessionService with ADK 1.0.0, the example shows passing session_id to create_session
        # This session_id is then used in run_async. Let's use interaction_user_id as the basis for session_id too
        # if we want the session to be identified by "Alice".
        # If instavibe-app is providing "Alice" as kwargs["session_id"], then interaction_user_id becomes "Alice".
        # We'll use this as the session_id for get/create, effectively making session_id = user_id for these calls.
        desired_session_id_for_service = interaction_user_id

        current_session_obj: Optional[Any] = None # Changed type hint to Optional[Any] for safety
        try:
            logger.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
            current_session_obj = await self._runner.session_service.get_session(
                app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
            )
            if current_session_obj:
                logger.info(f"Found existing session: {current_session_obj.id} for user {interaction_user_id}")
            else:
                # Handles get_session returning None if session not found
                logger.info(f"Session {desired_session_id_for_service} for user {interaction_user_id} not found (get_session returned None). Will create.")
                # current_session_obj is already None in this path
        except Exception as e_get:
            # Catches other errors from get_session (e.g., if it still raises something on 'not found' that isn't SessionNotFoundError)
            logger.warning(f"Exception during get_session for user '{interaction_user_id}', session_id '{desired_session_id_for_service}': {e_get}. Will assume session needs creation.")
            current_session_obj = None # Ensure it's None so create is attempted

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
                session_id=current_session_obj.id, # Use the ID from the obtained session object
                new_message=Content(parts=[Part(text=query)], role="user")
            ):
                response_event_data = event
                break
        except Exception as e_run:
            logger.error(f"Error during run_async for session {current_session_obj.id}: {e_run}", exc_info=True)
            return {"error": f"Agent execution error: {e_run}"}

        if response_event_data:
            if isinstance(response_event_data, dict):
                return response_event_data
            # ADK 1.0.0 Event might have .content.parts[0].text or similar for final response
            elif hasattr(response_event_data, 'is_final_response') and response_event_data.is_final_response():
                if response_event_data.content and response_event_data.content.parts:
                    # This is a common pattern for ADK final responses.
                    # Assuming the response is text, and needs to be a dict.
                    # This part is speculative based on typical ADK event structure.
                    # The actual dict structure might need to be built differently.
                    return {"output": response_event_data.content.parts[0].text}
            logger.warning(f"run_async returned event of type {type(response_event_data)} for session {current_session_obj.id}. Content: {str(response_event_data)[:200]}")
            return {"error": "Unexpected or non-final event type from agent execution", "event_preview": str(response_event_data)[:100]}
        else:
            logger.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            return {"error": "No response event received from agent execution"}