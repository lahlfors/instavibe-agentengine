import os # For path joining
import logging # Added
from dotenv import load_dotenv # To load .env
from typing import Any, Dict, Optional # Removed AsyncIterable, ensured Any, Dict, Optional
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.sessions import SessionNotFoundError # Added
# from google.adk.sessions import Session # Optional for type hint
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
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

  async def query(self, query_text: str, **kwargs: Any) -> Dict[str, Any]:
        logger = logging.getLogger(__name__)
        app_name = self._agent.name

        external_session_id = kwargs.get("session_id")

        interaction_user_id = self._user_id  # Agent's generic user ID by default
        desired_session_id: str

        if external_session_id:
            interaction_user_id = str(external_session_id) # Use external ID for user context
            desired_session_id = str(external_session_id) # Use external ID as desired session key
            logger.info(f"External session_id '{desired_session_id}' provided, setting interaction_user_id to match.")
        else:
            # No external session_id, generate a unique one for this interaction.
            # Keep agent's generic _user_id as the interaction_user_id.
            desired_session_id = self._user_id + "_" + os.urandom(4).hex()
            logger.info(f"No external session_id. Generated '{desired_session_id}' for user '{interaction_user_id}'.")

        current_session_obj = None
        try:
            logger.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id}'")
            current_session_obj = await self._runner.session_service.get_session(
                app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id
            )
            if current_session_obj:
                 logger.info(f"Found existing session: {current_session_obj.id} for user {interaction_user_id}")
        except SessionNotFoundError:
            logger.info(f"Session {desired_session_id} for user {interaction_user_id} not found by get_session. Will create.")
            current_session_obj = None
        except Exception as e_get:
            logger.warning(f"Error during get_session for {desired_session_id} (user {interaction_user_id}): {e_get}. Will try to create.")
            current_session_obj = None

        if current_session_obj is None:
            try:
                logger.info(f"Creating session: app='{app_name}', user='{interaction_user_id}', session_id_override='{desired_session_id}'")
                current_session_obj = await self._runner.session_service.create_session(
                    app_name=app_name, user_id=interaction_user_id, session_id_override=desired_session_id
                )
                logger.info(f"Successfully created session: {current_session_obj.id} for user {interaction_user_id}.")
            except Exception as e_create:
                logger.error(f"Failed to create session for user {interaction_user_id} with desired_id {desired_session_id}: {e_create}", exc_info=True)
                return {"error": f"Session management failure during create: {e_create}"}

        if not current_session_obj:
            logger.error(f"Critical error: Failed to obtain a session object for user {interaction_user_id}, session_id {desired_session_id}.")
            return {"error": "Failed to get or create a session."}

        response_event_data = None
        async for event in self._runner.run_async(
            user_id=interaction_user_id,
            session_id=current_session_obj.id,
            new_message={"text_content": query_text}
        ):
            response_event_data = event
            break

        if response_event_data:
            if isinstance(response_event_data, dict):
                return response_event_data
            else:
                logger.warning(f"run_async returned event of type {type(response_event_data)} instead of dict for session {current_session_obj.id}: {str(response_event_data)[:200]}")
                return {"error": "Unexpected event type from agent execution", "event_preview": str(response_event_data)[:100]}
        else:
            logger.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            return {"error": "No response event received from agent execution"}