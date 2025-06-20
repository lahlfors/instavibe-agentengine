import os # For path joining
import logging # Added
import asyncio # Added
import nest_asyncio # Added
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
from common.task_manager import AgentTaskManager # Reverted to common
from . import agent

# Load environment variables from the root .env file.
# While agent.py also does this, adding it here ensures that if PlannerAgent
# is used or tested in a context where agent.py wasn't the first import,
# the environment is still correctly configured.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Apply nest_asyncio to allow asyncio.run() within an existing event loop (e.g., server)
nest_asyncio.apply()

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

  def query(self, query: str, **kwargs: Any) -> Dict[str, Any]: # Renamed query_text back to query, made sync
        logger = logging.getLogger(__name__)
        app_name = self._agent.name

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
            # logger.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
            # Synchronous call
            current_session_obj = self._runner.session_service.get_session(
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
                # logger.info(f"Creating session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
                # Synchronous call, using session_id as override as per user example context
                current_session_obj = self._runner.session_service.create_session(
                    app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
                    # Note: ADK docs for BaseSessionService.create_session show session_id_override.
                    # User example for InMemorySessionService shows session_id. Assuming session_id works as override.
                )
                # logger.info(f"Successfully created session: {current_session_obj.id} for user {interaction_user_id}.")
            except Exception as e_create:
                logger.error(f"Failed to create session for user {interaction_user_id} with session_id {desired_session_id_for_service}: {e_create}", exc_info=True)
                return {"error": f"Session management failure during create: {e_create}"}

        if not current_session_obj:
            logger.error(f"Critical error: Failed to obtain a session object for user {interaction_user_id}, session_id {desired_session_id_for_service}.")
            return {"error": "Failed to get or create a session."}

        response_event_data = None

        async def _execute_run_and_get_first_event():
            """Helper async function to run the agent and get the first event."""
            # Assuming self._runner.run is an async generator or returns an async iterable
            async for event in self._runner.run(
                user_id=interaction_user_id,
                session_id=current_session_obj.id,
                new_message=Content(parts=[Part(text=query)], role="user")
            ):
                return event # Return the first event yielded by the runner
            return None # Should not happen if agent always yields at least one event before finishing

        try:
            # Run the async helper function using asyncio.run()
            response_event_data = asyncio.run(_execute_run_and_get_first_event())
        except Exception as e_run:
            logger.error(f"Error during asyncio.run(_execute_run_and_get_first_event) for session {current_session_obj.id}: {e_run}", exc_info=True)
            return {"error": f"Agent execution error: {e_run}"}

        if response_event_data:
            if isinstance(response_event_data, dict):
                # If the event itself is already the dict response we want
                return response_event_data
            # Check if it's an ADK Event object and extract content if it's the final response
            # This part needs to align with how ADK Event objects are structured.
            # The previous code checked for is_final_response(), content, and parts.
            # This structure might vary based on ADK version and agent type (LoopAgent vs LlmAgent directly).
            # For now, let's assume the event might be a dict or needs conversion from an ADK event object.
            # If it's not a dict, we need to know its structure to convert it.
            # For simplicity, if it's not a dict, we'll log and return it as is,
            # which might need further refinement based on actual event structure.
            # Example for ADK event (this is a guess, adapt to actual Event structure):
            if hasattr(response_event_data, 'content') and response_event_data.content and \
               hasattr(response_event_data.content, 'parts') and response_event_data.content.parts and \
               hasattr(response_event_data.content.parts[0], 'text'):
                return {"output": response_event_data.content.parts[0].text}

            logger.warning(f"Runner returned event of type {type(response_event_data)} that was not a dict and not directly convertible: {str(response_event_data)[:200]}")
            # If we don't know how to convert it, returning it as is or an error might be necessary.
            # Let's try to return its string representation within a dict for now.
            return {"raw_event_data": str(response_event_data)}
        else:
            logger.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            return {"error": "No response event received from agent execution"}