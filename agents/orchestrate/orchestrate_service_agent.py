from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from typing import Any, Dict, List # Added List for type hint

# Assuming agent.py (which defines root_agent) is in the same directory 'orchestrate'
# So, from .agent import root_agent as orchestrate_llm_agent should work.
from .agent import root_agent as orchestrate_llm_agent

class OrchestrateServiceAgent:
    """
    A wrapper class for the Orchestrate LlmAgent to provide a queryable interface
    compatible with the ADK deployment expectations.
    """
    SUPPORTED_CONTENT_TYPES: List[str] = ["text", "text/plain"] # Added type hint

    def __init__(self):
        self._agent: BaseAgent = orchestrate_llm_agent
        self._user_id: str = "orchestrate_service_user" # Added type hint

        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    def get_processing_message(self) -> str:
        return "Orchestrating the request..."

    async def async_query(self, query: str, **kwargs: Any) -> Dict[str, Any]: # Added type hint for kwargs
        """
        Handles the user's request by running the underlying Orchestrate LlmAgent.
        """
        agent_response = await self._runner.run_pipeline(
            app_name=self._agent.name,
            session_id=self._user_id,
            inputs={"text_content": query},
            stream=False,
            **kwargs
        )
        return agent_response
