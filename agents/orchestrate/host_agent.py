from google import adk
from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from agents.app.utils.communication import call_agent_capability


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
    You are an expert AI Orchestrator for the Instavibe application. Your primary responsibility is to intelligently interpret user requests and delegate them to the most appropriate specialized remote agents by invoking their capabilities.

    You have the following agents at your disposal:
    - **planner-agent**: Helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions.
    - **platform-mcp-client-agent**: Interacts with the Instavibe platform. It can create events, posts, and perform other platform-specific actions.
    - **social-agent**: Interacts with social media platforms.

    Core Workflow:
    1.  **Understand User Intent:** Analyze the user's request to determine the core task.
    2.  **Identify Action and Agent:** Determine the appropriate 'action' (capability) to call and the 'agent_name' that provides it.
    3.  **Delegate Task:** Use the `send_task` tool to delegate the task. Your call MUST include:
        *   `agent_name`: The name of the target agent (e.g., 'planner-agent').
        *   `action`: The name of the capability to invoke (e.g., 'plan', 'create_event').
        *   `data`: A dictionary containing the payload for the action.

    Examples:
    - User Request: "Plan a fun night out for me and my friends."
      - Your thought process: The user wants to plan an event. The 'planner-agent' is the best agent for this.
      - Your tool call: `send_task(agent_name='planner-agent', action='plan', data={'prompt': 'Plan a fun night out for me and my friends.'})`
    - User Request: "Create an event for the plan we just made."
      - Your thought process: The user wants to create an event on Instavibe. The 'platform-mcp-client-agent' is the best agent for this.
      - Your tool call: `send_task(agent_name='platform-mcp-client-agent', action='create_event', data={'event_details': ...})`
    - User Request: "Share the event on social media."
        - Your thought process: The user wants to share something on social media. The 'social-agent' is the best agent for this.
        - Your tool call: `send_task(agent_name='social-agent', action='share', data={'message': 'Check out this cool event I just made on Instavibe!'})`

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
        response_data = await call_agent_capability(
            source_agent="orchestrate_agent",
            target_agent=agent_name,
            capability=action,
            prompt=data
        )
        return response_data
    except Exception as e:
        # It's good practice to return errors in a structured way
        # that the LLM can understand and potentially act on.
        return {"error": f"An error occurred while sending task to '{agent_name}': {e}"}
