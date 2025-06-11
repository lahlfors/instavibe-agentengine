from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from common.task_manager import AgentWithTaskManager
from platform_mcp_client import agent
import os # For path joining
from dotenv import load_dotenv # To load .env

# Load environment variables from the root .env file.
# While agent.py (imported as platform_mcp_client.agent) also does this,
# adding it here ensures that if PlatformAgent is used or tested in a context
# where agent.py wasn't the first import, the environment is still correctly configured.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class PlatformAgent(AgentWithTaskManager):
  """An agent that post event and post to instavibe."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
    self._user_id = "platform_agent"
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
      return "Processing the social post and event request..."

  def _build_agent(self) -> LlmAgent:
    """Builds the LLM agent for the Processing the social post and event request."""
    return agent.root_agent

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """Handles the user's request by running the agent pipeline."""
    return await self._runner.run_pipeline(
        app_name=self._agent.name,
        session_id=self._user_id,
        inputs={"text_content": query},
        stream=False,
    )