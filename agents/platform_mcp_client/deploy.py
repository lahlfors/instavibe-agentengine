# Ensure nest_asyncio is applied if not already done by the agent module itself,
# as agent.py uses asyncio.run() at module level.
# However, agent.py already calls nest_asyncio.apply().
import nest_asyncio
nest_asyncio.apply()

from agents.platform_mcp_client import agent as platform_mcp_client_adk_agent_module
from agents.platform_mcp_client.platform_agent import PlatformAgent
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
import asyncio
import logging

log = logging.getLogger(__name__)

# The platform_mcp_client_adk_agent_module.agent (agent.py) runs an async initialization
# for its root_agent at the module level. We need to ensure this has completed.
# A simple way is to try to run the initialize function again, or access the agent
# which might implicitly wait or be ready.
# The agent.py already calls asyncio.run(initialize()) at module load.
# So, by the time we import platform_mcp_client_adk_agent_module, root_agent should be initialized
# or in the process.

# It's generally better if the module ensures its exported variables are ready upon import.
# Let's assume agent.py handles its own initialization correctly upon import.

# Instantiate the ReasoningEngine wrapper (PlatformAgent)
# This will internally call _build_agent() which accesses platform_mcp_client_adk_agent_module.root_agent
try:
    platform_reasoning_engine_instance = PlatformAgent()
except Exception as e:
    log.error(f"Error instantiating PlatformAgent: {e}. This might be due to async initialization of root_agent.", exc_info=True)
    # As a fallback or check, explicitly ensure initialization if direct access is needed later
    if platform_mcp_client_adk_agent_module.root_agent is None:
        log.info("Root agent is None, attempting to run initialization explicitly for deploy script context.")
        try:
            asyncio.run(platform_mcp_client_adk_agent_module.initialize())
            platform_reasoning_engine_instance = PlatformAgent() # Try again
        except Exception as e_init:
            log.error(f"Error during explicit initialization in deploy script: {e_init}", exc_info=True)
            raise RuntimeError("Failed to initialize PlatformAgent's underlying ADK agent.") from e_init
    if platform_mcp_client_adk_agent_module.root_agent is None:
        raise RuntimeError("Platform ADK agent (root_agent) is still None after attempted initialization.")


# Define display_name and description for the agent
display_name = "Platform MCP Client Agent"
description = """This agent interacts with a platform using MCP (Message Control Protocol) tools. It can help users create posts and register for events on the Instavibe social app."""

# Create the AdkApp instance for local execution (using the ReasoningEngine)
app = AdkApp(
    agent=platform_reasoning_engine_instance,
    enable_tracing=True,
)

# Create the deployed agent for Vertex AI Agent Engines (using the ADK agent module)
# The 'app' parameter here refers to the ADK agent or module to be deployed.
deployed_agent = agent_engines.create(
    app=platform_mcp_client_adk_agent_module,
    display_name=display_name,
    description=description,
    requirements_path="./requirements.txt", # Assuming requirements.txt is in the same directory
    # Ensure that any tools requiring async cleanup are handled.
    # The agent.py has an exit_stack for MCPToolset.
    # agent_engines.create needs to be aware of such resources if they need special handling
    # during deployment or undeployment. For now, assume standard ADK agent deployment.
)

# The agent.py also defines an exit_stack for cleaning up MCPToolset.
# This deploy script doesn't explicitly handle that stack for the deployed agent.
# It's assumed that the ADK agent itself, when run by Vertex AI Agent Engines,
# will manage its lifecycle, or that the MCP connection is managed per-session/invocation.
# If the MCPToolset needs to be explicitly closed when the *deployed agent service* stops,
# that's a more advanced deployment concern. The `atexit.register(_cleanup_sync)` in agent.py
# might handle this if the Python process exit is graceful on the server.

log.info(f"Platform MCP Client Agent deploy script setup complete. ADK App and deployed_agent configured.")
