from .host_agent import HostAgent
import asyncio
import os # Import os to read environment variables
from dotenv import load_dotenv
from google.genai import types
from google.adk.agents import BaseAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset # Removed SseServerParams
import logging
import nest_asyncio # Import nest_asyncio
import atexit
from agents.app.utils.logging_setup import setup_google_cloud_logging # Import the new utility
from agents.app.utils.tracing import setup_global_tracer # Assuming this sets up OTEL tracer

# Initialize OpenTelemetry Tracer Provider first
setup_global_tracer(service_name="orchestrate-agent") # Or appropriate service name

# Then setup logging, which might use OTEL context if LoggingInstrumentor is active
# Use a specific service name for logs in GCP
SERVICE_NAME_FOR_LOGS = "orchestrate-agent"
LOG_LEVEL = logging.INFO # Or logging.DEBUG, or from env var
setup_google_cloud_logging(log_level=LOG_LEVEL, service_name=SERVICE_NAME_FOR_LOGS)

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Get the logger after setup
log = logging.getLogger(__name__)
 
# --- Global variables ---
# Define them first, initialize as None

# --- Configuration ---
# It's better to get this from environment variables or a config file
# Defaulting to empty list if not set. Adjust as needed.
REMOTE_AGENT_ADDRESSES_STR = os.getenv("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES", "")
log.info(f"Remote Agent Addresses String (AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES): {REMOTE_AGENT_ADDRESSES_STR}")
REMOTE_AGENT_ADDRESSES = [addr.strip() for addr in REMOTE_AGENT_ADDRESSES_STR.split(',') if addr.strip()]
log.info(f"Remote Agent Addresses: {REMOTE_AGENT_ADDRESSES}")

# --- Agent Initialization ---
# Instantiate the HostAgent logic class
# You might want to add a task_callback here if needed, similar to run_orchestrator.py
host_agent_logic = HostAgent(remote_agent_addresses=REMOTE_AGENT_ADDRESSES)

# Create the actual ADK Agent instance
root_agent: BaseAgent = host_agent_logic.create_agent()
log.info(f"Orchestrator root agent '{root_agent.name}' created.")