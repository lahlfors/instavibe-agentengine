from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from typing import Any, Dict, List, Optional
import os # For path joining
# import asyncio # Removed
from dotenv import load_dotenv # To load .env
from google.genai.types import Content, Part # Added import

# Import HostAgent to create the underlying LlmAgent
from .host_agent import HostAgent
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

    def __init__(self):
        self._user_id: str = "orchestrate_service_user"

        # Instantiate HostAgent and create the underlying LlmAgent.
        # The remote_agent_addresses_str is no longer needed.

        self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = os.environ.get("GOOGLE_CLOUD_LOCATION")

        self.memory_bank_client = None
        if self.project_id:
            try:
                self.memory_bank_client = MemoryBankServiceClient(
                    client_options={"api_endpoint": f"{self.location}-aiplatform.googleapis.com"}
                )
                print("Memory Bank client initialized successfully.")
            except Exception as e:
                print(f"An unexpected error occurred during Memory Bank initialization: {e}")
                self.memory_bank_client = None
        else:
            print("Skipping Memory Bank client initialization due to missing GOOGLE_CLOUD_PROJECT.")

        host_agent_logic = HostAgent(tools=[self.create_memory, self.search_memories])
        self._agent: BaseAgent = host_agent_logic.create_agent()

        agent_engine_id = os.environ.get("AGENT_ENGINE_ID")

        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=VertexAiSessionService(
                project=project_id,
                location=location,
                agent_engine_id=agent_engine_id,
            ),
            memory_service=VertexAiMemoryBankService(
                project=project_id,
                location=location,
                agent_engine_id=agent_engine_id,
                client=memory_bank_client
            ),
        )

    def get_processing_message(self) -> str:
        return "Orchestrating the request..."

    def create_memory(self, user_id: str, content: str, metadata: dict):
        """Creates a new memory in the Memory Bank."""
        if not self.memory_bank_client:
            return None

        parent = self.memory_bank_client.common_location_path(self.project_id, self.location)
        memory = memory_bank_types.Memory(
            user_id=user_id,
            content=content,
            metadata=metadata,
        )
        request = memory_bank_types.CreateMemoryRequest(
            parent=parent,
            memory=memory,
        )
        try:
            response = self.memory_bank_client.create_memory(request=request)
            return response
        except Exception as e:
            print(f"Error creating memory: {e}")
            return None

    def search_memories(self, user_id: str, query: str, top_k: int = 5):
        """Searches for memories in the Memory Bank."""
        if not self.memory_bank_client:
            return None

        parent = self.memory_bank_client.common_location_path(self.project_id, self.location)
        request = memory_bank_types.SearchMemoriesRequest(
            parent=parent,
            user_id=user_id,
            query=query,
            top_k=top_k,
        )
        try:
            response = self.memory_bank_client.search_memories(request=request)
            return response
        except Exception as e:
            print(f"Error searching memories: {e}")
            return None

    def query(self, query: str, **kwargs: Any) -> Dict[str, Any]: # Renamed query_text back to query
        # Using module-level 'log'
        app_name = self._agent.name

        interaction_user_id = str(kwargs.get("session_id", self._user_id))
        desired_session_id_for_service = interaction_user_id

        current_session_obj: Optional[Any] = None
        try:
            log.debug(f"Attempting to get session: app='{app_name}', user='{interaction_user_id}', session_id='{desired_session_id_for_service}'")
            current_session_obj = self._runner.session_service.get_session( # Synchronous
                app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
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
