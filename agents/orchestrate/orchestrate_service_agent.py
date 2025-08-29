# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
import asyncio
import google.auth
import google.auth.credentials
from opentelemetry import trace
from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.planners import BuiltInPlanner
from google.adk.tools.tool_context import ToolContext
from google.genai.types import ThinkingConfig
from typing import Optional
from agents.app.utils.communication import call_agent_capability
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools import preload_memory_tool

logging.basicConfig(level=logging.INFO)
tracer = trace.get_tracer(__name__)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, interacting with Memory Bank via REST API and delegating tasks.
    """
    project: Optional[str] = None
    location: Optional[str] = None
    reasoning_engine_id: Optional[str] = None
    orchestrator_agent: Optional[Agent] = None
    memory_service: Optional[VertexAiMemoryBankService] = None

    def __init__(self, name: str, instruction: Optional[str] = None, description: Optional[str] = None):
        super().__init__(
            name=name,
            model="gemini-2.5-flash",
            instruction=instruction or "I am an orchestrator agent with memory and task delegation capabilities.",
            description=description or "An agent that can create/search memories and delegate tasks.",
        )

    async def set_up(self):
        """
        Called by the Agent Engine framework after deployment.
        """
        if self.orchestrator_agent:
            return

        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.reasoning_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")
        if not self.reasoning_engine_id:
            logging.error("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable not set.")
            raise RuntimeError("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable must be set.")

        self.memory_service = VertexAiMemoryBankService(
            project=self.project,
            location=self.location,
            agent_engine_id=self.reasoning_engine_id,
        )
        logging.info("VertexAiMemoryBankService initialized.")

        thinking_config = ThinkingConfig(
            include_thoughts=True,
            thinking_budget=-1,  # Use dynamic thinking
        )
        planner = BuiltInPlanner(thinking_config=thinking_config)
        all_tools = [self.send_task, preload_memory_tool.PreloadMemoryTool(memory=self.memory_service)]

        self.orchestrator_agent = Agent(
            model="gemini-2.5-flash",
            name="orchestrate_agent",
            instruction=self.root_instruction,
            description=(
                "This agent orchestrates the decomposition of the user request into"
                " tasks that can be performed by the child agents."
            ),
            tools=all_tools,
            planner=planner,
            memory=self.memory_service,
        )
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP COMPLETE ---")

    def root_instruction(self, context: ReadonlyContext) -> str:
        return """
    You are an expert AI Orchestrator for the Instavibe application. Your primary responsibility is to intelligently interpret user requests and delegate them to the most appropriate specialized remote agents by invoking their capabilities.

    You have the following agents at your disposal:
    - **planner-agent**: Helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions.
    - **platform-mcp-client-agent**: Interacts with the Instavibe platform. It can create events, posts, and perform other platform-specific actions.
    - **social-agent**: Interacts with social media platforms.

    Core Workflow:
    1.  **Understand User Intent:** Analyze the user's request to determine the core task.
    2.  **Identify Action and Agent:** Determine the appropriate 'action' (capability) to call and the 'agent_name' that provides it.
    3.  **Provide Reasoning:** After you have identified the agent and action, but before you call the tool, provide a brief summary of your reasoning for choosing a particular agent and action.
    4.  **Delegate Task:** Use the `send_task` tool to delegate the task. Your call MUST include:
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
        """
        with tracer.start_as_current_span("tool.send_task") as span:
            span.set_attribute("tool.name", "send_task")
            span.set_attribute("tool.parameters", f"agent_name={agent_name}, action={action}, data={data}")
            try:
                response_data = await call_agent_capability(
                    source_agent="orchestrate_agent",
                    target_agent=agent_name,
                    capability=action,
                    prompt=data
                )
                return response_data
            except Exception as e:
                return {"error": f"An error occurred while sending task to '{agent_name}': {e}"}

    def query(self, input_text: str) -> str:
        with tracer.start_as_current_span("orchestrate_agent_main") as span:
            span.set_attribute("user_query", input_text)
            if not self.orchestrator_agent:
                logging.error("OrchestratorAgent not initialized. set_up() was not called.")
                raise RuntimeError("Agent not properly initialized.")

            # The ADK's query method will automatically pick up the parent span
            # and create child spans for LLM calls and tool calls if the integration
            # is configured correctly.
            response = self.orchestrator_agent.query(input_text)

            # Since we don't have direct access to the LLM response here to add it as an attribute,
            # we rely on the ADK's auto-instrumentation. If that is not available,
            # we would need to find a way to intercept the LLM calls.
            span.set_attribute("llm.response", str(response))
            return response

OrchestrateServiceAgent.model_rebuild()

root_agent = OrchestrateServiceAgent(
    name="orchestrate_service_agent",
)
