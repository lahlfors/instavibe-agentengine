# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
from google.adk.agents import Agent
# No tool decorator import needed

# Correct import path for MemoryBankServiceClient
from google.cloud.aiplatform.preview.memory_bank import MemoryBankServiceClient

logging.basicConfig(level=logging.INFO)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, structured to follow the official
    ADK Memory Bank template.
    """
    def __init__(self):
        # Register tools by passing the method references in a list
        super().__init__(tools=[self.create_memory, self.search_memories])

    def set_up(self):
        """
        Called by the Agent Engine framework after deployment.
        """
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")

        self.parent = f"projects/{self.project}/locations/{self.location}"

        self.memory_bank_client = MemoryBankServiceClient(client_options={"api_endpoint": f"{self.location}-aiplatform.googleapis.com"})
        logging.info(f"MemoryBankServiceClient initialized for parent: {self.parent}")
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP COMPLETE ---")

    # NO @tool decorator
    def create_memory(self, description: str) -> str:
        """
        Creates a new memory in the Memory Bank.

        Args:
            description: The text content of the memory to create.

        Returns:
            The resource name of the newly created memory.
        """
        if not self.memory_bank_client:
            raise RuntimeError("Memory Bank client not initialized. Call set_up first.")

        logging.info(f"Creating memory: {description}")
        response = self.memory_bank_client.create_memory(
            parent=self.parent,
            memory={"description": description}
        )
        logging.info(f"Successfully created memory: {response.name}")
        return response.name

    # NO @tool decorator
    def search_memories(self, query: str) -> str:
        """
        Searches for relevant memories in the Memory Bank.

        Args:
            query: The text query to search for.

        Returns:
            A string containing the search results.
        """
        if not self.memory_bank_client:
            raise RuntimeError("Memory Bank client not initialized. Call set_up first.")

        logging.info(f"Searching memories with query: {query}")
        response = self.memory_bank_client.search_memories(
            parent=self.parent,
            query=query
        )
        results = [memory.memory.description for memory in response.search_results]
        logging.info(f"Found {len(results)} memories.")
        return "\n".join(results) if results else "No relevant memories found."

# The ADK framework looks for a 'root_agent' object to deploy.
root_agent = OrchestrateServiceAgent()
