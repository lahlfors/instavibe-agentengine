import adk
from adk.agents import Agent
from adk.agents.readonly_context import ReadonlyContext
from adk.tools.tool_context import ToolContext


class HostAgent:
  """The orchestrate agent.

  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work.
  """

  def __init__(self, **kwargs):
    # The new implementation does not need remote_agent_addresses or task_callback
    # at initialization. Agent discovery is handled by the ADK.
    pass

  def create_agent(self) -> Agent:
    # project_id, location, and model_config_kwargs are removed as LlmAgent will use
    # values from vertexai.init() or environment variables.
    return Agent(
        model="gemini-2.0-flash-001", # Updated model name
        name="orchestrate_agent",
        instruction=self.root_instruction,
        description=(
            "This agent orchestrates the decomposition of the user request into"
            " tasks that can be performed by the child agents."
        ),
        tools=[
            self.send_task,
        ]
    )

  def root_instruction(self, context: ReadonlyContext) -> str:
    # The new prompt instructs the agent to use the refactored `send_task` tool.
    # It no longer needs to list agents, as discovery is handled by the ADK.
    return """
    You are an expert AI Orchestrator. Your primary responsibility is to intelligently interpret user requests and delegate them to the most appropriate specialized remote agents by invoking their capabilities.

    Core Workflow:
    1.  **Understand User Intent:** Analyze the user's request to determine the core task.
    2.  **Identify Action and Agent:** Determine the appropriate 'action' (capability) to call and the 'agent_name' that provides it. You are aware of the available agents and their capabilities.
    3.  **Delegate Task:** Use the `send_task` tool to delegate the task. Your call MUST include:
        *   `agent_name`: The name of the target agent (e.g., 'social-agent-v1').
        *   `action`: The name of the capability to invoke (e.g., 'share', 'get_profile').
        *   `data`: A dictionary containing the payload for the action.

    Example:
    User Request: "Share a message saying 'Hello World' on the social platform."
    Your thought process: The user wants to share something. The 'social-agent-v1' has a 'share' capability. The data should be `{"message": "Hello World"}`.
    Your tool call: `send_task(agent_name='social-agent-v1', action='share', data={'message': 'Hello World'})`

    Rely strictly on your tools. If the user's request is ambiguous or missing information, ask for clarification.
    """

  async def send_task(
      self,
      agent_name: str,
      action: str,
      data: dict,
      tool_context: ToolContext
  ) -> dict:
    """
    Finds a remote agent and invokes one of its capabilities.

    Args:
      agent_name: The name of the agent to find (e.g., 'social-agent-v1').
      action: The name of the capability to invoke (e.g., 'share').
      data: The dictionary payload to send to the capability.
      tool_context: The tool context this method runs in.

    Returns:
      The response dictionary from the remote agent's capability.
    """
    try:
        agent = adk.agents.find(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found.")

        capability = agent.a2a.get_capability(action)
        if not capability:
            raise ValueError(f"Capability '{action}' not available on agent '{agent_name}'.")

        response_data = await capability.invoke(data)
        return response_data
    except Exception as e:
        # It's good practice to return errors in a structured way
        # that the LLM can understand and potentially act on.
        return {"error": f"An error occurred while sending task to '{agent_name}': {e}"}
