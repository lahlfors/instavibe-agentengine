import os
import logging
from .host_agent import HostAgent
from .tools import create_memory, search_memories
from .memory_client import get_memory_bank_client

logging.basicConfig(level=logging.INFO)

class OrchestrateServiceAgent:
    def __init__(self):
        self.host_agent = None
        self.memory_client = None
        self.tools = []
        # IMPORTANT: Don't do heavy initialization or os.getenv here
        # as __init__ might be called by the framework in various contexts.

    def set_up(self):
        """
        Called by the Agent Engine framework after the instance is created.
        This is the place to initialize resources and dependencies.
        """
        logging.info("--- AGENT ENGINE RUNTIME ENV CHECK ---")
        logging.info(f"GOOGLE_CLOUD_PROJECT: {os.getenv('GOOGLE_CLOUD_PROJECT')}")
        logging.info(f"ADK_SESSION_SPANNER_INSTANCE_ID: {os.getenv('ADK_SESSION_SPANNER_INSTANCE_ID')}")
        logging.info(f"ADK_SESSION_SPANNER_DATABASE_ID: {os.getenv('ADK_SESSION_SPANNER_DATABASE_ID')}")
        logging.info("------------------------------------")

        # Initialize dependencies
        self.memory_client = get_memory_bank_client()

        # Create tools
        # Example: wrap the functions to be callable methods or objects if needed
        self.tools = [
            create_memory(self.memory_client),
            search_memories(self.memory_client),
        ]

        # Initialize HostAgent with the created tools
        self.host_agent = HostAgent(tools=self.tools)
        logging.info("OrchestrateServiceAgent set_up complete.")

    def query(self, input_text: str) -> str:
        if not self.host_agent:
            logging.error("HostAgent not initialized. set_up() was not called.")
            raise RuntimeError("Agent not properly initialized.")
        # Delegate the query to the HostAgent instance
        return self.host_agent.handle_query(input_text)
