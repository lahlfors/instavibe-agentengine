# agents/platform_mcp_client/__init__.py
from .platform_agent import PlatformAgent
from .mcp_client import MCPClient

# The root_agent instantiation below is primarily for older local testing or
# if the local FastAPI service (main_platform_service.py) directly imports it.
# For deployments using agent_engines.create(), PlatformAgent is instantiated
# directly in the deploy.py script.
# root_agent = PlatformAgent()
