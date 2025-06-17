import os # For path joining
from dotenv import load_dotenv # To load .env
from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from common.task_manager import AgentTaskManager
from . import agent

# Load environment variables from the root .env file.
# While agent.py also does this, adding it here ensures that if PlannerAgent
# is used or tested in a context where agent.py wasn't the first import,
# the environment is still correctly configured.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class PlannerAgent(AgentTaskManager):
  """An agent to help user planning a night out with its desire location."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
    self._user_id = "remote_agent"
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
      return "Processing the planning request..."

  def _build_agent(self) -> LoopAgent:
    """Builds the LLM agent for the night out planning agent."""
    return agent.root_agent

  async def query(self, query: str, **kwargs) -> Dict[str, Any]:
    """Handles the user's request for planning."""
    # TODO(b/336700618): Implement the actual logic for handling the request.
    session_id = kwargs.pop("session_id", self._user_id + "_" + os.urandom(4).hex())
    response_event_data = None
    async for event in self._runner.run_async(
        user_id=self._user_id,
        session_id=session_id,
        new_message={"text_content": query}
        # Default run_config has StreamingMode.NONE, so expect one event.
    ):
        # Assuming the event itself is the dictionary response or contains the necessary data.
        response_event_data = event
        break # Expect only one event in non-streaming mode

    if response_event_data:
        # Assuming response_event_data is Dict[str, Any] or directly convertible
        # This matches the original intent of the method's return type.
        return response_event_data
    else:
        # Consider adding logging here if a logger is available in this class
        # e.g., self.logger.error("PlannerAgent: No response event received from run_async.")
        return {"error": "No response event received from agent execution"}