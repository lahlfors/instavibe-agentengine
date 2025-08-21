# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
import requests
import google.auth
import google.auth.transport.requests
from google.adk.agents import Agent

logging.basicConfig(level=logging.INFO)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, interacting with Memory Bank via REST API.
    """
    def __init__(self, name: str, model: str, instruction: str = None, description: str = None):
        # Pass required fields like name and model to the base class
        super().__init__(
            name=name,
            model=model,
            instruction=instruction or "I am an orchestrator agent with memory capabilities.",
            description=description or "An agent that can create and search memories.",
            tools=[self.create_memory, self.search_memories]
        )
        self.project = None
        self.location = None
        self.api_endpoint = None
        self.base_url = None
        self.memory_bank_url = None
        self.credentials = None
        self.reasoning_engine_id = None

    def set_up(self):
        """
        Called by the Agent Engine framework after deployment.
        """
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.reasoning_engine_id = os.getenv("REASONING_ENGINE_ID")

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")
        if not self.reasoning_engine_id:
            logging.error("REASONING_ENGINE_ID environment variable not set.")
            raise RuntimeError("REASONING_ENGINE_ID environment variable must be set.")

        self.api_endpoint = f"{self.location}-aiplatform.googleapis.com"
        self.base_url = f"https://{self.api_endpoint}/v1beta1/projects/{self.project}/locations/{self.location}/reasoningEngines/{self.reasoning_engine_id}"
        self.memory_bank_url = f"{self.base_url}/memories"

        try:
            self.credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        except google.auth.exceptions.DefaultCredentialsError as e:
            logging.error(f"Failed to get default credentials: {e}")
            raise RuntimeError("Failed to get default credentials. Ensure the environment is authenticated.") from e

        logging.info(f"Memory Bank URL set to: {self.memory_bank_url}")
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP COMPLETE ---")

    def _get_auth_headers(self):
        try:
            auth_req = google.auth.transport.requests.Request()
            if not self.credentials or not self.credentials.valid:
                self.credentials.refresh(auth_req)
            return {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.credentials.token}",
            }
        except Exception as e:
            logging.error(f"Error getting auth headers: {e}")
            raise

    # NO @tool decorator
    def create_memory(self, description: str, user_id: str) -> str:
        """
        Creates a new memory in the Memory Bank.

        Args:
            description: The text content of the memory to create.
            user_id: The user ID to associate with the memory.

        Returns:
            The resource name of the newly created memory.
        """
        if not self.memory_bank_url: self.set_up() # Ensure set_up called if not already
        headers = self._get_auth_headers()
        payload = {
            "fact": description,
            "user_id": user_id
        }
        logging.info(f"Creating memory at {self.memory_bank_url} for user: {user_id}")
        try:
            response = requests.post(url=self.memory_bank_url, headers=headers, json=payload)
            response.raise_for_status()
            memory = response.json()
            logging.info(f"Successfully created memory: {memory.get('name')}")
            return memory.get('name', '')
        except requests.exceptions.RequestException as e:
            logging.error(f"Error creating memory: {e} - Response: {e.response.text if e.response else 'No response'}")
            raise

    # NO @tool decorator
    def search_memories(self, query: str, user_id: str) -> str:
        """
        Searches for relevant memories in the Memory Bank for a specific user.

        Args:
            query: The text query to search for.
            user_id: The user ID to filter memories.

        Returns:
            A string containing the search results.
        """
        if not self.memory_bank_url: self.set_up() # Ensure set_up called if not already
        headers = self._get_auth_headers()
        search_url = f"{self.memory_bank_url}:search"
        payload = {
            "query": query,
            "user_id": user_id
        }
        logging.info(f"Searching memories at {search_url} for user: {user_id} with query: '{query}'")
        try:
            response = requests.post(url=search_url, headers=headers, json=payload)
            response.raise_for_status()
            search_response = response.json()
            results = [sr.get('memory', {}).get('fact') for sr in search_response.get('searchResults', []) if sr.get('memory', {}).get('fact')]
            logging.info(f"Found {len(results)} memories.")
            return "\n".join(results) if results else "No relevant memories found."
        except requests.exceptions.RequestException as e:
            logging.error(f"Error searching memories: {e} - Response: {e.response.text if e.response else 'No response'}")
            raise

# Add this line to help Pydantic resolve forward references
OrchestrateServiceAgent.model_rebuild()

# Instantiate the agent with required name and model
root_agent = OrchestrateServiceAgent(
    name="orchestrate_service_agent",
    model="gemini-1.5-flash"  # Specify a default or desired model
)
