from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService, SessionNotFoundError # Added SessionNotFoundError
from typing import Any, Dict, List, Optional # Added Optional
import os # For path joining
from dotenv import load_dotenv # To load .env

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

    async def query(self, query_text: str, **kwargs: Any) -> Dict[str, Any]:
        logger = logging.getLogger(__name__) # Define logger locally
        app_name = self._agent.name

        external_session_id = kwargs.get("session_id")

        interaction_user_id = self._user_id
        desired_session_id: str

        if external_session_id:
            interaction_user_id = str(external_session_id)
            desired_session_id = str(external_session_id)
        else:
            desired_session_id = self._user_id + "_" + os.urandom(4).hex()

        current_session_obj = None
        try:
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

        # Variable name was agent_response, changing to response_event_data for consistency
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
