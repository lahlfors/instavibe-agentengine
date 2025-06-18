from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService # Removed SessionNotFoundError, Session
from typing import Any, Dict, List, Optional
import os # For path joining
# import asyncio # Removed
from dotenv import load_dotenv # To load .env
from google.genai.types import Content, Part # Added import

# Import HostAgent to create the underlying LlmAgent
from agents.orchestrate.host_agent import HostAgent
import logging # For logging addresses

# Load environment variables from the root .env file
# This ensures that any underlying components (like HostAgent or its dependencies)
# that might implicitly rely on environment variables (e.g., for Google Cloud clients)
# have them loaded.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

log = logging.getLogger(__name__)

class OrchestrateServiceAgent:
    """
    A wrapper class for the Orchestrate LlmAgent to provide a queryable interface
    compatible with the ADK deployment expectations. It now accepts remote agent
    addresses at construction to configure the underlying HostAgent.
    """
    SUPPORTED_CONTENT_TYPES: List[str] = ["text", "text/plain"]

    def __init__(self, remote_agent_addresses_str: str):
        self._user_id: str = "orchestrate_service_user"

        # Parse the remote_agent_addresses_str into a list
        parsed_addresses: List[str] = [
            addr.strip() for addr in remote_agent_addresses_str.split(',') if addr.strip()
        ]
        log.info(f"OrchestrateServiceAgent received remote_agent_addresses: {parsed_addresses}")

        # Instantiate HostAgent and create the underlying LlmAgent
        # Assuming HostAgent does not require a task_callback for basic agent creation
        host_agent_logic = HostAgent(remote_agent_addresses=parsed_addresses, task_callback=None)
        self._agent: BaseAgent = host_agent_logic.create_agent()

        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    def get_processing_message(self) -> str:
        return "Orchestrating the request..."

    def query(self, query: str, **kwargs: Any) -> Dict[str, Any]: # Renamed query_text back to query
        # Using module-level 'log'
        app_name = self._agent.name

        interaction_user_id = str(kwargs.get("session_id", self._user_id))
        desired_session_id_for_service = interaction_user_id

        current_session_obj: Optional[Any] = None
        try:
            log.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id}'")
            current_session_obj = self._runner.session_service.get_session( # Synchronous
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
                log.info(f"Creating session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id}'")
                current_session_obj = self._runner.session_service.create_session( # Synchronous
                    app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id
                )
                log.info(f"Successfully created session: {current_session_obj.id} for user {interaction_user_id}.")
            except Exception as e_create:
                log.error(f"Failed to create session for user {interaction_user_id} with session_id {desired_session_id}: {e_create}", exc_info=True)
                return {"error": f"Session management failure during create: {e_create}"}

        if not current_session_obj:
            log.error(f"Critical error: Failed to obtain a session object for user {interaction_user_id}, session_id {desired_session_id}.")
            return {"error": "Failed to get or create a session."}

        response_event_data = None # Was agent_response before
        try:
            for event in self._runner.run( # Synchronous runner call
                user_id=interaction_user_id,
                session_id=current_session_obj.id,
                new_message=Content(parts=[Part(text=query)], role="user") # Use query parameter
            ):
                response_event_data = event
                break
        except Exception as e_run:
            log.error(f"Error during run for session {current_session_obj.id}: {e_run}", exc_info=True)
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
            log.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            return {"error": "No response event received from agent execution"}
