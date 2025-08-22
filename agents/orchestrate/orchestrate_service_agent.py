# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
from google.adk.agents import Agent
from google.adk.memory import VertexAiMemoryBankService
from google.adk.sessions import Session
from google.genai.types import Content, Part
from typing import Optional

logging.basicConfig(level=logging.INFO)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, interacting with Memory Bank via the ADK.
    """
    project: Optional[str] = None
    location: Optional[str] = None
    reasoning_engine_id: Optional[str] = None
    memory_service: Optional[VertexAiMemoryBankService] = None
    app_name: str = "orchestrate_service_agent"

    def __init__(self, name: str, model: str, instruction: Optional[str] = None, description: Optional[str] = None):
        super().__init__(
            name=name,
            model=model,
            instruction=instruction or "I am an orchestrator agent with memory capabilities.",
            description=description or "An agent that can create and search memories.",
            tools=[self.create_memory, self.search_memories]
        )

    def set_up(self):
        """
        Called by the Agent Engine framework after deployment.
        """
        if self.memory_service:  # Basic check to see if set_up has run
            return

        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.reasoning_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")
        if not self.reasoning_engine_id:
            logging.error("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable not set.")
            raise RuntimeError("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable must be set.")

        self.memory_service = VertexAiMemoryBankService(
            project=self.project,
            location=self.location,
            agent_engine_id=self.reasoning_engine_id
        )
        logging.info("VertexAiMemoryBankService initialized.")
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP COMPLETE ---")

    async def create_memory(self, description: str, user_id: str) -> str:
        """
        Creates a new memory in the Memory Bank.

        Args:
            description: The text content of the memory to create.
            user_id: The user ID to associate with the memory.

        Returns:
            A confirmation message.
        """
        if not self.memory_service:
            self.set_up()

        # The ADK's add_session_to_memory expects a Session object.
        # We can create a lightweight session with a single message to store the fact.
        memory_session = Session(
            app_name=self.app_name,
            user_id=user_id,
            messages=[Content(role='user', parts=[Part(text=description)])]
        )
        logging.info(f"Creating memory for user: {user_id}")
        try:
            await self.memory_service.add_session_to_memory(memory_session)
            logging.info(f"Successfully created memory for user: {user_id}")
            return f"Memory created for user {user_id}."
        except Exception as e:
            logging.error(f"Error creating memory: {e}")
            raise

    async def search_memories(self, query: str, user_id: str) -> str:
        """
        Searches for relevant memories in the Memory Bank for a specific user.

        Args:
            query: The text query to search for.
            user_id: The user ID to filter memories.

        Returns:
            A string containing the search results.
        """
        if not self.memory_service:
            self.set_up()

        logging.info(f"Searching memories for user: {user_id} with query: '{query}'")
        try:
            search_results = await self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=user_id,
                query=query
            )
            results = [
                result.get('memory', {}).get('fact')
                for result in search_results
                if result.get('memory', {}).get('fact')
            ]
            logging.info(f"Found {len(results)} memories.")
            return "\n".join(results) if results else "No relevant memories found."
        except Exception as e:
            logging.error(f"Error searching memories: {e}")
            raise

OrchestrateServiceAgent.model_rebuild()

root_agent = OrchestrateServiceAgent(
    name="orchestrate_service_agent",
    model="gemini-2.0-flash-001"
)
