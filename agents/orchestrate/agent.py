from .host_agent import HostAgent
import asyncio
import os # Import os to read environment variables
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)

# Log critical environment variables at startup
logging.info("--- ORCHESTRATOR AGENT RUNTIME ENV CHECK ---")
logging.info(f"GOOGLE_CLOUD_PROJECT: {os.getenv('GOOGLE_CLOUD_PROJECT')}")
logging.info(f"GOOGLE_CLOUD_REGION: {os.getenv('GOOGLE_CLOUD_REGION')}")
logging.info(f"ADK_SESSION_SPANNER_INSTANCE_ID: {os.getenv('ADK_SESSION_SPANNER_INSTANCE_ID')}")
logging.info(f"ADK_SESSION_SPANNER_DATABASE_ID: {os.getenv('ADK_SESSION_SPANNER_DATABASE_ID')}")
logging.info("------------------------------------------")
from dotenv import load_dotenv
from google.genai import types
from google.adk.agents import BaseAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset # Removed SseServerParams
import logging 
import nest_asyncio # Import nest_asyncio
import atexit

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
 
# --- Global variables ---
# Define them first, initialize as None

# --- Configuration ---
# The remote agent addresses are no longer needed here, as agent discovery
# is handled by the ADK framework.

# --- Agent Initialization ---
# Instantiate the HostAgent logic class
host_agent_logic = HostAgent()

# Create the actual ADK Agent instance
root_agent: BaseAgent = host_agent_logic.create_agent()
log.info(f"Orchestrator root agent '{root_agent.name}' created.")