from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from typing import Any, Dict, List
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

    async def query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Handles the user's request by running the underlying Orchestrate LlmAgent.
        """
        agent_response = await self._runner.arun(
            app_name=self._agent.name,
            session_id=self._user_id,
            inputs={"text_content": query},
            stream=False,
            **kwargs
        )
        return agent_response
