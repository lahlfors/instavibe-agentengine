from typing import Any, Dict, Optional
import logging
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from agents.app.common.task_manager import AgentTaskManager
from . import agent
import os
from dotenv import load_dotenv
import sys
sys.path.append('.')
from common.agent_gateway import AgentGateway

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class SocialAgent(AgentTaskManager):
  """An agent that handles social profile analysis."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = None
    self._user_id = None
    self._runner = None
    self.gateway = AgentGateway(service_name="social-agent")

  def set_up(self):
    if self._runner:
        return

    def _setup_impl():
        logging.info("Starting SocialAgent.set_up")
        self._agent = self._build_agent()
        self._user_id = "remote_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        logging.info("SocialAgent set up complete.")

    self.gateway.execute_sync("SocialAgent.set_up", _setup_impl)

  def get_processing_message(self) -> str:
      return "Processing the social profile analysis request..."

  def _build_agent(self) -> LoopAgent:
    """Builds the LLM agent for the social profile analysis agent."""
    return agent.create_agent()

  def query(self, input: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        self.set_up()

        def _query_impl():
            logger = logging.getLogger(__name__)
            app_name = self._agent.name

            action = input.get("action")
            data = input.get("data")

            if not action:
                return {"error": "No action specified in the input."}

            query = f"Action: {action}, Data: {data}"
            if action == "share":
                if isinstance(data, dict) and "message" in data:
                    query = f"Share this message: {data['message']}"
                else:
                    query = f"Share this content: {data}"
            elif action == "get_profile":
                if isinstance(data, dict) and "name" in data:
                    query = f"Get the profile for user {data['name']}"
                else:
                    query = f"Get the profile for {data}"

            interaction_user_id = str(kwargs.get("session_id", self._user_id))
            desired_session_id_for_service = interaction_user_id

            current_session_obj: Optional[Any] = None
            try:
                logger.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
                current_session_obj = self._runner.session_service.get_session(
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
                    logger.info(f"Creating session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
                    current_session_obj = self._runner.session_service.create_session(
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
                for event in self._runner.run(
                    user_id=interaction_user_id,
                    session_id=current_session_obj.id,
                    new_message=Content(parts=[Part(text=query)], role="user")
                ):
                    response_event_data = event
                    break
            except Exception as e_run:
                logger.error(f"Error during run for session {current_session_obj.id}: {e_run}", exc_info=True)
                return {"error": f"Agent execution error: {e_run}"}

            if response_event_data:
                if isinstance(response_event_data, dict):
                    return response_event_data
                elif hasattr(response_event_data, 'is_final_response') and response_event_data.is_final_response():
                    if response_event_data.content and response_event_data.content.parts and response_event_data.content.parts[0].text:
                        return {"output": response_event_data.content.parts[0].text}
                logger.warning(f"run_async returned event of type {type(response_event_data)} for session {current_session_obj.id}. Content: {str(response_event_data)[:200]}")
                return {"error": "Unexpected or non-final event type from agent execution", "event_preview": str(response_event_data)[:100]}
            else:
                logger.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
                return {"error": "No response event received from agent execution"}

        return self.gateway.execute_sync("SocialAgent.query", _query_impl)
