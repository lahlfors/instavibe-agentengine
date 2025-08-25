import os
import logging
import sys
sys.path.append('.')
from common.tracing import configure_tracer
configure_tracer(service_name="orchestrate-agent")
from google.adk.agents import Agent
from opentelemetry import trace

# Get a tracer. It's often best to get this once per module.
tracer = trace.get_tracer(__name__)

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
        # Start a main span for the entire set_up method
        with tracer.start_as_current_span("OrchestrateAgent.set_up") as main_span:
            main_span.add_event("Starting OrchestrateAgent set_up")
            print("ORCHESTRATE AGENT: Starting set_up method...")

            try:
                from .host_agent import HostAgent
                from .tools import create_memory, search_memories
                from .memory_client import get_memory_bank_client

                # --- Step 1: Memory Client ---
                with tracer.start_as_current_span("initialize_memory_client") as memory_span:
                    memory_span.add_event("Initializing memory bank client")
                    print("ORCHESTRATE AGENT: Initializing memory bank client...")
                    try:
                        self.memory_client = get_memory_bank_client()
                        instance_id = os.getenv('ADK_SESSION_SPANNER_INSTANCE_ID')
                        database_id = os.getenv('ADK_SESSION_SPANNER_DATABASE_ID')
                        memory_span.set_attribute("spanner_instance_id", instance_id or "Not Set")
                        memory_span.set_attribute("spanner_database_id", database_id or "Not Set")
                        print("ORCHESTRATE AGENT: Memory bank client initialized successfully.")
                        memory_span.add_event("Memory bank client initialized successfully")
                        memory_span.set_status(trace.Status(trace.StatusCode.OK))
                    except Exception as e:
                        print(f"ORCHESTRATE AGENT: ERROR during memory client init: {e}")
                        memory_span.record_exception(e)
                        memory_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        raise

                # --- Step 2: Tools ---
                with tracer.start_as_current_span("create_tools") as tools_span:
                    tools_span.add_event("Creating tools")
                    print("ORCHESTRATE AGENT: Creating tools...")
                    try:
                        self.tools = [
                            create_memory(self.memory_client),
                            search_memories(self.memory_client),
                        ]
                        print("ORCHESTRATE AGENT: Tools created successfully.")
                        tools_span.add_event("Tools created successfully")
                        tools_span.set_status(trace.Status(trace.StatusCode.OK))
                    except Exception as e:
                        print(f"ORCHESTRATE AGENT: ERROR during tool creation: {e}")
                        tools_span.record_exception(e)
                        tools_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        raise

                # --- Step 3: Host Agent ---
                with tracer.start_as_current_span("build_host_agent") as host_agent_span:
                    host_agent_span.add_event("Building host agent")
                    print("ORCHESTRATE AGENT: Building host agent...")
                    try:
                        self.host_agent = HostAgent(tools=self.tools)
                        print("ORCHESTRATE AGENT: Host agent built successfully.")
                        host_agent_span.add_event("Host agent built successfully")
                        host_agent_span.set_status(trace.Status(trace.StatusCode.OK))
                    except Exception as e:
                        print(f"ORCHESTRATE AGENT: ERROR during host agent build: {e}")
                        host_agent_span.record_exception(e)
                        host_agent_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        raise

                print("ORCHESTRATE AGENT: set_up method completed successfully!")
                main_span.add_event("set_up method completed successfully")
                main_span.set_status(trace.Status(trace.StatusCode.OK))

            except Exception as e:
                print(f"ORCHESTRATE AGENT: A CRITICAL ERROR occurred during set_up: {e}")
                logging.error(f"ORCHESTRATE AGENT: A CRITICAL ERROR occurred during set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(trace.Status(trace.StatusCode.ERROR, f"Setup failed: {e}"))
                raise

    def query(self, input_text: str) -> str:
        if not self.host_agent:
            logging.error("HostAgent not initialized. set_up() was not called.")
            raise RuntimeError("Agent not properly initialized.")
        # Delegate the query to the HostAgent instance
        return self.host_agent.handle_query(input_text)

# 4. Define the root_agent for the ADK to find and deploy.
root_agent = OrchestrateAgent()
