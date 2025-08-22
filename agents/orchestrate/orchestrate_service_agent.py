# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
import aiohttp
import google.auth
import google.auth.credentials  # Import for type hinting
import google.auth.transport.requests
import google.auth.transport._aiohttp_requests as aiohttp_requests
from google.adk.agents import Agent
from typing import Optional, List
from agents.app.utils.communication import call_http_endpoint

logging.basicConfig(level=logging.INFO)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, interacting with Memory Bank via REST API.
    """
    # Declare fields at the class level for Pydantic
    project: Optional[str] = None
    location: Optional[str] = None
    api_endpoint: Optional[str] = None
    base_url: Optional[str] = None
    memory_bank_url: Optional[str] = None
    credentials: Optional[google.auth.credentials.Credentials] = None
    reasoning_engine_id: Optional[str] = None

    def __init__(self, name: str, model: str, instruction: Optional[str] = None, description: Optional[str] = None):
        # Pass required fields like name and model to the base class
        super().__init__(
            name=name,
            model=model,
            instruction=instruction or "I am an orchestrator agent with memory capabilities.",
            description=description or "An agent that can create and search memories.",
            tools=[self.create_memory, self.search_memories]
        )
        # Do NOT initialize self.project, self.location, etc. here

    def set_up(self):
        """
        Called by the Agent Engine framework after deployment.
        """
        if self.project: # Basic check to see if set_up has run
            return

        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.reasoning_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID") # Use system-provided ID

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")
        if not self.reasoning_engine_id:
            logging.error("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable not set.")
            raise RuntimeError("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable must be set.")

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

    async def _get_auth_headers(self):
        """
        Asynchronously gets fresh, valid authentication headers.
        """
        try:
            # Use the async-native transport
            auth_req = aiohttp_requests.Request()

            if not self.credentials or not self.credentials.valid:
                # Await the non-blocking refresh call
                await self.credentials.refresh(auth_req)

            return {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.credentials.token}",
            }
        except Exception as e:
            logging.error(f"Error getting auth headers: {e}")
            raise

    async def create_memory(self, description: str, user_id: str) -> str:
        """
        Creates a new memory in the Memory Bank.

        Args:
            description: The text content of the memory to create.
            user_id: The user ID to associate with the memory.

        Returns:
            The resource name of the newly created memory.
        """
        if not self.memory_bank_url: self.set_up() # Ensure set_up called if not already
        headers = await self._get_auth_headers()
        payload = {"fact": description, "user_id": user_id}
        logging.info(f"Creating memory at {self.memory_bank_url} for user: {user_id}")
        try:
            memory = await call_http_endpoint(
                source_agent="orchestrate_service_agent",
                target_service="memory_bank",
                http_method="POST",
                url=self.memory_bank_url,
                headers=headers,
                json=payload
            )
            logging.info(f"Successfully created memory: {memory.get('name')}")
            return memory.get('name', '')
        except aiohttp.ClientError as e:
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
        if not self.memory_bank_url: self.set_up()
        headers = await self._get_auth_headers()
        search_url = f"{self.memory_bank_url}:search"
        payload = {"query": query, "user_id": user_id}
        logging.info(f"Searching memories at {search_url} for user: {user_id} with query: '{query}'")
        try:
            search_response = await call_http_endpoint(
                source_agent="orchestrate_service_agent",
                target_service="memory_bank",
                http_method="POST",
                url=search_url,
                headers=headers,
                json=payload
            )
            results = [sr.get('memory', {}).get('fact') for sr in search_response.get('searchResults', []) if sr.get('memory', {}).get('fact')]
            logging.info(f"Found {len(results)} memories.")
            return "\n".join(results) if results else "No relevant memories found."
        except aiohttp.ClientError as e:
            logging.error(f"Error searching memories: {e}")
            raise

OrchestrateServiceAgent.model_rebuild()

root_agent = OrchestrateServiceAgent(
    name="orchestrate_service_agent",
    model="gemini-2.0-flash-001"
)
