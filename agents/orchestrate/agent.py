import os
import logging
from google.adk.agents import Agent

logging.basicConfig(level=logging.INFO)

class OrchestrateAgent(Agent):
    """
    Your main agent class that will be deployed.
    """
    name: str = "orchestrate-agent"
    def set_up(self):
        """
        This method is called by the ADK framework on the server AFTER
        the agent is deployed. This is the correct place for runtime logic.
        """
        from .host_agent import HostAgent
        from .tools import create_memory, search_memories
        from .memory_client import get_memory_bank_client

        # --- 1. Move your logging here ---
        logging.info("--- ORCHESTRATOR AGENT RUNTIME ENV CHECK ---")
        logging.info(f"ADK_SESSION_SPANNER_INSTANCE_ID: {os.getenv('ADK_SESSION_SPANNER_INSTANCE_ID')}")
        logging.info(f"ADK_SESSION_SPANNER_DATABASE_ID: {os.getenv('ADK_SESSION_SPANNER_DATABASE_ID')}")
        logging.info("--------------------------------------")

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

        from agents.app.common.tracing import trace_function_enhanced
        from opentelemetry import trace
        tracer = trace.get_tracer(__name__)
        self.host_agent.handle_query = trace_function_enhanced(tracer, system_name="OrchestrateAgent")(self.host_agent.handle_query)

        logging.info("OrchestrateServiceAgent set_up complete.")

    def query(self, input_text: str) -> str:
        if not self.host_agent:
            logging.error("HostAgent not initialized. set_up() was not called.")
            raise RuntimeError("Agent not properly initialized.")
        # Delegate the query to the HostAgent instance
        return self.host_agent.handle_query(input_text)

# 4. Define the root_agent for the ADK to find and deploy.
root_agent = OrchestrateAgent()
